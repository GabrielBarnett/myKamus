@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "MYKAMUS_DIR=%~dp0"
if defined PYTHONPATH (
    set "PYTHONPATH=%MYKAMUS_DIR%.mykamus_vendor;!PYTHONPATH!"
) else (
    set "PYTHONPATH=%MYKAMUS_DIR%.mykamus_vendor"
)

set "PYTHON_CMD="

py -3 --version >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PYTHON_CMD=py -3"
) else (
    python --version >nul 2>nul
    if %ERRORLEVEL%==0 (
        set "PYTHON_CMD=python"
    )
)

if "%PYTHON_CMD%"=="" (
    echo myKamus needs Python before it can start.
    echo Install Python from https://www.python.org/downloads/
    echo During installation, tick "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

%PYTHON_CMD% -m gui_app.preflight
if not %ERRORLEVEL%==0 (
    echo.
    echo myKamus could not install or load its local Python packages.
    echo Please send myKamus_setup.log to your internal support person.
    pause
    exit /b 1
)

%PYTHON_CMD% -m gui_app.app
if not %ERRORLEVEL%==0 (
    echo.
    echo myKamus closed with an error.
    pause
    exit /b 1
)

endlocal
