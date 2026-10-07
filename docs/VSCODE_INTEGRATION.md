# Using the Coverity Tool from VS Code (and from an AI agent)

This repository ships three ways to drive the triage engine from VS Code. They
all run the **same Python analysis** (`context_builder` → `heuristic_analyzer`,
with z3 / libclang / cppcheck where available); they differ only in how the
result is presented.

| Route | What you get | Setup cost |
| --- | --- | --- |
| **1. MCP server** | The engine as agent tools (`coverity_analyze_defect`, …) in Copilot Chat agent mode, Claude Desktop, Cursor or any MCP client | None — the config file is already in `.vscode/mcp.json` |
| **2. Native extension** | Everything from route 1 **plus** a Findings view, Problems-panel squiggles with CWE links, status bar, commands, `#`-references in chat | `npm install && npm run compile` (one command) |
| **3. CLI / task** | JSON on stdout for scripts, CI and `.vscode/tasks.json` | None |

> Whichever route you choose, install the Python dependencies first —
> without them the analysis silently degrades (it still runs, but says so in
> every comment it produces):
>
> ```bash
> python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
> pip install -r requirements.txt
> python capabilities.py          # should print "analysis depth: FULL"
> ```

---

## How the pieces fit together

```
                           ┌──────────────────────────────┐
  Copilot Chat (agent mode)│ coverity_mcp_server.py       │  MCP tools
  Claude / Cursor / any  ───┤ (JSON-RPC over stdio)        │
  MCP client               └──────────────┬───────────────┘
                                          │ imports
  Copilot Chat + editor   ┌──────────────▼───────────────┐
  Problems / view /  ─────┤ vscode-extension/ (TypeScript)│  LM tools + UI
  status bar / commands   │ spawns →                     │
                          └──────────────┬───────────────┘
                                         │
  Terminal, CI, tasks ───────────────────┼──> vscode_bridge.py   (headless JSON CLI)
                                         │        │
                                         │        ├─ html_report_parser.py   (report → defects)
                                         │        ├─ context_builder.py      (source anchoring, callees, callers)
                                         │        └─ heuristic_analyzer.py   (verdict + rationale + fix)
                                         │              └─ z3 · libclang · tree-sitter · cppcheck · flow_analysis
```

`vscode_bridge.py` is the only analysis entry point. The MCP server imports it,
the extension spawns it, and the desktop GUIs (`local_gui.py`,
`coverity_triage.py`) call the same two functions underneath — so a defect
cannot get one disposition in the editor and a different one on the desktop.

---

> Day-to-day usage is in [USER_GUIDE.md](USER_GUIDE.md).

## Route 0 — Any agent, via the tools (recommended)

Coverity is a **capability**, not a persona: the engine is published as agent
tools, so the agent you already use — default, Plan, or your own — can triage
findings without you switching anything.

Three pieces make that work:

| Piece | File | What it does |
| --- | --- | --- |
| Tool provider (MCP) | `coverity_mcp_server.py` + `.vscode/mcp.json` | Publishes `coverity_capabilities`, `coverity_list_defects`, `coverity_analyze_defect`, `coverity_triage_report`, `coverity_export_results`, `coverity_source_context` |
| Tool provider (extension) | `vscode-extension/` | The same five as `coverityTool_*`, plus `#coverityAnalyzeDefect`-style references and a Findings view |
| Behaviour guidance | `.github/copilot-instructions.md`, `.github/instructions/coverity-findings.instructions.md` | Tells any agent *when* to call them and what a verdict means (never invent a CID, always pass `src_root`, `Needs review` ≠ verdict, re-analyse after a fix) |

Optional convenience: [`docs/coverity.toolsets.jsonc`](coverity.toolsets.jsonc)
defines a `coverity` tool set so `#coverity` enables all the Coverity tools at once in
any agent (tool sets live in your user profile — see the file's header).

**And the packaged pass:** the **Coverity Finding Analyzer**
([`.github/agents/coverity-finding-analyzer.agent.md`](../.github/agents/coverity-finding-analyzer.agent.md)) —
pick it in the agent dropdown when you want the whole job done in one run: it
collects the report and the source root, calls the tools for facts, **reads the
code itself on the VS Code model** to judge each defect, writes the reviewer
comment and a proposed fix, and re-analyses to prove each fix. The tools remain
usable from any agent; this is the version that does the analysis for you.

Step-by-step test runbook with expected output, any-agent path first:
**[docs/VSCODE_AGENTS.md](VSCODE_AGENTS.md)**.

---

## Route 1 — MCP server (no build step, works today)

VS Code discovers MCP servers from `.vscode/mcp.json`. This repository already
contains one:

```json
{
  "servers": {
    "coverity": {
      "type": "stdio",
      "command": "python3",
      "args": ["${workspaceFolder}/coverity_mcp_server.py"],
      "cwd": "${workspaceFolder}",
      "env": {
        "COVERITY_REPORT": "${workspaceFolder}/docs/sample_report/index.html",
        "COVERITY_SRC_ROOT": "${workspaceFolder}/docs",
        "COVERITY_LANGUAGE": "c"
      }
    }
  }
}
```

### Start it

1. Open the repository folder in VS Code.
2. `Ctrl+Shift+P` → **MCP: List Servers** → `coverity` → **Start Server**
   (or run **MCP: Add Server…** if you prefer to let VS Code write the entry).
3. VS Code asks whether you trust the server — it launches a local Python
   process, so review the command and accept.
4. In the Chat view, switch to **Agent** mode and open the tools picker: the
   five `coverity_*` tools are listed.

### Make it point at your real report

Edit the `env` block (the three `COVERITY_*` variables). They are only defaults:
every tool also accepts an explicit `report` / `src_root` argument, so one
server can serve several reports.

| Variable | Meaning |
| --- | --- |
| `COVERITY_REPORT` | `index.html`, the folder containing it, an `.xlsx` export, or a `.triage.json` |
| `COVERITY_SRC_ROOT` | Root of the analysed C/C++ checkout — **set this**, it is what turns "event trace" verdicts into code-anchored ones |
| `COVERITY_LANGUAGE` | `c` or `cpp` |
| `COVERITY_MCP_MAX_RESULTS` | Default row cap per tool call (default 25) |
| `COVERITY_MCP_OUTPUT_DIR` | Where `coverity_triage_report` caches `.triage.json` (default `<repo>/.coverity`) |

### Platform notes

* **Windows** — replace `"python3"` with `"python"`, or point at an interpreter
  explicitly: `"command": "${workspaceFolder}\\.venv\\Scripts\\python.exe"`.
* **Virtualenv** — any interpreter path works; the server only needs the
  packages from `requirements.txt` importable.
* **Every workspace** — copy the `servers` block into your *user* `mcp.json`
  (`Ctrl+Shift+P` → **MCP: Open User Configuration**) and use absolute paths
  instead of `${workspaceFolder}`.
* **No `python3` in PATH?** `python3 coverity_mcp_server.py --list-tools` will
  tell you the catalogue it would serve; if that fails, the interpreter is the
  problem, not VS Code.

### The five MCP tools

| Tool | Use it for |
| --- | --- |
| `coverity_capabilities` | Which backends are live and the resulting analysis depth (call before quoting numbers) |
| `coverity_list_defects` | Enumerate CIDs, checkers, severities, files — cheap, no analysis |
| `coverity_analyze_defect` | One CID: disposition, confidence, CWE-cited rationale, suggested fix, event trace, source window |
| `coverity_triage_report` | Whole-report triage with statistics; writes a reusable `.triage.json` |
| `coverity_source_context` | Just the numbered source around a CID (for writing a patch) |
| `coverity_export_results` | Triage + write the dispositions CSV the desktop Push page loads ([USER_GUIDE.md](USER_GUIDE.md) §7) |

---

## Route 2 — Native VS Code extension

The extension adds a real UI on top of the same engine. It is *in addition* to
route 1, not a replacement — install one or both.

### Build and run it

```bash
cd vscode-extension
npm install
npm run compile          # TypeScript -> out/
```

* **Try it in place:** open the repository root in VS Code and press **F5**
  (the committed `.vscode/launch.json` launches an Extension Development Host
  with this extension loaded).
* **Install it for real:** package and install the VSIX:

  ```bash
  cd vscode-extension
  npx @vscode/vsce package          # produces coverity-tool-1.0.0.vsix
  code --install-extension coverity-tool-1.0.0.vsix
  ```

  `Ctrl+Shift+P` → **Extensions: Install from VSIX…** does the same thing from
  the UI.

### What you get

| Feature | Where |
| --- | --- |
| **Findings view** — findings grouped by file, click to jump to the line, full rationale on hover | Activity bar → **Coverity Tool** |
| **Problems panel** — one diagnostic per finding, severity-mapped, `CWE-119` in the message links to MITRE | View → Problems (`Ctrl+Shift+M`) |
| **Status bar** — `$(shield) 42 findings · $(bug) 7 · $(question) 3` | Bottom-left; click to re-run |
| **Commands** | `Coverity: Analyse Report`, `Coverity: Show Analysis Capabilities`, `Coverity: Reload Cached Triages`, `Coverity: Export Triage JSON…`, `Coverity: Show Finding Under Cursor` (also in the editor context menu for C/C++ files) |
| **Agent tools** | Same five capabilities as the MCP server, plus `#coverityAnalyzeDefect`, `#coverityTriageReport`, … references in chat |

Disposition → Problems mapping: `Bug` → error, `Needs review` → warning,
`False positive` → info, `Intentional` → hint. Which ones are published is
configurable (`coverityTool.diagnosticDispositions`).

### Settings

| Setting | Default | Notes |
| --- | --- | --- |
| `coverityTool.reportPath` | *(empty)* | Empty → the Analyse command asks you to pick one |
| `coverityTool.sourceRoot` | `${workspaceFolder}` | The analysed checkout |
| `coverityTool.language` | `c` | `c` or `cpp` |
| `coverityTool.pythonPath` | *(auto)* | `.venv` next to the tool → `python3`/`python` |
| `coverityTool.bridgePath` | *(auto)* | `<ws>/Coverity-Tool/vscode_bridge.py` → `<ws>/vscode_bridge.py` → the copy next to the extension |
| `coverityTool.maxDefects` | `100` | Cap per run — keeps a 4000-finding report from stalling the editor |
| `coverityTool.timeoutSeconds` | `900` | Hard stop for a run |
| `coverityTool.publishDiagnostics` | `true` | Turn off if you only want the Findings view |

---

## Parity with the desktop Coverity Findings Analyzer

The question "does the VS Code route analyse the same way the desktop app
does?" is answered by `tests/test_desktop_parity.py`, which replicates the
desktop pipelines and compares them field by field against the bridge.

| Compared | Result |
| --- | --- |
| `local_gui.py` (primary desktop app) vs the agent/MCP/bridge path | **Identical** — disposition, comment, suggested fix and confidence |
| `coverity_triage.py` (focused HTML triage GUI) vs the bridge | **Identical verdict, confidence and fix**; its comment can be one sentence shorter |
| Desktop Excel route (`write_pull_excel` → `parse_coverity_excel`) vs HTML input | **Identical** — the `EventsJSON` column preserves the main-event line |
| CLI (`python vscode_bridge.py analyze`) vs in-process library use | **Identical** |

The one legitimate difference: `coverity_triage.py` passes the report's
*relative* path, so it cannot run the extra **cppcheck corroboration** pass and
its comment omits the "Independent corroboration: …" sentence. `local_gui.py`
and the VS Code route resolve the file to an absolute path and do get it. The
disposition never changes because of it.

`Various`-line rows (Excel exports) follow the desktop rule exactly:

* a checker that needs an access site (`BUFFER_SIZE`, `OVERRUN`, …) →
  `Needs review` with a message asking for the real line — even when the
  enclosing function was extracted;
* a line-agnostic checker (`CHECKED_RETURN`, `UNUSED_VALUE`, …) → analysed from
  the whole function, with the line zeroed so nothing anchors to a stale number.

What the VS Code route deliberately does **not** copy from the desktop app:
interactive row editing, pulling a snapshot from Coverity Connect
(`coverity_soap_client`) and pushing dispositions back (`coverity_push.py`).
Those need credentials and stay on the desktop / CLI, on your machine. The agent
*does* produce paste-ready Connect text (Mode C) so the same triage can be
written back manually.

---

## Route 3 — CLI and tasks (scripts, CI, no UI)

```bash
# What is in the report? (no analysis)
python3 vscode_bridge.py list --report coverity/index.html --pretty

# Full triage of a report against a checkout
python3 vscode_bridge.py analyze \
    --report coverity/index.html \
    --src    ./src \
    --language c \
    --out    .coverity/triage.json

# One defect, with the source window it was judged against
python3 vscode_bridge.py context --report coverity/index.html --cid 12345 --src ./src --lines 40

# Streaming: one JSON object per line, for long runs
python3 vscode_bridge.py analyze --report coverity/index.html --src ./src --jsonl | jq -c 'select(.event=="defect") | [.cid,.disposition]'
```

The contract the extension relies on, and that you can rely on too:

* **stdout is JSON only.** Progress and warnings go to stderr; even a stray
  `print()` inside a deep analyser cannot corrupt the payload.
* Every payload has `ok` and `schema` (`schema: 1`). Failures are JSON **and**
  a non-zero exit code:

  ```json
  { "ok": false, "schema": 1,
    "error": { "type": "NotFound",
               "message": "CID 999 not found in index.html.",
               "hint": "Use the list command to see the CIDs present in this report." } }
  ```

`.vscode/tasks.json` already wires three of these up
(`Ctrl+Shift+P` → **Tasks: Run Task** → `coverity:`…).

---

## Telling the AI how to use it

The MCP/extension tools are self-describing, but a short workspace instruction
file measurably improves how agents use them. `.github/copilot-instructions.md`
in this repository already contains that guidance:

```markdown
When triaging Coverity findings, use the coverity_* tools:
1. coverity_list_defects to see what the report contains.
2. coverity_analyze_defect per CID before proposing a fix.
3. Never present "Needs review" as a verdict; it means the evidence was
   inconclusive — check coverity_capabilities and say the depth was reduced.
Always set src_root so verdicts read the actual code.
```

---

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Could not find vscode_bridge.py` | The extension cannot locate the engine | Set `coverityTool.bridgePath`, or open the `Coverity-Tool` folder as the workspace |
| `spawn python3 ENOENT` / server won't start | No `python3` on PATH (typical on Windows) | Set `coverityTool.pythonPath`, or use `"command": "python"` in `mcp.json` |
| Every finding says **Needs review** | Report has no detail pages, or the source tree was not found | Set `sourceRoot` / `COVERITY_SRC_ROOT`; run `python capabilities.py` |
| Verdicts are lower quality than the GUI's | Missing backends (tree-sitter, libclang, z3) | `pip install -r requirements.txt`; check `coverityTool: Show Analysis Capabilities` |
| "Source file … not found locally" | Report paths come from the build machine | Point `sourceRoot` at the checkout — files are matched by trailing path components |
| Tools missing in Copilot Chat | Agent mode off, tools disabled, or VS Code too old | Enable **Agent** mode, tools picker → `coverity*`; VS Code 1.95+ for LM tools, 1.99+ for MCP |
| MCP server listed but tools do not appear | Server not started/trusted | **MCP: List Servers** → `coverity` → Start; check the server log in the Output panel |
| Run takes forever on a big report | Thousands of defects × optional backends | Lower `coverityTool.maxDefects` / pass `limit`, or narrow with `--checker` first |

---

## What was added for this integration

| File | Purpose |
| --- | --- |
| `vscode_bridge.py` | Headless JSON CLI + importable API (`op_capabilities`, `op_list`, `op_analyze`, `op_context`) |
| `coverity_mcp_server.py` | MCP stdio server exposing the five agent tools; zero extra dependencies |
| `vscode-extension/` | TypeScript extension: LM tools, Findings view, Problems panel, commands |
| `.vscode/mcp.json` | Registers the MCP server with VS Code |
| `.vscode/launch.json`, `.vscode/tasks.json` | F5 debugging for the extension; sample CLI tasks |
| `.github/copilot-instructions.md` | Tells the agent how to use the tools correctly |
| `tests/test_vscode_bridge.py`, `tests/test_mcp_server.py` | Contract tests (JSON purity, error shapes, tool catalogue, dispositions) |
| `tests/test_desktop_parity.py` | Proves the VS Code/agent route analyses the same way the desktop app does |
| `.github/agents/coverity-finding-analyzer.agent.md` | The agent: model-driven per-defect analysis, comment + fix quality bars, verification, Connect export |
| `.github/instructions/coverity-findings.instructions.md` | Path-scoped rules so **any** agent uses the tools correctly |
| `docs/coverity.toolsets.jsonc` | Tool-set template for `#coverity` (user-profile file) |
| `dist-store/` | Ready-to-upload agent-store artifacts (`.agent.md` + ZIP) |
| `docs/VSCODE_AGENTS.md` | Step-by-step VS Code test runbook for the agent and the extension |
| `code_extractor.py` | One fix: `find_function_line_by_name()` returned `None`-tree crash without tree-sitter — it now degrades like `extract_enclosing_function()` does |
