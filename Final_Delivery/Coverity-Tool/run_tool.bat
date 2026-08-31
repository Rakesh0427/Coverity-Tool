@echo off
REM Direct launcher - no Tcl error (TCL_LIBRARY handled in local_gui.py for frozen exe)
REM If CoverityTool.exe missing or Tcl error, this will still work via Python fallback
if exist CoverityTool.exe (
  start "" CoverityTool.exe
  exit /b
)
echo CoverityTool.exe not found - trying Python fallback...
python local_gui.py 2>nul
if errorlevel 1 (
  echo Please install Python 3.10+ or download the Release ZIP with exe
  pause
)
