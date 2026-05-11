param(
    [switch]$Clean,
    [switch]$SkipChecks
)

$ErrorActionPreference = "Stop"

# Set up logging
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$DistDir = Join-Path $Root "dist"
if (-not (Test-Path $DistDir)) {
    New-Item -ItemType Directory -Path $DistDir -Force | Out-Null
}
$LogFile = Join-Path $DistDir "build-$(Get-Date -Format 'yyyy-MM-dd_HH-mm-ss').log"

# Helper function to log output
function Log-Output {
    param(
        [Parameter(ValueFromPipeline = $true)]
        [Object]$InputObject
    )
    process {
        $InputObject | Tee-Object -FilePath $LogFile -Append
    }
}

# Header
"=== Bubba Media Viewer Build Process ===" | Log-Output
"Build started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Log-Output
"Log file: $LogFile" | Log-Output
"" | Log-Output

# Kill any running instances and clean up Python processes before build
"Cleaning up any existing builds and processes..." | Log-Output
Get-Process BubbaMediaViewer -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500
"Cleanup complete" | Log-Output
"" | Log-Output

$DistDir = Join-Path $Root "dist"
$BuildDir = Join-Path $Root "build"
$SpecPath = Join-Path $Root "packaging\bubba_media_viewer.spec"
$AppDistDir = Join-Path $DistDir "BubbaMediaViewer"
$ZipPath = Join-Path $DistDir "BubbaMediaViewer-windows-x64.zip"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

if (Test-Path $VenvPython) {
    $Python = $VenvPython
} else {
    $Python = "python"
}

Set-Location $Root

if ($Clean) {
    "Performing clean build..." | Log-Output
    if (Test-Path $BuildDir) {
        Remove-Item -LiteralPath $BuildDir -Recurse -Force
    }
    if (Test-Path $AppDistDir) {
        Remove-Item -LiteralPath $AppDistDir -Recurse -Force
    }
    if (Test-Path $ZipPath) {
        Remove-Item -LiteralPath $ZipPath -Force
    }
    if (Test-Path ".pytest_tmp") {
        Remove-Item -LiteralPath ".pytest_tmp" -Recurse -Force
    }
    "" | Log-Output
} else {
    "Removing old build artifacts..." | Log-Output
    if (Test-Path $AppDistDir) {
        Remove-Item -LiteralPath $AppDistDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    # Clean pytest temp directory to avoid permission issues
    if (Test-Path ".pytest_tmp") {
        Remove-Item -LiteralPath ".pytest_tmp" -Recurse -Force -ErrorAction SilentlyContinue
    }
    "" | Log-Output
}

"Installing/updating pip..." | Log-Output
& $Python -m pip install --upgrade pip 2>&1 | Log-Output
"" | Log-Output

"Installing Python dependencies..." | Log-Output
& $Python -m pip install -r requirements.txt -r requirements-build.txt 2>&1 | Log-Output
"" | Log-Output

if (-not $SkipChecks) {
    "Running ruff checks..." | Log-Output
    & $Python -m ruff check . 2>&1 | Log-Output
    "" | Log-Output
    
    "Running mypy type checks..." | Log-Output
    & $Python -m mypy 2>&1 | Log-Output
    "" | Log-Output
    
    "Running pytest..." | Log-Output
    & $Python -m pytest -q --basetemp=.pytest_tmp 2>&1 | Log-Output
    "" | Log-Output

    "Installing frontend dependencies..." | Log-Output
    if (Test-Path (Join-Path $Root "package-lock.json")) {
        npm ci 2>&1 | Log-Output
    } else {
        npm install 2>&1 | Log-Output
    }
    "" | Log-Output
    
    "Running eslint..." | Log-Output
    npm run lint:frontend 2>&1 | Log-Output
    "" | Log-Output
    
    "Checking prettier formatting..." | Log-Output
    npm run format:frontend:check 2>&1 | Log-Output
    "" | Log-Output
}

"Building with PyInstaller..." | Log-Output
$ErrorActionPreference = "Continue"
& $Python -m PyInstaller --noconfirm $SpecPath 2>&1 | Log-Output
$ErrorActionPreference = "Stop"
"" | Log-Output

# Check if build succeeded by looking for output files
if (-not (Test-Path $AppDistDir)) {
    "" | Log-Output
    "=== Build Failed ===" | Log-Output
    "PyInstaller build failed - output directory not found" | Log-Output
    "Build log: $LogFile" | Log-Output
    exit 1
}

"Creating archive..." | Log-Output
if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Compress-Archive -Path (Join-Path $AppDistDir "*") -DestinationPath $ZipPath 2>&1 | Log-Output
"" | Log-Output

"=== Build Completed Successfully ===" | Log-Output
"Built portable app: $AppDistDir" | Log-Output
"Built archive: $ZipPath" | Log-Output
"Build log: $LogFile" | Log-Output
"Build finished: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Log-Output
"" | Log-Output
