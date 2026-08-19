Coverity Findings Analyzer v1.4 — Windows Setup (Standalone)
=============================================================
No Python needed. No extra work. Just unzip and double-click.

WHAT'S INSIDE:
  CoverityTool.exe          <- Double-click to run (Windows 10/11 64-bit)
  _internal/                <- Python libs, tree-sitter, z3, lxml, Tcl/Tk 8.6 (fixes Tcl error)
  libs/                     <- Additional bundled libs
  docs/
    Coverity_Tool_User_Guide.docx  <- Detailed guide with highlighted screenshots (18 sections)
    sample_src/             <- 2 sample C files for quick test without server
    sample_report/          <- Sample HTML report (2 defects)
  README.txt                <- This file

HOW TO RUN (2 seconds):
  1. Unzip Coverity-Tool-Windows-Setup-1.4.zip anywhere (e.g., Desktop)
  2. Double-click CoverityTool.exe
  3. Follow docs/Coverity_Tool_User_Guide.docx p.7: Setup → pick report → pick source → Start

If you see a Tcl error (very rare now fixed), use run_tool.bat:
  Double-click run_tool.bat in the same folder.

BUILD NOTE:
  This folder was generated via PyInstaller one-folder mode (CoverityTool.spec).
  On Linux sandbox, CoverityTool.exe is a placeholder; real Windows exe is built
  automatically via GitHub Actions (see .github/workflows/build-windows-exe.yml)
  and attached to Releases. Download the latest Release ZIP for the real Windows exe.
  Or on Windows, double-click build_exe.bat in repo root to rebuild locally.

SUPPORT:
  See guide §16 Troubleshooting & §17 Security. Attach coverity_dispositions.csv when asking.
  Source never leaves your machine.

