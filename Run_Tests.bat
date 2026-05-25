@echo off
title TomeWeaver Tests
color 0B

echo ===================================================
echo             Running TomeWeaver Tests
echo ===================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found.
    echo Run setup.bat first, then retry.
    echo.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python -m pytest tests/ -v --tb=short %*

if %errorlevel% neq 0 (
    echo.
    echo [SYSTEM] One or more tests failed.
    pause
    exit /b %errorlevel%
)

echo.
echo [OK] All tests passed.
timeout /t 2 >nul
exit /b 0
