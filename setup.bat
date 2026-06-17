@echo off
echo === Cai dat Tour Video Generator ===

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python chua cai! Mo trinh duyet de tai...
    start https://www.python.org/downloads/
    echo Cai Python xong roi chay lai file nay.
    pause & exit
)

echo Tao moi truong ao...
python -m venv venv

echo Cai thu vien...
call venv\Scripts\activate
pip install -r requirements.txt

echo.
echo === Cai dat xong! Chay run.bat de bat dau ===
pause