---
description: 'How to use the Coverity Tool analysis when a task involves Coverity findings or the C/C++ code they point at — which tools to call, what a verdict means, and what must be verified rather than guessed.'
applyTo: '**/*.c, **/*.h, **/*.cc, **/*.cpp, **/*.cxx, **/*.hpp, **/*.hh, **/coverity/**, **/*.triage.json'
---

# Coverity findings in this workspace

This repository contains the **Coverity Tool** engine, and the VS Code agent
**Coverity Finding Analyzer** that analyses Coverity reports with the model you
have selected. When a task touches a Coverity finding — triaging one, deciding
whether it is real, fixing the code it points at, or answering "is this actually
a bug?" — you can do the analysis yourself: read the report, read the code, and
decide, quoting the lines you rely on.

**No local tool is required for that.** If the optional engine tools are present
(the MCP server is running, or the extension is installed) they give you exact
line numbers and an AST-anchored first pass very cheaply — use them when they are
there. If they are not, do not stall and do not mention it: read the report and
the code and produce the analysis, and never present work as tool-verified when
no tool ran.

These rules apply to **any agent**, in Agent mode, regardless of which persona is
selected. The same tools are also available to any MCP client.

## If you want the full pass done for you

Hand the job to the **Coverity Finding Analyzer** agent
(`.github/agents/coverity-finding-analyzer.agent.md`): report + source root in,
disposition + reviewer comment + proposed fix per defect out, with a
`Needs review` verdict instead of a guess when the evidence is not there.

## Tools to use

The optional accelerator exposes these capabilities. Look for either flavour —
they are the same Python code underneath. Use them when present; they are never
required:

| MCP tool | Extension tool | Use it for |
| --- | --- | --- |
| `coverity_capabilities` | `coverityTool_capabilities` (`#coverityCapabilities`) | Which analysis backends are live; the current analysis depth |
| `coverity_list_defects` | `coverityTool_listDefects` (`#coverityListDefects`) | Enumerate CIDs, checkers, severities, files |
| `coverity_analyze_defect` | `coverityTool_analyzeDefect` (`#coverityAnalyzeDefect`) | One CID: disposition, confidence, rationale, fix, event trace |
| `coverity_triage_report` | `coverityTool_triageReport` (`#coverityTriageReport`) | Whole report: verdicts and statistics |
| `coverity_export_results` | — (CLI: `--csv`) | Analyse a report and write the dispositions CSV the desktop app's Push page can load |
| `coverity_source_context` | `coverityTool_sourceContext` (`#coveritySourceContext`) | The numbered source a verdict was based on |

If the tools are missing and the user wants them, the MCP server is not running:
they can start it (**MCP: List Servers → `coverity` → Start Server**). Until then
— and if they never install it — analyse from the report and the code yourself.
Never pretend a tool result exists, and never present model reasoning as the
engine's verdict.

## Rules

1. **Never invent a CID, a line or a verdict.** Take the defect list from the
   report (`index.html`, the CSV, or `coverity_list_defects` when it is
   available) and the facts from the detail page, then analyse.
2. **Anchor everything to the source root** — the folder the report's paths are
   relative to (`src_root` for the optional tools; the folder you read the code
   from, otherwise). Without an anchor you cannot judge a defect; say which file
   you could not find rather than reasoning about a file you never read.
3. **`Needs review` is not a verdict.** It means the evidence was inconclusive.
   Never present it as a bug or as a false positive. If the analysis depth is
   `partial`/`minimal` (check `coverity_capabilities`), say that the reduced
   analysis is the likely reason.
4. **Attribute your evidence.** When a verdict comes from the optional engine,
   say so and quote its confidence and CWE reference. When it comes from your own
   reading, cite the file, the line and the code. Never blur the two, and never
   present your reasoning as the engine's output.
5. **Dispositions are a closed set:** `Bug`, `False positive`, `Intentional`,
   `Needs review`.
6. **Before editing code for a finding**, open the file and confirm the line
   still matches the report — the file may have moved since the scan. Change
   **one CID per edit**, minimally, in the file's own style. Then **re-check the
   same CID**: with the optional engine, re-analyse and quote the new verdict;
   without it, re-read the changed code and walk the original event trace
   through it, out loud. Either way, say that only a fresh Coverity scan
   re-certifies the defect. A fix you did not re-check is a claim, not a result.
7. **Never request or store Coverity credentials** and never contact Coverity
   Connect. Pushing dispositions is the user's own CLI step
   (`coverity_push.py`), with their credentials, on their machine.
8. **If you cannot determine something, say so.** Mark it `Needs review` and
   name the fact you would need (a build flag, a design intent, a file that is
   not in the workspace). A confident-sounding verdict that no evidence supports
   is worse than `Needs review`.

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
