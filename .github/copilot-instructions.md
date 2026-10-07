# Coverity Tool — agent instructions

This workspace analyses **Coverity** static-analysis findings for C/C++ with the
local Coverity Tool engine. Use its tools instead of guessing about a defect.

## Tools

| Tool | Use |
| --- | --- |
| `coverity_list_defects` | See what is in the report (CID, checker, severity, file, line) |
| `coverity_analyze_defect` | Disposition + CWE-cited rationale + suggested fix for one CID |
| `coverity_triage_report` | Whole-report verdicts and statistics |
| `coverity_source_context` | The numbered source a defect was judged against |
| `coverity_capabilities` | Which analysis backends are live / how strong the analysis is |

(The same capabilities are exposed by the extension as `coverityTool_*` tools
and by `python3 vscode_bridge.py` on the command line.)

## Rules

1. **List before analysing.** Use `coverity_list_defects` (or the Findings view)
   to get CIDs; never invent a CID.
2. **Always pass the source root** (`src_root`, or the `coverityTool.sourceRoot`
   setting). Without it the engine can only read the report's event trace, and
   verdicts get weaker.
3. **`Needs review` is not a verdict.** It means the evidence was inconclusive.
   Say so plainly, and check `coverity_capabilities` — a reduced analysis depth
   (`minimal`/`partial`) is a common reason.
4. **Quote the engine, don't paraphrase it away.** When you report a disposition
   include its confidence and the CWE reference the tool produced.
5. **Confirm before bulk runs.** `coverity_triage_report` can take minutes on a
   large report; prefer `limit` + `checker` for a first pass.
6. **Fixes come from the tool.** `proposed_fix` is the minimal change the
   analyser justified from the code — use it as the starting point of a patch
   rather than rewriting the function.
7. **Static analysis only.** These tools read the report and the source. They do
   not talk to Coverity Connect unless you explicitly run `cov_cli.py` /
   `coverity_push.py`, and they never need credentials.

## Environment

* The engine lives in this repository: `vscode_bridge.py` (headless JSON),
  `coverity_mcp_server.py` (MCP), `vscode-extension/` (editor UI).
* Python dependencies come from `requirements.txt`. If `coverity_capabilities`
  reports missing backends, suggest `pip install -r requirements.txt` rather
  than treating the current output as authoritative.
* Sample data for trying things out: `docs/sample_report` + `docs/sample_src`
  (two C defects, CIDs 1001 and 1002).
