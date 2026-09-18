@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Session 3 virtual environment is missing. See README.md.
  exit /b 1
)
".venv\Scripts\python.exe" gui.py
exit /b %ERRORLEVEL%

