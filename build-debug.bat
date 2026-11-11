@echo off
REM ============================================================
REM ConvTool - build exe versi CONSOLE (debug).
REM Exe ini menampilkan jendela hitam; error apa pun akan terlihat.
REM Hasil: dist\ConvTool-debug.exe
REM ============================================================
setlocal
cd /d %~dp0

set PY=
python --version >nul 2>&1
if not errorlevel 1 set PY=python
if "%PY%"=="" (
  py -3 --version >nul 2>&1
  if not errorlevel 1 set PY=py -3
)
if "%PY%"=="" (
  echo Python tidak ditemukan.
  pause
  exit /b 1
)

%PY% -m pip install -r requirements.txt
%PY% -m pip install pyinstaller
%PY% -m PyInstaller --noconfirm --onefile --name ConvTool-debug --add-data "assets;assets" convtool.py
if errorlevel 1 (
  echo BUILD DEBUG GAGAL.
  pause
  exit /b 1
)

echo.
echo BUILD DEBUG SELESAI: dist\ConvTool-debug.exe
echo Sekarang dijalankan dengan --help (harus tampil daftar verb):
echo.
dist\ConvTool-debug.exe --help
echo.
echo Kode keluar: %errorlevel%
echo Kalau jendela langsung tertutup atau muncul error di atas,
echo kirimkan isi jendela ini.
pause
