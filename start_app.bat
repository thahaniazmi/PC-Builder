@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt

python scripts\init_db.py

start "" http://localhost:8000
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
