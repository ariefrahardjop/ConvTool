# tests/test_single_instance.py — Uji single-instance (tanpa GUI).
#
# Skenario Rif 19 Nov 08:30: pilih 8 foto di Explorer -> Explorer
# memanggil exe SEKALI PER FILE -> 8 proses. Proses pertama harus
# jadi primary dan membuka SATU dialog; 7 proses lain meneruskan
# file-nya lalu keluar. Diuji di level modul: claim + forward +
# merge_pending (penggabungan ke dialog diuji di test_gui_smoke.py
# lewat add_files).

import os
import queue
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import single_instance  # noqa: E402

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work-si")
PASSES = [0]
FAILURES = []


def check(name, cond, detail=""):
    if cond:
        PASSES[0] += 1
        print("PASS ", name, detail)
    else:
        FAILURES.append(name)
        print("FAIL ", name, detail)


def _wait_inbox(inbox, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            return inbox.get_nowait()
        except queue.Empty:
            time.sleep(0.05)
    return None


def main():
    os.makedirs(WORK, exist_ok=True)
    files = []
    for i in range(3):
        p = os.path.join(WORK, "foto%d.jpg" % i)
        open(p, "wb").write(b"fake-%d" % i)
        files.append(p)

    print("\n== claim + forward ==")
    role1, inbox1 = single_instance.claim("exif", [files[0]])
    check("proses pertama primary", role1 == "primary", role1)
    role2, _inbox2 = single_instance.claim("exif", [files[1]])
    check("proses kedua forwarded", role2 == "forwarded", role2)
    got = _wait_inbox(inbox1)
    check("primary menerima kiriman proses kedua",
          got is not None and got[0] == "exif" and got[1] == [files[1]],
          str(got))
    role3, _inbox3 = single_instance.claim("watermark-klasik", [files[2]])
    check("proses ketiga forwarded (verb beda)", role3 == "forwarded",
          role3)
    got = _wait_inbox(inbox1)
    check("primary menerima kiriman verb beda",
          got is not None and got[0] == "watermark-klasik",
          str(got))

    print("\n== merge_pending ==")
    inbox = queue.Queue()
    inbox.put(("exif", [files[1], files[0]]))  # duplikat files[0]
    inbox.put(("watermark-klasik", [files[2]]))
    inbox.put(("exif", [os.path.join(WORK, "tidak-ada.jpg")]))
    merged, pending = single_instance.merge_pending(inbox, "exif",
                                                    [files[0]])
    check("merge gabung verb sama tanpa duplikat",
          merged == [files[0], files[1]], str(merged))
    check("merge file tak ada dilewati",
          os.path.join(WORK, "tidak-ada.jpg") not in merged, "")
    check("merge verb beda jadi pending",
          pending == [("watermark-klasik", [files[2]])], str(pending))

    print("\n== kiriman sampah diabaikan, listener tetap hidup ==")
    try:
        s = socket.create_connection(
            (single_instance.HOST, single_instance.PORT), timeout=2)
        s.sendall(b"bukan-json {{{")
        s.shutdown(socket.SHUT_WR)
        s.recv(2)
        s.close()
    except Exception:
        pass
    time.sleep(0.3)
    check("kiriman sampah tidak masuk antrean", inbox1.empty(), "")
    role4, _inbox4 = single_instance.claim("exif", [files[2]])
    check("claim setelah sampah tetap forwarded", role4 == "forwarded",
          role4)
    got = _wait_inbox(inbox1)
    check("primary tetap menerima kiriman sesudah sampah",
          got is not None and got[1] == [files[2]], str(got))

    print("\n== fallback: port dipakai aplikasi lain ==")
    # Squatter di proses TERPISAH (primary pertama masih memegang port
    # di proses ini, jadi squatter harus jalan di proses lain — tapi
    # port yang sama tidak bisa dipegang dua proses sekaligus. Maka
    # uji ini memakai port cadangan: jalankan squatter di PORT itu,
    # lalu claim dengan PORT yang di-override sementara.)
    import subprocess
    squat_code = (
        "import socket, time; "
        "s = socket.socket(); "
        "s.bind(('127.0.0.1', 49191)); s.listen(1); time.sleep(6)")
    proc = subprocess.Popen([sys.executable, "-c", squat_code])
    try:
        time.sleep(0.5)  # beri waktu squatter bind
        old_port = single_instance.PORT
        single_instance.PORT = 49191
        try:
            t0 = time.time()
            role5, _inbox5 = single_instance.claim("exif", [files[0]])
            dt = time.time() - t0
        finally:
            single_instance.PORT = old_port
        check("port disquat -> standalone (bukan forwarded)",
              role5 == "standalone", role5)
        check("fallback tidak menunggu terlalu lama (< 5 detik)",
              dt < 5.0, "%.1f detik" % dt)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()

    print("\n== mutex Windows: bukan Windows -> None ==")
    check("_win_acquire_mutex di Linux kembalikan None",
          single_instance._win_acquire_mutex() is None, "")
    check("_win_release_mutex di Linux aman dipanggil",
          single_instance._win_release_mutex() is None, "")

    print("\n== _send_to_primary: retry lalu menyerah ==")
    # Primary palsu: listen tapi tidak pernah kirim ACK -> claim
    # harus retry lalu standalone, bukan menggantung selamanya.
    import subprocess as _sp
    silent_code = (
        "import socket, time; "
        "s = socket.socket(); "
        "s.bind(('127.0.0.1', 49192)); s.listen(4); "
        "c, _ = s.accept(); time.sleep(5)")
    proc2 = _sp.Popen([sys.executable, "-c", silent_code])
    try:
        time.sleep(0.5)
        old_port = single_instance.PORT
        single_instance.PORT = 49192
        try:
            t0 = time.time()
            ok = single_instance._send_to_primary("exif", [files[0]])
            dt = time.time() - t0
        finally:
            single_instance.PORT = old_port
        check("listener diam -> _send_to_primary False", ok is False,
              str(ok))
        check("retry selesai dalam batas wajar (< 5 detik)",
              dt < 5.0, "%.1f detik" % dt)
    finally:
        proc2.terminate()
        try:
            proc2.wait(timeout=3)
        except Exception:
            proc2.kill()

    print("\n==================================")
    print("LOLOS: %d   GAGAL: %d" % (PASSES[0], len(FAILURES)))
    if FAILURES:
        print("Yang gagal:", ", ".join(FAILURES))
        return 1
    print("SEMUA UJI SINGLE-INSTANCE LOLOS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
