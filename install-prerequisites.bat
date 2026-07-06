@echo off
cd /d "%~dp0"
title SQL Server Agent Monitor - Install Prerequisites

echo ============================================================
echo   Download and install Python + ODBC (automatic)
echo ============================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap_prerequisites.ps1"
set "RC=%errorlevel%"

echo.
if %RC% equ 0 (
    echo Done. Run setup.bat next.
) else (
    echo Install failed. See errors above.
)

pause
exit /b %RC%
