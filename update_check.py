# update_check.py — Notif + pasang pembaruan ConvTool dari GitHub.
#
# Alur (disetujui Rif 19 Nov 2026):
#   1. Exe di-build OTOMATIS di GitHub (GitHub Actions, tiap versi
#      baru) dan dilampirkan di halaman Releases — pengguna TIDAK
#      perlu install Python.
#   2. Aplikasi mengecek rilis terbaru lewat GitHub Releases API
#      (repo publik — tanpa login/token) saat dibuka, di thread
#      latar, maksimal sekali sehari. Offline / GitHub tidak
#      terjangkau = diam saja, tool tetap jalan.
#   3. Ada versi baru -> dialog "Versi baru tersedia" (sekali per
#      versi). Pengguna pilih Perbarui -> exe baru diunduh, aplikasi
#      menutup, updater PowerShell mengganti exe lama (minta UAC
#      bila perlu, mis. terpasang di C:\Tools), lalu aplikasi
#      dibuka lagi. Pilih Nanti -> tidak ditanya lagi untuk versi
#      itu (tombol "Periksa Pembaruan" di launcher tetap bisa
#      memeriksa manual).
#
# Modul ini TIDAK mengimpor tkinter di level atas (supaya uji logika
# bisa jalan tanpa display); messagebox diimpor malas di dalam
# fungsi dialog.

import json
import os
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta

APP_VERSION = "1.9.6"

REPO_URL = "https://github.com/ariefrahardjop/ConvTool"
API_URL = ("https://api.github.com/repos/ariefrahardjop/ConvTool"
           "/releases/latest")
EXE_ASSET_NAME = "ConvTool.exe"

_FETCH_TIMEOUT = 6          # detik; uji boleh mengecilkan
_CHECK_INTERVAL = timedelta(hours=24)

# Hasil cek latar yang menunggu ditampilkan (satu slot).
_PENDING = None
_SHOWN_THIS_SESSION = False


# ----------------------------------------------------------------
# versi
# ----------------------------------------------------------------

def _parse_version(text):
    """'v1.9.6' -> (1, 9, 6); '1.10' -> (1, 10); sampah -> (0,)."""
    if not isinstance(text, str):
        return (0,)
    text = text.strip().lstrip("vV")
    parts = []
    for piece in text.split("."):
        m = re.match(r"(\d+)", piece)
        parts.append(int(m.group(1)) if m else 0)
    return tuple(parts) if parts else (0,)


def _is_newer(remote_tag, local_version=APP_VERSION):
    return _parse_version(remote_tag) > _parse_version(local_version)


# ----------------------------------------------------------------
# state lokal (sekali sehari + sekali per versi)
# ----------------------------------------------------------------

def _state_dir():
    override = os.environ.get("CONVTOOL_UPDATE_STATE_DIR")
    if override:
        return override
    appdata = os.environ.get("APPDATA")
    if appdata:
        return os.path.join(appdata, "ConvTool")
    return os.path.join(os.path.expanduser("~"), ".convtool")


def _state_path():
    return os.path.join(_state_dir(), "update-state.json")


def _load_state():
    try:
        with open(_state_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(state):
    try:
        os.makedirs(_state_dir(), exist_ok=True)
        with open(_state_path(), "w", encoding="utf-8") as fh:
            json.dump(state, fh)
    except Exception:
        pass  # state hanya pengingat; gagal simpan bukan error


def mark_notified(version):
    """Catat versi ini sudah diberitahukan (tidak ditanya lagi)."""
    state = _load_state()
    state["notified_version"] = version
    state.pop("pending", None)
    _save_state(state)


# ----------------------------------------------------------------
# ambil rilis terbaru dari GitHub
# ----------------------------------------------------------------

def _fetch_release():
    """GET /releases/latest -> dict rilis, atau None bila gagal
    (offline, 404, JSON rusak, timeout). Diam saja — bukan error."""
    req = urllib.request.Request(
        API_URL, headers={"User-Agent": "ConvTool/" + APP_VERSION,
                          "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
            return json.load(resp)
    except Exception:
        return None


def _info_from_release(release):
    """Pilih info pembaruan dari dict rilis GitHub, atau None bila
    rilis ini bukan pembaruan (versi <= versi jalan, atau tanpa
    aset exe)."""
    if not isinstance(release, dict):
        return None
    tag = release.get("tag_name", "")
    if not _is_newer(tag):
        return None
    asset = None
    for item in release.get("assets", []) or []:
        if item.get("name") == EXE_ASSET_NAME:
            asset = item
            break
    if asset is None:
        return None
    return {
        "version": _parse_version(tag),
        "version_text": tag.lstrip("vV"),
        "tag": tag,
        "notes": (release.get("body") or "").strip(),
        "download_url": asset.get("browser_download_url", ""),
        "size": asset.get("size", 0),
    }


def check_now(force=False):
    """Periksa pembaruan. Kembali (info, error):
    - info: dict pembaruan (lihat _info_from_release), atau None
      bila tidak ada pembaruan / cek dilewati.
    - error: True bila pengambilan gagal (offline dsb.); False
      bila hasil pasti (ada / tidak ada pembaruan).
    Tanpa force: maksimal sekali sehari, dan hasil yang tertunda
    (sudah ketemu tapi belum diberitahukan) dikembalikan tanpa
    mengambil lagi."""
    state = _load_state()
    if not force:
        # Hasil tertunda (sudah ketemu tapi belum diberitahukan)
        # dikembalikan tanpa mengambil lagi — hemat kuota cek
        # sekali-sehari. Cek manual (force) selalu mengambil baru.
        pending = state.get("pending")
        if isinstance(pending, dict) and pending.get("version_text"):
            if pending.get("version_text") != state.get("notified_version"):
                return pending, False
    if not force:
        last = state.get("last_check")
        try:
            last_dt = datetime.fromisoformat(last) if last else None
        except Exception:
            last_dt = None
        if last_dt and datetime.now() - last_dt < _CHECK_INTERVAL:
            return None, False
    release = _fetch_release()
    state["last_check"] = datetime.now().isoformat()
    if release is None:
        _save_state(state)
        return None, True
    info = _info_from_release(release)
    if info is None:
        state.pop("pending", None)
        _save_state(state)
        return None, False
    state["pending"] = info
    _save_state(state)
    return info, False


# ----------------------------------------------------------------
# cek latar + tampilkan dialog (dipanggil dari _poll_ipc)
# ----------------------------------------------------------------

def start_background_check():
    """Mulai cek di thread latar (daemon). Hasilnya ditampung di
    _PENDING; convtool.py menampilkannya lewat poll_and_show."""
    def _run():
        global _PENDING
        try:
            info, _err = check_now()
        except Exception:
            info = None
        if info is not None:
            _PENDING = info

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


def take_pending():
    global _PENDING
    info, _PENDING = _PENDING, None
    return info


def poll_and_show(root):
    """Dipanggil berkala dari _poll_ipc: bila ada pembaruan yang
    menunggu, tampilkan dialognya sekali di sesi ini."""
    global _SHOWN_THIS_SESSION
    if _SHOWN_THIS_SESSION:
        return
    info = take_pending()
    if info is None:
        return
    _SHOWN_THIS_SESSION = True
    _show_update_dialog(root, info)


def manual_check(parent):
    """Cek sekarang (tombol 'Periksa Pembaruan' di launcher):
    mengabaikan jadwal sekali-sehari. Hasilnya selalu dilaporkan
    (ada pembaruan / sudah terbaru / gagal)."""
    from tkinter import messagebox
    info, error = check_now(force=True)
    if info is not None:
        _show_update_dialog(parent, info)
    elif error:
        messagebox.showinfo(
            "Periksa Pembaruan",
            "Tidak dapat memeriksa pembaruan.\nPeriksa koneksi "
            "internet, lalu coba lagi.", parent=parent)
    else:
        messagebox.showinfo(
            "Periksa Pembaruan",
            "Kamu memakai versi terbaru (v%s)." % APP_VERSION,
            parent=parent)


def _show_update_dialog(root, info):
    """Dialog 'Versi baru tersedia'. Ya -> unduh + pasang + restart
    aplikasi. Tidak -> catat sudah diberitahukan (sekali per
    versi)."""
    from tkinter import messagebox
    text = ("Versi baru ConvTool v%s tersedia.\n"
            "Kamu memakai v%s.\n" % (info["version_text"], APP_VERSION))
    if info.get("notes"):
        text += "\nApa yang baru:\n%s\n" % info["notes"]
    text += ("\nPerbarui sekarang? Aplikasi akan menutup, memasang "
             "exe baru, lalu membuka lagi.")
    if messagebox.askyesno("Pembaruan tersedia", text, parent=root):
        # Ya: perform_update yang menandai sudah-diberitahukan,
        # TAPI hanya bila updater berhasil diluncurkan. Bila unduh
        # gagal, tidak ditandai — besok ditanya lagi.
        perform_update(root, info)
    else:
        mark_notified(info["version_text"])


# ----------------------------------------------------------------
# unduh + pasang (self-update)
# ----------------------------------------------------------------

def download_exe(url, dest, expected_size=0):
    """Unduh exe ke dest. Kembali True bila berkas ada dan ukurannya
    cocok (bila expected_size > 0)."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "ConvTool/" + APP_VERSION})
        with urllib.request.urlopen(req, timeout=60) as resp, \
                open(dest, "wb") as fh:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                fh.write(chunk)
    except Exception:
        return False
    try:
        size = os.path.getsize(dest)
    except Exception:
        return False
    return size > 0 and (not expected_size or size == expected_size)


def build_updater_script(target_exe, new_exe, pid):
    """Hasilkan skrip PowerShell updater. Placeholder diganti dengan
    .replace (bukan .format — skrip penuh kurung kurawal)."""
    script = r'''
param([string]$TargetExe, [string]$NewExe, [int]$AppPid)
# Updater ConvTool: tunggu aplikasi lama keluar, ganti exe-nya
# dengan yang baru, jalankan lagi. Bila butuh admin (mis. terpasang
# di C:\Tools), coba lagi lewat UAC.
try { Wait-Process -Id $AppPid -ErrorAction SilentlyContinue } catch {}
Start-Sleep -Milliseconds 500
$replaced = $false
try {
  Move-Item -LiteralPath $NewExe -Destination $TargetExe -Force
  $replaced = $true
} catch {
  try {
    $cmd = "Move-Item -LiteralPath '__NEW__' -Destination '__TARGET__' -Force"
    Start-Process powershell -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $cmd -Verb RunAs -Wait
    $replaced = Test-Path -LiteralPath $TargetExe
  } catch { $replaced = $false }
}
if ($replaced) { Start-Process -FilePath $TargetExe }
try { Remove-Item -LiteralPath $NewExe -ErrorAction SilentlyContinue } catch {}
$self = $PSCommandPath
if ($self) { Start-Process cmd -ArgumentList "/c ping -n 3 127.0.0.1 >nul & del `"$self`"" -WindowStyle Hidden }
'''
    return (script.replace("__TARGET__", target_exe.replace("'", "''"))
                  .replace("__NEW__", new_exe.replace("'", "''")))


def launch_updater(script_path, target_exe, new_exe, pid):
    """Jalankan updater PowerShell tanpa jendela. Kembali True bila
    proses updater berhasil diluncurkan."""
    if sys.platform != "win32":
        return False
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", script_path,
             "-TargetExe", target_exe, "-NewExe", new_exe,
             "-AppPid", str(pid)],
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW)
        return True
    except Exception:
        return False


def perform_update(root, info):
    """Unduh exe baru (dengan jendela progres), lalu luncurkan
    updater dan keluar dari aplikasi. Kembali True bila updater
    diluncurkan (aplikasi lalu keluar); False bila gagal di tengah
    (pengguna tetap di aplikasi lama)."""
    from tkinter import messagebox, ttk
    import tkinter as tk
    if not getattr(sys, "frozen", False):
        # Jalan dari source (bukan exe): tidak ada exe yang bisa
        # diganti — bukakan saja halaman rilisnya.
        import webbrowser
        webbrowser.open(REPO_URL + "/releases")
        return False
    target_exe = sys.executable
    tmpdir = os.path.join(os.environ.get("TEMP", "."), "ConvTool-update")
    try:
        os.makedirs(tmpdir, exist_ok=True)
    except Exception:
        pass
    new_exe = os.path.join(tmpdir, EXE_ASSET_NAME)
    script_path = os.path.join(tmpdir, "update.ps1")

    progress = tk.Toplevel(root)
    progress.title("Mengunduh pembaruan...")
    ttk.Label(progress, text="Mengunduh ConvTool v%s ..."
            % info["version_text"]).pack(padx=16, pady=(12, 6))
    bar = ttk.Progressbar(progress, mode="indeterminate", length=280)
    bar.pack(padx=16, pady=(0, 12))
    bar.start(20)
    result = {"ok": None}

    def _download():
        result["ok"] = download_exe(info["download_url"], new_exe,
                                    info.get("size", 0))

    thread = threading.Thread(target=_download, daemon=True)
    thread.start()

    def _poll():
        if result["ok"] is None:
            try:
                root.after(200, _poll)
            except Exception:
                pass
            return
        try:
            progress.destroy()
        except Exception:
            pass
        if not result["ok"]:
            messagebox.showerror(
                "Pembaruan gagal",
                "Gagal mengunduh exe baru.\nCoba lagi nanti, atau "
                "unduh manual dari:\n%s/releases" % REPO_URL,
                parent=root)
            return
        script = build_updater_script(target_exe, new_exe,
                                      os.getpid())
        try:
            with open(script_path, "w", encoding="utf-8") as fh:
                fh.write(script)
        except Exception:
            messagebox.showerror(
                "Pembaruan gagal",
                "Tidak dapat menulis updater. Coba jalankan "
                "ConvTool sebagai Administrator.", parent=root)
            return
        if not launch_updater(script_path, target_exe, new_exe,
                              os.getpid()):
            messagebox.showerror(
                "Pembaruan gagal",
                "Tidak dapat meluncurkan updater.",
                parent=root)
            return
        mark_notified(info["version_text"])
        # Updater menunggu proses ini keluar, lalu mengganti exe
        # dan membuka lagi. Keluar sekarang.
        _exit_app(root)

    try:
        root.after(200, _poll)
    except Exception:
        pass
    return True


def _exit_app(root):
    """Keluar dari aplikasi supaya updater bisa mengganti exe."""
    try:
        root.destroy()
    except Exception:
        pass
    os._exit(0)
