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

## Use it from VS Code (or an AI agent)

The triage engine is also exposed headlessly, so VS Code, Copilot and any MCP
client can drive it. All three routes run the same analysis as the desktop GUI.
Full walkthrough: [docs/VSCODE_INTEGRATION.md](docs/VSCODE_INTEGRATION.md).
Start here instead if your goal is the agent: [docs/AGENT_USER_MANUAL.md](docs/AGENT_USER_MANUAL.md) — install,
the two inputs, and the prompts that get good results.

```bash
# 1. Headless JSON — one command, no build step
python vscode_bridge.py list    --report coverity/index.html --pretty
python vscode_bridge.py analyze --report coverity/index.html --src ./src --out .coverity/triage.json
python vscode_bridge.py context --report coverity/index.html --cid 12345 --src ./src

# 2. MCP server — agent tools in Copilot Chat / Claude / Cursor
#    .vscode/mcp.json is already committed; just start the "coverity" server
#    from the command palette (MCP: List Servers -> Start Server).
python coverity_mcp_server.py --list-tools          # sanity check

# 3. Native extension — Findings view, Problems panel, LM tools
cd vscode-extension && npm install && npm run compile
cd .. && npx --yes @vscode/vsce package --out vscode-extension   # -> coverity-tool-*.vsix
```

**Coverity here is a capability, not an agent.** The engine is published to
*any* VS Code agent as tools — `coverity_*` through the MCP server,
`coverityTool_*` through the extension — so your usual agent can triage findings
without switching personas. `.github/instructions/coverity-findings.instructions.md`
tells any agent when to reach for them, and `docs/coverity.toolsets.jsonc` makes
one `#coverity` reference enable the whole set.

For the whole job — analyse every finding in a report against the source, decide
per defect, write the reviewer comment and the proposed fix — install the
**Coverity Finding Analyzer** agent:
`.github/agents/coverity-finding-analyzer.agent.md` (that file is the store
upload). **It runs on the VS Code model you select and needs nothing installed**:
the model reads the report's event traces and your source files. The engine above
is an optional accelerator it will use when present (exact line numbers,
AST-anchored first pass), and `coverity_report_text.py` — stdlib only, no
dependencies — flattens a large HTML report into text a model can read cheaply. Step-by-step VS Code test runbook — any-agent path first,
> **New to this?** Start with [docs/USER_GUIDE.md](docs/USER_GUIDE.md) — inputs, source-root placement,
> outputs, how the analysis works, pulling from Coverity Connect and pushing dispositions back.

agent path second: [docs/VSCODE_AGENTS.md](docs/VSCODE_AGENTS.md).

Ready-to-upload agent-store artifacts (single `.agent.md` + ZIP bundle) are in
`dist-store/`; rebuild with `python build_agent_bundle.py` and see
[docs/STORE_LISTING.md](docs/STORE_LISTING.md) for the listing copy.

Agent tools available through MCP (`coverity_*`) and the extension
(`coverityTool_*`): capabilities, list defects, analyse one defect, triage a
whole report, and fetch the source context behind a verdict.

## Same analysis as the desktop app

The VS Code / MCP route drives the same engine, and `tests/test_desktop_parity.py` pins that down: for the same defect the
agent path returns the **same disposition, comment, suggested fix and
confidence** as the desktop Coverity Findings Analyzer (`local_gui.py`),
including the Excel export route and the `Various`-line rules. The only
difference is that the desktop-only Connect pull/push and interactive row
editing stay on the desktop, where the credentials are.

## Validate

Compile the Python modules:

```bash
python -m compileall -q .
```

## Static-analysis corroboration (cppcheck)

Defects are optionally corroborated by a second, independent analyzer: after a
defect is anchored to a source line, the tool runs **cppcheck** on that file
and records any finding within ±3 lines as independent confirmation. cppcheck
runs fully offline (its rules are compiled into the binary), is native and
fast, and `pip install -r requirements.txt` gives you the library-form wheel
that bundles the official cppcheck binary. See
[docs/CORROBORATION_BACKEND.md](docs/CORROBORATION_BACKEND.md) for details.

- Disable with `COVERITY_DISABLE_CPPCHECK=1`.
- `COVERITY_CPPCHECK_BIN` overrides the binary path; run `python capabilities.py`
  to see whether the backend is live.

## Security note

The Coverity Connect integration accepts credentials in the desktop UI. The current SOAP client permits disabled certificate verification for self-signed corporate certificates; do not use that setting for production connections unless you explicitly trust the certificate chain.
