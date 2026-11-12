# ConvTool v1.8.1

Aplikasi desktop Windows untuk 6 alat konversi & resize — dipakai lewat
**klik kanan di Windows Explorer**. Dibangun dengan Python + tkinter
(bawaan Python) + Pillow + PyMuPDF, dibungkus jadi satu file
`ConvTool.exe` dengan PyInstaller.

Bahasa UI: Indonesia (nama ukuran tetap Inggris: Small / Medium / Large /
Phone / Custom, seperti dialog "Image Resizer for Windows").

## Perubahan v1.8.1 (12 Nov 2026)

- **Perbaikan instalasi di Windows ARM64 (Snapdragon):** PyMuPDF
  dipin ke `==1.28.2`. `requirements.txt` lama (`PyMuPDF>=1.24`)
  membuat pip mengambil 2.1, yang tidak punya wheel untuk
  `win_arm64` — pip lalu jatuh ke source tarball dan mencoba
  meng-compile MuPDF dari source, gagal karena Visual Studio 2022
  tidak terpasang. 1.28.2 adalah satu-satunya versi dengan wheel
  `win_arm64` (cp310-abi3, cocok untuk Python 3.10+, termasuk 3.11).
  Aplikasi sendiri tidak berubah; bila sudah terinstal, tidak perlu
  build ulang dari zip ini — cukup `pip install "PyMuPDF==1.28.2"`
  lalu jalankan `build.bat` lagi.

## Perubahan v1.8 (11 Nov 2026)

- **Pratinjau/alamat stuck di "Me-render..." / "Memuat alamat..." —
  DIPERBAIKI.** Penyebab: hasil thread latar dikirim lewat
  `widget.after()` dari thread — panggilan tkinter dari thread lain
  rawan hilang (race di Tcl), kadang tampil kadang tidak, tanpa error.
  Sekarang thread hanya memasukkan hasil ke `queue.Queue`, dan main
  thread memeriksa antrean tiap 200 md (`_poll_results`). Pola ini
  dipakai di dialog Watermark DAN EXIF Editor (peta EXIF juga pernah
  stuck dengan gejala sama).
- **Popup kalender tidak jelas — DIPERBAIKI.** Penyebab: popup
  mencampur pack (frame header) + grid (tanggal) di container yang
  sama — tkinter menolaknya sehingga kalender tidak tampil, hanya
  tombol < > yang kelihatan. Sekarang seluruh popup memakai grid
  saja, plus tombol Batal.
- **Pratinjau lebih cepat**: dirender dari salinan foto maks 1200 px
  (tampil di ~420 px, jadi render full 4000x3000 hanya membuang
  waktu); hasil akhir Terapkan tetap full-res.
- Uji logika: 98/98 lolos.

## Perubahan v1.7 (11 Nov 2026)

- **Pratinjau watermark terpotong saat foto landscape — DIPERBAIKI.**
  Penyebab: kolom pratinjau hanya selebar teks "Me-render pratinjau..."
  (~150 px), sementara gambar pratinjau selalu dibuat 460 px dan jendela
  (`resizable=False`) tidak membesar mengikuti gambar — jadi foto
  landscape terpotong di tepi dan teks alamat di kartu (sisi kiri)
  tidak kelihatan; di foto portrait tidak terasa karena gambarnya
  sempit. Perbaikan: kolom pratinjau diberi lebar awal ~420 px, dan
  gambar pratinjau diskalakan ke lebar kolom SEBENARNYA saat tampil
  (`core.fit_within`, tidak pernah diperbesar).
- Alamat di pratinjau: bila screenshot diambil saat "Memuat alamat..."
  masih berjalan, alamat memang belum ada — muat alamat (Nominatim) dan
  unduh tile peta bisa makan beberapa detik pada pemuatan pertama;
  begitu alamat terisi, pratinjau ikut me-render ulang otomatis.
- Uji logika: 95/95 lolos.

## Perubahan v1.6 (11 Nov 2026)

- **EXIF Editor**: tanggal memakai datepicker kalender + jam memakai time
  picker (spinbox); tag lain bisa diedit (dobel-klik nilai: Make, Model,
  ImageDescription, Artist, Copyright, Software, XResolution,
  YResolution); peta dimuat terpisah dari alamat (peta tampil segera
  setelah tile siap) + tile diunduh paralel sehingga tidak terasa "gagal";
  klik peta memilih koordinat (sudah ada sejak v1, kini ada petunjuknya).
  Orientation selalu 1 karena foto hasil simpan sudah ditegakkan.
- **Watermark Klasik & Job**: tanggal/jam memakai datepicker + time
  picker; pratinjau LANGSUNG di samping form (kolom kanan), diperbarui
  otomatis tiap isian berubah (tombol Pratinjau terpisah dihapus).
- **Images to PDF**: pilihan orientasi (Portrait/Landscape), ukuran
  kertas (A4/Folio/Letter/Legal/A5), mode gambar (fit dalam margin /
  full memenuhi halaman, dipotong tengah), dan resize gambar sebelum
  dimasukkan (Original/Small/Medium/Large — Small = PDF lebih kecil).
- **Perbaikan v1.5**: dialog klik kanan tidak muncul — penyebabnya
  `transient(parent)` ke root yang disembunyikan; kini transient hanya
  bila induk terlihat + dialog dipaksa tampil (deiconify/lift/focus).
- Uji logika: 91/91 lolos (termasuk round-trip klik-peta, edit tag EXIF,
  dan varian PDF baru).

## 6 alat

| # | Alat | Menu klik kanan | Hasil |
|---|------|-----------------|-------|
| 1 | **Resize Pictures** | foto JPG/JPEG/PNG/WEBP | File baru `nama (Small).jpg` dst. Ukuran: Small 854×480, Medium 1366×768, Large 1920×1080, Phone 320×569, Custom (Fit/Fill/Stretch + Pixels/Percent). Default: tidak pernah memperbesar, buat salinan (asli tidak ditimpa). Opsi lanjutan: kualitas JPEG (default 90), format output (ikut asli/JPEG/PNG). |
| 2 | **Resize PDF** | file PDF | PDF baru `nama (Small).pdf`; tiap halaman jadi berukuran target (px pada 96 DPI → point = px×72/96), konten diskalakan agar muat dan diletakkan di tengah. Konten tidak pernah diperbesar. |
| 3 | **Images to PDF** | foto (bisa banyak) | Satu PDF, tiap gambar satu halaman; orientasi Portrait/Landscape, kertas A4/Folio/Letter/Legal/A5, gambar fit dalam margin atau full memenuhi halaman (potong tengah), resize gambar Original/Small/Medium/Large. Ada tombol Tambah Gambar di dialog. |
| 4 | **PDF to Images** | file PDF | Tiap halaman jadi gambar `nama_p001.png` dst di folder yang sama, pada ukuran pilihan (sisi terpanjang dalam piksel), format PNG/JPG. |
| 5 | **Edit EXIF** | foto | Dialog: foto + tanggal & jam (DateTimeOriginal — datepicker kalender + time picker) + GPS lat/lon (bisa diedit) + pratinjau peta kecil (tile OSM; klik peta untuk geser koordinat) + alamat (Nominatim) + kamera make/model + daftar tag lain (dobel-klik nilai untuk mengedit: Make, Model, ImageDescription, Artist, Copyright, Software, XResolution, YResolution). Simpan = salinan baru `nama_exifedit.jpg` — asli tidak pernah ditimpa, semua EXIF lain dipertahankan. |
| 6 | **Watermark Klasik / Job** | foto | Stempel GPS mengikuti aplikasi web Stempel Foto GPS Web (bukan Galeriku — ada perbedaan: web memakai titik desimal & strip Job padat). **Klasik**: kartu gelap translusen 83% lebar foto + bayangan + peta satelit Esri + pill "GPS Map Camera" + judul tempat + bendera Indonesia + alamat + `Lat -7.276971° Long 112.747416°` (titik desimal) + tanggal `Kamis, 24/09/2026 09:22 GMT +07:00` + baris cuaca opsional. **Job**: strip abu-abu PADAT #7d7d7d + peta jalan OSM + alamat + tempat maks 3 baris + lat/lon + tanggal `2026-11-02(Sen) 07:23(AM)` + cuaca di kanan (ikon + `28°C` / `82°F`, default Berawan 28°C, bisa dimatikan). Dialog: tanggal/jam memakai datepicker + time picker, field Tempat terpisah, suhu & kondisi cuaca, slider Ukuran stempel 70–150% (default 100%), dan **pratinjau langsung di samping form** (diperbarui otomatis tiap isian berubah). Tempat terisi otomatis saat "Muat alamat": diturunkan dari data terstruktur Nominatim sebagai "Kecamatan {kecamatan}, {provinsi}, {negara}" (kecamatan = municipality, bukan bagian pertama/terakhir alamat) — mis. "Kecamatan Wonocolo, Jawa Timur, Indonesia"; masih bisa diedit manual. Data dari EXIF foto (GPS + DateTimeOriginal); bila GPS tidak ada, isi manual di dialog. Hasil `nama_klasik.jpg` / `nama_job.jpg`, GPS + tanggal asli dipertahankan. Tanpa field Nama Pekerjaan/Catatan/Altitude/Akurasi. |

## Cara install di PC Windows

1. **Salin folder ini** ke PC (mis. `C:\ConvTool-src\` atau di mana saja).
2. **Build exe** — dobel-klik `build.bat`. Butuh Python 3.10+ (install dari
   python.org, centang "Add python.exe to PATH") + internet (pip akan
   mengunduh Pillow, PyMuPDF, PyInstaller). Hasil: `dist\ConvTool.exe`.
   - Atau tanpa build: jalankan langsung `python convtool.py` (butuh
     `pip install -r requirements.txt` dulu).
3. **Install menu klik kanan** — klik kanan `install.bat` → **Run as
   administrator**. Ini menyalin `ConvTool.exe` ke `C:\Tools\ConvTool\`
   dan mendaftarkan submenu **ConvTool** di registry.
4. **Klik kanan pertama** — klik kanan sebuah foto JPG di Explorer →
   **ConvTool** → pilih alat, mis. **Resize Pictures**.

Tanpa klik kanan pun bisa: jalankan `ConvTool.exe` tanpa argumen untuk
membuka jendela launcher berisi 6 alat, atau dari baris perintah:

```
ConvTool.exe <verb> <file> [file...]
verb: resize-image | resize-pdf | images-to-pdf | pdf-to-images |
      exif | watermark-klasik | watermark-job
```

Contoh: `ConvTool.exe resize-image "C:\Foto\liburan.jpg"`

## Uninstall

Klik kanan `uninstall.bat` → **Run as administrator**. Menghapus semua
key registry ConvTool + folder `C:\Tools\ConvTool`. File hasil (foto/PDF)
tidak ikut dihapus.

## Aturan nama file hasil

- Resize gambar/PDF: `nama (Small).jpg`, `nama (Medium).pdf`, dst.
  (Custom → `nama (Custom).jpg`).
- PDF to Images: `nama_p001.png`, `nama_p002.png`, dst.
- Edit EXIF: `nama_exifedit.jpg`.
- Watermark: `nama_klasik.jpg`, `nama_job.jpg`.
- File asli **tidak pernah** ditimpa, kecuali bila checkbox
  "Resize the original pictures (don't create copies)" dicentang.

## Batasan yang diketahui (v1)

- **Windows 11**: entri registry klasik muncul di bawah **"Show more
  options"** di menu klik kanan, bukan di menu utama. Supaya muncul di
  menu utama perlu didaftarkan sebagai handler modern (IExplorerCommand)
  — di luar cakupan v1.
- **.exe dan registry belum pernah diuji** — build & install baru bisa
  dijalankan di PC Windows (VM Linux tidak bisa cross-compile .exe
  dengan PyInstaller dan tidak punya registry). `build.bat` /
  `install.bat` sudah diperiksa konstruksinya (sintaks + path), tapi
  uji nyatanya tetap di PC.
- **GUI tkinter belum diuji headless** — yang diuji di VM adalah logika
  inti (lihat `tests/test_convtool.py`: 63 uji, semua lolos). Dialog
  perlu dicek sekali di PC: buka tiap alat, pastikan tampil & tombol
  bekerja.
- **Butuh internet** untuk: tile peta (OSM/Esri), alamat reverse-geocode
  (Nominatim). Bila offline: peta diganti sketsa, alamat menampilkan
  pesan offline — alat tetap jalan.
- **Skala watermark tetap 1.0** (tanpa slider 70–150% seperti Galeriku).
- **Resize PDF tidak memperbesar** konten yang halamannya sudah lebih
  kecil dari target (konsisten dengan "Make pictures smaller but not
  larger").
- **Multi-pilih di Explorer**: Windows memanggil exe sekali per file;
  untuk Images to PDF, tambahkan gambar lain lewat tombol
  **Tambah Gambar** di dialog.
- **Foto HEIC** tidak didukung (Pillow standar tidak membaca HEIC).
- **"Ignore the orientation of pictures"** (default ON, seperti
  aslinya): bila ON, orientasi EXIF diabaikan (piksel apa adanya);
  bila OFF, foto diputar sesuai EXIF dulu.

## Struktur file

```
convtool.py            Entry point + launcher + routing CLI
core.py                Logika inti (preset, resize, EXIF, tile, PDF, geocode)
ui_common.py           Widget preset ukuran bersama
pickers.py             DatePickerEntry (popup kalender) + TimePickerEntry
resize_dialog.py       Dialog Resize gambar & PDF
pdf_tools.py           Dialog Images -> PDF & PDF -> Images
exif_editor.py         Dialog EXIF Editor
watermark.py           Render watermark Klasik & Job (Pillow)
watermark_dialog.py    Dialog Watermark (form data + pratinjau langsung)
requirements.txt       Pillow, PyMuPDF
build.bat              Build ConvTool.exe (di PC Windows)
install.bat            Copy exe + daftarkan menu klik kanan (admin)
uninstall.bat          Hapus menu klik kanan + folder install (admin)
context_menu.reg.template  Template registry (diisi install.bat)
assets/                Ikon GPS Map Camera (untuk pill watermark Klasik)
tests/test_convtool.py Uji logika inti (headless)
```

Referensi layout watermark: `~/workspace/galeriku/src/com/gobel/galeriku/Watermark.java`
dan Stempel Foto GPS Web (`~/workspace/ts-spaces/stempel-foto-gps-web/`).
