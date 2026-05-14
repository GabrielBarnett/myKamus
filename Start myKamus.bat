@echo off
setlocal
cd /d "%~dp0"

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
    echo myKamus could not finish setup.
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
