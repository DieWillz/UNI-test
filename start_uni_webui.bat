@echo off
REM UNI WebUI launcher - double-click to start the dev console (opens browser).
setlocal
set PY=C:\LLM\python312\python.exe
set ROOT=C:\LLM\UNI
if not exist "%PY%" (
  echo Python not found: %PY%
  pause
  exit /b 1
)
cd /d "%ROOT%"
set PYTHONPATH=%ROOT%
start "" "%PY%" -m uni.webui --port 8787
timeout /t 3 >nul
start "" http://127.0.0.1:8787/
endlocal
