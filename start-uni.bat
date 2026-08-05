@echo off
REM UNI single-instance launcher. ANSI, no BOM.
setlocal
set "ROOT=%~dp0"
set "PIDFILE=%ROOT%.uni.pid"
set "PY=C:\LLM\python312\python.exe"

if not exist "%PY%" (
  echo Python not found: %PY%
  pause
  exit /b 1
)

cd /d "%ROOT%"

REM --- single-instance: если .uni.pid есть и процесс жив - выходим ---
if exist "%PIDFILE%" (
  set /p OLD_PID=<%PIDFILE%
  tasklist /FI "PID eq %OLD_PID%" 2>nul | find "%OLD_PID%" >nul
  if not errorlevel 1 (
    echo UNI already running (PID %OLD_PID%). Exiting.
    pause
    exit /b 0
  )
  del "%PIDFILE%" 2>nul
)

REM --- записываем PID запущенного python ---
for /f %%p in ('"%PY%" -c "import os;print(os.getpid())"') do set "MYPID=%%p"
echo %MYPID%> "%PIDFILE%"

set PYTHONPATH=%ROOT%;%PYTHONPATH%
echo Session UNI started (PID %MYPID%)
"%PY%" -m uni --webui --text
set EXITCODE=%errorlevel%
del "%PIDFILE%" 2>nul
if not %EXITCODE%==0 (
  echo UNI exited with code %EXITCODE%
  pause
)
endlocal
