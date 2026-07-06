@echo off
setlocal EnableDelayedExpansion
set "PYTHON_CMD="

REM Try Python launcher first (most reliable on Windows)
for %%V in (-3.12 -3.11 -3.10 -3.9 -3) do (
    where py >nul 2>&1
    if not errorlevel 1 (
        py %%V -c "import sys; raise SystemExit(0 if sys.version_info>=(3,9) else 1)" >nul 2>&1
        if not errorlevel 1 (
            set "PYTHON_CMD=py %%V"
            goto :found
        )
    )
)

REM Direct python executables
for %%P in (python3 python) do (
    where %%P >nul 2>&1
    if not errorlevel 1 (
        %%P -c "import sys; raise SystemExit(0 if sys.version_info>=(3,9) else 1)" >nul 2>&1
        if not errorlevel 1 (
            set "PYTHON_CMD=%%P"
            goto :found
        )
    )
)

call "%~dp0print_python_help.cmd"
exit /b 1

:found
endlocal & set "PYTHON_CMD=%PYTHON_CMD%"
exit /b 0
