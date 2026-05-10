@echo off
REM Start backend server (prefer virtualenv Python if available)
setlocal enabledelayedexpansion
REM Resolve project root (script directory)
set "PROJECT_DIR=%~dp0"
REM Path to venv python
set "VENV_PY=%PROJECT_DIR%.venv\Scripts\python.exe"
if exist "!VENV_PY!" (
	set "PY_EXEC=!VENV_PY!"
) else (
	set "PY_EXEC=python"
)
pushd "!PROJECT_DIR!backend"
start "Asset Viewer Backend" cmd /k ""!PY_EXEC!" server.py"
popd
endlocal