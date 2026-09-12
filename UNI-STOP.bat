@echo off
REM ============================================================
REM  UNI-STOP.bat  -  stop all UNI processes (LLM, WebUI, Electron)
REM ============================================================
chcp 65001 >nul
setlocal
set "LOGD=C:\LLM\UNI\runtime\logs"

echo [%date% %time%] UNI-STOP: stopping all UNI services... >> "%LOGD%\uni_bat.log"

REM --- stop by ports (kill the process owning them) ---
REM LLM on :1235
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 1235 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
REM WebUI on :8787
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8787 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
REM Electron (by window title)
taskkill /FI "WINDOWTITLE eq UNI*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq uni-desktop*" /T /F >nul 2>&1

echo [%date% %time%] UNI-STOP: all services stopped. >> "%LOGD%\uni_bat.log"
exit /b 0
