# Lemonade Arcade Executable Build Script
# This script builds the Lemonade Arcade application using PyInstaller

param(
    [switch]$Clean,
    [string]$OutputDir = "dist"
)

Write-Host "Lemonade Arcade Executable Builder" -ForegroundColor Green
Write-Host "==================================" -ForegroundColor Green

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

# Function to run commands with error handling
function Invoke-Command-Safe {
    param([string]$Command, [string]$ErrorMessage = "Command failed")
    
    Write-Host "Running: $Command" -ForegroundColor Yellow
    Invoke-Expression $Command
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error $ErrorMessage
        exit 1
    }
}

# Clean previous builds if requested
if ($Clean) {
    Write-Host "Cleaning previous builds..." -ForegroundColor Cyan
    if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
    if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
    if (Test-Path "__pycache__") { Remove-Item -Recurse -Force "__pycache__" }
}

# Install dependencies
Write-Host "Installing build dependencies..." -ForegroundColor Cyan
Invoke-Command-Safe "python -m pip install --upgrade pip" "Failed to upgrade pip"
Invoke-Command-Safe "python -m pip install pyinstaller" "Failed to install PyInstaller"

# Build executable
Write-Host "Building executable with PyInstaller..." -ForegroundColor Cyan
Invoke-Command-Safe "python -m PyInstaller lemonade_arcade.spec" "Failed to build executable"

# Verify executable was created
$ExePath = "$OutputDir\LemonadeArcade.exe"
if (-not (Test-Path $ExePath)) {
    Write-Error "Executable not found at $ExePath"
    exit 1
}

# Show build results
$ExeFile = Get-Item $ExePath
Write-Host "" -ForegroundColor Green
Write-Host "Build completed successfully!" -ForegroundColor Green
Write-Host "Output file:" -ForegroundColor Green
Write-Host "  - Executable: $(Resolve-Path $ExePath)" -ForegroundColor White
Write-Host "  - Size: $([math]::Round($ExeFile.Length / 1MB, 2)) MB" -ForegroundColor White
Write-Host "" -ForegroundColor Green
Write-Host "To run the application:" -ForegroundColor Cyan
Write-Host "  Double-click: $ExePath" -ForegroundColor White
Write-Host "  Or from command line: $ExePath" -ForegroundColor White
