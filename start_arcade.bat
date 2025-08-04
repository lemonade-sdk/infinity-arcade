@echo off
REM Lemonade Arcade Launcher for Windows
REM This script activates the conda environment and starts the application

echo Starting Lemonade Arcade...
echo ================================

REM Check if conda is available
where conda >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: Conda not found in PATH
    echo Please install Miniconda or Anaconda first
    pause
    exit /b 1
)

REM Check if arcade environment exists
conda info --envs | findstr "arcade" >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: 'arcade' conda environment not found
    echo Please run: conda create -n arcade python=3.11 -y
    pause
    exit /b 1
)

REM Activate environment and start application
echo Activating conda environment 'arcade'...
call conda activate arcade

echo Checking installation...
python test_installation.py
if %errorlevel% neq 0 (
    echo Installation check failed. Please run: pip install -e .
    pause
    exit /b 1
)

echo Starting Lemonade Arcade...
echo The application will open in your web browser.
echo Press Ctrl+C to stop the server.
echo.

lemonade-arcade
