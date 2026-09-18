@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Session 3 virtual environment is missing.
  exit /b 1
)
".venv\Scripts\python.exe" scripts\generate_proto.py
exit /b %ERRORLEVEL%

