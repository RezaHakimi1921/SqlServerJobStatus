@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   SQL Server Agent Monitor - Setup
echo ============================================================
echo.

call :find_python
if not defined PYTHON_CMD (
    echo Python not found. Downloading and installing automatically...
    echo This requires internet access and may take a few minutes.
    echo.
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap_prerequisites.ps1"
    if errorlevel 1 (
        call "%~dp0scripts\print_python_help.bat"
        pause
        exit /b 1
    )
    call :find_python
)

if not defined PYTHON_CMD (
    call "%~dp0scripts\print_python_help.bat"
    pause
    exit /b 1
)

echo Using: %PYTHON_CMD%
%PYTHON_CMD% --version
if errorlevel 1 (
    call "%~dp0scripts\print_python_help.bat"
    pause
    exit /b 1
)

echo.
echo [1/3] Upgrading pip...
%PYTHON_CMD% -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: pip failed. Check internet connection and try again.
    pause
    exit /b 1
)

echo.
echo [2/3] Installing packages from requirements.txt...
%PYTHON_CMD% -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo ERROR: Package install failed.
    pause
    exit /b 1
)

echo.
echo [3/3] Checking packages and ODBC drivers...
%PYTHON_CMD% "%~dp0scripts\check_prerequisites.py"
set "CHECK_RC=!errorlevel!"

if !CHECK_RC! neq 0 (
    echo.
    echo ODBC driver missing. Installing automatically...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap_prerequisites.ps1"
    %PYTHON_CMD% "%~dp0scripts\check_prerequisites.py"
    set "CHECK_RC=!errorlevel!"
)

echo.
if !CHECK_RC! equ 0 (
    echo ============================================================
    echo   Setup complete. Run run.bat to start the app.
    echo ============================================================
) else (
    echo Setup finished with warnings. See messages above.
)

pause
exit /b !CHECK_RC!

:find_python
set "PYTHON_CMD="
for /f "delims=" %%P in ('call "%~dp0scripts\resolve_python.bat"') do set "PYTHON_CMD=%%P"
exit /b 0
