# convtool.py — Entry point ConvTool (aplikasi desktop Windows).
#
# Cara pakai (dipanggil dari menu klik kanan / baris perintah):
#   ConvTool.exe <verb> <file> [file...]
#   verb: resize-image | resize-pdf | images-to-pdf | pdf-to-images |
#         exif | watermark-klasik | watermark-job
# Tanpa argumen: tampilkan jendela launcher berisi daftar 6 alat
# (klik alat -> buka file picker).
#
# Semua alat membuka dialog tkinter sendiri; modul ini hanya routing
# dan launcher. Build exe: lihat build.bat (PyInstaller, --windowed).
#
# SINGLE-INSTANCE (single_instance.py): Explorer memanggil command
# klik kanan SEKALI PER FILE bila MultiSelectModel tidak berlaku —
# pilih 8 foto = 8 proses. Proses pertama menjadi primary dan membuka
# SATU dialog berisi daftar; proses berikutnya meneruskan file-nya ke
# primary lewat socket localhost lalu keluar. Dialog yang sedang
# terbuka menerima file kiriman lewat add_files() (tiap dialog punya
# metode itu); kiriman ber-verb beda antre dan dibuka sesudah dialog
# aktif tutup.

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import core  # noqa: F401  (dipakai tidak langsung oleh modul dialog)
import exif_editor
import pdf_tools
import resize_dialog
import single_instance
import watermark_dialog
from ui_common import fit_to_screen

# Dialog yang sedang terbuka + antrean kiriman single-instance.
_ACTIVE = {"verb": None, "dialog": None}
_PENDING = []  # [(verb, files)] ber-verb beda, dibuka sesudahnya
_IPC_INBOX = None

VERBS = {
    "resize-image", "resize-pdf", "images-to-pdf", "pdf-to-images",
    "exif", "watermark-klasik", "watermark-job",
}

IMAGE_TYPES = [("Images", "*.jpg *.jpeg *.png *.webp *.bmp *.gif"),
               ("All files", "*.*")]
PDF_TYPES = [("PDF", "*.pdf"), ("All files", "*.*")]


def _existing_files(paths):
    out = []
    for p in paths:
        if os.path.isfile(p):
            out.append(os.path.abspath(p))
    return out


def _run_verb(root, verb, files):
    """Buka dialog untuk (verb, files) dan tunggu sampai tutup.
    Melacak dialog aktif supaya _poll_ipc bisa menggabungkan kiriman
    single-instance ke dalamnya."""
    if verb == "resize-image":
        dlg = resize_dialog.run_resize_dialog(root, files, kind="image")
    elif verb == "resize-pdf":
        dlg = resize_dialog.run_resize_dialog(root, files, kind="pdf")
    elif verb == "images-to-pdf":
        dlg = pdf_tools.run_images_to_pdf(root, files)
    elif verb == "pdf-to-images":
        dlg = pdf_tools.run_pdf_to_images(root, files)
    elif verb == "exif":
        # SATU dialog untuk semua foto (dulu: satu dialog per foto).
        dlg = exif_editor.run_exif_editor(root, files)
    elif verb == "watermark-klasik":
        dlg = watermark_dialog.run_watermark_dialog(root, files, "klasik")
    elif verb == "watermark-job":
        dlg = watermark_dialog.run_watermark_dialog(root, files, "job")
    else:
        return
    _ACTIVE["verb"] = verb
    _ACTIVE["dialog"] = dlg
    try:
        root.wait_window(dlg)
    finally:
        _ACTIVE["verb"] = None
        _ACTIVE["dialog"] = None


def _poll_ipc(root):
    """Periksa kiriman single-instance tiap 200 md. Tiket berikutnya
    dijadwalkan DULU (di awal) supaya rantai tetap jalan meski
    _run_verb di bawah memblokir di wait_window (event loop bersarang
    tetap menjalankan after)."""
    try:
        root.after(200, lambda: _poll_ipc(root))
    except Exception:
        return  # root sudah dihancurkan, rantai berhenti
    dlg = _ACTIVE["dialog"]
    if dlg is not None:
        merged, pending = single_instance.merge_pending(
            _IPC_INBOX, _ACTIVE["verb"], dlg.files)
        if merged != dlg.files:
            try:
                dlg.add_files(merged)
            except Exception:
                pass
        _PENDING.extend(pending)
        # Kait diagnostik: bila CONVTOOL_STATE_FILE diset (dipakai uji
        # E2E dan diagnosis di PC), tulis daftar file dialog aktif ke
        # berkas itu tiap tick — membuktikan primary menerima kiriman.
        state_file = os.environ.get("CONVTOOL_STATE_FILE")
        if state_file:
            try:
                with open(state_file, "w",
                          encoding="utf-8") as fh:
                    fh.write("\n".join(dlg.files))
            except Exception:
                pass
    else:
        _merged, pending = single_instance.merge_pending(
            _IPC_INBOX, None, [])
        _PENDING.extend(pending)
        if _PENDING:
            verb, files = _PENDING.pop(0)
            _run_verb(root, verb, files)


def _pick_files(filetypes, title):
    return list(filedialog.askopenfilenames(title=title,
                                            filetypes=filetypes))


class Launcher(tk.Tk):
    """Jendela utama bila ConvTool dijalankan tanpa argumen."""

    TOOLS = [
        ("Resize Pictures", "Perkecil gambar (JPG/PNG/WEBP) ke "
         "Small / Medium / Large / Phone / Custom.", "image"),
        ("Resize PDF", "Perkecil halaman PDF ke ukuran Small / Medium / "
         "Large / Phone / Custom.", "pdf"),
        ("Images to PDF", "Gabung beberapa gambar menjadi satu file PDF "
         "(satu gambar satu halaman A4).", "images"),
        ("PDF to Images", "Ubah tiap halaman PDF menjadi gambar "
         "PNG/JPG.", "pdfs"),
        ("Edit EXIF", "Lihat & ubah tanggal, GPS, dan tag EXIF foto "
         "(disimpan sebagai salinan _exifedit).", "exif"),
        ("Watermark Klasik", "Stempel GPS Map Camera Klasik: kartu gelap "
         "+ peta satelit.", "wm-klasik"),
        ("Watermark Job", "Stempel Job Timestamp: strip abu-abu + peta "
         "jalan.", "wm-job"),
    ]

    def __init__(self):
        super().__init__()
        self.title("ConvTool")
        self.resizable(False, False)
        ttk.Label(self, text="ConvTool", font=("", 18, "bold"),
                  foreground="#1a5fb4").pack(anchor="w", padx=14, pady=(12, 0))
        ttk.Label(self, text="Pilih alat, lalu pilih file.").pack(
            anchor="w", padx=14, pady=(0, 8))
        for (label, desc, key) in self.TOOLS:
            btn = ttk.Button(self, text=label,
                             command=lambda k=key: self._open_tool(k))
            btn.pack(fill="x", padx=14, pady=2)
            ttk.Label(self, text=desc, wraplength=420,
                      foreground="#555555").pack(anchor="w", padx=18)
        ttk.Button(self, text="Tutup", command=self.destroy).pack(
            pady=(10, 12))
        fit_to_screen(self)

    def _open_tool(self, key):
        if key == "image":
            files = _pick_files(IMAGE_TYPES, "Pilih gambar")
            if files:
                _run_verb(self, "resize-image", files)
        elif key == "pdf":
            files = _pick_files(PDF_TYPES, "Pilih PDF")
            if files:
                _run_verb(self, "resize-pdf", files)
        elif key == "images":
            files = _pick_files(IMAGE_TYPES, "Pilih gambar")
            if files:
                _run_verb(self, "images-to-pdf", files)
        elif key == "pdfs":
            files = _pick_files(PDF_TYPES, "Pilih PDF")
            if files:
                _run_verb(self, "pdf-to-images", files)
        elif key == "exif":
            files = _pick_files(IMAGE_TYPES, "Pilih foto")
            if files:
                _run_verb(self, "exif", files)
        elif key == "wm-klasik":
            files = _pick_files(IMAGE_TYPES, "Pilih foto")
            if files:
                _run_verb(self, "watermark-klasik", files)
        elif key == "wm-job":
            files = _pick_files(IMAGE_TYPES, "Pilih foto")
            if files:
                _run_verb(self, "watermark-job", files)


def main(argv):
    global _IPC_INBOX
    args = list(argv[1:])
    if not args:
        app = Launcher()
        # Launcher juga jadi primary bila belum ada (supaya kiriman
        # klik-kanan yang datang belakangan membuka dialog di sini).
        role, inbox = single_instance.claim(None, [])
        if role == "primary":
            _IPC_INBOX = inbox
            app.after(200, lambda: _poll_ipc(app))
        app.mainloop()
        return 0
    verb = args[0].lower()
    if verb in ("-h", "--help", "/?"):
        print("Pakai: ConvTool.exe <verb> <file> [file...]")
        print("verb: " + " | ".join(sorted(VERBS)))
        print("Tanpa argumen: buka jendela launcher.")
        return 0
    # Root tersembunyi dibuat dulu supaya messagebox selalu punya induk.
    root = tk.Tk()
    root.withdraw()
    if verb not in VERBS:
        messagebox.showerror(
            "ConvTool",
            "Perintah tidak dikenal: %s\n\nPerintah yang tersedia:\n%s"
            % (verb, "\n".join(sorted(VERBS))), parent=root)
        root.destroy()
        return 2
    files = _existing_files(args[1:])
    if not files:
        messagebox.showwarning(
            "ConvTool", "Tidak ada file yang valid untuk perintah %s."
            % verb, parent=root)
        root.destroy()
        return 2
    # Single-instance: proses lain yang sudah jalan menerima file ini
    # (primary membuka satu dialog berisi daftar); proses ini keluar.
    role, inbox = single_instance.claim(verb, files)
    if role == "forwarded":
        root.destroy()
        return 0
    _IPC_INBOX = inbox
    root.after(200, lambda: _poll_ipc(root))
    # Gabungkan kiriman yang sudah tiba selama startup (proses lain
    # biasanya sudah mulai lebih dulu) sebelum dialog dibuka.
    files, pending = single_instance.merge_pending(inbox, verb, files)
    _PENDING.extend(pending)
    try:
        _run_verb(root, verb, files)
        # Kiriman ber-verb beda yang antre selama dialog terbuka.
        while _PENDING:
            next_verb, next_files = _PENDING.pop(0)
            _run_verb(root, next_verb, next_files)
    except Exception:
        # Exe windowed tidak menampilkan traceback: tulis ke log di
        # %TEMP% dan tampilkan di messagebox supaya kelihatan.
        import traceback
        err = traceback.format_exc()
        log_path = os.path.join(
            os.environ.get("TEMP", "."), "convtool-error.log")
        try:
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(err + "\n")
        except Exception:
            pass
        messagebox.showerror(
            "ConvTool - error",
            "Terjadi error. Detail lengkap tersimpan di:\n%s\n\n%s"
            % (log_path, err[-1500:]), parent=root)
    finally:
        try:
            root.destroy()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
