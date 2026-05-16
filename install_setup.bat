@echo off
title TomeWeaver Setup
color 0B

echo ===================================================
echo             TomeWeaver - Initial Setup
echo ===================================================
echo.

:: 1. Check if Python is installed and accessible
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your system PATH.
    echo Please install Python 3.10+ from https://python.org and ensure you check the "Add Python to PATH" box.
    echo.
    pause
    exit /b
)

echo [1/3] Creating Python Virtual Environment (venv)...
python -m venv venv
if %errorlevel% neq 0 (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b
)

echo [2/3] Activating Virtual Environment...
call venv\Scripts\activate

echo [3/3] Installing required packages...
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install requirements. Check your internet connection.
    pause
    exit /b
)

echo.
echo ===================================================
echo   Setup Complete!
echo ===================================================
echo.

pause