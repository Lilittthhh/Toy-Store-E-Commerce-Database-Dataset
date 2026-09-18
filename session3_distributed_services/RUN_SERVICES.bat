@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" exit /b 1
".venv\Scripts\python.exe" scripts\run_services.py
exit /b %ERRORLEVEL%

