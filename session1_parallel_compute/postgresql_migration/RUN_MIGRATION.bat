@echo off
cd /d "%~dp0"
if not exist ".env" (
  echo ERROR: .env not found.
  echo Copy .env.example to .env and enter your PostgreSQL credentials first.
  pause
  exit /b 1
)
python migrate_csv_to_postgres.py
pause
