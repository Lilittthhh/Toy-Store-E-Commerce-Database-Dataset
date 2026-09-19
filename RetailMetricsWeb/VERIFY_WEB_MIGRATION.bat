@echo off
setlocal
cd /d "%~dp0"

set "WEB_PYTHON=.venv\Scripts\python.exe"
if not exist "%WEB_PYTHON%" set "WEB_PYTHON=python"

"%WEB_PYTHON%" scripts\verify_migration.py
if errorlevel 1 (
  echo.
  echo Post-migration verification failed.
  pause
  exit /b 1
)

echo.
echo Post-migration verification passed.
pause
exit /b 0
