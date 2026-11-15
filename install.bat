@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
py -3.11 -m venv .venv
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" scripts/setup.py
pause
