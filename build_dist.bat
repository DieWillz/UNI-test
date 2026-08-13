@echo off
REM ============================================================
REM  build_dist.bat — сборка portable UNI.exe (ФАЗА 7, F-01)
REM  Запускать на ЦЕЛЕВОЙ Windows-машине (где установлены
REM  Python 3.12 + PyInstaller + нужные колёса).
REM  Итог: dist\UNI.exe (onefile, windowed) + electron\ + runtime\llama\
REM ============================================================
chcp 65001 >nul
setlocal
set "UNI_ROOT=%~dp0"
cd /d "%UNI_ROOT%"

REM 1) обновить pip + поставить PyInstaller (если нет)
python -m pip install --upgrade pip
python -m pip install pyinstaller

REM 2) убедиться, что зависимости стоят (единый constraints.txt)
python -m pip install -r constraints.txt

REM 3) PyInstaller по спеке (windowed, onefile)
pyinstaller UNI.spec --clean --noconfirm

REM 4) скопировать side-car файлы, которые PyInstaller не замораживает
if not exist "dist\electron" mkdir "dist\electron"
xcopy /E /I /Y "uni\desktop" "dist\electron" >nul
if not exist "dist\runtime\llama" mkdir "dist\runtime\llama"
if exist "runtime\llama\llama-server.exe" copy /Y "runtime\llama\llama-server.exe" "dist\runtime\llama\" >nul

REM 5) config.example.yaml -> dist\config.yaml (БЕЗ секретов)
copy /Y "config.example.yaml" "dist\config.yaml" >nul

echo.
echo [build_dist] Готово. dist\UNI.exe собран. Проверьте: dist\UNI.exe -> "На связи" <=60s.
echo [build_dist] Для инсталлятора: iscc UNI_Setup.iss (требует Inno Setup).
exit /b 0
