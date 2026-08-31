@echo off
REM Coverity Findings Analyzer v1.4 — One-click launcher (no exe needed)
REM Works on any Windows with Python 3.10+ installed. No Tcl error.

setlocal
set "HERE=%~dp0"
echo Starting Coverity Findings Analyzer...
echo.

REM Try Python from PATH
python --version >nul 2>&1
if %errorlevel% neq 0 (
  echo [ERROR] Python not found. Please install Python 3.10+ from https://python.org
  echo         Tick "Add Python to PATH" during install, then double-click this bat again.
  echo.
  echo Alternative: Use the pre-built CoverityTool.exe from GitHub Releases (no Python needed)
  echo   https://github.com/Rakesh0427/Coverity-Tool/releases
  pause
  exit /b 1
)

REM Check if we are in the Windows Setup folder (with _internal) or in repo root
if exist "%HERE%local_gui.py" (
  REM Running from repo root
  python "%HERE%local_gui.py"
) else if exist "%HERE%..\local_gui.py" (
  REM Running from setup/docs subfolder?
  python "%HERE%..\local_gui.py"
) else (
  REM Running from setup folder that has no local_gui.py — need to copy or use installed
  echo [INFO] Looking for local_gui.py...
  if exist "%HERE%..\Coverity-Tool\local_gui.py" (
    python "%HERE%..\Coverity-Tool\local_gui.py"
  ) else (
    echo [ERROR] local_gui.py not found. Please unzip the full Coverity-Tool-Setup.zip
    echo         It should contain Coverity-Tool-Windows-Setup-1.4 + docs + local_gui.py
    pause
    exit /b 1
  )
)
