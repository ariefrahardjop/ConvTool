# resize_dialog.py — Dialog Resize (gambar & PDF) ConvTool.
#
# Meniru dialog "Image Resizer for Windows" di screenshot user:
# radio Small/Medium/Large/Phone/Custom + checkbox + tombol
# "Advanced options..." + Resize/Cancel.
#
# Gambar: hasil default file BARU "nama (Small).jpg" dst; checkbox
# "Resize the original pictures" bila ON menimpa file asli.
# PDF: BUKAN resize ukuran piksel halaman, melainkan kompres ukuran
# file — tiga preset langsung: Small / Medium / Large (DPI render +
# kualitas JPEG). Tiap halaman dirender jadi gambar JPEG, jadi teks
# di PDF tidak bisa diseleksi lagi.
#
# Responsif: isi dialog di dalam ScrollableFrame (ui_common) sehingga
# di layar kecil isi bisa di-scroll dan tombol Resize/Cancel di bawah
# selalu terlihat.

import os
import tkinter as tk
from tkinter import messagebox, ttk

import core
from ui_common import PresetFrame, ScrollableFrame, make_status

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif",
              ".tiff")


class ResizeDialog(tk.Toplevel):
    def __init__(self, parent, files, kind="image"):
        """kind: 'image' atau 'pdf'."""
        super().__init__(parent)
        self.files = list(files)
        self.kind = kind
        self.title("Resize your pictures" if kind == "image"
                   else "Resize PDF")
        self.resizable(True, True)
        # transient HANYA bila induk terlihat. Di jalur klik kanan,
        # induknya root yang disembunyikan (withdraw) — transient ke
        # jendela tersembunyi membuat dialog tidak tampil di Windows.
        if parent is not None and parent.winfo_viewable():
            self.transient(parent)
        self.grab_set()

        title = ("Resize your pictures" if kind == "image"
                 else "Resize PDF")
        ttk.Label(self, text=title, font=("", 14, "bold"),
                  foreground="#1a5fb4").pack(anchor="w", padx=12, pady=(10, 2))
        info = "%d file dipilih." % len(self.files)
        if len(self.files) == 1:
            info = os.path.basename(self.files[0])
        self.info_label = ttk.Label(self, text=info)
        self.info_label.pack(anchor="w", padx=12, pady=(0, 6))

        # ---- isi (bisa di-scroll di layar kecil) + tombol tetap di bawah
        body = ScrollableFrame(self)
        body.pack(fill="both", expand=True)
        self._body = body
        content = body.inner

        if kind == "pdf":
            # Resize PDF = kompres ukuran file, langsung tiga preset.
            # Bukan ukuran piksel halaman (cara lama hanya menampilkan
            # ulang konten asli tanpa mengecilkan file).
            ttk.Label(
                content,
                text="Pilih ukuran hasil — makin kecil makin hemat "
                     "ruang, makin besar makin dekat aslinya.").pack(
                         anchor="w", padx=12, pady=(0, 2))
            ttk.Label(
                content,
                text="Small mengubah halaman jadi hitam-putih pekat — "
                     "cocok untuk dokumen teks/scan; foto & stempel "
                     "jadi hitam-putih. Tiap halaman jadi gambar — "
                     "teks tidak bisa diseleksi lagi.").pack(
                         anchor="w", padx=12)
            self.pdf_preset = tk.StringVar(value="Medium")
            preset_frame = ttk.LabelFrame(content, text="Ukuran hasil")
            preset_frame.pack(fill="x", padx=12, pady=6)
            for name, desc in (
                    ("Small", "Hitam-putih pekat (teks) — file paling "
                              "kecil"),
                    ("Medium", "Hitam-putih — seimbang"),
                    ("Large", "Berwarna — paling dekat aslinya")):
                ttk.Radiobutton(preset_frame, text=name,
                                variable=self.pdf_preset,
                                value=name).pack(anchor="w", padx=8,
                                                 pady=(4, 0))
                ttk.Label(preset_frame, text="    " + desc).pack(
                    anchor="w", padx=8)
            ttk.Label(preset_frame, text="").pack()
        else:
            ref = self._reference_size()
            self.preset = PresetFrame(content, ref_size=ref)
            self.preset.pack(fill="x", padx=12, pady=4)

            self.smaller_only = tk.BooleanVar(value=True)
            ttk.Checkbutton(
                content, text="Make pictures smaller but not larger",
                variable=self.smaller_only).pack(anchor="w", padx=12, pady=1)
        self.overwrite = tk.BooleanVar(value=False)
        self.ignore_orientation = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            content, text="Resize the original pictures "
                       "(don't create copies)",
            variable=self.overwrite).pack(anchor="w", padx=12, pady=1)
        if kind == "image":
            ttk.Checkbutton(
                content, text="Ignore the orientation of pictures",
                variable=self.ignore_orientation).pack(
                    anchor="w", padx=12, pady=1)

        # Advanced options (khusus gambar): kualitas JPEG + format output.
        self.adv_frame = ttk.LabelFrame(content, text="Advanced options")
        self.quality = tk.IntVar(value=core.JPEG_QUALITY_DEFAULT)
        self.out_format = tk.StringVar(value="same")
        if kind == "image":
            ttk.Label(self.adv_frame, text="JPEG quality:").grid(
                row=0, column=0, sticky="w", padx=8, pady=4)
            ttk.Spinbox(self.adv_frame, from_=10, to=100, width=6,
                        textvariable=self.quality).grid(
                            row=0, column=1, padx=4, pady=4)
            ttk.Label(self.adv_frame, text="Output format:").grid(
                row=1, column=0, sticky="w", padx=8, pady=4)
            ttk.Combobox(self.adv_frame, textvariable=self.out_format,
                         width=18, state="readonly",
                         values=["same", "JPEG", "PNG"]).grid(
                             row=1, column=1, padx=4, pady=4)
            ttk.Label(self.adv_frame,
                      text="same = ikut format asli").grid(
                          row=1, column=2, sticky="w", padx=4)
            self.adv_visible = False
            ttk.Button(content, text="Advanced options...",
                       command=self._toggle_adv).pack(
                           anchor="w", padx=12, pady=(6, 0))

        self.status = make_status(content)

        # ---- tombol: selalu terlihat (di luar area scroll)
        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=12, pady=(6, 12))
        ttk.Button(btns, text="Resize", command=self._do_resize,
                   default="active").pack(side="right", padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(
            side="right", padx=4)
        self.bind("<Escape>", lambda e: self.destroy())
        # Batas tinggi isi 82% layar (sisanya tombol + tepi); lebar
        # dan tinggi jendela juga dibatasi agar muat di layar kecil.
        body.fit_to_window()

    # ------------------------------------------------------------- helpers

    def add_files(self, paths):
        """Tambah file ke dialog yang sedang terbuka (single-instance:
        proses lain meneruskan file-nya ke sini)."""
        new = [os.path.abspath(p) for p in paths
               if os.path.isfile(p) and os.path.abspath(p) not in
               [os.path.abspath(f) for f in self.files]]
        if not new:
            return
        self.files.extend(new)
        self.info_label.configure(
            text="%d file dipilih." % len(self.files))

    def _reference_size(self):
        """Ukuran referensi untuk Custom Percent: gambar pertama
        (gambar) atau halaman pertama dalam piksel 96 DPI (PDF)."""
        try:
            if self.kind == "image":
                from PIL import Image
                with Image.open(self.files[0]) as im:
                    return (im.width, im.height)
            import pymupdf
            doc = pymupdf.open(self.files[0])
            r = doc[0].rect
            doc.close()
            return (int(r.width * 96 / 72), int(r.height * 96 / 72))
        except Exception:
            return (None, None)

    def _toggle_adv(self):
        if self.adv_visible:
            self.adv_frame.pack_forget()
            self.adv_visible = False
        else:
            self.adv_frame.pack(fill="x", padx=12, pady=4)
            self.adv_visible = True

    # ------------------------------------------------------------- proses

    def _do_resize(self):
        ok, fail = 0, []
        sizes_info = []  # (nama file, sebelum byte, sesudah byte) — PDF
        total = len(self.files)
        for i, path in enumerate(self.files):
            self.status.set("Memproses %d/%d: %s"
                            % (i + 1, total, os.path.basename(path)))
            self.update_idletasks()
            try:
                if self.kind == "image":
                    tw, th = self.preset.get_target()
                    if tw is None or th is None:
                        messagebox.showwarning(
                            "Ukuran tidak valid",
                            "Isi lebar dan tinggi Custom dengan angka "
                            "> 0.", parent=self)
                        return
                    preset = self.preset.get_preset_name()
                    mode = self.preset.get_fit_mode()
                    smaller_only = self.smaller_only.get()
                    overwrite = self.overwrite.get()
                    if overwrite:
                        dst = path
                    else:
                        ext = None
                        if self.out_format.get() != "same":
                            ext = "." + self.out_format.get().lower()
                        dst = core.output_path_for_resize(path, preset, ext)
                    core.resize_image_file(
                        path, dst, tw, th, mode=mode,
                        smaller_only=smaller_only,
                        quality=self.quality.get(),
                        out_format=self.out_format.get(),
                        ignore_orientation=self.ignore_orientation.get())
                else:
                    preset = self.pdf_preset.get()
                    overwrite = self.overwrite.get()
                    dst = path if overwrite else core.output_path_for_resize(
                        path, preset, ".pdf")
                    before = os.path.getsize(path)
                    if os.path.abspath(dst) == os.path.abspath(path):
                        # Timpa PDF asli: tulis ke temp lalu ganti.
                        tmp = dst + ".convtool-tmp"
                        core.resize_pdf(path, tmp, preset)
                        os.replace(tmp, dst)
                    else:
                        core.resize_pdf(path, dst, preset)
                    sizes_info.append((os.path.basename(dst), before,
                                       os.path.getsize(dst)))
                ok += 1
            except Exception as exc:
                fail.append("%s: %s" % (os.path.basename(path), exc))
        if fail:
            messagebox.showwarning(
                "Selesai dengan %d gagal" % len(fail),
                "Berhasil: %d file.\nGagal:\n%s"
                % (ok, "\n".join(fail)), parent=self)
        elif self.kind == "pdf" and sizes_info:
            lines = []
            for name, before, after in sizes_info:
                line = "%s: %s -> %s" % (name, core.human_size(before),
                                         core.human_size(after))
                if after >= before:
                    line += " (tidak bisa lebih kecil — sudah optimal)"
                lines.append(line)
            messagebox.showinfo("Selesai", "\n".join(lines), parent=self)
        else:
            messagebox.showinfo("Selesai", "Berhasil me-resize %d file."
                                % ok, parent=self)
        self.destroy()


def run_resize_dialog(parent, files, kind="image"):
    """Buat dialog dan kembalikan; pemanggil yang menunggu
    (wait_window) supaya convtool.py bisa melacak dialog aktif
    untuk single-instance."""

    dlg = ResizeDialog(parent, files, kind=kind)
    dlg.deiconify()
    dlg.lift()
    dlg.focus_force()
    return dlg
