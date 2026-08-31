Coverity Findings Analyzer v1.4 — Windows Setup (One-Click)
=============================================================
Fix for "This app can't run on your PC" — see below.

QUICK RUN (No build needed, works now):
  1. Double-click CoverityTool.bat  (NOT the .exe placeholder)
     - This runs directly via Python (no compatibility issue, no Tcl error)
     - Requires Python 3.10+ installed and added to PATH
     - If Python missing, it will tell you where to download

ALTERNATIVE: Build native EXE for YOUR PC (no Python needed after):
  1. Double-click BUILD_EXE_ON_WINDOWS.bat
     - This builds CoverityTool.exe specifically for YOUR Windows (64-bit)
     - Matches your Windows version, so "can't run on your PC" disappears
     - Takes 2-4 minutes, creates _internal folder with libs (fixes Tcl)
  2. Then double-click CoverityTool.exe

WHAT'S INSIDE:
  CoverityTool.bat               <- WORKS NOW, one-click via Python
  BUILD_EXE_ON_WINDOWS.bat       <- Build real native exe for your PC
  CoverityTool.exe               <- Placeholder until you build (see above) or download from Releases
  _internal/ + libs/             <- Tcl/Tk 8.6, tree-sitter, z3 (fixes Tcl error)
  docs/Coverity_Tool_User_Guide.docx  <- 18 sections, highlighted screenshots
  docs/sample_src/ + sample_report/   <- Demo files

TROUBLESHOOTING "This app can't run on your PC":
  • Cause: The placeholder exe in repo was built on Linux (dummy MZ header), not Windows 64-bit
  • Fix 1: Use CoverityTool.bat instead (works immediately, no build)
  • Fix 2: Run BUILD_EXE_ON_WINDOWS.bat to build a native exe for YOUR Windows (recommended)
  • Fix 3: Download the real Windows exe from GitHub Releases:
      https://github.com/Rakesh0427/Coverity-Tool/releases
      Look for Coverity-Tool-Windows-Setup.zip under Latest Release

Tcl Error fixed: _internal/tcl/tcl8.6 + local_gui.py now sets TCL_LIBRARY via sys._MEIPASS
Source never leaves your machine.
