@echo off
REM 🤖 DEPRECATED by Hermes 2026-08-13: это тонкий алиас на UNI.bat (единая точка входа).
REM Файл оставлен для совместимости с ярлыком ЮНИ.lnk (который на него указывает).
REM Реальная логика — в UNI.bat / scripts/launcher.js.
chcp 65001 >nul
call "%~dp0UNI.bat" %*
exit /b %ERRORLEVEL%
