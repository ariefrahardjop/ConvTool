@echo off
REM ============================================================
REM ConvTool - uninstall: hapus menu klik kanan + folder install.
REM HARUS dijalankan sebagai Administrator:
REM   klik kanan uninstall.bat > Run as administrator
REM ============================================================
setlocal

net session >nul 2>&1
if errorlevel 1 (
  echo HARUS dijalankan sebagai Administrator.
  echo Klik kanan uninstall.bat, pilih "Run as administrator".
  pause
  exit /b 1
)

echo Menghapus perintah ConvTool dari CommandStore...
reg delete "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\CommandStore\shell\ConvTool.Resize" /f >nul 2>&1
reg delete "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\CommandStore\shell\ConvTool.ImagesToPdf" /f >nul 2>&1
reg delete "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\CommandStore\shell\ConvTool.Exif" /f >nul 2>&1
reg delete "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\CommandStore\shell\ConvTool.WatermarkKlasik" /f >nul 2>&1
reg delete "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\CommandStore\shell\ConvTool.WatermarkJob" /f >nul 2>&1
reg delete "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\CommandStore\shell\ConvTool.ResizePdf" /f >nul 2>&1
reg delete "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\CommandStore\shell\ConvTool.PdfToImages" /f >nul 2>&1

echo Menghapus submenu ConvTool...
reg delete "HKCR\SystemFileAssociations\.jpg\shell\ConvTool" /f >nul 2>&1
reg delete "HKCR\SystemFileAssociations\.jpeg\shell\ConvTool" /f >nul 2>&1
reg delete "HKCR\SystemFileAssociations\.png\shell\ConvTool" /f >nul 2>&1
reg delete "HKCR\SystemFileAssociations\.webp\shell\ConvTool" /f >nul 2>&1
reg delete "HKCR\SystemFileAssociations\.pdf\shell\ConvTool" /f >nul 2>&1

echo Menghapus folder install...
rmdir /S /Q "C:\Tools\ConvTool" >nul 2>&1

echo.
echo UNINSTALL SELESAI.
echo (File foto/PDF hasil ConvTool tidak ikut dihapus.)
pause
