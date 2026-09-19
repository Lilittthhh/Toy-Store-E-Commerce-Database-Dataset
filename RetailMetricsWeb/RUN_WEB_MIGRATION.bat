@echo off
setlocal
cd /d "%~dp0"

set "WEB_PYTHON=.venv\Scripts\python.exe"
if not exist "%WEB_PYTHON%" set "WEB_PYTHON=python"

"%WEB_PYTHON%" scripts\run_migration.py
if errorlevel 1 (
  echo.
  echo Migration did not complete successfully.
  pause
  exit /b 1
)

echo.
echo Migration completed. Run VERIFY_WEB_MIGRATION.bat next.
pause
exit /b 0
