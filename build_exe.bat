@echo off
REM Build CoverityTool.exe — one-folder, windowed
REM Requires: Python 3.10+ installed and added to PATH (check from python.org)
REM Run this file by double-clicking in Explorer.

echo === Coverity Findings Analyzer — EXE Build ===
echo.

REM Check Python
python --version 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found in PATH. Install Python 3.10+ from https://python.org and tick "Add to PATH".
  pause
  exit /b 1
)

echo [1/4] Creating venv .venv_build ...
python -m venv .venv_build
if errorlevel 1 (
  echo [ERROR] venv creation failed. Ensure python3-full is installed.
  pause
  exit /b 1
)

echo [2/4] Installing dependencies (this may take 1-2 minutes)...
call .venv_build\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

echo [3/4] Sanity check compile...
python -m compileall -q .
if errorlevel 1 (
  echo [WARN] compileall reported errors — check output above.
)

echo [4/4] Running PyInstaller (one-folder, windowed) ...
pyinstaller CoverityTool.spec --noconfirm --clean

echo.
echo === Build complete ===
echo Look for: dist\CoverityTool\CoverityTool.exe  (plus _internal folder)
echo Ship the ENTIRE dist\CoverityTool folder as a zip — do NOT move the exe alone.
echo Test: double-click dist\CoverityTool\CoverityTool.exe  or run dist\CoverityTool\run_tool.bat
echo.
REM Copy docs into dist for shipping
if exist docs\Coverity_Tool_User_Guide.docx (
  mkdir dist\CoverityTool\docs 2>nul
  copy /Y docs\Coverity_Tool_User_Guide.docx dist\CoverityTool\docs\ >nul
  echo Copied User Guide to dist\CoverityTool\docs\
)
pause
