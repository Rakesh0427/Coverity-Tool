# Coverity Tool

A local desktop tool for reviewing Coverity defects, enriching them with C/C++ source context, and generating suggested triage decisions.

## Windows desktop build (no Python needed)

A ready-to-run 64-bit Windows package (`Coverity-Tool-Windows-Setup.zip`) is built by CI
(`.github/workflows/build-windows-exe.yml`) and attached to
[GitHub Releases](https://github.com/Rakesh0427/Coverity-Tool/releases) whenever a `v*` tag
is pushed. Unzip the folder and double-click `CoverityTool.exe` — keep the whole folder
together, the exe needs the `_internal` folder beside it.

> **"This app can't run on your PC"?** Older pre-1.4 ZIPs shipped a placeholder
> `CoverityTool.exe`, which is exactly that error. Fix: use the current release ZIP, run the
> app through Python (below) via `CoverityTool.bat`, or build the exe on your own PC by
> double-clicking `build_exe.bat` (requires Python 3.10+, takes 2–4 minutes).

## Requirements (running from source with Python)

- Python 3.10 or newer
- `tkinter` for the desktop interface (on Linux, install the distribution package such as `python3-tk`)
- A Coverity HTML report or Coverity Excel export
- Optional: a local checkout of the analysed C/C++ source tree

## Installation

Create and activate a virtual environment, then install the dependencies:

```bash
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run

Start the primary desktop application:

```bash
python local_gui.py
```

For the focused HTML-report triage interface:

```bash
python coverity_triage.py
```

Both commands launch desktop GUIs; they are not command-line batch commands.

## Validate

Compile the Python modules:

```bash
python -m compileall -q .
```

## Security note

The Coverity Connect integration accepts credentials in the desktop UI. The current SOAP client permits disabled certificate verification for self-signed corporate certificates; do not use that setting for production connections unless you explicitly trust the certificate chain.
