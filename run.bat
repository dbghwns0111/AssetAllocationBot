@echo off
rem Run in a console window (development / quick check). For 24h service use install_service.bat
cd /d "%~dp0"
if not exist .venv (
  echo [setup] creating virtual environment...
  python -m venv .venv
)
.venv\Scripts\python -m pip install -q -r requirements.txt
set PORT=5001
if exist .env (
  for /f "usebackq tokens=1,* delims==" %%a in (".env") do if "%%a"=="HAA_PORT" set PORT=%%b
)
start "" http://127.0.0.1:%PORT%
.venv\Scripts\python main.py
pause
