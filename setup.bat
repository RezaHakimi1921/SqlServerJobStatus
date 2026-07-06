@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   SQL Server Agent Monitor - Setup
echo ============================================================
echo.

echo [0/3] Looking for Python...
call :find_python
if defined PYTHON_EXE echo   Found: %PYTHON_EXE% %PYTHON_PYARG%

if not defined PYTHON_EXE (
    echo   Python not found.
    echo   Downloading and installing Python 3.12 automatically...
    echo   Please wait 3-8 minutes. Do not close this window.
    echo.
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap_prerequisites.ps1" -PythonOnly
    if errorlevel 1 (
        call "%~dp0scripts\print_python_help.bat"
        pause
        exit /b 1
    )
    echo.
    echo [0/3] Looking for Python again...
    call :find_python
)

if not defined PYTHON_EXE (
    call "%~dp0scripts\print_python_help.bat"
    pause
    exit /b 1
)

echo.
call :run_python --version
if errorlevel 1 (
    call "%~dp0scripts\print_python_help.bat"
    pause
    exit /b 1
)

echo.
echo [1/3] Upgrading pip - please wait 1-2 min...
set "PYTHONUNBUFFERED=1"
call :run_python -u -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: pip upgrade failed. Check internet and try again.
    pause
    exit /b 1
)
echo   pip OK.

echo.
echo [2/3] Installing packages - please wait 2-8 min...
call :run_python -u -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo ERROR: Package install failed.
    pause
    exit /b 1
)
echo   Packages OK.

echo.
echo [3/3] Verifying install...
call :run_python "%~dp0scripts\check_prerequisites.py"
set "CHECK_RC=!errorlevel!"

echo.
if !CHECK_RC! equ 0 (
    echo ============================================================
    echo   Setup complete. Run run.bat to start the app.
    echo ============================================================
) else (
    echo Setup finished with warnings. See messages above.
    echo ODBC missing? Run install-prerequisites.bat then setup.bat again.
)

pause
exit /b !CHECK_RC!

:find_python
set "PYTHON_EXE="
set "PYTHON_PYARG="
for /f "tokens=1,2 delims=|" %%A in ('powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\resolve_python.ps1" 2^>nul') do (
    if /i "%%A"=="EXE" set "PYTHON_EXE=%%B"
    if /i "%%A"=="PY" set "PYTHON_EXE=py" & set "PYTHON_PYARG=%%B"
)
exit /b 0

:run_python
if defined PYTHON_PYARG (
    %PYTHON_EXE% %PYTHON_PYARG% %*
) else (
    "%PYTHON_EXE%" %*
)
exit /b %errorlevel%
