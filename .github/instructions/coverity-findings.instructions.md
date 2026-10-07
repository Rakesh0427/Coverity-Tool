---
description: 'How to use the Coverity Tool analysis when a task involves Coverity findings or the C/C++ code they point at — which tools to call, what a verdict means, and what must be verified rather than guessed.'
applyTo: '**/*.c, **/*.h, **/*.cc, **/*.cpp, **/*.cxx, **/*.hpp, **/*.hh, **/coverity/**, **/*.triage.json'
---

# Coverity findings in this workspace

This repository runs **Coverity** static analysis for C/C++. When a task touches
a Coverity finding — triaging one, deciding whether it is real, fixing the code
it points at, or answering "is this actually a bug?" — the verdict must come
from the **Coverity Tool engine**, not from reading the report page and
reasoning about it.

These rules apply to **any agent**, in Agent mode, regardless of which persona
is selected. The same tools are also available to any MCP client.

## Tools to use

The engine exposes five capabilities. Look for either flavour — they are the
same Python code underneath:

| MCP tool | Extension tool | Use it for |
| --- | --- | --- |
| `coverity_capabilities` | `coverityTool_capabilities` (`#coverityCapabilities`) | Which analysis backends are live; the current analysis depth |
| `coverity_list_defects` | `coverityTool_listDefects` (`#coverityListDefects`) | Enumerate CIDs, checkers, severities, files |
| `coverity_analyze_defect` | `coverityTool_analyzeDefect` (`#coverityAnalyzeDefect`) | One CID: disposition, confidence, rationale, fix, event trace |
| `coverity_triage_report` | `coverityTool_triageReport` (`#coverityTriageReport`) | Whole report: verdicts and statistics |
| `coverity_export_results` | — (CLI: `--csv`) | Analyse a report and write the dispositions CSV the desktop app's Push page can load |
| `coverity_source_context` | `coverityTool_sourceContext` (`#coveritySourceContext`) | The numbered source a verdict was based on |

If the tools are missing, the MCP server is not running: tell the user to
start it (**MCP: List Servers → `coverity` → Start Server**) or to add the
`coverity` server from `.vscode/mcp.json`. Never pretend a tool result exists.

## Rules

1. **Never invent a CID or a verdict.** Enumerate with `coverity_list_defects`
   first, then analyse.
2. **Always pass the source root** (`src_root`, or the
   `coverityTool.sourceRoot` setting). Without it the engine can only read the
   report's event trace, and it says so in the comment — pass that limitation
   on to the user rather than hiding it.
3. **`Needs review` is not a verdict.** It means the evidence was inconclusive.
   Never present it as a bug or as a false positive. If the analysis depth is
   `partial`/`minimal` (check `coverity_capabilities`), say that the reduced
   analysis is the likely reason.
4. **Quote the engine.** Include the confidence and the CWE reference it
   produced. Do not paraphrase a verdict into something stronger.
5. **Dispositions are a closed set:** `Bug`, `False positive`, `Intentional`,
   `Needs review`.
6. **Before editing code for a finding**, read it with
   `coverity_source_context` and confirm the line still matches the report —
   the file may have moved since the scan. Change **one CID per edit**, apply
   the engine's `proposed_fix` minimally, and then **re-analyse the same CID**
   and quote the new verdict. A fix you did not re-verify is a claim, not a
   result.
7. **Never request or store Coverity credentials** and never contact Coverity
   Connect. Pushing dispositions is the user's own CLI step
   (`coverity_push.py`), with their credentials, on their machine.
8. **If the engine cannot answer, say so and stop.** A plausible-sounding
   triage produced without the tool is worse than no answer.

## Terminal equivalents (identical JSON)

```bash
python3 vscode_bridge.py capabilities
python3 vscode_bridge.py list    --report <report> --limit 50
python3 vscode_bridge.py analyze --report <report> --src <srcroot> --limit 25
python3 vscode_bridge.py context --report <report> --cid <cid> --src <srcroot> --lines 40
```

If `python capabilities.py` does not end with `analysis depth: FULL`, recommend
`pip install -r requirements.txt` before treating any number as authoritative.

## When the work is "analyse every finding and decide"

You can do that from here: call the tools, read the code the finding points at,
and decide per defect. For a longer pass — a whole report, a reviewer-grade
comment per defect, a proposed fix, and re-analysis to prove each fix — point the
user at the **Coverity Finding Analyzer** agent
(`.github/agents/coverity-finding-analyzer.agent.md`). It runs on the same tools
and reads the code itself. Mention it as an option; do not require it.
