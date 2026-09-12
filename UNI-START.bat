@echo off
REM ============================================================
REM  UNI-START.bat  -  launch LLM + WebUI + Desktop (hidden)
REM  All in one click. No console windows visible.
REM ============================================================
chcp 65001 >nul
setlocal
set "UNI_ROOT=C:\LLM\UNI"
set "PYTHON=C:\LLM\python312\python.exe"
set "NODE=node"
set "LOGD=%UNI_ROOT%\runtime\logs"
cd /d "%UNI_ROOT%"

echo [%date% %time%] UNI-START: launching all services... >> "%LOGD%\uni_bat.log"

REM --- LLM (port 1235) ---
powershell -NoProfile -WindowStyle Hidden -Command "$ok=Test-NetConnection 127.0.0.1 -Port 1235 -InformationLevel Quiet; if(-not $ok){Start-Process -FilePath '%UNI_ROOT%\runtime\llama\llama-server.exe' -ArgumentList @('--model','%UNI_ROOT%\downloads\Qwen3-8B-Q4_K_M.gguf','--host','127.0.0.1','--port','1235','--n-gpu-layers','99','--api-key','uni-local') -WindowStyle Hidden -RedirectStandardOutput '%LOGD%\llama.log' -RedirectStandardError '%LOGD%\llama.err'}"

REM --- WebUI (port 8787) ---
powershell -NoProfile -WindowStyle Hidden -Command "$ok=Test-NetConnection 127.0.0.1 -Port 8787 -InformationLevel Quiet; if(-not $ok){$env:PYTHONPATH='%UNI_ROOT%';$env:UNI_WEBUI_PORT='8787';Start-Process -FilePath '%PYTHON%' -ArgumentList @('-m','uni.webui.server') -WorkingDirectory '%UNI_ROOT%' -WindowStyle Hidden -RedirectStandardOutput '%LOGD%\webui.log' -RedirectStandardError '%LOGD%\webui.err'}"

REM --- Desktop (Electron) ---
powershell -NoProfile -WindowStyle Hidden -Command "Start-Process -FilePath '%NODE%' -ArgumentList @('node_modules/electron/cli.js','.') -WorkingDirectory '%UNI_ROOT%\uni\desktop' -WindowStyle Hidden"

echo [%date% %time%] UNI-START: services launched. GUI will appear. >> "%LOGD%\uni_bat.log"
exit /b 0
