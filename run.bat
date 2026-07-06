@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "PYTHON_EXE="
set "PYTHON_PYARG="
for /f "tokens=1,2 delims=|" %%A in ('powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\resolve_python.ps1" 2^>nul') do (
    if /i "%%A"=="EXE" set "PYTHON_EXE=%%B"
    if /i "%%A"=="PY" set "PYTHON_EXE=py" & set "PYTHON_PYARG=%%B"
)

if not defined PYTHON_EXE (
    call "%~dp0scripts\print_python_help.bat"
    echo Run setup.bat first.
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

if defined PYTHON_PYARG (
    %PYTHON_EXE% %PYTHON_PYARG% "%~dp0app.py"
) else (
    "%PYTHON_EXE%" "%~dp0app.py"
)
set "APP_RC=!errorlevel!"

if !APP_RC! neq 0 (
    echo.
    echo App exited with error. Run setup.bat if packages are missing.
)

pause
exit /b !APP_RC!
