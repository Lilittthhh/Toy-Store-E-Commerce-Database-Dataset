@echo off
cd /d "%~dp0"
if exist "..\session1_parallel_compute\.venv\Scripts\python.exe" (
  "..\session1_parallel_compute\.venv\Scripts\python.exe" gui.py
) else (
  python gui.py
)
pause
