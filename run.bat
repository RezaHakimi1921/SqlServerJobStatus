@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "PYTHON_CMD="
for /f "delims=" %%P in ('call "%~dp0scripts\resolve_python.bat"') do set "PYTHON_CMD=%%P"

if not defined PYTHON_CMD (
    call "%~dp0scripts\print_python_help.bat"
    echo Run setup.bat first after installing Python.
    echo اول Python را نصب کنید، بعد setup.bat را اجرا کنید.
    pause
    exit /b 1
)

if not exist "%~dp0app.py" (
    echo ERROR: app.py not found. Run this file from the project folder.
    pause
    exit /b 1
)

echo Starting SQL Server Agent Monitor...
echo Browser: http://localhost:8050
start "" "http://localhost:8050" 2>nul
%PYTHON_CMD% "%~dp0app.py"
set "APP_RC=!errorlevel!"

if !APP_RC! neq 0 (
    echo.
    echo App exited with error. If packages are missing, run setup.bat first.
)

pause
exit /b !APP_RC!
