# pickers.py — Pemilih tanggal & jam tkinter murni (tanpa dependensi).
#
# DatePickerEntry: Entry YYYY-MM-DD + tombol kalender popup (navigasi
# bulan, grid hari, klik hari untuk memilih). TimePickerEntry: spinbox
# jam (00-23) + menit (00-59). Dipakai dialog EXIF Editor & Watermark.
# Sengaja TIDAK memakai tkcalendar: paket itu butuh babel (data locale)
# yang rawan tidak ikut ter-bundel PyInstaller sehingga exe bisa gagal
# start; popup kalender di sini murni tkinter sehingga aman di exe.

import calendar
import tkinter as tk
from datetime import date, datetime
from tkinter import ttk

MONTHS_ID = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
             "Juli", "Agustus", "September", "Oktober", "November",
             "Desember"]
DAYS_ID = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]


def parse_date_str(s):
    """'YYYY-MM-DD' -> datetime.date; None bila tidak valid."""
    try:
        return datetime.strptime(str(s).strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def parse_time_str(s):
    """'HH:MM' -> (jam, menit); None bila tidak valid."""
    try:
        parts = str(s).strip().split(":")
        if len(parts) != 2:
            return None
        h, m = int(parts[0]), int(parts[1])
        if 0 <= h <= 23 and 0 <= m <= 59:
            return (h, m)
    except Exception:
        pass
    return None


class DatePickerEntry(ttk.Frame):
    """Entry tanggal YYYY-MM-DD + tombol kalender popup."""

    def __init__(self, parent, initial=""):
        super().__init__(parent)
        self.var = tk.StringVar(value=initial)
        self._last_valid = initial
        self.entry = ttk.Entry(self, textvariable=self.var, width=12)
        self.entry.pack(side="left")
        ttk.Button(self, text="\U0001f4c5", width=3,
                   command=self._open_popup).pack(side="left", padx=(2, 0))
        self.entry.bind("<FocusOut>", self._on_focus_out)
        self._popup = None

    def get(self):
        return self.var.get().strip()

    def set(self, value):
        self.var.set(value or "")
        self._last_valid = self.var.get()

    def _on_focus_out(self, _event=None):
        d = parse_date_str(self.var.get())
        if d is None:
            self.var.set(self._last_valid)
        else:
            self.var.set(d.isoformat())
            self._last_valid = self.var.get()

    def _open_popup(self):
        if self._popup is not None and self._popup.winfo_exists():
            self._popup.destroy()
            self._popup = None
            return
        d = parse_date_str(self.var.get()) or date.today()
        self._popup = _CalendarPopup(self, d, self._on_pick)
        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height() + 2
        self._popup.geometry("+%d+%d" % (x, y))

    def _on_pick(self, d):
        self.var.set(d.isoformat())
        self._last_valid = self.var.get()
        if self._popup is not None and self._popup.winfo_exists():
            self._popup.destroy()
            self._popup = None


class _CalendarPopup(tk.Toplevel):
    """Popup kalender satu bulan; klik hari untuk memilih.

    CATATAN: seluruh isi memakai grid (SATU geometry manager).
    Versi sebelumnya mencampur pack (frame header) + grid (hari) di
    container yang sama — tkinter menolaknya (TclError) sehingga
    __init__ abort sebelum _render() dan popup hanya menampilkan
    tombol < > tanpa kalender."""

    def __init__(self, parent, selected, on_pick):
        super().__init__(parent)
        self.on_pick = on_pick
        self.selected = selected
        self.year, self.month = selected.year, selected.month
        self.title("Pilih tanggal")
        self.resizable(False, False)
        try:
            self.transient(parent.winfo_toplevel())
        except Exception:
            pass
        # Baris 0: navigasi bulan (grid, 7 kolom seperti hari).
        ttk.Button(self, text="<", width=3,
                   command=lambda: self._shift(-1)).grid(
                       row=0, column=0, padx=2, pady=4)
        self.title_var = tk.StringVar()
        ttk.Label(self, textvariable=self.title_var, width=18,
                  anchor="center").grid(row=0, column=1, columnspan=5,
                                        padx=2, pady=4)
        ttk.Button(self, text=">", width=3,
                   command=lambda: self._shift(1)).grid(
                       row=0, column=6, padx=2, pady=4)
        # Baris 1: nama hari; baris 2-7: grid tanggal.
        for i, name in enumerate(DAYS_ID):
            ttk.Label(self, text=name, width=4,
                      anchor="center").grid(row=1, column=i, padx=1)
        self._cells = {}
        for r in range(6):
            for c in range(7):
                b = tk.Button(self, width=4,
                              command=lambda r=r, c=c: self._click(r, c))
                b.grid(row=2 + r, column=c, padx=1, pady=1)
                self._cells[(r, c)] = b
        # Warna tombol default sistem (dipakai untuk mengembalikan sel
        # hari biasa; "SystemButtonFace" hanya ada di Windows).
        self._default_bg = self._cells[(0, 0)].cget("bg")
        # Baris 8: aksi bawah.
        ttk.Button(self, text="Hari ini",
                   command=self._today).grid(row=8, column=0, columnspan=3,
                                            pady=(4, 6))
        ttk.Button(self, text="Batal",
                   command=self.destroy).grid(row=8, column=3, columnspan=4,
                                             pady=(4, 6))
        self._render()
        self.bind("<Escape>", lambda e: self.destroy())

    def _shift(self, delta):
        m = self.month + delta
        y = self.year
        if m < 1:
            m, y = 12, y - 1
        elif m > 12:
            m, y = 1, y + 1
        self.month, self.year = m, y
        self._render()

    def _render(self):
        self.title_var.set("%s %d" % (MONTHS_ID[self.month - 1], self.year))
        first_weekday, ndays = calendar.monthrange(self.year, self.month)
        today = date.today()
        for (r, c), b in self._cells.items():
            day = r * 7 + c - first_weekday + 1
            if 1 <= day <= ndays:
                b.configure(text=str(day), state="normal")
                d = date(self.year, self.month, day)
                if d == self.selected:
                    b.configure(bg="#1a5fb4", fg="white")
                elif d == today:
                    b.configure(bg="#dce8f5", fg="black")
                else:
                    b.configure(bg=self._default_bg, fg="black")
            else:
                b.configure(text="", state="disabled",
                            bg=self._default_bg)

    def _click(self, r, c):
        first_weekday, ndays = calendar.monthrange(self.year, self.month)
        day = r * 7 + c - first_weekday + 1
        if 1 <= day <= ndays:
            self.on_pick(date(self.year, self.month, day))

    def _today(self):
        self.on_pick(date.today())


class TimePickerEntry(ttk.Frame):
    """Pemilih jam: spinbox HH (00-23) + MM (00-59)."""

    def __init__(self, parent, initial=""):
        super().__init__(parent)
        h, m = parse_time_str(initial) or (0, 0)
        self.hour_var = tk.StringVar(value="%02d" % h)
        self.min_var = tk.StringVar(value="%02d" % m)
        ttk.Spinbox(self, from_=0, to=23, format="%02d",
                    textvariable=self.hour_var, width=3).pack(side="left")
        ttk.Label(self, text=":").pack(side="left")
        ttk.Spinbox(self, from_=0, to=59, format="%02d",
                    textvariable=self.min_var, width=3).pack(side="left")

    def get(self):
        t = parse_time_str("%s:%s" % (self.hour_var.get(),
                                      self.min_var.get()))
        if t is None:
            return ""
        return "%02d:%02d" % t

    def set(self, value):
        t = parse_time_str(value)
        if t is None:
            return
        self.hour_var.set("%02d" % t[0])
        self.min_var.set("%02d" % t[1])
