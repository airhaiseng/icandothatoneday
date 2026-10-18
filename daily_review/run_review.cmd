@echo off
setlocal
if not exist "%~dp0logs" mkdir "%~dp0logs"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_review.ps1" >> "%~dp0logs\task.log" 2>&1
exit /b %errorlevel%
