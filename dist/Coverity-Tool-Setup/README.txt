Coverity Findings Analyzer — Quick Start for Testers
=====================================================
Version 1.4 Expert CWE Edition | 19-Aug-2026

1. UNZIP
   Unzip Coverity-Tool-Setup.zip to a folder, e.g. C:\Tools\Coverity-Tool-Setup\
   Keep the whole folder — do NOT move CoverityTool.exe out of its folder (it needs _internal\ beside it).

2. RUN
   Double-click CoverityTool.exe
   (If a Tcl error appears, double-click run_tool.bat or run_tool.ps1 instead)

3. TRY WITH SAMPLE (no server needed)
   Setup page → Coverity Report → Browse to docs\sample_report\ (or any HTML folder with index.html)
   Source Code Root → Browse to docs\sample_src\ (or your repo root)
   Output Folder → Browse to Documents
   Code Language → C++
   ▶ Start Disposition → wait for Analysis → Results

4. PULL FROM SERVER (optional)
   Setup → ⬇ Pull from Coverity → Host/Port/User/Pass → Test Connection → Project → Stream → Pull
   Check Allow self-signed certificate if your Coverity uses self-signed cert.

5. REVIEW & PUSH
   Results → filter by Bug/False positive → double-click row → read Comment (CWE/CERT/OWASP) + Proposed Fix (code line)
   → Accept or Override → coverity_final_decisions.csv is updated
   Header → ⬆ Push to Coverity → pick CSV → Validate → Push

For details with screenshots see: docs\Coverity_Tool_User_Guide.docx (open in Word)

Requirements (for EXE): Windows 10/11 64-bit, no Python needed.
For Python run: python local_gui.py (see docs guide §2.2)

Support: Contact Tool Owner — attach coverity_dispositions.csv + needs_review_breakdown.txt + pull log if issue.
Source never leaves your machine.
