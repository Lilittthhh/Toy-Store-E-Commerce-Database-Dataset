@echo off
setlocal
cd /d "%~dp0"

set "WEB_PYTHON=.venv\Scripts\python.exe"
if not exist "%WEB_PYTHON%" set "WEB_PYTHON=python"

"%WEB_PYTHON%" scripts\generate_jwt_secret.py
exit /b %errorlevel%
