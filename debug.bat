@echo off
REM ============================================================
REM ConvTool - diagnosis: jalankan versi Python langsung (bukan exe),
REM supaya error apa pun terlihat di jendela ini.
REM Jalankan dari folder source ini (dobel-klik debug.bat).
REM ============================================================
setlocal
cd /d %~dp0

echo --- Cek Python ---
python --version
if errorlevel 1 (
  echo "python" tidak ketemu, coba launcher "py":
  py -3 --version
)

echo.
echo --- Cek library ---
python -c "import PIL; print('Pillow', PIL.__version__)"
python -c "import pymupdf; print('PyMuPDF', pymupdf.__version__)"
python -c "import tkinter; print('tkinter OK')"

echo.
echo --- Jalankan launcher ConvTool (versi Python) ---
echo Kalau jendela ConvTool muncul: kode + Python beres,
echo berarti masalahnya ada di file .exe hasil build.
echo Kalau muncul error di bawah ini, kirimkan isi jendela ini.
echo.
python convtool.py

echo.
echo ConvTool (Python) selesai, kode keluar: %errorlevel%
pause
