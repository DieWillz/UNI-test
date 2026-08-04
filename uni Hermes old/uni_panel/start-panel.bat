@echo off
cd /d "%~dp0"
echo UNI Control Panel
echo http://127.0.0.1:8787
echo.
python -m pip install -q -r requirements.txt
python app.py
pause
