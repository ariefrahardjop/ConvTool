# tests/test_gui_smoke.py — Uji GUI ConvTool di bawah Xvfb (headless).
#
# Jalankan dari ~/workspace/convtool dengan layar virtual KECIL
# (mensimulasikan laptop 1024x600 — di sinilah tombol dialog dulu
# tertutup):
#   xvfb-run -a -s "-screen 0 1024x600x24" \
#       .venv-test/bin/python tests/test_gui_smoke.py
#
# Yang diuji (tanpa jaringan — foto tanpa GPS, jadi tidak ada unduh
# tile peta / reverse-geocode):
#   - semua dialog muat di layar (tinggi <= tinggi layar) dan tombol
#     bawahnya terlihat penuh (tidak tertutup / terpotong)
#   - EXIF Editor: satu dialog untuk banyak foto (daftar foto, pindah
#     foto tanpa kehilangan edit, Simpan + Simpan Semua)
#   - Watermark: satu dialog untuk banyak foto (daftar foto, klik foto
#     mengganti pratinjau)
# messagebox di-patch jadi no-op supaya tidak menunggu klik.

import os
import shutil
import sys
import tkinter as tk
from tkinter import messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# messagebox tidak boleh blocking di smoke test.
messagebox.showinfo = lambda *a, **k: None
messagebox.showwarning = lambda *a, **k: None
messagebox.showerror = lambda *a, **k: None

from PIL import Image  # noqa: E402

import exif_editor  # noqa: E402
import pdf_tools  # noqa: E402
import resize_dialog  # noqa: E402
import single_instance  # noqa: E402
import watermark_dialog  # noqa: E402

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work-gui")
PASSES = [0]
FAILURES = []


def check(name, cond, detail=""):
    if cond:
        PASSES[0] += 1
        print("PASS ", name, detail)
    else:
        FAILURES.append(name)
        print("FAIL ", name, detail)


def all_buttons(widget):
    """Semua tombol (tk/ttk Button) di bawah widget, rekursif."""
    out = []
    for child in widget.winfo_children():
        cls = child.winfo_class()
        if cls in ("Button", "TButton"):
            out.append(child)
        out.extend(all_buttons(child))
    return out


def assert_fits(root, dlg, name):
    """Dialog muat di layar dan SEMUA tombolnya terlihat penuh."""
    dlg.deiconify()
    dlg.update_idletasks()
    dlg.update()
    scr_h = dlg.winfo_screenheight()
    scr_w = dlg.winfo_screenwidth()
    h, w = dlg.winfo_height(), dlg.winfo_width()
    check("%s tinggi muat di layar (%d <= %d)" % (name, h, scr_h),
          h <= scr_h, "")
    check("%s lebar muat di layar (%d <= %d)" % (name, w, scr_w),
          w <= scr_w, "")
    dlg_top = dlg.winfo_rooty()
    for btn in all_buttons(dlg):
        top = btn.winfo_rooty() - dlg_top
        bottom = top + btn.winfo_height()
        check("%s tombol '%s' terlihat penuh"
              % (name, btn.cget("text") or btn.winfo_class()),
              0 <= top and bottom <= h,
              "y=%d..%d dari %d" % (top, bottom, h))


def make_photo(path, color=(40, 120, 200)):
    im = Image.new("RGB", (800, 600), color)
    im.save(path, "JPEG", quality=90)
    return path


def make_pdf(path):
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((100, 100), "Halo ConvTool", fontsize=40)
    doc.save(path)
    doc.close()
    return path


def main():
    if os.path.exists(WORK):
        shutil.rmtree(WORK)
    os.makedirs(WORK)
    root = tk.Tk()
    root.withdraw()

    photos = [make_photo(os.path.join(WORK, "foto%d.jpg" % i),
                         (40 + i * 60, 120, 200 - i * 40))
              for i in range(3)]
    pdf = make_pdf(os.path.join(WORK, "dok.pdf"))

    print("\n== dialog muat di layar kecil 1024x600 ==")
    dlg = resize_dialog.ResizeDialog(root, photos, kind="image")
    assert_fits(root, dlg, "resize gambar")
    dlg.destroy()

    dlg = resize_dialog.ResizeDialog(root, [pdf], kind="pdf")
    assert_fits(root, dlg, "resize PDF")
    dlg.destroy()

    dlg = pdf_tools.ImagesToPdfDialog(root, photos)
    assert_fits(root, dlg, "images to PDF")
    dlg.destroy()

    dlg = pdf_tools.PdfToImagesDialog(root, [pdf])
    assert_fits(root, dlg, "PDF to images")
    dlg.destroy()

    print("\n== EXIF Editor multi-foto satu frame ==")
    dlg = exif_editor.ExifEditorDialog(root, photos)
    dlg.deiconify()
    dlg.update_idletasks()
    dlg.update()
    check("exif daftar berisi 3 foto", dlg.file_list.size() == 3, "")
    check("exif judul foto 1 dari 3",
          "Foto 1 dari 3" in dlg.title(), dlg.title())
    assert_fits(root, dlg, "EXIF editor")
    # Edit foto 1, pindah ke foto 2, kembali — edit tidak hilang.
    dlg.lat_var.set("-7.111111")
    dlg.lon_var.set("112.222222")
    dlg.file_list.selection_clear(0)
    dlg.file_list.selection_set(1)
    dlg.file_list.event_generate("<<ListboxSelect>>")
    dlg.update_idletasks()
    check("exif pindah ke foto 2",
          dlg._current == 1 and "Foto 2 dari 3" in dlg.title(),
          dlg.title())
    dlg.file_list.selection_clear(1)
    dlg.file_list.selection_set(0)
    dlg.file_list.event_generate("<<ListboxSelect>>")
    dlg.update_idletasks()
    check("exif edit foto 1 tidak hilang saat pindah",
          dlg.lat_var.get() == "-7.111111"
          and dlg.lon_var.get() == "112.222222",
          "%s, %s" % (dlg.lat_var.get(), dlg.lon_var.get()))
    # Simpan foto 1 (salinan _exifedit).
    dlg._save()
    check("exif Simpan menulis salinan",
          os.path.exists(os.path.join(WORK, "foto0_exifedit.jpg")), "")
    # Edit foto 3 lalu Simpan Semua.
    dlg.file_list.selection_clear(0)
    dlg.file_list.selection_set(2)
    dlg.file_list.event_generate("<<ListboxSelect>>")
    dlg.update_idletasks()
    dlg.lat_var.set("-7.333333")
    dlg.lon_var.set("112.444444")
    dlg._save_all()
    check("exif Simpan Semua menulis foto 3",
          os.path.exists(os.path.join(WORK, "foto2_exifedit.jpg")), "")
    dlg.destroy()

    print("\n== Watermark multi-foto satu frame ==")
    dlg = watermark_dialog.WatermarkDialog(root, photos, "klasik")
    dlg.deiconify()
    dlg.update_idletasks()
    dlg.update()
    check("watermark daftar berisi 3 foto", dlg.file_list.size() == 3, "")
    check("watermark pratinjau awal foto 1",
          dlg._current_file == photos[0]
          and "foto 1 dari 3" in dlg.pv.cget("text"),
          dlg.pv.cget("text"))
    assert_fits(root, dlg, "watermark klasik")
    dlg.file_list.selection_clear(0)
    dlg.file_list.selection_set(1)
    dlg.file_list.event_generate("<<ListboxSelect>>")
    dlg.update_idletasks()
    check("watermark klik foto 2 ganti pratinjau",
          dlg._current_file == photos[1]
          and "foto 2 dari 3" in dlg.pv.cget("text"),
          dlg.pv.cget("text"))
    dlg.destroy()

    print("\n== add_files (single-instance: kiriman proses lain) ==")
    dlg = exif_editor.ExifEditorDialog(root, photos[:1])
    dlg.deiconify()
    dlg.update_idletasks()
    dlg.update()
    # Daftar SELALU ada di atas sejak init (bahkan untuk 1 foto),
    # dan ter-pack SEBELUM isi + tombol: pack_slaves()[0] = frame daftar.
    check("exif 1 foto awal daftar sudah ada di atas",
          dlg.file_list is not None and dlg.file_list.size() == 1
          and dlg.pack_slaves()[0] is dlg._list_frame, "")
    check("exif tombol tetap paling bawah",
          dlg.pack_slaves()[-1].winfo_children()[0].cget("text")
          == "Simpan", "")
    dlg.add_files(photos[1:])
    check("exif add_files membuat daftar 3 foto",
          dlg.file_list is not None and dlg.file_list.size() == 3, "")
    check("exif add_files daftar TETAP di atas",
          dlg.pack_slaves()[0] is dlg._list_frame, "")
    check("exif add_files judul jadi Foto 1 dari 3",
          "Foto 1 dari 3" in dlg.title(), dlg.title())
    dlg.add_files(photos[1:])  # kiriman duplikat diabaikan
    check("exif add_files duplikat diabaikan",
          dlg.file_list.size() == 3, "")
    dlg.destroy()

    dlg = watermark_dialog.WatermarkDialog(root, photos[:1], "klasik")
    dlg.deiconify()
    dlg.update_idletasks()
    dlg.update()
    check("watermark 1 foto awal daftar sudah ada di atas form",
          dlg.file_list is not None and dlg.file_list.size() == 1
          and dlg._left_frame.pack_slaves().index(dlg._list_frame) == 2,
          "")
    dlg.add_files(photos[1:])
    check("watermark add_files membuat daftar 3 foto",
          dlg.file_list is not None and dlg.file_list.size() == 3, "")
    check("watermark add_files judul pratinjau foto 1 dari 3",
          "foto 1 dari 3" in dlg.pv.cget("text"), dlg.pv.cget("text"))
    check("watermark add_files label jumlah 3 foto",
          dlg.count_var.get().startswith("3 foto dipilih."),
          dlg.count_var.get()[:20])
    dlg.destroy()

    dlg = resize_dialog.ResizeDialog(root, photos[:1], kind="image")
    dlg.deiconify()
    dlg.update_idletasks()
    dlg.update()
    dlg.add_files(photos[1:])
    check("resize add_files label 3 file dipilih",
          dlg.info_label.cget("text") == "3 file dipilih.",
          dlg.info_label.cget("text"))
    dlg.destroy()

    dlg = pdf_tools.PdfToImagesDialog(root, [pdf])
    dlg.deiconify()
    dlg.update_idletasks()
    dlg.update()
    pdf2 = make_pdf(os.path.join(WORK, "dok2.pdf"))
    pdf3 = make_pdf(os.path.join(WORK, "dok3.pdf"))
    dlg.add_files([pdf2, pdf3])
    check("pdf-to-images add_files label 3 file PDF",
          dlg.info_label.cget("text") == "3 file PDF dipilih.",
          dlg.info_label.cget("text"))
    dlg.destroy()

    dlg = pdf_tools.ImagesToPdfDialog(root, photos[:1])
    dlg.deiconify()
    dlg.update_idletasks()
    dlg.update()
    dlg.add_files(photos[1:])
    check("images-to-pdf add_files listbox 3",
          dlg.listbox.size() == 3, "")
    dlg.destroy()

    print("\n== _poll_ipc menggabungkan kiriman ke dialog terbuka ==")
    import convtool as convtool_main
    role, inbox = single_instance.claim("exif", photos[:1])
    check("smoke claim primary", role == "primary", role)
    convtool_main._IPC_INBOX = inbox
    dlg = exif_editor.ExifEditorDialog(root, photos[:1])
    dlg.deiconify()
    dlg.update_idletasks()
    dlg.update()
    convtool_main._ACTIVE["verb"] = "exif"
    convtool_main._ACTIVE["dialog"] = dlg
    inbox.put(("exif", photos[1:]))
    inbox.put(("watermark-klasik", photos[1:]))
    convtool_main._poll_ipc(root)
    dlg.update_idletasks()
    check("poll_ipc gabung kiriman verb sama ke daftar",
          dlg.file_list is not None and dlg.file_list.size() == 3, "")
    check("poll_ipc kiriman verb beda antre pending",
          len(convtool_main._PENDING) == 1
          and convtool_main._PENDING[0][0] == "watermark-klasik",
          str(convtool_main._PENDING))
    convtool_main._ACTIVE["verb"] = None
    convtool_main._ACTIVE["dialog"] = None
    convtool_main._PENDING.clear()
    convtool_main._IPC_INBOX = None
    dlg.destroy()

    root.destroy()
    print("\n==================================")
    print("LOLOS: %d   GAGAL: %d" % (PASSES[0], len(FAILURES)))
    if FAILURES:
        print("Yang gagal:", ", ".join(FAILURES))
        return 1
    print("SEMUA UJI GUI LOLOS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
