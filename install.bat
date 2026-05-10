@echo off
REM Install script for Asset Viewer Standalone
setlocal enabledelayedexpansion

REM Resolve project root (script directory)
set "PROJECT_DIR=%~dp0"

echo.
echo ========================================
echo  Asset Viewer Standalone - Setup
echo ========================================
echo.

REM Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
	echo Error: Python is not installed or not in PATH
	echo Please install Python 3.10 or later from https://www.python.org/
	pause
	exit /b 1
)

echo Detected Python:
python --version

REM Create virtual environment
echo.
echo Creating virtual environment...
if exist "!PROJECT_DIR!.venv" (
	echo Virtual environment already exists. Skipping creation.
) else (
	python -m venv "!PROJECT_DIR!.venv"
	if errorlevel 1 (
		echo Error: Failed to create virtual environment
		pause
		exit /b 1
	)
)

REM Activate virtual environment
echo Activating virtual environment...
call "!PROJECT_DIR!.venv\Scripts\activate.bat"

REM Upgrade pip
echo.
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install requirements
echo.
echo Installing dependencies...
pip install -r "!PROJECT_DIR!requirements.txt"
if errorlevel 1 (
	echo Error: Failed to install dependencies
	pause
	exit /b 1
)

echo.
echo ========================================
echo  Setup Complete!
echo ========================================
echo.
echo To start the backend server, run:
echo   start.bat
echo.
echo Or manually:
echo   .venv\Scripts\activate
echo   python backend/server.py
echo.
echo Then open http://localhost:5001/ in your browser.
echo.
pause
endlocal
