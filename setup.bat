@echo off
cd /d "%~dp0"
echo Installing dependencies...
where py >nul 2>&1
if %errorlevel%==0 (
    set PYTHON_CMD=py
) else (
    set PYTHON_CMD=python
)
%PYTHON_CMD% -m pip install --upgrade pip
%PYTHON_CMD% -m pip install -r requirements.txt
echo.
echo Setup complete. Run run.bat to start.
pause
