@echo off
REM ============================================================
REM ConvTool - cek instalasi: build? install? menu? exe?
REM Jalankan dari folder source ini (dobel-klik cek-instalasi.bat).
REM Salin seluruh isi jendela ini dan kirimkan ke saya.
REM ============================================================
setlocal
cd /d %~dp0

echo ===== 0. Windows =====
ver

echo.
echo ===== 1. Python =====
python --version
if errorlevel 1 (
  py -3 --version
)

echo.
echo ===== 2. Hasil build (dist) =====
if exist "%~dp0dist\ConvTool.exe" (
  echo ADA: dist\ConvTool.exe
  for %%F in ("%~dp0dist\ConvTool.exe") do echo Ukuran: %%~zF byte
) else (
  echo TIDAK ADA: dist\ConvTool.exe -- build.bat belum berhasil.
)

echo.
echo ===== 3. Hasil install (C:\Tools\ConvTool) =====
if exist "C:\Tools\ConvTool\ConvTool.exe" (
  echo ADA: C:\Tools\ConvTool\ConvTool.exe
  for %%F in ("C:\Tools\ConvTool\ConvTool.exe") do echo Ukuran: %%~zF byte
) else (
  echo TIDAK ADA: C:\Tools\ConvTool\ConvTool.exe -- install.bat belum berhasil.
)

echo.
echo ===== 4. Registry menu klik kanan =====
reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\CommandStore\shell\ConvTool.Resize\command" 2>nul
if errorlevel 1 (
  echo TIDAK ADA: menu ConvTool belum terdaftar di registry.
) else (
  echo ADA: perintah Resize terdaftar di atas.
)
reg query "HKCR\SystemFileAssociations\.jpg\shell\ConvTool" 2>nul
if errorlevel 1 (
  echo TIDAK ADA: submenu ConvTool untuk .jpg belum terdaftar.
) else (
  echo ADA: submenu ConvTool untuk .jpg terdaftar di atas.
)

echo.
echo ===== 5. Coba jalankan exe langsung =====
if exist "C:\Tools\ConvTool\ConvTool.exe" (
  echo Membuka C:\Tools\ConvTool\ConvTool.exe ...
  echo Kalau jendela ConvTool muncul, exe beres (masalahnya di menu).
  echo Kalau tidak muncul apa-apa, exe gagal start.
  start "" "C:\Tools\ConvTool\ConvTool.exe"
  timeout /t 5 /nobreak >nul
  tasklist /FI "IMAGENAME eq ConvTool.exe" | find "ConvTool.exe" >nul
  if errorlevel 1 (
    echo HASIL: ConvTool.exe TIDAK sedang berjalan (langsung tertutup/gagal start).
  ) else (
    echo HASIL: ConvTool.exe SEDANG BERJALAN.
    taskkill /F /IM ConvTool.exe >nul 2>&1
  )
) else (
  echo Dilewati: exe belum terinstall.
)

echo.
echo ===== 6. Log error (bila ada) =====
if exist "%TEMP%\convtool-error.log" (
  echo ADA: %TEMP%\convtool-error.log
  type "%TEMP%\convtool-error.log"
) else (
  echo TIDAK ADA: belum ada log error.
)

echo.
echo ===== SELESAI =====
echo Salin seluruh isi jendela ini dan kirimkan ke saya.
pause
