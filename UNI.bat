@echo off
REM 🤖 Единая точка входа ЮНИ (ФИНАЛ 2026-08-13, §13).
REM Поднимает scripts/launcher.js (он сам: llama :1235 + WebUI :8787 + Electron-оверлей),
REM окна консолей скрыты (start /min). Этот cmd сам завершается сразу.
REM Закрытие Юни (tray «Выход» или закрытие окна) убивает ВСЕ серверы по pids.json.
chcp 65001 >nul
setlocal
set UNI_ROOT=C:\LLM\UNI
cd /d %UNI_ROOT%
if not exist runtime\llama\llama-server.exe (
  echo [ЮНИ] runtime/llama не распакован — распакуйте downloads/llama-*-win-cuda-*.zip в runtime/llama
  pause
  exit /b 1
)
start "" /min cmd /c "cd /d %UNI_ROOT% && node scripts/launcher.js %*"
echo [ЮНИ] Запуск инициирован. Оверлей появится справа снизу; админка: http://127.0.0.1:8787/admin-status.html
exit /b 0
