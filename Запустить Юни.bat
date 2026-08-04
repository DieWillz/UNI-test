@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "UNI_DIR=%~dp0"
set "PYTHON=C:\LLM\python312\python.exe"
set "PORT=8787"
set "PYTHONPATH=%UNI_DIR%"

if not exist "%PYTHON%" (
  echo Python not found: %PYTHON%
  echo Expected Python 3.12 at C:\LLM\python312\python.exe
  pause
  exit /b 1
)

if not exist "%UNI_DIR%uni\webui\server.py" (
  echo UNI WebUI was not found in: %UNI_DIR%
  pause
  exit /b 1
)

echo Starting UNI WebUI: http://127.0.0.1:%PORT%/
echo Press Ctrl+C or close this window to stop UNI WebUI.
echo.

start "UNI WebUI browser opener" /min powershell.exe -NoProfile -WindowStyle Hidden -Command ^
  "$url='http://127.0.0.1:%PORT%/'; for($i=0;$i -lt 40;$i++){try{Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 1 ^| Out-Null; Start-Process $url; exit 0}catch{Start-Sleep -Milliseconds 250}}"

"%PYTHON%" -m uni.webui --port %PORT%
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" echo UNI WebUI stopped with error code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%
