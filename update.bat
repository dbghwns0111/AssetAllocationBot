@echo off
rem For the server (cloud PC): pull latest code and update packages.
rem Close the running server window first, then start again with run.bat.
cd /d "%~dp0"
git pull --ff-only
if errorlevel 1 (
  echo [error] git pull failed
  pause
  exit /b 1
)
if not exist .venv python -m venv .venv
.venv\Scripts\python -m pip install -q -r requirements.txt
echo Update done. Restart the server with run.bat
pause
