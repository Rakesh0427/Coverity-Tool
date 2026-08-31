# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Coverity Findings Analyzer — one-folder, windowed, faster start
# Build on Windows: pyinstaller CoverityTool.spec
# Output: dist/CoverityTool/CoverityTool.exe + _internal/

block_cipher = None

import os, sys, sysconfig


# Ensure PyInstaller's tkinter probe uses the interpreter's real Tcl/Tk
# instead of inherited external toolchain variables.
_base_tcl = os.path.join(getattr(sys, "base_prefix", ""), "tcl", "tcl8.6")
_base_tk = os.path.join(getattr(sys, "base_prefix", ""), "tcl", "tk8.6")
if os.path.isfile(os.path.join(_base_tcl, "init.tcl")):
    os.environ["TCL_LIBRARY"] = _base_tcl
if os.path.isfile(os.path.join(_base_tk, "tk.tcl")):
    os.environ["TK_LIBRARY"] = _base_tk


def _dedupe_pairs(pairs):
    out, seen = [], set()
    for src, dst in pairs:
        key = (os.path.normcase(os.path.abspath(src)), dst)
        if key in seen:
            continue
        seen.add(key)
        out.append((src, dst))
    return out


def _python_roots():
    roots = []
    for p in (
        sysconfig.get_path("data"),
        getattr(sys, "base_prefix", ""),
        getattr(sys, "prefix", ""),
        os.path.dirname(os.path.dirname(sys.executable)),
    ):
        if p and p not in roots:
            roots.append(p)
    return roots


# --- Bundle Tcl/Tk + _tkinter for frozen exe ---
# Virtual environments on Windows may not carry Tcl/Tk files under their own
# root, so probe both the venv and base interpreter roots.
_tcl_datas = []
_tk_binaries = []
for _root in _python_roots():
    _tcl_root = os.path.join(_root, "tcl")
    _dll_dir = os.path.join(_root, "DLLs")

    for _sub in ("tcl8.6", "tk8.6"):
        _src = os.path.join(_tcl_root, _sub)
        if os.path.isdir(_src):
            _tcl_datas.append((_src, os.path.join("tcl", _sub)))

    for _dll in ("_tkinter.pyd", "tcl86t.dll", "tk86t.dll"):
        _src = os.path.join(_dll_dir, _dll)
        if os.path.isfile(_src):
            _tk_binaries.append((_src, "."))

_tcl_datas = _dedupe_pairs(_tcl_datas)
_tk_binaries = _dedupe_pairs(_tk_binaries)

# --- Bundle cppcheck (offline corroboration backend) from the pip wheel ---
# capabilities.find_cppcheck_bin() finds it at runtime under
# _MEIPASS/cppcheck/Cppcheck/ (or next to the exe, copied by build_exe.bat).
_cppcheck_datas = []
try:
    import cppcheck as _cppcheck_wheel
    _cc_dir = os.path.join(os.path.dirname(_cppcheck_wheel.__file__), "Cppcheck")
    if os.path.isdir(_cc_dir):
        _cppcheck_datas.append((_cc_dir, os.path.join("cppcheck", "Cppcheck")))
except Exception:
    pass

a = Analysis(
    ['local_gui.py'],
    pathex=[],
    binaries=_tk_binaries,
    datas=_tcl_datas + _cppcheck_datas + [
        ('docs/Coverity_Tool_User_Guide.docx', 'docs'),
        ('docs/CORROBORATION_BACKEND.md', 'docs'),
        ('docs/sample_src', 'docs/sample_src'),
        ('docs/sample_report', 'docs/sample_report'),
        ('COVERITY_TOOL_MANUAL.md', '.'),
        ('README.md', '.'),
    ],
    hiddenimports=[
        'zeep', 'zeep.transports', 'zeep.wsse.username', 'zeep.exceptions',
        'lxml', 'lxml.etree', 'bs4', 'openpyxl', 'openpyxl.styles',
        'requests', 'urllib3',
        'tkinter', 'tkinter.ttk', 'tkinter.scrolledtext', '_tkinter',
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
