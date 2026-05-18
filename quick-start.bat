@echo off
echo ========================================
echo Inventory Management System - Quick Start
echo ========================================
echo.

:: Check Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.9 or higher
    pause
    exit /b 1
)

echo Python found!
python --version
echo.

:: Navigate to backend
cd backend

:: Create virtual environment
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    echo Virtual environment created!
) else (
    echo Virtual environment already exists
)

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Install dependencies
echo Installing dependencies...
pip install -r requirements.txt --quiet

:: Create .env file
if not exist ".env" (
    echo Creating .env file...
    copy .env.example .env
    echo .env file created with default settings
) else (
    echo .env file already exists
)

:: Create directories
if not exist "app\uploads" mkdir app\uploads
if not exist "app\models" mkdir app\models

echo.
echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo Next Steps:
echo 1. Start the backend server:
echo    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
echo.
echo 2. Open frontend\index.html in your browser
echo.
echo 3. Upload your CSV data and start analyzing!
echo.
echo API Documentation: http://127.0.0.1:8000/docs
echo.
pause
