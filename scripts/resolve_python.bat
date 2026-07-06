@echo off
REM Legacy wrapper - calls PowerShell resolver (safe, no Store alias hang).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0resolve_python.ps1"
exit /b %errorlevel%
