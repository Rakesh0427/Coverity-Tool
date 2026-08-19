# Fixes Tcl conflict between Tornado (Tcl 8.0) and Python tkinter (Tcl 8.6)
$pyHome = "C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.13_3.13.3824.0_x64__qbz5n2kfra8p0"
$env:TCL_LIBRARY = "$pyHome\lib\tcl8.6"
$env:TK_LIBRARY  = "$pyHome\lib\tk8.6"
$env:TCLLIBPATH  = ""

python "$PSScriptRoot\local_gui.py"
