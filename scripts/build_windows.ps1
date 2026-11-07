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
function Write-LogOutput {
    param(
        [Parameter(ValueFromPipeline = $true)]
        [Object]$InputObject
    )
    process {
        $InputObject | Tee-Object -FilePath $LogFile -Append
    }
}

function Invoke-LoggedNativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$ArgumentList
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $FilePath @ArgumentList 2>&1 | Write-LogOutput
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -ne 0) {
        throw "Command failed with exit code ${exitCode}: $FilePath $($ArgumentList -join ' ')"
    }
}

# Header
"=== Bubba Media Viewer Build Process ===" | Write-LogOutput
"Build started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Write-LogOutput
"Log file: $LogFile" | Write-LogOutput
"" | Write-LogOutput

# Kill any running instances and clean up Python processes before build
"Cleaning up any existing builds and processes..." | Write-LogOutput
Get-Process BubbaMediaViewer -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500
"Cleanup complete" | Write-LogOutput
"" | Write-LogOutput

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
    "Performing clean build..." | Write-LogOutput
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
    "" | Write-LogOutput
} else {
    "Removing old build artifacts..." | Write-LogOutput
    if (Test-Path $AppDistDir) {
        Remove-Item -LiteralPath $AppDistDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    # Clean pytest temp directory to avoid permission issues
    if (Test-Path ".pytest_tmp") {
        Remove-Item -LiteralPath ".pytest_tmp" -Recurse -Force -ErrorAction SilentlyContinue
    }
    "" | Write-LogOutput
}

"Installing/updating pip..." | Write-LogOutput
Invoke-LoggedNativeCommand $Python -m pip install --upgrade pip
"" | Write-LogOutput

"Installing Python dependencies..." | Write-LogOutput
Invoke-LoggedNativeCommand $Python -m pip install -r requirements.txt -r requirements-build.txt
"" | Write-LogOutput

if (-not $SkipChecks) {
    "Installing browser test dependencies..." | Write-LogOutput
    Invoke-LoggedNativeCommand $Python -m pip install -r requirements-dev.txt
    if (-not $env:PLAYWRIGHT_BROWSERS_PATH) {
        $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $Root "build\browsers"
    }
    Invoke-LoggedNativeCommand $Python -m playwright install chromium

    "Running ruff checks..." | Write-LogOutput
    Invoke-LoggedNativeCommand $Python -m ruff check .
    "" | Write-LogOutput
    
    "Running mypy type checks..." | Write-LogOutput
    Invoke-LoggedNativeCommand $Python -m mypy
    "" | Write-LogOutput
    
    "Running pytest..." | Write-LogOutput
    Invoke-LoggedNativeCommand $Python -m pytest -q --basetemp=.pytest_tmp
    "" | Write-LogOutput

    "Installing frontend dependencies..." | Write-LogOutput
    if (Test-Path (Join-Path $Root "package-lock.json")) {
        Invoke-LoggedNativeCommand "npm.cmd" ci
    } else {
        Invoke-LoggedNativeCommand "npm.cmd" install
    }
    "" | Write-LogOutput
    
    "Running eslint..." | Write-LogOutput
    Invoke-LoggedNativeCommand "npm.cmd" run lint:frontend
    "" | Write-LogOutput
    
    "Checking prettier formatting..." | Write-LogOutput
    Invoke-LoggedNativeCommand "npm.cmd" run format:frontend:check
    Invoke-LoggedNativeCommand "npm.cmd" run test:frontend
    "" | Write-LogOutput
}

"Building with PyInstaller..." | Write-LogOutput
Invoke-LoggedNativeCommand $Python -m PyInstaller --noconfirm $SpecPath
"" | Write-LogOutput

# Check if build succeeded by looking for output files
if (-not (Test-Path $AppDistDir)) {
    "" | Write-LogOutput
    "=== Build Failed ===" | Write-LogOutput
    "PyInstaller build failed - output directory not found" | Write-LogOutput
    "Build log: $LogFile" | Write-LogOutput
    exit 1
}

"Creating archive..." | Write-LogOutput
if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Compress-Archive -Path (Join-Path $AppDistDir "*") -DestinationPath $ZipPath 2>&1 | Write-LogOutput
"" | Write-LogOutput

"=== Build Completed Successfully ===" | Write-LogOutput
"Built portable app: $AppDistDir" | Write-LogOutput
"Built archive: $ZipPath" | Write-LogOutput
"Build log: $LogFile" | Write-LogOutput
"Build finished: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Write-LogOutput
"" | Write-LogOutput
