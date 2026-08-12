@echo off
REM UNI Desktop Companion — запуск одним кликом (для координатора)
REM Electron уже установлен в node_modules (см. D-19).
cd /d "%~dp0"
echo Запуск UNI Desktop Companion...
REM Способ 1: через npx (если node в PATH)
npx electron .
REM Если npx не резолвит node в под-shell, fallback на прямой вызов:
IF ERRORLEVEL 1 (
  echo npx не сработал, пробуем прямой вызов node...
  node "%~dp0node_modules\electron\cli.js" .
)
pause
