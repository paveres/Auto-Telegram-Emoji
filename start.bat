@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Сначала запустите install.bat
  pause
  exit /b 1
)
if not exist ".env" (
  ".venv\Scripts\python.exe" scripts/setup.py
  if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -m auto_telegram_emoji
pause
