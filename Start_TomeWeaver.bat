@echo off
title TomeWeaver
color 0B

echo ===================================================
echo             Starting TomeWeaver Engine
echo ===================================================
echo.

:: 1. Verify Python is installed and accessible
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to your system PATH.
    echo Please install Python 3.10+ from python.org and try again.
    echo.
    pause
    exit /b 1
)

:: 2. Activate Virtual Environment (If it exists)
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo [WARNING] Virtual environment not found. 
    echo Did you run 'setup.bat' first? Attempting to use global Python...
    echo.
)

:: 3. Launch the engine (No arguments triggers the Main Menu Wizard)
python scripts/tome_weaver.py

:: 4. Graceful exit/pause handling
if %errorlevel% neq 0 (
    echo.
    echo [SYSTEM] The engine exited with an error. See details above.
    pause
) else (
    timeout /t 2 >nul
)

exit /b 0