# ui_common.py — Widget tkinter bersama untuk dialog-dialog ConvTool.
#
# PresetFrame: pilihan ukuran seperti dialog "Image Resizer for Windows":
# radio Small / Medium / Large / Phone / Custom, lalu baris Custom berisi
# dropdown mode (Fit/Fill/Stretch), kolom lebar x tinggi, dan dropdown
# satuan (Pixels/Percent). Bila preset dipilih (bukan Custom), kolom
# Custom dinonaktifkan.

import tkinter as tk
from tkinter import ttk

import core


def fit_size_for_screen(req_w, req_h, scr_w, scr_h, max_w_frac=0.96,
                        max_h_frac=0.94):
    """(lebar, tinggi) jendela yang muat di layar — tidak pernah
    melebihi pecahan layar yang diberikan."""
    return (max(200, min(req_w, int(scr_w * max_w_frac))),
            max(200, min(req_h, int(scr_h * max_h_frac))))


def fit_to_screen(window, max_w_frac=0.96, max_h_frac=0.94):
    """Batasi ukuran jendela dialog agar muat di layar (dipanggil
    setelah semua widget terpasang). Tanpa ini, dialog yang isinya
    tinggi (watermark, EXIF editor) bisa melebihi layar kecil dan
    tombol bawahnya tertutup / tidak bisa diklik."""
    window.update_idletasks()
    w, h = fit_size_for_screen(
        window.winfo_reqwidth(), window.winfo_reqheight(),
        window.winfo_screenwidth(), window.winfo_screenheight(),
        max_w_frac, max_h_frac)
    window.geometry("%dx%d" % (w, h))


class ScrollableFrame(ttk.Frame):
    """Wadah isi dialog yang bisa di-scroll vertikal bila konten lebih
    tinggi dari ruang yang tersedia.

    Pola pakai: isi dialog dipack ke ``body.inner``; baris tombol
    dipack ke dialognya langsung (DI LUAR body) sehingga tombol
    selalu terlihat — isi yang di-scroll, tombol tidak ikut bergeser.
    Di layar besar, body menampilkan seluruh isi tanpa scrollbar
    yang mengganggu (scrollbar tetap ada tapi tidak aktif).

    Scroll mouse wheel hanya aktif saat kursor di atas frame ini,
    supaya tidak merebut scroll dialog lain."""

    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.vbar = ttk.Scrollbar(self, orient="vertical",
                                  command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="right", fill="y")
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner,
                                              anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind(
            "<Enter>",
            lambda _e: self.canvas.bind_all(
                "<MouseWheel>", self._on_mousewheel))
        self.canvas.bind(
            "<Leave>",
            lambda _e: self.canvas.unbind_all("<MouseWheel>"))

    def _on_inner_configure(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        # Lebar isi mengikuti lebar canvas (tidak ada scroll horizontal).
        self.canvas.itemconfigure(self._win, width=event.width)

    def _on_mousewheel(self, event):
        # Windows: delta kelipatan 120 (negatif = ke bawah).
        try:
            steps = -int(event.delta / 120)
        except Exception:
            steps = 0
        if steps:
            self.canvas.yview_scroll(steps, "units")

    def fit_height(self, max_h):
        """Batasi tinggi canvas: setinggi isi bila isi pendek, atau
        max_h bila isi panjang (sisanya di-scroll). Dipanggil setelah
        isi terpasang."""
        self.update_idletasks()
        need = self.inner.winfo_reqheight()
        self.canvas.configure(height=max(100, min(need, max_h)))

    def fit_to_window(self, max_frac=0.92):
        """Batasi tinggi canvas supaya SELURUH jendela (isi + tombol +
        judul) muat di layar: canvas mendapat sisa ruang setelah
        semua isi tetap di luarnya. Dipanggil di akhir __init__
        dialog, setelah semua widget terpasang. Tanpa ini, canvas
        yang dipatok 82% layar ditambah tombol/daftar di luarnya
        bisa melebihi layar dan tombol bawah tertutup (kasus EXIF
        Editor di layar 1024x600: tombol di y=574 dari jendela 564).

        Tinggi isi tetap dihitung dari tinggi total yang diminta
        jendela dikurangi tinggi body ini — jadi padding pack ikut
        terhitung, bukan hanya tinggi widgetnya."""
        top = self.winfo_toplevel()
        top.update_idletasks()
        scr_h = top.winfo_screenheight()
        other = top.winfo_reqheight() - self.winfo_reqheight()
        self.fit_height(int(scr_h * max_frac) - other)
        fit_to_screen(top, max_h_frac=max_frac)


class PresetFrame(ttk.LabelFrame):
    """Frame 'Select a size.' — mengembalikan (lebar, tinggi) piksel
    atau None bila Custom belum valid. Untuk Percent, lebar/tinggi
    dihitung terhadap ukuran referensi yang diberikan (ref_w, ref_h);
    bila tidak ada referensi, kembalikan None."""

    def __init__(self, parent, ref_size=None):
        super().__init__(parent, text="Select a size.")
        self.ref_w, self.ref_h = ref_size or (None, None)
        self.choice = tk.StringVar(value="Small")
        self.fit_mode = tk.StringVar(value="Fit")
        self.unit = tk.StringVar(value="Pixels")
        self.custom_w = tk.StringVar(value="1024")
        self.custom_h = tk.StringVar(value="640")

        for i, name in enumerate(core.PRESET_ORDER):
            if name == "Custom":
                continue
            w, h = core.PRESETS[name]
            rb = ttk.Radiobutton(
                self, text="%s (fits within %d \u00d7 %d pixels)"
                % (name, w, h),
                variable=self.choice, value=name,
                command=self._on_change)
            rb.grid(row=i, column=0, columnspan=4, sticky="w",
                    padx=8, pady=2)

        row = len(core.PRESETS) - 1
        ttk.Radiobutton(self, text="Custom", variable=self.choice,
                        value="Custom",
                        command=self._on_change).grid(
                            row=row, column=0, sticky="w", padx=8, pady=2)
        self.fit_combo = ttk.Combobox(
            self, textvariable=self.fit_mode, width=8, state="readonly",
            values=["Fit", "Fill", "Stretch"])
        self.fit_combo.grid(row=row, column=1, padx=2)
        self.w_entry = ttk.Entry(self, textvariable=self.custom_w, width=8)
        self.w_entry.grid(row=row, column=2, padx=2)
        ttk.Label(self, text="\u00d7").grid(row=row, column=3, padx=1)
        self.h_entry = ttk.Entry(self, textvariable=self.custom_h, width=8)
        self.h_entry.grid(row=row, column=4, padx=2)
        self.unit_combo = ttk.Combobox(
            self, textvariable=self.unit, width=8, state="readonly",
            values=["Pixels", "Percent"])
        self.unit_combo.grid(row=row, column=5, padx=2)

        self._on_change()

    def _on_change(self):
        custom = self.choice.get() == "Custom"
        state = "normal" if custom else "disabled"
        for w in (self.fit_combo, self.w_entry, self.h_entry,
                  self.unit_combo):
            w.configure(state=state if w is not self.fit_combo
                        else ("readonly" if custom else "disabled"))

    def get_target(self):
        """(lebar, tinggi) piksel target, atau (None, None) bila Custom
        tidak valid / Percent tanpa referensi."""
        name = self.choice.get()
        if name != "Custom":
            return core.PRESETS[name]
        try:
            w = float(self.custom_w.get())
            h = float(self.custom_h.get())
        except ValueError:
            return (None, None)
        if w <= 0 or h <= 0:
            return (None, None)
        if self.unit.get() == "Percent":
            if not self.ref_w or not self.ref_h:
                return (None, None)
            return (int(round(self.ref_w * w / 100.0)),
                    int(round(self.ref_h * h / 100.0)))
        return (int(w), int(h))

    def get_preset_name(self):
        return self.choice.get()

    def get_fit_mode(self):
        return self.fit_mode.get().lower()


def make_status(parent):
    """Label status satu baris di bawah dialog."""
    var = tk.StringVar(value="")
    label = ttk.Label(parent, textvariable=var, wraplength=520,
                      foreground="#333333")
    label.pack(fill="x", padx=10, pady=(4, 2))
    return var
