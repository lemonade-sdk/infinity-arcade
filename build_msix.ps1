# Lemonade Arcade MSIX Build Script
# This script builds the Lemonade Arcade application and packages it as an MSIX installer

param(
    [switch]$Clean,
    [switch]$SkipBuild,
    [string]$OutputDir = "dist"
)

Write-Host "Lemonade Arcade MSIX Builder" -ForegroundColor Green
Write-Host "=============================" -ForegroundColor Green

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
    if (Test-Path "msix_staging") { Remove-Item -Recurse -Force "msix_staging" }
}

# Install dependencies
Write-Host "Installing build dependencies..." -ForegroundColor Cyan
Invoke-Command-Safe "python -m pip install --upgrade pip" "Failed to upgrade pip"
Invoke-Command-Safe "python -m pip install pyinstaller" "Failed to install PyInstaller"

# Build executable if not skipping
if (-not $SkipBuild) {
    Write-Host "Building executable..." -ForegroundColor Cyan
    Invoke-Command-Safe "python -m PyInstaller lemonade_arcade.spec" "Failed to build executable"
    
    # Verify executable was created
    if (-not (Test-Path "dist\LemonadeArcade.exe")) {
        Write-Error "Executable not found after build"
        exit 1
    }
    
    Write-Host "Executable built successfully!" -ForegroundColor Green
}

# Find Windows SDK makeappx.exe
Write-Host "Looking for Windows SDK tools..." -ForegroundColor Cyan

$PossiblePaths = @(
    "${env:ProgramFiles(x86)}\Windows Kits\10\bin\10.0.22621.0\x64\makeappx.exe",
    "${env:ProgramFiles(x86)}\Windows Kits\10\bin\10.0.19041.0\x64\makeappx.exe",
    "${env:ProgramFiles(x86)}\Windows Kits\10\bin\10.0.18362.0\x64\makeappx.exe",
    "${env:ProgramFiles}\Windows Kits\10\bin\10.0.22621.0\x64\makeappx.exe"
)

$MakeAppX = $null
foreach ($Path in $PossiblePaths) {
    if (Test-Path $Path) {
        $MakeAppX = $Path
        Write-Host "Found makeappx.exe at: $Path" -ForegroundColor Green
        break
    }
}

if (-not $MakeAppX) {
    Write-Error "makeappx.exe not found. Please install Windows 10 SDK from: https://developer.microsoft.com/en-us/windows/downloads/windows-10-sdk/"
    exit 1
}

# Create MSIX staging directory
Write-Host "Preparing MSIX package..." -ForegroundColor Cyan

$StagingDir = "msix_staging"
if (Test-Path $StagingDir) { Remove-Item -Recurse -Force $StagingDir }
New-Item -ItemType Directory -Path $StagingDir | Out-Null

# Copy executable
Copy-Item "dist\LemonadeArcade.exe" "$StagingDir\LemonadeArcade.exe"

# Copy manifest
Copy-Item "msix\Package.appxmanifest" "$StagingDir\AppxManifest.xml"

# Create Assets directory and copy assets
New-Item -ItemType Directory -Path "$StagingDir\Assets" | Out-Null

# Copy any existing assets
if (Test-Path "msix\Assets\*.png") {
    Copy-Item "msix\Assets\*.png" "$StagingDir\Assets\"
}

# Create default assets if none exist
$RequiredAssets = @(
    @{Name="StoreLogo.png"; Size="50x50"},
    @{Name="Square150x150Logo.png"; Size="150x150"},
    @{Name="Square44x44Logo.png"; Size="44x44"},
    @{Name="Wide310x150Logo.png"; Size="310x150"},
    @{Name="SplashScreen.png"; Size="620x300"}
)

foreach ($Asset in $RequiredAssets) {
    $AssetPath = "$StagingDir\Assets\$($Asset.Name)"
    if (-not (Test-Path $AssetPath)) {
        Write-Host "Creating placeholder asset: $($Asset.Name) ($($Asset.Size))" -ForegroundColor Yellow
        # Create a minimal 1x1 PNG (would need proper images in production)
        # For now, create an empty file as placeholder
        New-Item -ItemType File -Path $AssetPath | Out-Null
    }
}

# Ensure output directory exists
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

# Create MSIX package
$OutputMsix = "$OutputDir\LemonadeArcade.msix"
Write-Host "Creating MSIX package: $OutputMsix" -ForegroundColor Cyan

Write-Host "Running: `"$MakeAppX`" pack /d `"$StagingDir`" /p `"$OutputMsix`"" -ForegroundColor Yellow
& $MakeAppX pack /d $StagingDir /p $OutputMsix

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to create MSIX package"
    exit 1
}

# Clean up staging directory
Remove-Item -Recurse -Force $StagingDir

Write-Host "" -ForegroundColor Green
Write-Host "Build completed successfully!" -ForegroundColor Green
Write-Host "Output files:" -ForegroundColor Green
Write-Host "  - Executable: $(Resolve-Path "dist\LemonadeArcade.exe")" -ForegroundColor White
Write-Host "  - MSIX Package: $(Resolve-Path $OutputMsix)" -ForegroundColor White
Write-Host "" -ForegroundColor Green
Write-Host "To install the MSIX package:" -ForegroundColor Cyan
Write-Host "  1. Double-click the .msix file" -ForegroundColor White
Write-Host "  2. Or use: Add-AppxPackage -Path '$OutputMsix'" -ForegroundColor White
