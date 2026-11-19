#!/usr/bin/env python3
"""Ambil catatan rilis untuk satu versi dari CHANGELOG.md.

Pakai: python scripts/release_notes.py 1.9.6
Cetak isi bagian "## v1.9.6" (tanpa judulnya). Bila bagian tidak
ditemukan, cetak satu baris fallback. Dipakai workflow GitHub
Actions sebagai body rilis.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def notes_for(version):
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    # Bagian "## v1.9.6" sampai "## " berikutnya / akhir berkas.
    pattern = re.compile(
        r"^## v" + re.escape(version) + r"\b.*?\n(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL)
    match = pattern.search(text)
    if not match:
        return "ConvTool v%s — lihat README.md untuk daftar perubahan." % version
    return match.group(1).strip()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Pakai: release_notes.py <versi, mis. 1.9.6>")
    print(notes_for(sys.argv[1]))
