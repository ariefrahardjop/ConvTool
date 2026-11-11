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
