# Coverity Tool — VS Code extension

Triage Coverity C/C++ findings without leaving the editor. The extension is a
thin UI over the local Coverity Tool Python engine, so a defect gets the same
disposition here as it does in the desktop GUI.

## What it does

* **Agent tools for GitHub Copilot** (agent mode / `#` references):
  * `#coverityCapabilities` – which analysis backends are live
  * `#coverityListDefects` – what is in the report
  * `#coverityAnalyzeDefect` – disposition, CWE-cited rationale, suggested fix
  * `#coverityTriageReport` – whole-report triage with statistics
  * `#coveritySourceContext` – the numbered source a verdict was based on
* **Findings view** – findings grouped by file; click to jump to the line, hover
  for the full rationale.
* **Problems panel** – one diagnostic per finding, severity-mapped, with the CWE
  link (`Bug` → error, `Needs review` → warning, `False positive` → info,
  `Intentional` → hint).
* **Status bar** – `42 findings · 7 bugs · 3 need review`, click to re-run.
* **Commands** – analyse a report, show capabilities, reload cached triages,
  export JSON/CSV (the CSV is **push-ready**: same columns the desktop
  Coverity Findings Analyzer loads on its Push page), show the finding under the cursor.

## Requirements

1. **Python 3.10+** with the tool's dependencies:

   ```bash
   pip install -r requirements.txt      # from the Coverity-Tool checkout
   python capabilities.py               # expect "analysis depth: FULL"
   ```

2. A **Coverity report** (HTML `index.html`, its folder, or an `.xlsx` export)
   and, ideally, **the analysed source tree** — verdicts are far more accurate
   when the engine can read the code.

3. VS Code **1.95+** (GitHub Copilot Chat for the agent tools).

## Getting started

1. Install the extension (VSIX, or F5 from the repository for development).
2. `Ctrl+Shift+P` → **Coverity: Analyse Report** and pick your report the first
   time; the path is remembered in the `coverityTool.reportPath` setting.
3. Set `coverityTool.sourceRoot` to the analysed checkout if it is not the
   workspace folder.
4. Open the **Coverity Tool** view in the activity bar, or ask Copilot:

   > Triage the Coverity report and tell me which findings are real bugs.

## Settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `coverityTool.reportPath` | *(empty)* | Report to analyse (`index.html`, folder, `.xlsx`, `.triage.json`) |
| `coverityTool.sourceRoot` | `${workspaceFolder}` | The analysed C/C++ checkout |
| `coverityTool.language` | `c` | `c` or `cpp` |
| `coverityTool.pythonPath` | *(auto)* | Interpreter that has the tool's requirements |
| `coverityTool.bridgePath` | *(auto)* | Path to `vscode_bridge.py` |
| `coverityTool.maxDefects` | `100` | Cap per run |
| `coverityTool.timeoutSeconds` | `900` | Hard stop for a run |
| `coverityTool.publishDiagnostics` | `true` | Publish to the Problems panel |
| `coverityTool.diagnosticDispositions` | `["Bug","Needs review"]` | Which verdicts become Problems |

## Interpreting the output

* **Confidence** is the engine's own confidence, not a probability of the
  defect existing — read it with the rationale.
* **`Needs review`** means the evidence was genuinely inconclusive: usually a
  missing source tree, a "Various" line in an Excel export, or a machine
  without the optional analysis backends. Run **Coverity: Show Analysis
  Capabilities** to see which backends are live.
* The comment always states the CWE/CERT reference the verdict was reasoned
  from, and when the analysis depth was reduced that is written into the comment
  itself.

## Prefer MCP instead?

This repository also ships `coverity_mcp_server.py` and a ready-to-use
`.vscode/mcp.json`, which exposes the same engine to *any* MCP client (Copilot
Chat, Claude, Cursor, …) with no build step. See
[`docs/VSCODE_INTEGRATION.md`](../docs/VSCODE_INTEGRATION.md).

## License

MIT — same as the Coverity Tool repository.
