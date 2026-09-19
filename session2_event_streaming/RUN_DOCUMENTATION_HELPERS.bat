@echo off
cd /d "%~dp0"
set PY=python
if exist "..\session1_parallel_compute\.venv\Scripts\python.exe" set PY=..\session1_parallel_compute\.venv\Scripts\python.exe

echo ============================================================
echo RetailMetrics Session 2 - Documentation Helpers
echo ============================================================
%PY% generate_documentation_summary.py
if errorlevel 1 goto :error
echo.
%PY% check_submission_completeness.py
if errorlevel 1 goto :error
echo.
echo Done. See results\session2_documentation_summary.txt
pause
exit /b 0

:error
echo.
echo One or more documentation checks need attention.
pause
exit /b 1
