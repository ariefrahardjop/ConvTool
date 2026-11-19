# single_instance.py — Satu jendela ConvTool untuk banyak peluncuran.
#
# Latar: tanpa MultiSelectModel, Explorer memanggil command klik kanan
# SEKALI PER FILE — pilih 8 foto = 8 proses ConvTool.exe, masing-masing
# dengan 1 file (bukti: screenshot Rif 19 Nov 08:30 — 8 item terpilih,
# tiap jendela "Foto 1 dari 1"). MultiSelectModel=Player (v1.9.1)
# seharusnya mencegah ini, tapi di PC Rif tetap terbuka satu-persatu.
# v1.9.2 mencoba election lewat bind socket — TETAP GAGAL di PC Rif
# (screenshot 19 Nov 08:48: masih banyak jendela). Penyebabnya:
# claim() memakai SO_REUSEADDR. Di Linux SO_REUSEADDR TIDAK
# mengizinkan dua socket bind port yang sama (makanya semua uji di
# sini lolos), TAPI DI WINDOWS MENGIZINKAN — jadi ketiga proses
# berhasil bind 127.0.0.1:49190 dan ketiganya mengira dirinya primary.
# v1.9.3: SO_REUSEADDR DIHAPUS, dan di Windows election memakai
# NAMED MUTEX (CreateMutexW) — mekanisme standar Windows untuk
# single-instance; socket localhost hanya dipakai untuk meneruskan
# daftar file, bukan untuk election.
#
# Mekanisme (stdlib saja, tanpa dependensi baru):
#   - claim(verb, files): di Windows, coba rebut named mutex
#     "ConvToolSingleInstance_v1". Menang -> primary: bind TCP
#     127.0.0.1:PORT (tanpa SO_REUSEADDR) + thread listener mulai
#     menerima kiriman. Kalah (mutex sudah ada) -> coba connect ke
#     primary, kirim JSON {"app","verb","files"}, tunggu ACK "OK"
#     (4 percobaan, tiap percobaan maks 0,5 detik — menutup jeda
#     antara primary merebut mutex dan listener-nya siap).
#     ACK diterima -> ("forwarded", None), pemanggil harus keluar.
#     Connect/ACK gagal (primary mati di tengah jalan, atau port
#     dipakai aplikasi lain) -> ("standalone", None): jalan sendiri
#     seperti biasa, jangan sampai file hilang.
#     Di non-Windows (Linux/macOS), election tetap lewat bind socket
#     (tanpa SO_REUSEADDR) seperti sebelumnya.
#   - merge_pending(inbox, verb, files): kosongkan antrean inbox
#     (non-blocking). File ber-verb SAMA digabung ke `files` (tanpa
#     duplikat, hanya yang masih ada); verb BERBEDA dikembalikan
#     sebagai daftar pending untuk dibuka sesudah dialog aktif tutup.
# Hanya loopback (127.0.0.1): tidak ada traffic jaringan, tidak ada
# prompt firewall Windows untuk loopback.

import json
import os
import queue
import socket
import threading
import time

HOST = "127.0.0.1"
PORT = 49190
MAGIC = "ConvTool-1"
ACK = b"OK"
MUTEX_NAME = "ConvToolSingleInstance_v1"
ERROR_ALREADY_EXISTS = 183

# Handle mutex Windows (bila dipakai) — disimpan global supaya tidak
# pernah ditutup selama proses hidup; OS melepasnya saat proses mati.
_WIN_MUTEX_HANDLE = None


def _win_acquire_mutex():
    """Rebut named mutex Windows. Kembalikan True (menang -> primary),
    False (sudah ada -> ada primary lain), atau None (gagal dibuat /
    bukan Windows -> fallback ke election via socket)."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [
            wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.GetLastError.argtypes = []
        kernel32.GetLastError.restype = wintypes.DWORD
        global _WIN_MUTEX_HANDLE
        handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if not handle:
            return None
        _WIN_MUTEX_HANDLE = handle
        return kernel32.GetLastError() != ERROR_ALREADY_EXISTS
    except Exception:
        return None


def _win_release_mutex():
    """Lepas mutex (dipakai bila menang mutex tapi bind listener gagal,
    supaya proses berikutnya tidak terkunci menunggu primary yang
    tidak pernah punya listener)."""
    global _WIN_MUTEX_HANDLE
    if _WIN_MUTEX_HANDLE is None or os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.kernel32.CloseHandle(_WIN_MUTEX_HANDLE)
    except Exception:
        pass
    _WIN_MUTEX_HANDLE = None


def _send_to_primary(verb, files, attempts=4):
    """Kirim (verb, files) ke primary. True bila primary membalas ACK.
    Dicoba ulang beberapa kali: primary mungkin baru saja merebut
    mutex dan listener-nya belum siap saat proses ini connect."""
    payload = json.dumps({"app": MAGIC, "verb": verb,
                          "files": list(files)}).encode("utf-8")
    for _try in range(attempts):
        try:
            sock = socket.create_connection((HOST, PORT), timeout=0.5)
            try:
                sock.settimeout(0.5)
                sock.sendall(payload)
                sock.shutdown(socket.SHUT_WR)
                if sock.recv(len(ACK)) == ACK:
                    return True
            finally:
                sock.close()
        except Exception:
            pass
        time.sleep(0.2)
    return False


def _listener_loop(server, inbox):
    """Thread primary: terima kiriman, validasi, masukkan ke antrean."""
    while True:
        try:
            conn, _addr = server.accept()
        except Exception:
            return  # server ditutup (proses berakhir)
        try:
            conn.settimeout(2.0)
            chunks = []
            while True:
                data = conn.recv(65536)
                if not data:
                    break
                chunks.append(data)
            try:
                msg = json.loads(b"".join(chunks).decode("utf-8"))
            except Exception:
                msg = None
            if (isinstance(msg, dict) and msg.get("app") == MAGIC
                    and isinstance(msg.get("files"), list)):
                inbox.put((msg.get("verb"), list(msg["files"])))
                conn.sendall(ACK)
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass


def claim(verb, files):
    """Tentukan peran proses ini. Kembalikan (role, inbox):
    ("primary", inbox) / ("forwarded", None) / ("standalone", None)."""
    files = [f for f in files if os.path.isfile(f)]
    inbox = queue.Queue()
    # --- election: mutex di Windows, bind socket di tempat lain.
    won_mutex = _win_acquire_mutex()
    if won_mutex is False:
        # Ada primary lain (mutex sudah dipegang).
        if files and _send_to_primary(verb, files):
            return ("forwarded", None)
        return ("standalone", None)
    # won_mutex True (menang) atau None (bukan Windows / mutex gagal):
    # lanjut ke bind listener. TANPA SO_REUSEADDR — di Windows nilai
    # itu mengizinkan banyak proses bind port yang sama (bug v1.9.2).
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.bind((HOST, PORT))
        server.listen(8)
    except Exception:
        try:
            server.close()
        except Exception:
            pass
        _win_release_mutex()
        # Tanpa file tidak ada yang diteruskan (mis. launcher dobel-klik
        # saat primary sudah jalan) — langsung standalone.
        if files and _send_to_primary(verb, files):
            return ("forwarded", None)
        return ("standalone", None)
    thread = threading.Thread(target=_listener_loop, args=(server, inbox),
                              daemon=True)
    thread.start()
    return ("primary", inbox)


def merge_pending(inbox, verb, files):
    """Kosongkan inbox (non-blocking). Kembalikan (files, pending):
    files = daftar awal + file kiriman ber-verb sama (tanpa duplikat,
    hanya yang masih ada di disk); pending = [(verb, files)] ber-verb
    beda, untuk dibuka sesudah dialog aktif tutup."""
    merged = list(files)
    pending = []
    if inbox is None:
        return (merged, pending)
    while True:
        try:
            other_verb, other_files = inbox.get_nowait()
        except queue.Empty:
            break
        other_files = [f for f in other_files if os.path.isfile(f)]
        if other_verb == verb:
            for f in other_files:
                if f not in merged:
                    merged.append(f)
        elif other_files:
            pending.append((other_verb, other_files))
    return (merged, pending)
