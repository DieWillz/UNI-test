@echo off
REM ============================================================
REM  UNI-SERVER.bat  -  launch only WebUI server (port 8787)
REM  Hidden console window. Admin panel at http://127.0.0.1:8787
REM ============================================================
chcp 65001 >nul
setlocal
set "UNI_ROOT=C:\LLM\UNI"
set "PYTHON=C:\LLM\python312\python.exe"
set "LOGD=%UNI_ROOT%\runtime\logs"
cd /d "%UNI_ROOT%"

echo [%date% %time%] UNI-SERVER: launching WebUI... >> "%LOGD%\uni_bat.log"

powershell -NoProfile -WindowStyle Hidden -Command "$ok=Test-NetConnection 127.0.0.1 -Port 8787 -InformationLevel Quiet; if(-not $ok){$env:PYTHONPATH='%UNI_ROOT%';$env:UNI_WEBUI_PORT='8787';Start-Process -FilePath '%PYTHON%' -ArgumentList @('-m','uni.webui.server') -WorkingDirectory '%UNI_ROOT%' -WindowStyle Hidden -RedirectStandardOutput '%LOGD%\webui.log' -RedirectStandardError '%LOGD%\webui.err'}else{Write-Host 'WebUI already running on :8787'}"

echo [%date% %time%] UNI-SERVER: done. Open http://127.0.0.1:8787 >> "%LOGD%\uni_bat.log"
exit /b 0
