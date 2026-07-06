@echo off
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
    set PYTHON_CMD=py
) else (
    set PYTHON_CMD=python
)
echo Starting SQL Server Agent Monitor...
echo Open http://localhost:8050 in your browser
start "" http://localhost:8050
%PYTHON_CMD% app.py
pause
