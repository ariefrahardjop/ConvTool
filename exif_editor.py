# exif_editor.py — Dialog EXIF Editor ConvTool.
#
# Menampilkan foto + panel edit:
#   - tanggal & jam (DateTimeOriginal, bisa diedit) — datepicker
#     kalender + time picker (spinbox jam/menit)
#   - GPS lat/lon (bisa diedit) + pratinjau peta kecil (tile OSM zoom 15;
#     bila offline tampilkan koordinat + tombol "Buka di OpenStreetMap")
#     — klik pada peta menggeser lat/lon ke titik yang diklik; peta
#     dimuat terpisah dari alamat agar tampil secepat tile siap
#   - alamat hasil reverse-geocode Nominatim (otomatis, thread latar)
#   - kamera make/model + daftar tag EXIF lain (dobel-klik nilai
#     untuk mengedit: Make, Model, ImageDescription, Artist,
#     Copyright, Software, XResolution, YResolution)
# Simpan = file BARU dengan akhiran _exifedit (asli tidak pernah ditimpa),
# semua EXIF lain dipertahankan. Hanya Pillow untuk baca/tulis EXIF.

import os
import queue
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

import core
from pickers import DatePickerEntry, TimePickerEntry

MAP_ZOOM = 15
MAP_W, MAP_H = 360, 240

# Tag yang bisa diedit lewat dobel-klik pada tabel. Orientation SENGAJA
# tidak ada: hasil simpan selalu ditegakkan (exif_transpose) sehingga
# Orientation harus tetap 1.
EDITABLE_TAGS = {"Make", "Model", "ImageDescription", "Artist",
                 "Copyright", "Software", "XResolution", "YResolution"}


class ExifEditorDialog(tk.Toplevel):
    def __init__(self, parent, path):
        super().__init__(parent)
        self.path = path
        self.title("Edit EXIF — %s" % os.path.basename(path))
        self.resizable(False, False)
        # transient HANYA bila induk terlihat (lihat resize_dialog).
        if parent is not None and parent.winfo_viewable():
            self.transient(parent)
        self.grab_set()
        self.info = core.read_exif(path)
        self.map_photo = None
        self.map_lat = self.info["lat"]
        self.map_lon = self.info["lon"]

        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=12, pady=10)

        # ---- kiri: pratinjau foto
        left = ttk.Frame(main)
        left.pack(side="left", anchor="n", padx=(0, 12))
        try:
            img = Image.open(path)
            img.thumbnail((360, 360))
            self.photo = ImageTk.PhotoImage(img)
            ttk.Label(left, image=self.photo).pack()
        except Exception as exc:
            ttk.Label(left, text="Pratinjau gagal: %s" % exc).pack()
        ttk.Label(left, text=os.path.basename(path),
                  wraplength=340).pack(pady=(4, 0))

        # ---- kanan: form
        right = ttk.Frame(main)
        right.pack(side="left", anchor="n", fill="y")

        ttk.Label(right, text="Tanggal & Jam (DateTimeOriginal)",
                  font=("", 10, "bold")).pack(anchor="w")
        dt_row = ttk.Frame(right)
        dt_row.pack(fill="x", pady=(2, 6))
        dt = core.parse_exif_datetime(self.info["datetime"])
        self.date_picker = DatePickerEntry(
            dt_row, dt.strftime("%Y-%m-%d") if dt else "")
        self.date_picker.pack(side="left")
        ttk.Label(dt_row, text=" ").pack(side="left")
        self.time_picker = TimePickerEntry(
            dt_row, dt.strftime("%H:%M") if dt else "")
        self.time_picker.pack(side="left")

        ttk.Label(right, text="GPS (latitude, longitude)",
                  font=("", 10, "bold")).pack(anchor="w")
        gps_row = ttk.Frame(right)
        gps_row.pack(fill="x", pady=(2, 6))
        self.lat_var = tk.StringVar(
            value=("%.6f" % self.info["lat"]) if self.info["lat"] is not None
            else "")
        self.lon_var = tk.StringVar(
            value=("%.6f" % self.info["lon"]) if self.info["lon"] is not None
            else "")
        ttk.Entry(gps_row, textvariable=self.lat_var, width=14).pack(
            side="left")
        ttk.Label(gps_row, text=", ").pack(side="left")
        ttk.Entry(gps_row, textvariable=self.lon_var, width=14).pack(
            side="left")
        ttk.Button(gps_row, text="Tampilkan Peta",
                   command=self._load_map).pack(side="left", padx=6)

        self.map_label = ttk.Label(right, text="")
        self.map_label.pack(anchor="w", pady=(0, 2))
        self.map_label.bind("<Button-1>", self._on_map_click)
        ttk.Label(right, text="Klik peta untuk memilih koordinat.",
                  foreground="#555555").pack(anchor="w", pady=(0, 2))
        self.addr_var = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.addr_var, wraplength=360,
                  foreground="#555555").pack(anchor="w", pady=(0, 4))
        ttk.Button(right, text="Buka di OpenStreetMap",
                   command=self._open_osm).pack(anchor="w")

        cam = []
        if self.info["make"]:
            cam.append(self.info["make"])
        if self.info["model"]:
            cam.append(self.info["model"])
        ttk.Label(right, text="Kamera: %s" % (" ".join(cam) or "-"),
                  wraplength=360).pack(anchor="w", pady=(8, 0))

        # ---- bawah: daftar tag EXIF lain (dobel-klik nilai untuk edit)
        ttk.Label(self, text="Tag EXIF lain "
                             "(dobel-klik nilai untuk mengedit)",
                  font=("", 10, "bold")).pack(anchor="w", padx=12)
        cols = ("Tag", "Nilai")
        self.tree = ttk.Treeview(self, columns=cols, show="headings",
                                 height=7)
        self.tree.heading("Tag", text="Tag")
        self.tree.heading("Nilai", text="Nilai")
        self.tree.column("Tag", width=180)
        self.tree.column("Nilai", width=480)
        self.tree.pack(fill="x", padx=12, pady=(2, 6))
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.edits = {}
        for name, value in self.info["tags"]:
            self.tree.insert("", "end", values=(name, value))
        ttk.Label(self, text="Orientation selalu 1 — foto hasil simpan "
                             "sudah ditegakkan.",
                  foreground="#555555").pack(anchor="w", padx=12)

        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=12, pady=(6, 12))
        ttk.Button(btns, text="Simpan sebagai salinan (_exifedit)",
                   command=self._save, default="active").pack(
                       side="right", padx=4)
        ttk.Button(btns, text="Batal", command=self.destroy).pack(
            side="right", padx=4)
        self.bind("<Escape>", lambda e: self.destroy())

        # Hasil thread latar dikirim lewat ANTREAN (queue), bukan
        # widget.after() dari thread — after() dari thread lain rawan
        # hilang (race di Tcl) sehingga peta/alamat bisa stuck di
        # "Memuat..." tanpa pernah tampil (lihat watermark_dialog).
        self._result_queue = queue.Queue()
        self._poll_results()

        if self.info["lat"] is not None and self.info["lon"] is not None:
            self._load_map()

    # ------------------------------------------------------------- antrean

    def _poll_results(self):
        """Periksa antrean hasil thread latar. Hanya main thread yang
        menyentuh widget — pola ini yang aman di tkinter."""
        try:
            while True:
                item = self._result_queue.get_nowait()
                if item[0] == "map":
                    self._apply_map(item[1])
                elif item[0] == "addr":
                    self._apply_addr(item[1])
        except queue.Empty:
            pass
        except Exception:
            pass
        try:
            self.after(200, self._poll_results)
        except Exception:
            pass

    # ------------------------------------------------------------- peta

    def _parse_latlon(self):
        try:
            lat = float(self.lat_var.get().replace(",", "."))
            lon = float(self.lon_var.get().replace(",", "."))
        except ValueError:
            return (None, None)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return (None, None)
        return (lat, lon)

    def _load_map(self):
        lat, lon = self._parse_latlon()
        if lat is None:
            messagebox.showwarning(
                "GPS belum diisi",
                "Isi latitude dan longitude dulu (desimal, mis. "
                "-7.276971, 112.747416).", parent=self)
            return
        self.map_lat, self.map_lon = lat, lon
        self.map_label.configure(text="Memuat peta...")
        self.addr_var.set("Memuat alamat...")
        threading.Thread(target=self._load_map_bg, args=(lat, lon),
                         daemon=True).start()

    def _load_map_bg(self, lat, lon):
        # Peta diterapkan SEGERA setelah tile siap; alamat dimuat
        # terpisah sesudahnya (sebelumnya alamat ditunggu dulu sehingga
        # peta terasa "gagal" padahal tile sudah siap).
        img, _drawn = core.stitch_map(lat, lon, MAP_W, MAP_H, "road")
        self._result_queue.put(("map", img))
        addr = core.reverse_geocode(lat, lon)
        self._result_queue.put(("addr", addr))

    def _apply_map(self, img):
        try:
            self.map_photo = ImageTk.PhotoImage(img)
            self.map_label.configure(image=self.map_photo, text="")
        except Exception:
            self.map_label.configure(
                text="Peta tidak dapat ditampilkan (offline?).")

    def _apply_addr(self, addr):
        self.addr_var.set(addr if addr else
                          "Alamat tidak dapat dimuat (offline?).")

    def _on_map_click(self, event):
        """Klik pada peta -> geser lat/lon ke titik yang diklik
        (kebalikan pemetaan tile, zoom 15 — sama seperti Galeriku)."""
        if self.map_photo is None or self.map_lat is None:
            return
        lat, lon = core.map_pixel_to_latlon(
            self.map_lat, self.map_lon, MAP_W, MAP_H,
            event.x, event.y, MAP_ZOOM)
        self.lat_var.set("%.6f" % lat)
        self.lon_var.set("%.6f" % lon)
        self._load_map()

    def _open_osm(self):
        lat, lon = self._parse_latlon()
        if lat is None:
            messagebox.showwarning("GPS belum diisi",
                                   "Isi latitude dan longitude dulu.",
                                   parent=self)
            return
        webbrowser.open(
            "https://www.openstreetmap.org/?mlat=%.6f&mlon=%.6f#map=17/"
            "%.6f/%.6f" % (lat, lon, lat, lon))

    # ------------------------------------------------------------- tag edit

    def _on_tree_double_click(self, event):
        """Dobel-klik sel Nilai -> edit langsung di tempat (hanya tag
        di EDITABLE_TAGS). Enter/klik luar = simpan, Escape = batal."""
        item = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not item or col != "#2":
            return
        name, value = self.tree.item(item, "values")
        if name not in EDITABLE_TAGS:
            return
        bbox = self.tree.bbox(item, column=col)
        if not bbox:
            return
        x, y, w, h = bbox
        var = tk.StringVar(value=value)
        entry = ttk.Entry(self.tree, textvariable=var)
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()
        entry.select_range(0, "end")

        def commit(_e=None):
            new = var.get().strip()
            entry.destroy()
            if name in ("XResolution", "YResolution"):
                try:
                    f = float(new.replace(",", "."))
                    if f <= 0:
                        raise ValueError
                    new = ("%.2f" % f).rstrip("0").rstrip(".")
                except ValueError:
                    messagebox.showwarning(
                        "Nilai tidak valid",
                        "%s harus angka > 0." % name, parent=self)
                    return
            self.tree.item(item, values=(name, new))
            self.edits[name] = new

        def cancel(_e=None):
            entry.destroy()

        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)
        entry.bind("<Escape>", cancel)

    # ------------------------------------------------------------- simpan

    def _save(self):
        dt = None
        d = self.date_picker.get()
        t = self.time_picker.get()
        if d or t:
            try:
                dt = datetime.strptime(
                    "%s %s" % (d or "2000-01-01", t or "00:00"),
                    "%Y-%m-%d %H:%M")
            except ValueError:
                messagebox.showwarning(
                    "Tanggal tidak valid",
                    "Pilih tanggal dari kalender dan jam yang valid.",
                    parent=self)
                return
        lat, lon = self._parse_latlon()
        if (self.lat_var.get().strip() or self.lon_var.get().strip()) \
                and lat is None:
            messagebox.showwarning(
                "GPS tidak valid",
                "Latitude -90..90, longitude -180..180 (desimal).",
                parent=self)
            return
        folder = os.path.dirname(self.path)
        stem = os.path.splitext(os.path.basename(self.path))[0]
        ext = os.path.splitext(self.path)[1] or ".jpg"
        dst = os.path.join(folder, stem + "_exifedit" + ext)
        try:
            core.save_image_with_exif(self.path, dst,
                                      new_datetime=dt,
                                      new_lat=lat, new_lon=lon,
                                      extra_tags=self.edits or None)
        except Exception as exc:
            messagebox.showerror("Gagal menyimpan", str(exc), parent=self)
            return
        messagebox.showinfo("Tersimpan",
                            "Salinan tersimpan sebagai:\n%s" % dst,
                            parent=self)
        self.destroy()


def run_exif_editor(parent, path):
    dlg = ExifEditorDialog(parent, path)
    dlg.deiconify()
    dlg.lift()
    dlg.focus_force()
    parent.wait_window(dlg)
