@echo off
set UNI_DIR=C:\LLM\UNI
set PY=C:\LLM\python312\python.exe
set PYTHONPATH=C:\LLM\UNI

cd /d %UNI_DIR%

del /s /q %UNI_DIR%\uni\*.pyc >nul 2>&1
for /r %UNI_DIR%\uni %%f in (*.pyc) do del /q "%%f" >nul 2>&1

start "" %PY% -m uni.webui

timeout /t 3 >nul
start "" http://127.0.0.1:8787/

exit
