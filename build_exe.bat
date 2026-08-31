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

REM Force valid Tcl/Tk paths for this interpreter to avoid inherited toolchain
REM variables (for example Tornado) breaking PyInstaller's tkinter probe.
for /f "delims=" %%P in ('python -c "import os,sys; print(os.path.join(sys.base_prefix, 'tcl', 'tcl8.6'))"') do set "TCL_LIBRARY=%%P"
for /f "delims=" %%P in ('python -c "import os,sys; print(os.path.join(sys.base_prefix, 'tcl', 'tk8.6'))"') do set "TK_LIBRARY=%%P"

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
REM Bundle the cppcheck corroboration backend (from the pip wheel) next to the exe
set "CPPCHECK_DIR="
for /f "delims=" %%D in ('python -c "import cppcheck;print(cppcheck.get_cppcheck_dir())" 2^>nul') do set "CPPCHECK_DIR=%%D"
if defined CPPCHECK_DIR (
  if exist "%CPPCHECK_DIR%\cppcheck.exe" (
    copy /Y "%CPPCHECK_DIR%\cppcheck.exe" dist\CoverityTool\ >nul
    echo Copied cppcheck.exe (offline corroboration backend) next to CoverityTool.exe
  ) else if exist "%CPPCHECK_DIR%\cppcheck" (
    copy /Y "%CPPCHECK_DIR%\cppcheck" dist\CoverityTool\cppcheck.exe >nul
    echo Copied cppcheck.exe (offline corroboration backend) next to CoverityTool.exe
  ) else (
    echo [WARN] cppcheck binary not found in the pip wheel directory
  )
) else (
  echo [WARN] cppcheck pip package not installed - corroboration will be disabled in the exe
  echo        Fix: pip install cppcheck (bundles the official cppcheck binary)
)
pause
