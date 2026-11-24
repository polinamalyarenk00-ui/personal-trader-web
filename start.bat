@echo off
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python -m pip install -r requirements.txt
if errorlevel 1 goto fail
.venv\Scripts\python -m streamlit run app.py
pause
exit /b
:fail
echo Install Python 3.12 from https://www.python.org/downloads/ and try again.
pause
