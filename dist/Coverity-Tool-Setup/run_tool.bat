@echo off
REM Launcher that sets Tcl/Tk paths correctly (fixes _tkinter Tcl_FindExecutable issues on some Windows)
REM Use this if direct double-click on CoverityTool.exe shows a Tcl error.

setlocal
set "HERE=%~dp0"
REM PyInstaller one-folder layout: exe is at dist\CoverityTool\CoverityTool.exe with _internal beside it
REM If you copied exe alone, this will fail — keep _internal folder beside exe!

REM Try to set Tcl/Tk lib paths if bundled
if exist "%HERE%_internal\tcl8.6" set "TCL_LIBRARY=%HERE%_internal\tcl8.6"
if exist "%HERE%_internal\tk8.6" set "TK_LIBRARY=%HERE%_internal\tk8.6"
if exist "%HERE%tcl\tcl8.6" set "TCL_LIBRARY=%HERE%tcl\tcl8.6"

start "" "%HERE%CoverityTool.exe"
