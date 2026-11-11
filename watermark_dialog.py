# watermark_dialog.py — Dialog Watermark Klasik / Job Timestamp.
#
# Data per file: GPS + tanggal/jam diambil dari EXIF foto bila ada;
# bila GPS tidak ada, pakai lat/lon manual dari dialog ini.
# Alamat diisi otomatis lewat reverse-geocode Nominatim (bisa diedit).
# Tanggal/jam memakai datepicker kalender + time picker.
# Pratinjau LANGSUNG di samping form (kolom kanan), diperbarui otomatis
# tiap isian berubah (debounce 600 md, render di thread latar).
# Terapkan menulis file BARU (_klasik / _job) untuk semua file.

import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from PIL import Image, ImageOps, ImageTk

import core
import watermark
from pickers import DatePickerEntry, TimePickerEntry


class WatermarkDialog(tk.Toplevel):
    def __init__(self, parent, files, style):
        super().__init__(parent)
        self.files = list(files)
        self.style = style
        self.title("Watermark %s" % ("Klasik" if style == "klasik"
                                     else "Job Timestamp"))
        self.resizable(False, False)
        # transient HANYA bila induk terlihat (lihat resize_dialog).
        if parent is not None and parent.winfo_viewable():
            self.transient(parent)
        self.grab_set()

        # Data awal dari file pertama.
        first = core.read_exif(self.files[0]) if self.files else {}
        dt = core.parse_exif_datetime(first.get("datetime")) \
            or datetime.now()

        # ---- dua kolom: form (kiri) + pratinjau langsung (kanan)
        main = ttk.Frame(self)
        main.pack(fill="both", expand=True)
        left = ttk.Frame(main)
        left.pack(side="left", anchor="n", fill="y", padx=(12, 0),
                  pady=(10, 12))
        right = ttk.Frame(main)
        right.pack(side="left", anchor="n", fill="both", expand=True,
                   padx=(12, 12), pady=(10, 12))
        pv = ttk.LabelFrame(right, text="Pratinjau langsung")
        pv.pack(fill="both", expand=True)
        # width (satuan karakter) memberi kolom pratinjau lebar awal
        # yang cukup (~420 px) — tanpa ini kolom hanya selebar teks
        # "Me-render pratinjau..." dan gambar landscape terpotong.
        self.preview_label = ttk.Label(pv, text="Me-render pratinjau...",
                                       wraplength=420, width=60,
                                       anchor="center")
        self.preview_label.pack(padx=8, pady=8)
        self._preview_gen = 0
        self._preview_job = None
        self._preview_photo = None
        # Hasil thread latar dikirim lewat ANTREAN (queue), bukan
        # widget.after() dari thread — after() dari thread lain rawan
        # hilang (race di Tcl) sehingga pratinjau/alamat bisa stuck
        # di "Me-render..." / "Memuat alamat..." tanpa pernah tampil.
        # Main thread memeriksa antrean berkala (_poll_results).
        self._result_queue = queue.Queue()
        self._poll_results()

        ttk.Label(left, text="Watermark %s" % (
            "Klasik (GPS Map Camera)" if style == "klasik"
            else "Job Timestamp"), font=("", 14, "bold"),
            foreground="#1a5fb4").pack(anchor="w", pady=(0, 2))
        ttk.Label(left, text="%d foto dipilih. GPS & tanggal diambil "
                             "dari EXIF tiap foto bila ada; bila tidak "
                             "ada, dipakai isian di bawah ini."
                  % len(self.files), wraplength=500).pack(
                      anchor="w", pady=(0, 6))

        form = ttk.Frame(left)
        form.pack(fill="x", pady=4)
        ttk.Label(form, text="Latitude:").grid(row=0, column=0, sticky="w",
                                               pady=2)
        self.lat_var = tk.StringVar(
            value=("%.6f" % first.get("lat")) if first.get("lat") is not None
            else "")
        ttk.Entry(form, textvariable=self.lat_var, width=16).grid(
            row=0, column=1, sticky="w", pady=2)
        ttk.Label(form, text="Longitude:").grid(row=1, column=0, sticky="w",
                                                pady=2)
        self.lon_var = tk.StringVar(
            value=("%.6f" % first.get("lon")) if first.get("lon") is not None
            else "")
        ttk.Entry(form, textvariable=self.lon_var, width=16).grid(
            row=1, column=1, sticky="w", pady=2)
        ttk.Button(form, text="Muat alamat",
                   command=self._load_address).grid(
                       row=0, column=2, rowspan=2, padx=8)
        ttk.Label(form, text="Tanggal:").grid(row=2, column=0, sticky="w",
                                              pady=2)
        self.date_picker = DatePickerEntry(form, dt.strftime("%Y-%m-%d"))
        self.date_picker.grid(row=2, column=1, sticky="w", pady=2)
        ttk.Label(form, text="Jam:").grid(row=3, column=0, sticky="w",
                                          pady=2)
        self.time_picker = TimePickerEntry(form, dt.strftime("%H:%M"))
        self.time_picker.grid(row=3, column=1, sticky="w", pady=2)
        ttk.Label(form, text="Tempat:").grid(row=4, column=0, sticky="nw",
                                             pady=2)
        self.place_var = tk.StringVar(value="")
        ttk.Entry(form, textvariable=self.place_var, width=52).grid(
            row=4, column=1, columnspan=2, sticky="w", pady=2)
        ttk.Label(form, text="Alamat:").grid(row=5, column=0, sticky="nw",
                                             pady=2)
        self.addr_var = tk.StringVar(value="")
        ttk.Entry(form, textvariable=self.addr_var, width=52).grid(
            row=5, column=1, columnspan=2, sticky="w", pady=2)
        ttk.Label(form, text="Cuaca (Klasik):").grid(
            row=6, column=0, sticky="w", pady=2)
        self.weather_var = tk.StringVar(value="")
        ttk.Entry(form, textvariable=self.weather_var, width=52).grid(
            row=6, column=1, columnspan=2, sticky="w", pady=2)
        ttk.Label(form, text="(opsional, mis. Cerah 31°C)").grid(
            row=7, column=1, columnspan=2, sticky="w", pady=0)

        wframe = ttk.Frame(left)
        wframe.pack(fill="x", pady=4)
        self.show_weather_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(wframe, text="Tampilkan cuaca (Job)",
                        variable=self.show_weather_var).pack(
                            side="left", padx=2)
        ttk.Label(wframe, text="Suhu °C:").pack(side="left", padx=(8, 2))
        self.temp_var = tk.StringVar(value="28")
        ttk.Entry(wframe, textvariable=self.temp_var, width=5).pack(
            side="left")
        ttk.Label(wframe, text="Kondisi:").pack(side="left", padx=(8, 2))
        self.cond_var = tk.StringVar(value="Berawan")
        ttk.Combobox(wframe, textvariable=self.cond_var, width=16,
                     state="readonly",
                     values=["Berawan", "Sebagian berawan", "Cerah",
                             "Hujan"]).pack(side="left")

        sframe = ttk.Frame(left)
        sframe.pack(fill="x", pady=4)
        ttk.Label(sframe, text="Ukuran stempel:").pack(side="left", padx=2)
        self.scale_var = tk.IntVar(value=100)
        ttk.Scale(sframe, from_=70, to=150, orient="horizontal",
                  variable=self.scale_var, length=160).pack(side="left")
        self.scale_lbl = ttk.Label(sframe, text="100%")
        self.scale_lbl.pack(side="left", padx=6)
        self.scale_var.trace_add(
            "write",
            lambda *a: self.scale_lbl.config(
                text="%d%%" % self.scale_var.get()))

        self.status_var = tk.StringVar(value="")
        ttk.Label(left, textvariable=self.status_var, wraplength=500,
                  foreground="#333333").pack(fill="x", pady=4)

        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=(6, 0))
        ttk.Button(btns, text="Terapkan Watermark",
                   command=self._apply, default="active").pack(
                       side="right", padx=4)
        ttk.Button(btns, text="Batal", command=self.destroy).pack(
            side="right", padx=4)
        self.bind("<Escape>", lambda e: self.destroy())

        # Pratinjau langsung: tiap isian berubah -> render ulang
        # (debounce, thread latar).
        for var in (self.lat_var, self.lon_var, self.addr_var,
                    self.place_var, self.weather_var, self.temp_var,
                    self.cond_var, self.show_weather_var, self.scale_var):
            var.trace_add("write", lambda *a: self._schedule_preview())
        self.date_picker.var.trace_add(
            "write", lambda *a: self._schedule_preview())
        self.time_picker.hour_var.trace_add(
            "write", lambda *a: self._schedule_preview())
        self.time_picker.min_var.trace_add(
            "write", lambda *a: self._schedule_preview())

        if first.get("lat") is not None:
            self._load_address()
        self._schedule_preview(300)

    # ------------------------------------------------------------- data

    def _parse_latlon(self):
        try:
            lat = float(self.lat_var.get().replace(",", "."))
            lon = float(self.lon_var.get().replace(",", "."))
        except ValueError:
            return (None, None)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return (None, None)
        return (lat, lon)

    def _parse_datetime(self):
        try:
            return datetime.strptime(
                "%s %s" % (self.date_picker.get(),
                           self.time_picker.get() or "00:00"),
                "%Y-%m-%d %H:%M")
        except ValueError:
            return None

    def _load_address(self):
        lat, lon = self._parse_latlon()
        if lat is None:
            messagebox.showwarning(
                "GPS belum diisi",
                "Isi latitude dan longitude dulu.", parent=self)
            return
        self.status_var.set("Memuat alamat...")
        threading.Thread(target=self._load_address_bg, args=(lat, lon),
                         daemon=True).start()

    def _poll_results(self):
        """Periksa antrean hasil thread latar. Hanya main thread yang
        menyentuh widget — pola ini yang aman di tkinter."""
        try:
            while True:
                item = self._result_queue.get_nowait()
                kind = item[0]
                if kind == "address":
                    self._apply_address(item[1], item[2])
                elif kind == "preview":
                    self._apply_preview(item[1], item[2])
                elif kind == "preview_error":
                    self._apply_preview_error(item[1], item[2])
        except queue.Empty:
            pass
        except Exception:
            pass
        try:
            self.after(200, self._poll_results)
        except Exception:
            pass

    def _load_address_bg(self, lat, lon):
        addr, addr_dict = core.reverse_geocode_full(lat, lon)
        self._result_queue.put(("address", addr, addr_dict))

    def _apply_address(self, addr, addr_dict=None):
        if addr:
            self.addr_var.set(addr)
            # Tempat diturunkan dari data terstruktur Nominatim:
            # "Kecamatan Wonocolo, Jawa Timur, Indonesia" (kecamatan =
            # municipality, BUKAN bagian pertama/terakhir alamat).
            place = core.place_from_address(addr_dict or {})
            if place:
                self.place_var.set(place)
            else:
                # Cadangan: 3 bagian terakhir alamat.
                parts = [p.strip() for p in addr.split(",") if p.strip()]
                if len(parts) > 3:
                    self.place_var.set(", ".join(parts[-3:]))
                else:
                    self.place_var.set(addr)
            self.status_var.set("")
        else:
            self.status_var.set("Alamat tidak dapat dimuat (offline?).")

    def _per_file_data(self, path):
        """(lat, lon, dt, address, place, weather_text, temp_c, cond,
        show_weather, scale) untuk satu file: EXIF dulu, lalu isian
        dialog sebagai cadangan."""
        info = core.read_exif(path)
        lat = info["lat"]
        lon = info["lon"]
        dlat, dlon = self._parse_latlon()
        if lat is None:
            lat = dlat
        if lon is None:
            lon = dlon
        dt = core.parse_exif_datetime(info["datetime"])
        if dt is None:
            dt = self._parse_datetime() or datetime.now()
        try:
            temp_c = float(self.temp_var.get().replace(",", "."))
        except ValueError:
            temp_c = 28
        cond_map = {"Berawan": "cloudy", "Sebagian berawan": "partly",
                    "Cerah": "sunny", "Hujan": "rain"}
        return (lat, lon, dt, self.addr_var.get().strip(),
                self.place_var.get().strip(),
                self.weather_var.get().strip(), temp_c,
                cond_map.get(self.cond_var.get(), "cloudy"),
                bool(self.show_weather_var.get()),
                int(self.scale_var.get()))

    # -------------------------------------------------- pratinjau langsung

    def _schedule_preview(self, delay=600):
        if self._preview_job is not None:
            try:
                self.after_cancel(self._preview_job)
            except Exception:
                pass
        try:
            self._preview_job = self.after(delay, self._render_preview)
        except Exception:
            self._preview_job = None

    def _render_preview(self):
        """Render file pertama dengan isian saat ini (thread latar);
        hasil lama yang telat datang diabaikan (generation counter)."""
        self._preview_job = None
        if not self.files:
            return
        try:
            data = self._per_file_data(self.files[0])
        except Exception:
            return
        (lat, lon, _dt, _addr, _place, _wt, _tc, _cond,
         _sw, _scale) = data
        if lat is None or lon is None:
            self.preview_label.configure(
                image="",
                text="Isi GPS (atau pilih foto ber-GPS) untuk melihat "
                     "pratinjau.")
            self._preview_photo = None
            return
        self._preview_gen += 1
        gen = self._preview_gen
        self.preview_label.configure(text="Me-render pratinjau...")
        threading.Thread(target=self._render_preview_bg,
                         args=(gen, self.files[0], data),
                         daemon=True).start()

    def _render_preview_bg(self, gen, path, data):
        (lat, lon, dt, addr, place, weather_text, temp_c, cond,
         show_weather, scale) = data
        try:
            img = Image.open(path)
            img = ImageOps.exif_transpose(img)
            # Pratinjau dirender dari salinan kecil (maks 1200 px) —
            # tampil di ~420 px, jadi render full 4000x3000 hanya
            # membuang waktu. Hasil akhir (Terapkan) tetap full-res.
            img.thumbnail((1200, 1200))
            if self.style == "klasik":
                out = watermark.render_klasik(
                    img, lat, lon, dt, addr, place=place,
                    weather_text=weather_text, s=scale / 100.0)
            else:
                out = watermark.render_job(
                    img, lat, lon, dt, addr, place=place, temp_c=temp_c,
                    cond=cond, show_weather=show_weather, s=scale / 100.0)
        except Exception as exc:
            self._result_queue.put(("preview_error", gen, str(exc)))
            return
        self._result_queue.put(("preview", gen, out))

    def _apply_preview(self, gen, out):
        if gen != self._preview_gen:
            return  # hasil lama, sudah ada render yang lebih baru
        # Skalakan ke lebar kolom SEBENARNYA (winfo_width), bukan ukuran
        # tetap 460 — jendela resizable=False tidak membesar mengikuti
        # gambar, sehingga pratinjau landscape terpotong di tepi.
        avail_w = self.preview_label.winfo_width()
        if avail_w < 100:  # belum ter-layout, pakai lebar rencana
            avail_w = 440
        avail_w = max(200, avail_w - 16)
        tw, th = core.fit_within(out.width, out.height, avail_w, 480)
        disp = out.resize((tw, th), Image.LANCZOS)
        self._preview_photo = ImageTk.PhotoImage(disp)
        self.preview_label.configure(image=self._preview_photo, text="")

    def _apply_preview_error(self, gen, msg):
        if gen != self._preview_gen:
            return
        self.preview_label.configure(image="",
                                     text="Pratinjau gagal: %s" % msg)
        self._preview_photo = None

    # ------------------------------------------------------------- aksi

    def _apply(self):
        ok, fail = 0, []
        for i, path in enumerate(self.files):
            self.status_var.set("Memproses %d/%d: %s"
                                % (i + 1, len(self.files),
                                   os.path.basename(path)))
            self.update_idletasks()
            try:
                (lat, lon, dt, addr, place, weather_text, temp_c, cond,
                 show_weather, scale) = self._per_file_data(path)
                if lat is None or lon is None:
                    raise ValueError(
                        "tidak ada GPS (EXIF kosong & manual belum diisi)")
                dst = watermark.watermark_output_path(path, self.style)
                watermark.apply_watermark(
                    path, dst, self.style, lat, lon, dt, addr,
                    place=place, weather_text=weather_text, temp_c=temp_c,
                    cond=cond, show_weather=show_weather, scale=scale)
                ok += 1
            except Exception as exc:
                fail.append("%s: %s" % (os.path.basename(path), exc))
        if fail:
            messagebox.showwarning(
                "Selesai dengan %d gagal" % len(fail),
                "Berhasil: %d foto.\nGagal:\n%s"
                % (ok, "\n".join(fail)), parent=self)
        else:
            messagebox.showinfo(
                "Selesai",
                "Watermark %s diterapkan ke %d foto."
                % (self.style, ok), parent=self)
        self.destroy()


def run_watermark_dialog(parent, files, style):
    dlg = WatermarkDialog(parent, files, style)
    dlg.deiconify()
    dlg.lift()
    dlg.focus_force()
    parent.wait_window(dlg)
