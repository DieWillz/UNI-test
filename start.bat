@echo off
REM 🤖 DEPRECATED by Hermes 2026-08-13: алиас на UNI.bat (единая точка входа).
REM Оставлен для совместимости, НЕ удалён.
chcp 65001 >nul
call "%~dp0UNI.bat" %*
exit /b %ERRORLEVEL%
