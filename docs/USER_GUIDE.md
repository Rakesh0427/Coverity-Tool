# Coverity in VS Code — user guide

Everything a user needs in order to *use* this: where to put the report, where to
put the code, what the agent does with them, where the results go, how to get
data out of Coverity Connect, and how to push dispositions back.

If you only read one section, read [Quick start](#1-quick-start-10-minutes).
If you are wondering "can I trust it?", read
[How the analysis works](#4-how-the-analysis-works).

- [1. Quick start (10 minutes)](#1-quick-start-10-minutes)
- [2. Giving it input](#2-giving-it-input)
- [3. Where the code folder goes](#3-where-the-code-folder-goes)
- [4. How the analysis works](#4-how-the-analysis-works)
- [5. Where the output goes](#5-where-the-output-goes)
- [6. Getting data out of Coverity Connect](#6-getting-data-out-of-coverity-connect)
- [7. Pushing dispositions back](#7-pushing-dispositions-back)
- [8. Copy-paste prompts](#8-copy-paste-prompts)
- [9. When something is wrong](#9-when-something-is-wrong)
- [10. FAQ](#10-faq)

---

## 1. Quick start (10 minutes)

**Step 0 — you need nothing installed.** The **Coverity Finding Analyzer** agent
runs on the VS Code model you select: it reads the report and your source code
itself. Install the optional engine (Step 1) only if you want exact line numbers
and an AST-anchored first pass on top of that — it makes big reports cheaper, not
possible.

**Step 1 — optional: install the engine** (once per machine):

```bash
cd <this repo>
pip install -r requirements.txt
python capabilities.py          # must print: analysis depth: FULL
```

If it prints `minimal`, install the missing backends it lists. Skipping this step
entirely is fine: the agent analyses from the report and the code, and says what
its evidence was.

**Step 2 — decide how to run it:** as **MCP tools** (works with every agent in
VS Code, recommended) or as the **extension** (adds Problems-panel entries).
For the agent route — the prompts that get good results, and how to read
the answer — see [AGENT_USER_MANUAL.md](AGENT_USER_MANUAL.md).
[VSCODE_INTEGRATION.md](VSCODE_INTEGRATION.md) has the engine routes, in 3
minutes each.
For MCP you need `.vscode/mcp.json` (already committed here) and then:

> `Ctrl+Shift+P` → **MCP: List Servers** → `coverity` → **Start Server**

**Step 3 — make a report available** (pick any one):

| You have | Where to put it | What you pass |
| --- | --- | --- |
| A Coverity HTML export (folder with `index.html`) | anywhere in or near the repo, e.g. `reports/2026-08-14/index.html` | the folder or the `index.html` |
| A Coverity `.xlsx` export | anywhere, e.g. `reports/defects.xlsx` | the file path |
| Nothing yet | — | see [§6](#6-getting-data-out-of-coverity-connect) |

**Step 4 — point it at the source.** Put the analysed checkout somewhere
(usually it *is* your workspace) and note its **root** — the folder that
corresponds to the top of the paths inside the report. See
[§3](#3-where-the-code-folder-goes).

**Step 5 — ask, in plain language, in any agent:**

> Use the Coverity tools to triage `reports/2026-08-14/index.html` with source
> root `.` — summarise the findings and explain the top one.

That is the whole loop. Everything below is detail on each step.

---

## 2. Giving it input

### 2.1 Supported inputs

| Input | Notes |
| --- | --- |
| **Coverity HTML export folder** | Folder containing `index.html` (+ the per-defect detail pages). Richest input: carries the event trace, which is what lets the engine reason about the data flow. |
| **Coverity HTML file** | A single defect detail page also works. |
| **Excel export (`.xlsx`)** | Columns are matched fuzzily (`CID`, `Checker`, `Subtype`/`Type`, `Severity`, `File`, `Line`, `Function`, `Events Summary`/`EventsJSON`, `Action`). Missing event traces are reconstructed, exactly as the desktop app does. |
| **`*.triage.json`** | A previous run's output. Useful for "explain CID 1002 from yesterday's triage" without re-analysing. |

A report with **no** source tree still gets analysed — from the report's own
detail pages — but verdicts are weaker. Pass the source root.

### 2.2 Three ways to tell the agent which report to use

1. **In the prompt** (recommended, most explicit — the agent then passes it to
   every tool call):
   > "Triage `reports/2026-08-14/index.html` with source root `.`"
2. **In a setting**, so you never type it again — `.vscode/settings.json`:
   ```jsonc
   {
     "coverityTool.reportPath": "${workspaceFolder}/reports/index.html",
     "coverityTool.sourceRoot": "${workspaceFolder}",
     "coverityTool.language": "c"
   }
   ```
   (Used by the extension; for MCP set `COVERITY_REPORT` / `COVERITY_SRC_ROOT`
   in the server entry instead — see [VSCODE_AGENTS.md](VSCODE_AGENTS.md) §3.3.)
3. **By attaching/opening the report file** in the editor and referring to "this
   report" / `#file`.

If a tool needs a path you did not give, it asks for it rather than guessing.

### 2.3 Paths: relative vs absolute

Relative paths are resolved against the **workspace folder**, so
`reports/index.html` and `docs/sample_report/index.html` work as written. For
reports living outside the workspace (a shared network drive, an unzipped
export in `~/Downloads`), pass an absolute path. Paths with spaces are fine —
quote them in the prompt.

---

## 3. Where the code folder goes

The report contains paths *as Coverity saw them at analysis time*, for example
`src/net/parse.c`. For code-anchored verdicts the tool must map that onto a real
file, so it needs the **source root**: the local folder that
`src/net/parse.c` is relative to.

```
Coverity analysed:      /build/jenkins/workspace/proj        ← "source root" on the build machine
Report path inside:     src/net/parse.c
Your machine:           ~/work/proj/src/net/parse.c
                        ^^^^^^^^^^^^ this is the source root you pass
```

Practical rules:

* **Most common case — the report was made from this very repo:** source root is
  the workspace root: `.` (VS Code passes `${workspaceFolder}`).
* **Repo nested inside a bigger tree:** pass the folder that makes the report's
  paths line up. If the report says `proj/src/net/parse.c` and your checkout is
  `~/work/proj`, the root is `~/work` (its parent), because the report keeps the
  `proj/` segment.
* **Checks out under a different top-level name:** put the file tree so the
  first path segment matches the report; a symlink is enough.
* **You only have part of the tree:** pass what you have. Files that cannot be
  found come back as *Needs review* with an explicit
  "source file could not be located" message — never as an invented verdict.

The tool tells you when resolution fails, and `coverity_source_context` shows
the exact file and line it used, so you can verify the mapping once and trust it
afterwards.

> **Tip** — click through one finding with `coverity_source_context` on your
> first report. If the file it shows is the right file, the root is right for
> every defect in that report.

---

## 4. How the analysis works

This is the same engine the desktop Coverity Findings Analyzer uses. Nothing is
sent anywhere; no Coverity license is needed for this part.

```
index.html / .xlsx
      │  parse_coverity_html / parse_coverity_excel      ── read defects + event trace
      ▼
 defect list (CID, checker, subtype, severity, file, line, function, events)
      │  resolve file against the source root
      ▼
 build_defect_context          ── the enclosing function, its callees/callers,
      │                            signatures, cross-file index (workspace cache)
      ▼
 analyze_defect               ── checker-specific reasoning over that code:
      │                            bounds, lifetimes, null paths, return values, …
      │                            cross-checked with tree-sitter AST facts + clang
      ▼
 disposition + rationale + suggested fix + confidence
      │
      ▼
 Bug │ False positive │ Intentional │ Needs review
```

What each disposition means, and what you should do with it:

| Disposition | Meaning | Typical next step |
| --- | --- | --- |
| **Bug** | The code really can misbehave as Coverity describes; a concrete fix is proposed | Fix it, then ask the agent to re-analyse that CID to confirm the fix |
| **False positive** | The analyser can show why the flagged path cannot happen (null already checked, bounds enforced by a caller, etc.) | Push it as `Ignore` with the rationale as evidence |
| **Intentional** | The behaviour is deliberate (assert-guarded, by design) | Push as `Ignore`, or document it |
| **Needs review** | Not enough evidence to decide mechanically — e.g. no line number in the report, file missing, or a reduced-depth engine | A human decides; the comment states *why* it stopped |

**Depth matters.** `coverity_capabilities` reports `full` or `minimal`. At
`full` the engine has tree-sitter/clang/cppcheck; at `minimal` it can still judge
many checkers but is deliberately quicker to say *Needs review*. The same defect
can therefore be `Bug` at full depth and `Needs review` at minimal — check the
depth before acting on a "weak" verdict.

**Where the code comes in.** For every defect the tool extracts the enclosing
function, its callers and callees, the declarations and guards around the defect
line, and the specific lines the event trace names — an **evidence dossier** that
travels with the verdict, so the agent judges from the same code the engine read.
The verdict is derived from the code it actually read — which is why passing the
source root matters, and why an agent can quote the line back to you.

**Where the answer came from.** Each finding says what the agent read: the report
facts it used (event trace, line) and the exact source range it opened. If the
optional engine is present and was used, the answer says so too. Nothing is ever
presented as verified by a tool that did not run.

**Re-analysis after a fix.** Change the code, then ask:

> Re-analyse CID 1002 in `reports/index.html` with source root `.`

The agent re-reads the file from disk, so the new verdict reflects your edit —
this is how you verify a fix instead of hoping.

---

## 5. Where the output goes

Nothing is written to your repo unless you (or the agent) ask for a file. By
default the answer is *in the chat*, and machine-readable payloads are already in
the tool result.

| Artefact | Where | Produced by | Purpose |
| --- | --- | --- | --- |
| **Chat answer** — disposition table + per-defect rationale, CWE, confidence, suggested fix | the agent's reply | every tool | reading |
| **Cached triage** `<output dir>/<report>.triage.json` | `.coverity/` at the repo root | `coverity_triage_report` | avoids paying for the same analysis twice; agents reload it for follow-up questions |
| **Dispositions CSV** `<output dir>/<report>_dispositions.csv` | `.coverity/` by default, any path if you pass one | `coverity_export_results`, or `analyze --csv` | **hand this to the desktop app to push** ([§7](#7-pushing-dispositions-back)) |
| **JSONL stream** (`--jsonl`) | stdout, one JSON object per defect | CLI | CI logs, piping into other tools |
| **Annotation JSON** (`--out FILE`) | wherever you say | CLI | full payload for a script or a dashboard |
| **Problems-panel diagnostics** | VS Code Problems | the **extension** route | clickable findings in the editor, filtered by `coverityTool.diagnosticDispositions` |

The output directory is `.coverity/` next to the tool (override with
`COVERITY_MCP_OUTPUT_DIR`, or the extension's output setting). It is a cache —
safe to delete, and already git-ignored here.

The CSV columns are exactly the ones the desktop app writes, so a human can read
it in Excel and the desktop Push page can load it:

```
CID, Checker, Type, Severity, Action, File, Line, Function,
Classification, Comment, Fix, Timestamp, Category
```

---

## 6. Getting data out of Coverity Connect

**The agent never talks to Connect and never asks for credentials.** That is
deliberate: credentials stay in the desktop app or on the command line, where
you can see what is being sent. So "getting the data" means *exporting it once*
by one of these routes, then pointing the tools at the export.

| Route | How | When to use |
| --- | --- | --- |
| **A. Desktop app → Pull → export** | Coverity Findings Analyzer → enter your Connect host/user/password → select project, stream, triage store → Pull → save the results (it writes `coverity_dispositions.csv` and can write an `.xlsx`) | the normal path; you already review in this app |
| **B. Coverity web UI export** | Connect → *Defects* view → filter → **Export** → HTML or Excel | no desktop app to hand, or a one-off view |
| **C. CI / command line** | In the build, `cov-analyze` + `cov-format-errors --html-output <dir>`, archive the folder as a build artifact | you want the agent to triage the *same* report the nightly build produced |
| **D. Already have an export** | drop the file in the repo, per [§2](#2-giving-it-input) | someone emailed you the report |

Route C is the one that scales: the report is a build artefact, so the agent can
be pointed at exactly the run you care about, and you keep an audit trail.

What the tool does with any of these is identical — it is just a file.

---

## 7. Pushing dispositions back

Pushing writes to Coverity Connect, so it needs credentials and stays in the
desktop app. The loop is: **agent decides → CSV → desktop app pushes.**

1. **Ask the agent to produce the file:**
   > "Triage `reports/index.html` with source root `.`, then export the results
   > to `reports/triage.csv` so I can push them."

   (Or from the CLI: `python vscode_bridge.py analyze --report reports/index.html
   --src . --csv reports/triage.csv`.)

2. The tool writes the **exact** column layout the desktop app's Push page
   accepts, with Connect's action vocabulary already filled in:

   | Disposition from the agent | `Action` written | What Connect will show |
   | --- | --- | --- |
   | Bug | `Fix Required` | Fix Required |
   | False positive | `Ignore` | Ignore |
   | Intentional | `Ignore` | Ignore |
   | Needs review | `Undecided` | Undecided (a human still has to decide) |

3. **Open the desktop Coverity Findings Analyzer → Push page**, connect to
   Connect (its host/user/password fields), then use **Select Dispositions CSV**
   to choose `reports/triage.csv`. The page lists every CID; double-click any
   row to change a disposition before it goes.
4. Press **Validate CIDs** so the app checks each CID against the server — this
   catches a defect that was fixed or remapped since the report was exported.
5. **Push.** Dispositions are written in batches of at most 100 per call, and a
   pushed comment is stamped with your reviewer name, so the change is
   attributable in Connect.

Checklist before pushing: depth was `full` (`coverity_capabilities`), nothing is
left as *Needs review* unless you meant it, and the rationale text reads the way
you want it to appear in Connect — because that comment is what a reviewer sees
months later.

Without the desktop app? The agent can also give you **paste-ready Connect text**
per defect (Mode C) — ask for it — and the underlying mapping lives in
`coverity_push.py` if you want to script the push yourself.

---

## 8. Copy-paste prompts

| Goal | Prompt |
| --- | --- |
| Overview first | "Use the Coverity tools to triage `reports/index.html` with source root `.`; give me the disposition counts and list anything urgent." |
| Understand one finding | "Explain CID 1002 from `reports/index.html` (source root `.`) — show me the code and why it is a bug." |
| Fix it | "Propose a minimal patch for CID 1002 that keeps behaviour otherwise identical, then re-analyse the file to confirm." |
| Verify a fix | "I changed the file; re-analyse CID 1002 and tell me if it is still a finding." |
| Filter noise | "Which `DEADCODE` defects in this report are false positives and why?" |
| One checker only | "Analyse only `USE_AFTER_FREE` defects with source root `.`." |
| Work with Connect later | "Export the triage of `reports/index.html` to `reports/triage.csv` with the Connect actions filled in." |
| Handle a big report | "Start with the 25 highest-severity defects, summarise, then continue." |
| Check the engine | "Run `coverity_capabilities` and tell me the analysis depth and what is missing." |

---

## 9. When something is wrong

| Symptom | Cause | Fix |
| --- | --- | --- |
| Every defect is *Needs review* with "no concrete defect line (Various)" | Excel export without line numbers, and the checker needs one | Use the HTML export, or a correct `.xlsx` with the `Line` column filled |
| "source file could not be located or read" | Wrong source root | See [§3](#3-where-the-code-folder-goes); verify with `coverity_source_context` |
| Verdicts look shallower than the desktop app | Depth is `minimal` | `pip install -r requirements.txt`, then `python capabilities.py` → `FULL` |
| The agent has no Coverity tools | MCP server not started | `Ctrl+Shift+P` → **MCP: List Servers** → `coverity` → **Start Server**; check `.vscode/mcp.json` |
| Push page says "No valid rows found" | The CSV was edited and lost `CID`/`Classification` | Re-export; both columns are required, `Action` is optional |
| Push page shows fewer rows than the CSV | Duplicate CIDs (last one wins) or a row with an empty CID | Regenerate from the report with `--csv` |
| `#coverity` tool set does nothing | Known VS Code bug with qualified MCP names | Use the tool picker once, or start from `docs/coverity.toolsets.jsonc` — see [VSCODE_AGENTS.md](VSCODE_AGENTS.md) §13 |
| Different verdict than the desktop app | Different engine depth on this machine | Compare `coverity_capabilities` with `python capabilities.py` |

---

## 10. FAQ

**Do I have to install the agent for any of this?**
No. The tools work in any agent. The **Coverity Finding Analyzer**
(`.github/agents/coverity-finding-analyzer.agent.md`) is the packaged version of
the whole job: it reads the code itself, writes the reviewer comment and the
proposed fix per defect, and re-analyses to prove each fix. Install it if you
want that pass done for you rather than assembled yourself.

**Does my code or report leave my machine?**
No. The engine runs locally on your CPU. Agents may summarise results in chat,
which is why the instructions file tells them to quote verdicts, CWE and
confidence, not to paste large chunks of your code.

**Do I need a Coverity license to use this?**
Not to analyse a report you already have. You need Connect access (and
credentials) only to pull new data or push dispositions — and that happens in
the desktop app, not here.

**Will it modify my code?**
No. It writes only its own outputs (`.coverity/` cache, a CSV you asked for).
Patches are shown for you to apply; the agent can edit a file only if you ask an
editing-capable agent to do so, and the instructions require one CID per edit
followed by re-analysis.

**How do I keep results out of Git?**
`.coverity/` is already ignored; keep exported CSVs next to your reports and add
that folder to `.gitignore` too.

**Does it work in CI?**
Yes — the CLI is JSON-only on stdout (`vscode_bridge.py analyze --jsonl`), which
is how the desktop-free path is meant to be scripted.
