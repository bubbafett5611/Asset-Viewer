param(
    [switch]$Clean,
    [switch]$SkipChecks
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
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
    if (Test-Path $BuildDir) {
        Remove-Item -LiteralPath $BuildDir -Recurse -Force
    }
    if (Test-Path $AppDistDir) {
        Remove-Item -LiteralPath $AppDistDir -Recurse -Force
    }
    if (Test-Path $ZipPath) {
        Remove-Item -LiteralPath $ZipPath -Force
    }
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt -r requirements-build.txt

if (-not $SkipChecks) {
    & $Python -m ruff check .
    & $Python -m mypy
    & $Python -m pytest -q

    if (Test-Path (Join-Path $Root "package-lock.json")) {
        npm ci
    } else {
        npm install
    }
    npm run lint:frontend
    npm run format:frontend:check
}

& $Python -m PyInstaller --noconfirm $SpecPath

if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

Compress-Archive -Path (Join-Path $AppDistDir "*") -DestinationPath $ZipPath

Write-Host "Built portable app: $AppDistDir"
Write-Host "Built archive: $ZipPath"
