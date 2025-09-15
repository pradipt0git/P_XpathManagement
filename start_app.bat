@echo off
REM Always work from the folder where this script is located
cd /d %~dp0

REM Create .venv in this folder if it doesn't exist
if not exist .venv (
    echo Creating Python virtual environment...
    python -m venv .venv
    echo Installing requirements...
    call .venv\Scripts\activate
    pip install --upgrade pip
    pip install -r requirements.txt
)

REM Activate venv
call .venv\Scripts\activate

REM Start the app (modules folder is inside this folder)
start "" http://127.0.0.1:5005/
python main.py
pause
