@echo off
REM Build real Windows exe on YOUR Windows PC (fixes "can't run on your PC" compatibility)
REM This creates a native 64-bit exe that matches your Windows version — no compatibility issue.

echo === Building CoverityTool.exe for YOUR Windows (64-bit) ===
echo This will create dist\CoverityTool\CoverityTool.exe that WILL run on your PC
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
  echo [ERROR] Python not found. Install Python 3.10+ and tick "Add to PATH"
  pause
  exit /b 1
)

if not exist "..\..\CoverityTool.spec" (
  if not exist "CoverityTool.spec" (
    echo [ERROR] CoverityTool.spec not found. Run this from repo root or setup folder
    pause
    exit /b 1
  )
)

echo [1/3] Installing PyInstaller...
pip install --upgrade pip
pip install -r requirements.txt 2>nul || pip install -r ..\requirements.txt 2>nul || echo [WARN] requirements.txt not found, continuing
pip install pyinstaller

echo [2/3] Building with PyInstaller (this takes 2-4 minutes)...
if exist "CoverityTool.spec" (
  pyinstaller CoverityTool.spec --noconfirm --clean
) else (
  pyinstaller ..\CoverityTool.spec --noconfirm --clean
)

echo [3/3] Copying to setup folder...
if exist "dist\CoverityTool\CoverityTool.exe" (
  copy /Y "dist\CoverityTool\CoverityTool.exe" "CoverityTool.exe"
  xcopy /E /I /Y "dist\CoverityTool\_internal" "_internal"
  echo [OK] Built CoverityTool.exe for YOUR Windows — double-click it now!
) else if exist "..\dist\CoverityTool\CoverityTool.exe" (
  copy /Y "..\dist\CoverityTool\CoverityTool.exe" "CoverityTool.exe"
  xcopy /E /I /Y "..\dist\CoverityTool\_internal" "_internal"
  echo [OK] Built CoverityTool.exe
) else (
  echo [ERROR] Build failed — check output above
)

pause
