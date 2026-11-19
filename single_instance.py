# single_instance.py — Satu jendela ConvTool untuk banyak peluncuran.
#
# Latar: tanpa MultiSelectModel, Explorer memanggil command klik kanan
# SEKALI PER FILE — pilih 8 foto = 8 proses ConvTool.exe, masing-masing
# dengan 1 file (bukti: screenshot Rif 19 Nov 08:30 — 8 item terpilih,
# tiap jendela "Foto 1 dari 1"). MultiSelectModel=Player (v1.9.1)
# seharusnya mencegah ini, tapi di PC Rif tetap terbuka satu-persatu
# (registry lama belum di-install ulang, atau nilainya tidak dihormati
# untuk SubCommands). Modul ini membuat aplikasinya sendiri yang
# menggabungkan: proses PERTAMA menjadi "primary" dan membuka SATU
# dialog berisi daftar; proses berikutnya meneruskan file-nya ke
# primary lewat socket localhost lalu langsung keluar.
#
# Mekanisme (stdlib saja, tanpa dependensi baru):
#   - claim(verb, files): coba bind TCP 127.0.0.1:PORT. Berhasil ->
#     ("primary", inbox) + thread listener mulai menerima kiriman.
#     Gagal (port sudah dipakai) -> coba connect ke primary, kirim
#     JSON {"app","verb","files"}, tunggu ACK "OK" (maks 2 detik).
#     ACK diterima -> ("forwarded", None), pemanggil harus keluar.
#     Connect/ACK gagal (primary mati di tengah jalan, atau port
#     dipakai aplikasi lain) -> ("standalone", None): jalan sendiri
#     seperti biasa, jangan sampai file hilang.
#   - merge_pending(inbox, verb, files): kosongkan antrean inbox
#     (non-blocking). File ber-verb SAMA digabung ke `files` (tanpa
#     duplikat, hanya yang masih ada); verb BERBEDA dikembalikan
#     sebagai daftar pending untuk dibuka sesudah dialog aktif tutup.
# Hanya loopback (127.0.0.1): tidak ada traffic jaringan, tidak ada
# prompt firewall Windows untuk loopback.

import json
import queue
import socket
import threading

HOST = "127.0.0.1"
PORT = 49190
MAGIC = "ConvTool-1"
ACK = b"OK"
TIMEOUT = 2.0


def _send_to_primary(verb, files):
    """Kirim (verb, files) ke primary. True bila primary membalas ACK."""
    try:
        payload = json.dumps({"app": MAGIC, "verb": verb,
                              "files": list(files)}).encode("utf-8")
        sock = socket.create_connection((HOST, PORT), timeout=TIMEOUT)
        try:
            sock.settimeout(TIMEOUT)
            sock.sendall(payload)
            sock.shutdown(socket.SHUT_WR)
            return sock.recv(len(ACK)) == ACK
        finally:
            sock.close()
    except Exception:
        return False


def _listener_loop(server, inbox):
    """Thread primary: terima kiriman, validasi, masukkan ke antrean."""
    while True:
        try:
            conn, _addr = server.accept()
        except Exception:
            return  # server ditutup (proses berakhir)
        try:
            conn.settimeout(TIMEOUT)
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
    import os
    files = [f for f in files if os.path.isfile(f)]
    inbox = queue.Queue()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(8)
    except Exception:
        try:
            server.close()
        except Exception:
            pass
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
    import os
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
