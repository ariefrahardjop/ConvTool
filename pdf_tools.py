# pdf_tools.py — Dialog Convert Images -> PDF dan PDF -> Images.
#
# Images -> PDF: daftar gambar (tombol Tambah Gambar / Hapus), tiap gambar
# jadi satu halaman; bisa dipilih orientasi (portrait/landscape), ukuran
# kertas (A4/Folio/Letter/Legal/A5), mode gambar (fit dalam margin /
# full memenuhi halaman, dipotong tengah), dan resize gambar sebelum
# dimasukkan (Original/Small/Medium/Large — Small = PDF lebih kecil).
# Output dipilih lewat save dialog (default: nama gambar pertama + .pdf).
# PDF -> Images: render tiap halaman jadi PNG/JPG pada ukuran pilihan
# (opsi S/M/L/Custom sama seperti resize; ukuran = sisi terpanjang
# dalam piksel), nama hasil "nama_p001.png" dst di folder yang sama.

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import core
from ui_common import PresetFrame, make_status

IMAGE_FILETYPES = [("Images", "*.jpg *.jpeg *.png *.webp *.bmp *.gif"),
                   ("All files", "*.*")]


class ImagesToPdfDialog(tk.Toplevel):
    def __init__(self, parent, files):
        super().__init__(parent)
        self.title("Convert Images to PDF")
        self.resizable(False, False)
        # transient HANYA bila induk terlihat (lihat resize_dialog).
        if parent is not None and parent.winfo_viewable():
            self.transient(parent)
        self.grab_set()
        self.files = list(files)

        ttk.Label(self, text="Images to PDF", font=("", 14, "bold"),
                  foreground="#1a5fb4").pack(anchor="w", padx=12, pady=(10, 2))
        ttk.Label(self, text="Tiap gambar menjadi satu halaman.").pack(
            anchor="w", padx=12)

        list_frame = ttk.Frame(self)
        list_frame.pack(fill="both", padx=12, pady=6)
        self.listbox = tk.Listbox(list_frame, width=64, height=8)
        self.listbox.pack(side="left", fill="both", expand=True)
        side = ttk.Frame(list_frame)
        side.pack(side="left", padx=(6, 0))
        ttk.Button(side, text="Tambah Gambar",
                   command=self._add).pack(fill="x", pady=2)
        ttk.Button(side, text="Hapus",
                   command=self._remove).pack(fill="x", pady=2)
        ttk.Button(side, text="Naik",
                   command=lambda: self._move(-1)).pack(fill="x", pady=2)
        ttk.Button(side, text="Turun",
                   command=lambda: self._move(1)).pack(fill="x", pady=2)
        self._refresh_list()

        opt = ttk.LabelFrame(self, text="Pengaturan halaman")
        opt.pack(fill="x", padx=12, pady=4)
        ttk.Label(opt, text="Orientasi:").grid(
            row=0, column=0, sticky="w", padx=4, pady=2)
        self.orientation_var = tk.StringVar(value="portrait")
        ttk.Radiobutton(opt, text="Portrait",
                        variable=self.orientation_var,
                        value="portrait").grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(opt, text="Landscape",
                        variable=self.orientation_var,
                        value="landscape").grid(row=0, column=2, sticky="w")
        ttk.Label(opt, text="Ukuran kertas:").grid(
            row=1, column=0, sticky="w", padx=4, pady=2)
        self.paper_var = tk.StringVar(value="A4")
        ttk.Combobox(opt, textvariable=self.paper_var, width=10,
                     state="readonly",
                     values=core.PAPER_ORDER).grid(
                         row=1, column=1, sticky="w", pady=2)
        ttk.Label(opt, text="Gambar:").grid(
            row=2, column=0, sticky="w", padx=4, pady=2)
        self.fill_var = tk.StringVar(value="fit")
        ttk.Radiobutton(opt, text="Muat dalam halaman (fit)",
                        variable=self.fill_var,
                        value="fit").grid(row=2, column=1, columnspan=2,
                                          sticky="w")
        ttk.Radiobutton(opt, text="Penuhi halaman / full (potong)",
                        variable=self.fill_var,
                        value="full").grid(row=3, column=1, columnspan=2,
                                           sticky="w")
        ttk.Label(opt, text="Resize gambar:").grid(
            row=4, column=0, sticky="w", padx=4, pady=2)
        self.resize_var = tk.StringVar(value="Original")
        ttk.Combobox(opt, textvariable=self.resize_var, width=10,
                     state="readonly",
                     values=["Original", "Small", "Medium",
                             "Large"]).grid(row=4, column=1, sticky="w",
                                            pady=2)
        ttk.Label(opt, text="(Small = PDF lebih kecil)").grid(
            row=4, column=2, sticky="w", pady=2)

        self.status = make_status(self)
        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=12, pady=(6, 12))
        ttk.Button(btns, text="Convert to PDF",
                   command=self._do_convert,
                   default="active").pack(side="right", padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(
            side="right", padx=4)
        self.bind("<Escape>", lambda e: self.destroy())

    def _refresh_list(self):
        self.listbox.delete(0, "end")
        for f in self.files:
            self.listbox.insert("end", os.path.basename(f))

    def _add(self):
        chosen = filedialog.askopenfilenames(
            parent=self, title="Tambah gambar", filetypes=IMAGE_FILETYPES)
        for f in chosen:
            if f not in self.files:
                self.files.append(f)
        self._refresh_list()

    def _remove(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        del self.files[sel[0]]
        self._refresh_list()

    def _move(self, delta):
        sel = self.listbox.curselection()
        if not sel:
            return
        i = sel[0]
        j = i + delta
        if j < 0 or j >= len(self.files):
            return
        self.files[i], self.files[j] = self.files[j], self.files[i]
        self._refresh_list()
        self.listbox.selection_set(j)

    def _do_convert(self):
        if not self.files:
            messagebox.showwarning("Belum ada gambar",
                                   "Tambahkan minimal satu gambar.",
                                   parent=self)
            return
        first_stem = os.path.splitext(
            os.path.basename(self.files[0]))[0]
        out = filedialog.asksaveasfilename(
            parent=self, title="Simpan PDF sebagai",
            initialfile=first_stem + ".pdf",
            initialdir=os.path.dirname(self.files[0]),
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")])
        if not out:
            return
        resize = self.resize_var.get()
        if resize == "Original":
            resize = None
        try:
            n = core.images_to_pdf(
                self.files, out,
                page_size=self.paper_var.get(),
                orientation=self.orientation_var.get(),
                fill=self.fill_var.get() == "full",
                resize=resize)
        except Exception as exc:
            messagebox.showerror("Gagal", "Convert gagal: %s" % exc,
                                 parent=self)
            return
        messagebox.showinfo("Selesai",
                            "PDF dibuat: %s (%d halaman)."
                            % (os.path.basename(out), n), parent=self)
        self.destroy()


class PdfToImagesDialog(tk.Toplevel):
    def __init__(self, parent, files):
        super().__init__(parent)
        self.files = list(files)
        self.title("Convert PDF to Images")
        self.resizable(False, False)
        # transient HANYA bila induk terlihat (lihat resize_dialog).
        if parent is not None and parent.winfo_viewable():
            self.transient(parent)
        self.grab_set()

        ttk.Label(self, text="PDF to Images", font=("", 14, "bold"),
                  foreground="#1a5fb4").pack(anchor="w", padx=12, pady=(10, 2))
        info = "%d file PDF dipilih." % len(self.files)
        if len(self.files) == 1:
            info = os.path.basename(self.files[0])
        ttk.Label(self, text=info).pack(anchor="w", padx=12, pady=(0, 4))
        ttk.Label(self, text="Ukuran = sisi terpanjang tiap halaman "
                             "(piksel).").pack(anchor="w", padx=12)

        self.preset = PresetFrame(self)
        self.preset.pack(fill="x", padx=12, pady=4)

        fmt_frame = ttk.Frame(self)
        fmt_frame.pack(fill="x", padx=12, pady=4)
        ttk.Label(fmt_frame, text="Format hasil:").pack(side="left")
        self.out_format = tk.StringVar(value="PNG")
        ttk.Combobox(fmt_frame, textvariable=self.out_format, width=8,
                     state="readonly", values=["PNG", "JPG"]).pack(
                         side="left", padx=6)

        self.status = make_status(self)
        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=12, pady=(6, 12))
        ttk.Button(btns, text="Convert", command=self._do_convert,
                   default="active").pack(side="right", padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(
            side="right", padx=4)
        self.bind("<Escape>", lambda e: self.destroy())

    def _do_convert(self):
        tw, th = self.preset.get_target()
        if tw is None or th is None:
            messagebox.showwarning(
                "Ukuran tidak valid",
                "Isi lebar dan tinggi Custom dengan angka > 0.",
                parent=self)
            return
        longest = max(tw, th)
        total = 0
        fail = []
        for i, path in enumerate(self.files):
            self.status.set("Memproses %d/%d: %s"
                            % (i + 1, len(self.files),
                               os.path.basename(path)))
            self.update_idletasks()
            try:
                folder = os.path.dirname(path)
                base = os.path.splitext(os.path.basename(path))[0]
                made = core.pdf_to_images(path, folder, base, longest,
                                          fmt=self.out_format.get())
                total += len(made)
            except Exception as exc:
                fail.append("%s: %s" % (os.path.basename(path), exc))
        if fail:
            messagebox.showwarning(
                "Selesai dengan %d gagal" % len(fail),
                "Gambar dibuat: %d.\nGagal:\n%s"
                % (total, "\n".join(fail)), parent=self)
        else:
            messagebox.showinfo("Selesai",
                                "%d gambar dibuat dari %d PDF."
                                % (total, len(self.files)), parent=self)
        self.destroy()


def run_images_to_pdf(parent, files):
    dlg = ImagesToPdfDialog(parent, files)
    dlg.deiconify()
    dlg.lift()
    dlg.focus_force()
    parent.wait_window(dlg)


def run_pdf_to_images(parent, files):
    dlg = PdfToImagesDialog(parent, files)
    dlg.deiconify()
    dlg.lift()
    dlg.focus_force()
    parent.wait_window(dlg)
