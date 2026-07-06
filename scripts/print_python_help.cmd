@echo off
chcp 65001 >nul
echo.
echo ============================================================
echo   Python 3.9+ not found on this computer
echo ============================================================
echo.
echo This project needs Python. The Windows Store shortcut is NOT enough.
echo.
echo OPTION A - Automatic install (recommended, needs winget):
echo   Run:  install-prerequisites.bat
echo.
echo OPTION B - Manual install:
echo   1. Download Python 3.12 from https://www.python.org/downloads/
echo   2. During setup, CHECK: "Add python.exe to PATH"
echo   3. Disable Store alias (important):
echo      Settings ^> Apps ^> Advanced app settings ^> App execution aliases
echo      Turn OFF: python.exe and python3.exe
echo   4. Close this window, open a NEW Command Prompt, run setup.bat again
echo.
echo OPTION C - winget in terminal (Admin):
echo   winget install Python.Python.3.12 --accept-package-agreements
echo.
echo ============================================================
exit /b 1
