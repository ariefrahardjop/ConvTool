@echo off
REM ============================================================
REM ConvTool - install menu klik kanan.
REM HARUS dijalankan sebagai Administrator:
REM   klik kanan install.bat > Run as administrator
REM Langkah:
REM   1. Copy dist\ConvTool.exe ke C:\Tools\ConvTool\
REM   2. Generate file .reg dari template (isi path install)
REM   3. reg import (daftarkan menu klik kanan)
REM ============================================================
setlocal
cd /d %~dp0

net session >nul 2>&1
if errorlevel 1 (
  echo HARUS dijalankan sebagai Administrator.
  echo Klik kanan install.bat, pilih "Run as administrator".
  pause
  exit /b 1
)

set INSTALLDIR=C:\Tools\ConvTool

if not exist "%~dp0dist\ConvTool.exe" (
  echo dist\ConvTool.exe tidak ditemukan.
  echo Jalankan build.bat dulu sampai selesai, baru install.bat.
  pause
  exit /b 1
)

echo [1/3] Menyalin ConvTool.exe ke %INSTALLDIR% ...
mkdir "%INSTALLDIR%" 2>nul
copy /Y "%~dp0dist\ConvTool.exe" "%INSTALLDIR%\"
if errorlevel 1 (
  echo GAGAL menyalin exe.
  pause
  exit /b 1
)

echo [2/3] Membuat file registry dari template...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$t = Get-Content -Raw -LiteralPath '%~dp0context_menu.reg.template'; $t = $t.Replace('__INSTALLDIR__', $env:INSTALLDIR.Replace('\', '\\')); Set-Content -LiteralPath \"$env:TEMP\ConvTool_context_menu.reg\" -Value $t -Encoding Unicode"
if errorlevel 1 (
  echo GAGAL membuat file .reg.
  pause
  exit /b 1
)

echo [3/3] Mendaftarkan menu klik kanan...
reg import "%TEMP%\ConvTool_context_menu.reg"
if errorlevel 1 (
  echo GAGAL import registry.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo INSTALL SELESAI.
echo Coba: klik kanan sebuah foto JPG di Explorer ^> ConvTool.
echo Catatan Windows 11: menu klasik muncul di bawah
echo "Show more options" (lihat README.md).
echo ============================================================
pause
