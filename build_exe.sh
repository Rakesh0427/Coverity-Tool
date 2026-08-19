#!/bin/bash
# Build CoverityTool on Linux/macOS (for dev test; exe needs Windows)
set -e
echo "=== CoverityTool — Build (Linux/macOS) ==="
python3 -m venv .venv_build
source .venv_build/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
python -m compileall -q .
pyinstaller CoverityTool.spec --noconfirm --clean
echo "Build done: dist/CoverityTool/CoverityTool (Linux binary — for Windows, run build_exe.bat on Windows)"
