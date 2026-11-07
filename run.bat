@echo off
cd /d "%~dp0"
set PYCMD=py
where py >nul 2>nul || set PYCMD=python
where %PYCMD% >nul 2>nul || (
  echo Python is not installed. Install Python 3.12 from python.org and tick "Add python.exe to PATH", then run this file again.
  pause
  exit /b 1
)
if not exist .venv\Scripts\activate.bat %PYCMD% -m venv .venv
call .venv\Scripts\activate.bat
python -c "import django, whitenoise, openpyxl" >nul 2>nul || pip install -q -r requirements.txt
python manage.py makemigrations permits
python manage.py migrate
echo.
echo ================================================================
echo  UBL Permit to Work - demo
echo  On this PC:            http://localhost:8000
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do echo  On phones (same Wi-Fi):  http://%%a:8000
echo  Keep this window open while presenting. Press Ctrl+C to stop.
echo ================================================================
echo.
python manage.py runserver 0.0.0.0:8000
pause
