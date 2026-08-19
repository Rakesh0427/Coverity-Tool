# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Coverity Findings Analyzer — one-folder, windowed, faster start
# Build on Windows: pyinstaller CoverityTool.spec
# Output: dist/CoverityTool/CoverityTool.exe + _internal/

block_cipher = None

a = Analysis(
    ['local_gui.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Ensure tree-sitter language libs are bundled
        # (PyInstaller collects them via hiddenimports below, datas not needed for pure wheels)
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
