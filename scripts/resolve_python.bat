@echo off
REM Prints a working Python command (py -3, py, python3, python) to stdout.
REM Exit 0 on success, 1 if no real Python installation found.
setlocal EnableDelayedExpansion

where py >nul 2>&1
if !errorlevel! equ 0 (
    py -3 -c "import sys" >nul 2>&1
    if !errorlevel! equ 0 (
        endlocal & echo py -3
        exit /b 0
    )
)

where py >nul 2>&1
if !errorlevel! equ 0 (
    py -c "import sys" >nul 2>&1
    if !errorlevel! equ 0 (
        endlocal & echo py
        exit /b 0
    )
)

where python3 >nul 2>&1
if !errorlevel! equ 0 (
    python3 -c "import sys" >nul 2>&1
    if !errorlevel! equ 0 (
        endlocal & echo python3
        exit /b 0
    )
)

where python >nul 2>&1
if !errorlevel! equ 0 (
    python -c "import sys" >nul 2>&1
    if !errorlevel! equ 0 (
        endlocal & echo python
        exit /b 0
    )
)

endlocal
exit /b 1
