# exif_editor.py — Dialog EXIF Editor ConvTool.
#
# SATU frame untuk banyak foto: daftar foto di atas; klik foto untuk
# mengeditnya. Edit tiap foto disimpan sementara (pending) saat pindah
# foto, jadi tidak hilang. "Simpan" menyimpan foto yang sedang
# dibuka; "Simpan Semua" menyimpan semua foto yang sudah diedit.
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
#
# Responsif: isi dialog di dalam ScrollableFrame (ui_common) sehingga
# di layar kecil isi bisa di-scroll dan tombol bawah selalu terlihat.

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
from ui_common import ScrollableFrame

MAP_ZOOM = 15
MAP_W, MAP_H = 360, 240

# Tag yang bisa diedit lewat dobel-klik pada tabel. Orientation SENGAJA
# tidak ada: hasil simpan selalu ditegakkan (exif_transpose) sehingga
# Orientation harus tetap 1.
EDITABLE_TAGS = {"Make", "Model", "ImageDescription", "Artist",
                 "Copyright", "Software", "XResolution", "YResolution"}


class ExifEditorDialog(tk.Toplevel):
    def __init__(self, parent, paths):
        super().__init__(parent)
        if isinstance(paths, str):
            paths = [paths]
        self.files = list(paths)
        self._current = 0
        self._pending = {}  # path -> {"date","time","lat","lon","edits"}
        self._dirty = set()
        self._loading = False  # True saat form diisi dari data (bukan ketikan)
        self._map_gen = 0
        self.path = self.files[0] if self.files else ""
        self.title("Edit EXIF")
        self.resizable(True, True)
        # transient HANYA bila induk terlihat (lihat resize_dialog).
        if parent is not None and parent.winfo_viewable():
            self.transient(parent)
        self.grab_set()
        self.info = {}
        self.map_photo = None
        self.map_lat = None
        self.map_lon = None

        # ---- daftar foto: SELALU di atas (di luar area scroll), supaya
        # posisinya tetap walau foto lain masuk belakangan lewat
        # single-instance. Dulu daftar dibuat hanya bila >1 foto, dan
        # bila dibuat belakangan dari add_files ia ter-pack PALING
        # BAWAH, di bawah tombol (screenshot Rif 19 Nov 09:01).
        self._create_file_list()

        # ---- isi (bisa di-scroll di layar kecil) + tombol tetap di bawah
        body = ScrollableFrame(self)
        body.pack(fill="both", expand=True)
        self._body = body
        inner = body.inner

        main = ttk.Frame(inner)
        main.pack(fill="both", expand=True, padx=12, pady=10)

        # ---- kiri: pratinjau foto
        left = ttk.Frame(main)
        left.pack(side="left", anchor="n", padx=(0, 12))
        self.preview_label = ttk.Label(left, text="")
        self.preview_label.pack()
        self.filename_label = ttk.Label(left, text="", wraplength=340)
        self.filename_label.pack(pady=(4, 0))

        # ---- kanan: form
        right = ttk.Frame(main)
        right.pack(side="left", anchor="n", fill="y")

        ttk.Label(right, text="Tanggal & Jam (DateTimeOriginal)",
                  font=("", 10, "bold")).pack(anchor="w")
        dt_row = ttk.Frame(right)
        dt_row.pack(fill="x", pady=(2, 6))
        self.date_picker = DatePickerEntry(dt_row, "")
        self.date_picker.pack(side="left")
        ttk.Label(dt_row, text=" ").pack(side="left")
        self.time_picker = TimePickerEntry(dt_row, "")
        self.time_picker.pack(side="left")

        ttk.Label(right, text="GPS (latitude, longitude)",
                  font=("", 10, "bold")).pack(anchor="w")
        gps_row = ttk.Frame(right)
        gps_row.pack(fill="x", pady=(2, 6))
        self.lat_var = tk.StringVar(value="")
        self.lon_var = tk.StringVar(value="")
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

        self.camera_label = ttk.Label(right, text="", wraplength=360)
        self.camera_label.pack(anchor="w", pady=(8, 0))

        # ---- bawah: daftar tag EXIF lain (dobel-klik nilai untuk edit)
        ttk.Label(inner, text="Tag EXIF lain "
                              "(dobel-klik nilai untuk mengedit)",
                  font=("", 10, "bold")).pack(anchor="w", padx=12)
        cols = ("Tag", "Nilai")
        self.tree = ttk.Treeview(inner, columns=cols, show="headings",
                                 height=7)
        self.tree.heading("Tag", text="Tag")
        self.tree.heading("Nilai", text="Nilai")
        self.tree.column("Tag", width=180)
        self.tree.column("Nilai", width=480)
        self.tree.pack(fill="x", padx=12, pady=(2, 6))
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.edits = {}
        ttk.Label(inner, text="Orientation selalu 1 — foto hasil simpan "
                              "sudah ditegakkan.",
                  foreground="#555555").pack(anchor="w", padx=12)

        # ---- tombol: selalu terlihat (di luar area scroll)
        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=12, pady=(6, 12))
        ttk.Button(btns, text="Simpan",
                   command=self._save, default="active").pack(
                       side="right", padx=4)
        ttk.Button(btns, text="Simpan Semua",
                   command=self._save_all).pack(side="right", padx=4)
        ttk.Button(btns, text="Batal", command=self.destroy).pack(
            side="right", padx=4)
        self.bind("<Escape>", lambda e: self.destroy())

        # Perubahan apa pun pada form menandai foto sedang dibuka
        # sebagai sudah diedit (kecuali saat form diisi program).
        for var in (self.lat_var, self.lon_var, self.date_picker.var,
                    self.time_picker.hour_var, self.time_picker.min_var):
            var.trace_add("write", lambda *a: self._mark_dirty())

        # Hasil thread latar dikirim lewat ANTREAN (queue), bukan
        # widget.after() dari thread — after() dari thread lain rawan
        # hilang (race di Tcl) sehingga peta/alamat bisa stuck di
        # "Memuat..." tanpa pernah tampil (lihat watermark_dialog).
        self._result_queue = queue.Queue()
        self._poll_results()

        if self.files:
            self._load_photo(0)
        # Batas tinggi isi 82% layar (sisanya tombol + tepi); lebar
        # dan tinggi jendela juga dibatasi agar muat di layar kecil.
        body.fit_to_window()

    # ------------------------------------------------------------- antrean

    def _poll_results(self):
        """Periksa antrean hasil thread latar. Hanya main thread yang
        menyentuh widget — pola ini yang aman di tkinter."""
        try:
            while True:
                item = self._result_queue.get_nowait()
                if item[0] == "map":
                    self._apply_map(item[1], item[2])
                elif item[0] == "addr":
                    self._apply_addr(item[1], item[2])
        except queue.Empty:
            pass
        except Exception:
            pass
        try:
            self.after(200, self._poll_results)
        except Exception:
            pass

    # ------------------------------------------------- ganti foto & pending

    def _create_file_list(self):
        """Buat daftar foto di ATAS dialog (di luar area scroll).
        Dipanggil sekali saat init — selalu, bahkan untuk 1 foto —
        supaya posisinya tidak pernah pindah saat foto lain masuk."""
        list_frame = ttk.Frame(self)
        list_frame.pack(fill="x", padx=12, pady=(10, 0))
        self._list_frame = list_frame
        ttk.Label(list_frame, text="Foto:",
                  font=("", 10, "bold")).pack(side="left", anchor="n")
        self.file_list = tk.Listbox(
            list_frame, height=min(max(len(self.files), 1), 5),
            exportselection=False)
        for f in self.files:
            self.file_list.insert("end", os.path.basename(f))
        self.file_list.pack(side="left", fill="x", expand=True,
                            padx=(6, 0))
        scroll = ttk.Scrollbar(list_frame, orient="vertical",
                               command=self.file_list.yview)
        self.file_list.configure(yscrollcommand=scroll.set)
        scroll.pack(side="left", fill="y")
        self.file_list.bind("<<ListboxSelect>>", self._on_select_file)
        self.file_list.selection_set(self._current)

    def add_files(self, paths):
        """Tambah foto ke dialog yang sedang terbuka (single-instance:
        proses lain meneruskan file-nya ke sini). Daftar sudah ada di
        atas sejak init — di sini hanya menambah baris. Edit foto yang
        sedang dibuka tidak terganggu."""
        new = [os.path.abspath(p) for p in paths
               if os.path.isfile(p) and os.path.abspath(p) not in
               [os.path.abspath(f) for f in self.files]]
        if not new:
            return
        self.files.extend(new)
        for f in new:
            self.file_list.insert("end", os.path.basename(f))
        self.file_list.configure(height=min(len(self.files), 5))
        self.title("Edit EXIF — Foto %d dari %d"
                   % (self._current + 1, len(self.files)))
        try:
            from ui_common import fit_to_screen
            fit_to_screen(self)
        except Exception:
            pass

    def _pending_for(self, path):
        """Nilai edit sementara untuk satu foto (dibuat dari EXIF bila
        foto itu belum pernah diedit di dialog ini)."""
        p = self._pending.get(path)
        if p is None:
            info = core.read_exif(path)
            dt = core.parse_exif_datetime(info["datetime"])
            p = {
                "date": dt.strftime("%Y-%m-%d") if dt else "",
                "time": dt.strftime("%H:%M") if dt else "",
                "lat": ("%.6f" % info["lat"])
                       if info["lat"] is not None else "",
                "lon": ("%.6f" % info["lon"])
                       if info["lon"] is not None else "",
                "edits": {},
            }
            self._pending[path] = p
        return p

    def _store_pending(self):
        """Simpan isi form saat ini sebagai edit sementara foto yang
        sedang dibuka (dipanggil sebelum pindah foto / sebelum simpan)."""
        if not self.path:
            return
        p = self._pending_for(self.path)
        p["date"] = self.date_picker.get()
        p["time"] = self.time_picker.get()
        p["lat"] = self.lat_var.get().strip()
        p["lon"] = self.lon_var.get().strip()
        p["edits"] = dict(self.edits)

    def _mark_dirty(self):
        if not self._loading and self.path:
            self._dirty.add(self.path)

    def _on_select_file(self, _event=None):
        if not hasattr(self, "file_list"):
            return
        sel = self.file_list.curselection()
        if not sel or sel[0] == self._current:
            return
        self._store_pending()
        self._load_photo(sel[0])

    def _load_photo(self, index):
        """Muat foto ke-index ke seluruh widget (form, pratinjau, peta,
        tabel tag). Edit sementara foto itu (bila ada) dipakai lagi."""
        self._current = index
        self.path = self.files[index]
        self.info = core.read_exif(self.path)
        p = self._pending_for(self.path)
        self.title("Edit EXIF — Foto %d dari %d"
                   % (index + 1, len(self.files)))
        self._loading = True
        try:
            try:
                img = Image.open(self.path)
                img.thumbnail((360, 360))
                self.photo = ImageTk.PhotoImage(img)
                self.preview_label.configure(image=self.photo, text="")
            except Exception as exc:
                self.photo = None
                self.preview_label.configure(
                    image="", text="Pratinjau gagal: %s" % exc)
            self.filename_label.configure(
                text=os.path.basename(self.path))
            self.date_picker.set(p["date"])
            self.time_picker.set(p["time"])
            self.lat_var.set(p["lat"])
            self.lon_var.set(p["lon"])
            cam = []
            if self.info["make"]:
                cam.append(self.info["make"])
            if self.info["model"]:
                cam.append(self.info["model"])
            self.camera_label.configure(
                text="Kamera: %s" % (" ".join(cam) or "-"))
            self.edits = dict(p["edits"])
            for row in self.tree.get_children():
                self.tree.delete(row)
            for name, value in self.info["tags"]:
                if name in self.edits:
                    value = self.edits[name]
                self.tree.insert("", "end", values=(name, value))
            # Peta: muat ulang bila foto ini ber-GPS valid, kosongkan
            # bila tidak (tanpa popup peringatan saat pindah foto).
            self.map_photo = None
            self.map_lat = self.info["lat"]
            self.map_lon = self.info["lon"]
            if self._parse_latlon()[0] is not None:
                self._load_map()
            else:
                self.map_label.configure(image="", text="")
                self.addr_var.set("")
        finally:
            self._loading = False

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
        self._map_gen += 1
        gen = self._map_gen
        threading.Thread(target=self._load_map_bg, args=(gen, lat, lon),
                         daemon=True).start()

    def _load_map_bg(self, gen, lat, lon):
        # Peta diterapkan SEGERA setelah tile siap; alamat dimuat
        # terpisah sesudahnya (sebelumnya alamat ditunggu dulu sehingga
        # peta terasa "gagal" padahal tile sudah siap).
        try:
            img, _drawn = core.stitch_map(lat, lon, MAP_W, MAP_H, "road")
            self._result_queue.put(("map", gen, img))
        except Exception:
            self._result_queue.put(("map", gen, None))
        try:
            addr = core.reverse_geocode(lat, lon)
        except Exception:
            addr = None
        self._result_queue.put(("addr", gen, addr))

    def _apply_map(self, gen, img):
        if gen != self._map_gen:
            return  # hasil peta foto lama, sudah pindah foto
        if img is None:
            self.map_label.configure(
                text="Peta tidak dapat ditampilkan (offline?).")
            self.map_photo = None
            return
        try:
            self.map_photo = ImageTk.PhotoImage(img)
            self.map_label.configure(image=self.map_photo, text="")
        except Exception:
            self.map_label.configure(
                text="Peta tidak dapat ditampilkan (offline?).")

    def _apply_addr(self, gen, addr):
        if gen != self._map_gen:
            return
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
            self._mark_dirty()

        def cancel(_e=None):
            entry.destroy()

        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)
        entry.bind("<Escape>", cancel)

    # ------------------------------------------------------------- simpan

    def _save_values(self, path, date_str, time_str, lat_str, lon_str,
                     edits):
        """Tulis salinan _exifedit untuk satu foto dari nilai yang
        diberikan (bukan dari form). Mengembalikan path hasil.
        ValueError = nilai tidak valid (pesan untuk messagebox)."""
        dt = None
        if date_str or time_str:
            try:
                dt = datetime.strptime(
                    "%s %s" % (date_str or "2000-01-01",
                               time_str or "00:00"),
                    "%Y-%m-%d %H:%M")
            except ValueError:
                raise ValueError(
                    "Tanggal tidak valid: pilih tanggal dari kalender "
                    "dan jam yang valid.")
        lat = lon = None
        if lat_str or lon_str:
            try:
                lat = float(lat_str.replace(",", "."))
                lon = float(lon_str.replace(",", "."))
            except ValueError:
                lat = lon = None
            if lat is None or not (-90 <= lat <= 90
                                   and -180 <= lon <= 180):
                raise ValueError(
                    "GPS tidak valid: latitude -90..90, longitude "
                    "-180..180 (desimal).")
        folder = os.path.dirname(path)
        stem = os.path.splitext(os.path.basename(path))[0]
        ext = os.path.splitext(path)[1] or ".jpg"
        dst = os.path.join(folder, stem + "_exifedit" + ext)
        core.save_image_with_exif(path, dst,
                                  new_datetime=dt,
                                  new_lat=lat, new_lon=lon,
                                  extra_tags=edits or None)
        return dst

    def _save(self):
        """Simpan foto yang sedang dibuka (tetap di dialog supaya bisa
        lanjut ke foto berikutnya)."""
        self._store_pending()
        p = self._pending_for(self.path)
        try:
            dst = self._save_values(self.path, p["date"], p["time"],
                                    p["lat"], p["lon"], p["edits"])
        except ValueError as exc:
            messagebox.showwarning("Nilai tidak valid", str(exc),
                                   parent=self)
            return
        except Exception as exc:
            messagebox.showerror("Gagal menyimpan", str(exc), parent=self)
            return
        self._dirty.discard(self.path)
        messagebox.showinfo("Tersimpan",
                            "Salinan tersimpan sebagai:\n%s" % dst,
                            parent=self)

    def _save_all(self):
        """Simpan semua foto yang sudah diedit (yang ada di daftar
        dirty). Foto yang tidak diedit dilewati."""
        self._store_pending()
        if not self._dirty:
            messagebox.showinfo("Tidak ada yang disimpan",
                                "Belum ada foto yang diedit.",
                                parent=self)
            return
        ok, fail = 0, []
        for path in list(self.files):
            if path not in self._dirty:
                continue
            p = self._pending_for(path)
            try:
                self._save_values(path, p["date"], p["time"], p["lat"],
                                  p["lon"], p["edits"])
                self._dirty.discard(path)
                ok += 1
            except Exception as exc:
                fail.append("%s: %s" % (os.path.basename(path), exc))
        if fail:
            messagebox.showwarning(
                "Selesai dengan %d gagal" % len(fail),
                "Berhasil: %d foto.\nGagal:\n%s"
                % (ok, "\n".join(fail)), parent=self)
        else:
            messagebox.showinfo("Tersimpan",
                                "%d foto tersimpan sebagai salinan "
                                "(_exifedit)." % ok, parent=self)


def run_exif_editor(parent, paths):
    """paths: satu path (str) atau daftar path. Satu dialog untuk
    semua foto."""
    if isinstance(paths, str):
        paths = [paths]
    dlg = ExifEditorDialog(parent, paths)
    dlg.deiconify()
    dlg.lift()
    dlg.focus_force()
    return dlg
