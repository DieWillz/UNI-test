@echo off
REM ============================================================
REM  UNI.bat - single entry point for UNI (one click).
REM  Starts LLM (llama :1235) + WebUI (:8787) + Electron window,
REM  ALL HIDDEN (no console windows). Only the UNI GUI shows.
REM  Stop: UNI tray "Exit", or admin "Stop all".
REM ============================================================
chcp 65001 >nul
setlocal
set "UNI_ROOT=C:\LLM\UNI"
set "PYTHON=C:\LLM\python312\python.exe"
set "NODE=node"
set "LOGD=%UNI_ROOT%\runtime\logs"
cd /d "%UNI_ROOT%"

REM --- re-launch self hidden so no cmd window is visible ---
if not defined UNI_HIDDEN (
  set "UNI_HIDDEN=1"
  powershell -NoProfile -WindowStyle Hidden -Command "Start-Process -FilePath 'cmd.exe' -ArgumentList '/c','set UNI_HIDDEN=1 & \"%UNI_ROOT%\UNI.bat\"' -WindowStyle Hidden"
  exit /b
)

REM --- pre-flight checks (no pause: just log + exit) ---
if not exist "runtime\llama\llama-server.exe" (
  echo [%date% %time%] MISSING runtime\llama\llama-server.exe >> "%LOGD%\uni_bat.log"
  exit /b 1
)
if not exist "downloads\Qwen3-8B-Q4_K_M.gguf" (
  echo [%date% %time%] MISSING downloads\Qwen3-8B-Q4_K_M.gguf >> "%LOGD%\uni_bat.log"
  exit /b 1
)

echo [%date% %time%] Starting UNI (hidden)... >> "%LOGD%\uni_bat.log"

REM --- LLM (llama :1235) - keep an already running server ---
powershell -NoProfile -WindowStyle Hidden -Command "$ok=Test-NetConnection 127.0.0.1 -Port 1235 -InformationLevel Quiet; if(-not $ok){Start-Process -FilePath '%UNI_ROOT%\runtime\llama\llama-server.exe' -ArgumentList @('--model','%UNI_ROOT%\downloads\Qwen3-8B-Q4_K_M.gguf','--host','127.0.0.1','--port','1235','--n-gpu-layers','99','--api-key','uni-local') -WindowStyle Hidden -RedirectStandardOutput '%LOGD%\llama.log' -RedirectStandardError '%LOGD%\llama.err'; Add-Content '%LOGD%\uni_bat.log' ('LLM started '+(Get-Date))}else{Add-Content '%LOGD%\uni_bat.log' ('LLM already running '+(Get-Date))}"

REM --- WebUI (:8787) - start only when absent ---
powershell -NoProfile -WindowStyle Hidden -Command "$ok=Test-NetConnection 127.0.0.1 -Port 8787 -InformationLevel Quiet; if(-not $ok){$env:PYTHONPATH='%UNI_ROOT%';$env:UNI_WEBUI_PORT='8787';Start-Process -FilePath '%PYTHON%' -ArgumentList @('-m','uni.webui.server') -WorkingDirectory '%UNI_ROOT%' -WindowStyle Hidden -RedirectStandardOutput '%LOGD%\webui.log' -RedirectStandardError '%LOGD%\webui.err'; Add-Content '%LOGD%\uni_bat.log' ('WebUI started '+(Get-Date))}else{Add-Content '%LOGD%\uni_bat.log' ('WebUI already running '+(Get-Date))}"

REM --- UNI window (Electron) - hidden console, GUI shows ---
powershell -NoProfile -WindowStyle Hidden -Command "Start-Process -FilePath '%NODE%' -ArgumentList @('node_modules/electron/cli.js','.') -WorkingDirectory '%UNI_ROOT%\uni\desktop' -WindowStyle Hidden"

echo [%date% %time%] UNI started (hidden). GUI window should appear. >> "%LOGD%\uni_bat.log"
exit /b 0
