# ConvTool — Perubahan

## v1.9.6 (19 Nov 2026)
- Notif update: aplikasi mengecek GitHub saat dibuka dan memberi tahu bila ada versi baru.
- Update berupa exe jadi: unduh ConvTool.exe baru, aplikasi menutup, memasang, lalu membuka lagi sendiri — tanpa Python, tanpa build manual.
- Exe di-build otomatis di GitHub (GitHub Actions) tiap versi baru dan dilampirkan di halaman Releases.
- Launcher: tombol "Periksa Pembaruan" + label versi.
- install.bat kini menerima ConvTool.exe di sampingnya (paket zip rilis) atau di dist/ (hasil build lokal).

## v1.9.5 (19 Nov 2026)
- Edit EXIF: daftar foto jadi sidebar kiri (Varian B) + toggle sembunyi/tampil.

## v1.9.4 (19 Nov 2026)
- Daftar foto selalu dibuat sejak init, di atas dialog (EXIF) / di atas form (Watermark) + scrollbar.

## v1.9.3 (19 Nov 2026)
- Single-instance: election lewat named mutex Windows (SO_REUSEADDR di Windows mengizinkan banyak proses bind port yang sama).

## v1.9.2 (19 Nov 2026)
- Single-instance: banyak proses klik kanan digabung ke satu dialog lewat socket localhost.

## v1.9.1 (19 Nov 2026)
- MultiSelectModel=Player di semua verb CommandStore (registry).

## v1.9.0 (19 Nov 2026)
- Multi-foto satu frame (EXIF + Watermark) + dialog responsif layar kecil (ScrollableFrame).

## v1.8.5 (17 Nov 2026)
- Resize PDF Small kini 1-bit hitam-putih 150 DPI (paling kecil) + jaminan hasil tidak lebih besar dari asli.
