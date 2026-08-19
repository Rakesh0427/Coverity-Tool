# PowerShell launcher — sets Tcl/Tk paths then starts exe
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$exe = Join-Path $here "CoverityTool.exe"
if (-not (Test-Path $exe)) {
  Write-Host "Not found: $exe  — did you build with build_exe.bat? Look in dist\CoverityTool\" -ForegroundColor Red
  pause; exit 1
}
# Set Tcl/Tk if needed
if (Test-Path (Join-Path $here "_internal\tcl8.6")) { $env:TCL_LIBRARY = Join-Path $here "_internal\tcl8.6" }
if (Test-Path (Join-Path $here "_internal\tk8.6")) { $env:TK_LIBRARY = Join-Path $here "_internal\tk8.6" }
Start-Process -FilePath $exe
