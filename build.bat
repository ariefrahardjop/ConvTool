@echo off
REM ============================================================
REM ConvTool - build ConvTool.exe di PC Windows.
REM Jalankan dari folder source ini (dobel-klik build.bat).
REM Butuh: Python 3.10+ (python.org) + koneksi internet (pip).
REM Hasil: dist\ConvTool.exe
REM ============================================================
setlocal
cd /d %~dp0

REM Cari Python: coba "python" dulu, lalu launcher "py".
set PY=
python --version >nul 2>&1
if not errorlevel 1 set PY=python
if "%PY%"=="" (
  py -3 --version >nul 2>&1
  if not errorlevel 1 set PY=py -3
)
if "%PY%"=="" (
  echo Python tidak ditemukan.
  echo Install dulu dari https://www.python.org/downloads/
  echo Centang "Add python.exe to PATH" saat install.
  echo Lalu jalankan build.bat lagi.
  pause
  exit /b 1
)
echo Python dipakai: %PY%
%PY% --version

echo [1/3] Install dependensi...
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
  echo GAGAL install requirements.txt - periksa koneksi internet.
  pause
  exit /b 1
)

echo [2/3] Install PyInstaller...
%PY% -m pip install pyinstaller
if errorlevel 1 (
  echo GAGAL install PyInstaller.
  pause
  exit /b 1
)

echo [3/3] Build exe (onefile, windowed)...
%PY% -m PyInstaller --noconfirm --onefile --windowed --name ConvTool --add-data "assets;assets" convtool.py
if errorlevel 1 (
  echo BUILD GAGAL.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo BUILD SELESAI: dist\ConvTool.exe
echo Langkah berikut: klik kanan install.bat ^> Run as administrator.
echo ============================================================
pause
