@echo off
chcp 65001 >nul
cd /d "%~dp0"
title SQL Server Agent Monitor - Install Prerequisites

echo ============================================================
echo   Install system prerequisites (Python + ODBC Driver)
echo ============================================================
echo.

where winget >nul 2>&1
if errorlevel 1 (
    echo winget is not available on this PC.
    echo.
    echo Install manually:
    echo   Python:  https://www.python.org/downloads/
    echo   ODBC 17: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server
    echo.
    call "%~dp0scripts\print_python_help.bat"
    pause
    exit /b 1
)

echo Installing Python 3.12 ...
winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo Python install via winget failed. Try manual install from python.org
)

echo.
echo Installing ODBC Driver 17 for SQL Server ...
winget install --id Microsoft.MicrosoftODBCDriver17ForSQLServer -e --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo ODBC 17 install failed — try ODBC 18 or download from Microsoft.
    winget install --id Microsoft.MicrosoftODBCDriver18ForSQLServer -e --accept-package-agreements --accept-source-agreements
)

echo.
echo ============================================================
echo   IMPORTANT: Close this window and open a NEW terminal
echo   Then run:  setup.bat
echo ============================================================
echo.
echo Also disable Windows Store Python aliases:
echo   Settings ^> Apps ^> Advanced app settings ^> App execution aliases
echo   Turn OFF: python.exe and python3.exe
echo.
pause
