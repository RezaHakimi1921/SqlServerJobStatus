@echo off
REM Prints a working Python 3.9+ command to stdout. Exit 1 if not found.
setlocal EnableDelayedExpansion

for %%V in (-3.12 -3.11 -3.10 -3.9 -3) do (
    where py >nul 2>&1
    if !errorlevel! equ 0 (
        py %%V -c "import sys; raise SystemExit(0 if sys.version_info>=(3,9) else 1)" >nul 2>&1
        if !errorlevel! equ 0 (
            endlocal & echo py %%V
            exit /b 0
        )
    )
)

for %%P in (python3 python) do (
    where %%P >nul 2>&1
    if !errorlevel! equ 0 (
        %%P -c "import sys; raise SystemExit(0 if sys.version_info>=(3,9) else 1)" >nul 2>&1
        if !errorlevel! equ 0 (
            endlocal & echo %%P
            exit /b 0
        )
    )
)

for %%F in (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
) do (
    if exist %%F (
        %%F -c "import sys; raise SystemExit(0 if sys.version_info>=(3,9) else 1)" >nul 2>&1
        if !errorlevel! equ 0 (
            endlocal & echo %%F
            exit /b 0
        )
    )
)

endlocal
exit /b 1
