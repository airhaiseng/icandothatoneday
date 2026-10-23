@echo off
setlocal
cd /d "%~dp0"
set "PY=C:\Users\28704\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" control_server.py --port 8777
echo.
pause
