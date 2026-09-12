@echo off
REM ============================================================
REM  UNI-DESKTOP.bat  -  launch only Electron overlay
REM  Will auto-start WebUI server if missing.
REM ============================================================
chcp 65001 >nul
setlocal
set "UNI_ROOT=C:\LLM\UNI"
set "PYTHON=C:\LLM\python312\python.exe"
set "NODE=node"
set "LOGD=%UNI_ROOT%\runtime\logs"
cd /d "%UNI_ROOT%"

REM --- auto-start WebUI if not running ---
powershell -NoProfile -WindowStyle Hidden -Command "$ok=Test-NetConnection 127.0.0.1 -Port 8787 -InformationLevel Quiet; if(-not $ok){$env:PYTHONPATH='%UNI_ROOT%';$env:UNI_WEBUI_PORT='8787';Start-Process -FilePath '%PYTHON%' -ArgumentList @('-m','uni.webui.server') -WorkingDirectory '%UNI_ROOT%' -WindowStyle Hidden -RedirectStandardOutput '%LOGD%\webui.log' -RedirectStandardError '%LOGD%\webui.err'}"

REM --- Electron overlay ---
echo [%date% %time%] UNI-DESKTOP: launching Electron overlay... >> "%LOGD%\uni_bat.log"
powershell -NoProfile -WindowStyle Hidden -Command "Start-Process -FilePath '%NODE%' -ArgumentList @('node_modules/electron/cli.js','.') -WorkingDirectory '%UNI_ROOT%\uni\desktop' -WindowStyle Hidden"

echo [%date% %time%] UNI-DESKTOP: overlay launched. >> "%LOGD%\uni_bat.log"
exit /b 0
