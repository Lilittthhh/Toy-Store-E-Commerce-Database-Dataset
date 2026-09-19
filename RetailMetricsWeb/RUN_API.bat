@echo off
setlocal
cd /d "%~dp0"

set "WEB_PYTHON=.venv\Scripts\python.exe"
if not exist "%WEB_PYTHON%" set "WEB_PYTHON=python"

"%WEB_PYTHON%" -m uvicorn api.main:app --host 127.0.0.1 --port 8000
exit /b %errorlevel%
