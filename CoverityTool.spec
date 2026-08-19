# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Coverity Findings Analyzer — one-folder, windowed, faster start
# Build on Windows: pyinstaller CoverityTool.spec
# Output: dist/CoverityTool/CoverityTool.exe + _internal/

block_cipher = None

import os, sys, sysconfig
# --- Bundle Tcl/Tk for frozen exe (fixes Tcl errors) ---
_tcl_datas = []
try:
    _tcl_root = os.path.join(sysconfig.get_path("data"), "tcl")
    if os.path.isdir(_tcl_root):
        for _sub in ("tcl8.6", "tk8.6"):
            _src = os.path.join(_tcl_root, _sub)
            if os.path.isdir(_src):
                _tcl_datas.append((_src, os.path.join("tcl", _sub)))
    # Also handle PyInstaller _MEIPASS case via runtime hook (local_gui.py does os.environ setup)
except Exception:
    pass

a = Analysis(
    ['local_gui.py'],
    pathex=[],
    binaries=[],
    datas=_tcl_datas + [
        ('docs/Coverity_Tool_User_Guide.docx', 'docs'),
        ('docs/sample_src', 'docs/sample_src'),
        ('docs/sample_report', 'docs/sample_report'),
        ('COVERITY_TOOL_MANUAL.md', '.'),
        ('README.md', '.'),
    ],
    hiddenimports=[
        'zeep', 'zeep.transports', 'zeep.wsse.username', 'zeep.exceptions',
        'lxml', 'lxml.etree', 'bs4', 'openpyxl', 'openpyxl.styles',
        'requests', 'urllib3',
        'tree_sitter', 'tree_sitter_c', 'tree_sitter_cpp',
        'pygments', 'pygments.lexers', 'pygments.formatters',
        'yaml', 'networkx',
        # Optional heavy deps — included if present, degraded gracefully if not
        'clang.cindex', 'z3', 'z3.z3core',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter.test', 'sqlite3.test'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CoverityTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # windowed, no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CoverityTool',
)
