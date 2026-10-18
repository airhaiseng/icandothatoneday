@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0control_auto_review.ps1" -Action resume
echo.
pause
