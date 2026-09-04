@echo off
cd /d "%~dp0"
if exist "..\session1_parallel_compute\.venv\Scripts\python.exe" (
  "..\session1_parallel_compute\.venv\Scripts\python.exe" render_diagrams.py
) else (
  python render_diagrams.py
)
pause
