@echo off
setlocal
cd /d "%~dp0"

set "WEB_PYTHON=.venv\Scripts\python.exe"
if not exist "%WEB_PYTHON%" set "WEB_PYTHON=python"

set "RUN_DB_INTEGRATION_TESTS=1"
"%WEB_PYTHON%" -m pytest -m integration tests\integration\test_auth_postgresql.py
exit /b %errorlevel%
