@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: RetailMetricsWeb virtual environment was not found.
    exit /b 1
)

".venv\Scripts\python.exe" "scripts\run_migration_002.py"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
