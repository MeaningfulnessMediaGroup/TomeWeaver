@echo off
setlocal EnableDelayedExpansion

:: ---------------------------------------------------------
:: TOMEWEAVER ADVENTURE LAUNCHER
:: ---------------------------------------------------------
:: This script provides a quick-launch shortcut for a specific adventure.
:: To create a launcher for a new story, duplicate this file and change 
:: the ADVENTURE_PATH and ADVENTURE_NAME variable below.
:: ---------------------------------------------------------

set "ADVENTURE_PATH=adventures\Mallow the Cat"
set "ADVENTURE_NAME=Mallow the Cat"
 
 
title TomeWeaver: %ADVENTURE_NAME%

echo ===================================================
echo   Launching TomeWeaver Engine
echo   Adventure: %ADVENTURE_NAME%
echo ===================================================
echo.

:: 1. Verify Python is installed and accessible
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to your system PATH.
    echo Please install Python 3.10 or higher from python.org and try again.
    echo.
    pause
    exit /b 1
)

:: 2. Activate Virtual Environment (If it exists)
:: This ensures the engine uses the isolated packages installed via setup.bat
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo [WARNING] Virtual environment not found. 
    echo Did you run 'setup.bat' first? Attempting to use global Python...
    echo.
)

:: 3. Launch the engine
:: Pass the folder path of the specific adventure to the python script
python scripts/tome_weaver.py "%ADVENTURE_PATH%"

:: 4. Graceful exit/pause handling
if %errorlevel% neq 0 (
    echo.
    echo [SYSTEM] The engine exited with an error. See details above.
    pause
) else (
    echo.
    echo [SYSTEM] Adventure closed safely.
    timeout /t 3 >nul
)

exit /b 0