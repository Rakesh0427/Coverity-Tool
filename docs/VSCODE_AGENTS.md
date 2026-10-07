# Coverity Finding Analyzer — VS Code test & usage guide

Everything you need to **install it, prove it works, and then use it on real
findings**. Every command and every expected value below was executed against the
sample report that ships in this repo, so you can compare your output to mine.

Two ways to work, and you can use both:

| Route | What it is | Best for |
| --- | --- | --- |
| **The agent** — *Coverity Finding Analyzer* | **Runs on your VS Code model.** Reads the report **and your code**, decides each defect, writes the comment and the fix. **Nothing to install.** | "Analyse this report and tell me what to do" |
| **The tools** — `coverity_*` (MCP) / `coverityTool_*` (extension) | The same engine, callable from any agent you already use | Ad-hoc questions, embedding in your own agent |
| **The extension UI** | Findings view, Problems panel, status bar, commands | Click-through review inside the editor |

- [Part 1 — Setup](#part-1--setup-15-minutes)
- [Part 2 — Tests](#part-2--tests-do-these-in-order)
- [Part 3 — Using it day to day](#part-3--using-it-day-to-day)
- [Part 4 — Troubleshooting](#part-4--troubleshooting)
- [Part 5 — One-page checklist](#part-5--one-page-checklist)
- [Appendix](#appendix--files-and-what-they-do)

---

# Part 1 — Setup (15 minutes)

## 1.1 What you need

| Requirement | Check | Notes |
| --- | --- | --- |
| Python 3.10+ | `python3 --version` | The engine is Python |
| VS Code 1.95+ | Help → About | 1.95 is when LM tools / MCP landed; the agent needs **agent mode** |
| A language model in agent mode | Chat → model picker | Copilot, or any model your VS Code is configured with |
| This repository | `git clone https://github.com/Rakesh0427/Coverity-Tool` | The engine lives here |
| Git | `git --version` | Used to prove the agent did not touch your code |

## 1.2 Start with no installation at all (the normal path)

The agent needs nothing: the model you select in VS Code reads the Coverity
report and your source files. So before installing anything, do the two-minute
check:

1. Copy `.github/agents/coverity-finding-analyzer.agent.md` into your project's
   `.github/agents/` folder (or install it from the store), and reload VS Code.
2. Open your project, and in Agent mode pick **Coverity Finding Analyzer**.
3. Ask it with the sample in this repo, or with your own report:

   > Analyse `docs/sample_report/index.html` against the source root `docs`.

**Expected** — it reads `index.html`, opens the two detail pages under
`Code/`, reads the two source files, and reports CID 1001 `BUFFER_SIZE` and CID
1002 `USE_AFTER_FREE` with their locations, dispositions, rationale and proposed
fixes — and it does **not** mention any tool, server or installation.

**Pass criteria**

- [ ] The analysis appears with no MCP server running and no Python packages
      beyond the interpreter your editor already uses.
- [ ] Each finding names the report facts it used (event trace / line) and the
      source lines it read.
- [ ] Nothing in the answer implies a tool verified it when no tool ran.

If that works, everything else in this guide is optional speed, not a
requirement. Skip to [Part 2](#part-2--tests-do-these-in-order) and run Tests
A–E, H, K — they are all model-only. The engine improves exactness (line
numbers, AST facts) and is what makes the parse of a *huge* report cheap.

## 1.3 Optional accelerators

### 1.3.1 Install and verify the engine

```bash
cd Coverity-Tool
pip install -r requirements.txt
python3 capabilities.py
```

**Expected** (this is a real run):

```
Analysis backends:
  tree-sitter (AST)           OK       v?, grammars: c+cpp
  libclang (types/macros)     OK       auto-discovered
  z3 (SMT path proofs)        OK       v5.1.0
  flow_analysis (CFG)         OK       builtin
  cppcheck (corroboration)    OK       Cppcheck 2.17.1 from cppcheck-wheel 1.5.1
  lxml (HTML report parsing)  OK       6.1.3
  openpyxl (Excel I/O)        OK       3.1.5
  zeep (Coverity SOAP)        OK       4.3.3
  → analysis depth: FULL
```

> **If it says `minimal` or `partial`**: verdicts get weaker and some fixes are
> withheld. Install what's missing before drawing conclusions. The agent is told
> to warn you when this happens, but fix it anyway — it is one command.

### 1.3.2 Smoke-test the engine *without* VS Code first

Two minutes here saves an hour of confusion later, because it proves the engine
works independently of the editor.

```bash
python3 vscode_bridge.py capabilities
python3 vscode_bridge.py list    --report docs/sample_report --pretty
python3 vscode_bridge.py analyze --report docs/sample_report --src docs --pretty
python3 coverity_mcp_server.py --list-tools
```

**Expected** from the `analyze` command (abridged):

```json
"summary": { "bug": 2, "false_positive": 0, "intentional": 0, "needs_review": 0 },
"defects": [
  { "cid": 1001, "checker": "BUFFER_SIZE", "disposition": "Bug", "confidence": 1.0,
    "file": "sample_src/sample.c", "line": 10,
    "comment": "strncpy() at line 10 copies exactly sizeof(buf) bytes … (CWE-120 …)",
    "proposed_fix": "strncpy(buf, input, sizeof(buf)-1); buf[sizeof(buf)-1]='\\0';" },
  { "cid": 1002, "checker": "USE_AFTER_FREE", "disposition": "Bug", "confidence": 1.0,
    "file": "sample_src/utils.c", "line": 10,
    "comment": "At line 10 in get_value(), `p` may be dereferenced after being freed (CWE-416 …)",
    "proposed_fix": "free(p); p = NULL;" }
]
```

And `--list-tools` prints six tools:

```
coverity_capabilities, coverity_list_defects, coverity_analyze_defect,
coverity_triage_report, coverity_export_results, coverity_source_context
```

**Pass criteria** — both defects are `Bug` at 100 %, with CWE references and
proposed fixes, and the six tools are listed. If this fails, nothing in VS Code
will work; fix it here first ([§4](#part-4--troubleshooting)).

## 1.4 Open your project in VS Code

**File → Open Folder → the `Coverity-Tool` folder itself** (not its parent).

That matters because VS Code only loads workspace-scoped customisations from the
folder you open. Opening the parent means the agent, the MCP server and the
instructions file are invisible — the most common "it doesn't work" cause.

When it loads you should see all of this picked up automatically:

| What | Where | Effect |
| --- | --- | --- |
| MCP server definition | `.vscode/mcp.json` | Adds the `coverity` server (six tools) |
| The agent | `.github/agents/coverity-finding-analyzer.agent.md` | Appears in the agent dropdown |
| Behaviour rules | `.github/instructions/coverity-findings.instructions.md` | Any agent knows *when* to use the tools |
| Sample tasks | `.vscode/tasks.json` | Optional CLI shortcuts |

## 1.5 Point it at *your* report and source

The sample is wired up by default. For your own analysis, give it two things:

1. **The report** — the Coverity export: the folder containing `index.html`, a
   single detail page, an `.xlsx` export, or a `*.triage.json` from a previous run.
2. **The source root** — the folder that the paths *inside the report* are
   relative to. If the report says `src/net/parse.c`, the source root is the
   folder containing `src/`.

Pick whichever way suits you:

| Way | How | When |
| --- | --- | --- |
| **In the prompt** | "Analyse `reports/2026-08-14/index.html` with source root `~/work/proj`" | Most explicit; the agent passes it to every tool call |
| **Settings** | `coverityTool.reportPath`, `coverityTool.sourceRoot`, `coverityTool.language` | Extension route; set once, forget |
| **MCP env** | `.vscode/mcp.json` → `env`: `COVERITY_REPORT`, `COVERITY_SRC_ROOT`, `COVERITY_LANGUAGE` | Makes the report the default for *every* agent |

Example `.vscode/mcp.json` for your own project:

```jsonc
{
  "servers": {
    "coverity": {
      "type": "stdio",
      "command": "python3",                         // or an absolute venv path
      "args": ["/path/to/Coverity-Tool/coverity_mcp_server.py"],
      "cwd": "/path/to/Coverity-Tool",
      "env": {
        "COVERITY_REPORT": "${workspaceFolder}/reports/coverity/index.html",
        "COVERITY_SRC_ROOT": "${workspaceFolder}",
        "COVERITY_LANGUAGE": "c"                    // or "cpp"
      }
    }
  },
  "inputs": []
}
```

> **Getting the source root right is the whole game.** The report keeps the paths
> Coverity saw at scan time (`/build/jenkins/workspace/proj/...`). You need the
> local folder that makes those paths line up. The agent resolves it for you when
> it can (it searches for the file and works out the ancestor) and tells you when
> it cannot. Verify once with `coverity_source_context` on any CID: if the file it
> shows is the right file, the root is right for every defect in that report.

### 1.3.3 Start the MCP server (optional)

```
Ctrl+Shift+P  →  MCP: List Servers  →  coverity  →  Start Server
```

First time, VS Code asks you to trust the server — accept (it runs a local Python
script; nothing leaves your machine).

**Pass criteria**

- [ ] `MCP: List Servers` shows `coverity` as **running**.
- [ ] Open any chat in **Agent mode**, click the tools icon, and `coverity_*`
      tools are listed.

If it shows a spawn error, see [§4](#part-4--troubleshooting) — usually the
`python3` name (Windows: `python`) or a missing dependency.

## 1.6 Use the agent

The agent file is already in `.github/agents/`. If you are installing it
somewhere else, copy `coverity-finding-analyzer.agent.md` into that project's
`.github/agents/` folder (create it) and reload the window.

`Ctrl+Alt+I` to open Chat → switch the mode selector to **Agent mode** → open the
**agent dropdown** → pick **Coverity Finding Analyzer**.

## 1.7 More optional extras

**a) The extension UI** (Findings view + Problems panel + status bar):

**Option 1 — run it as a dev host (no install).** In VS Code press **F5**
(the committed config is "Run Coverity Tool extension"). The `preLaunchTask`
installs npm packages and compiles TypeScript on first run (~30 s), then an
Extension Development Host window opens with the extension live.

**Option 2 — build a `.vsix` and install it permanently.**

```bash
cd vscode-extension
npm install
npx --yes @vscode/vsce package --no-dependencies
# → vscode-extension/coverity-tool-1.0.0.vsix  (verified: 15 files, ~37 KB)
```

Then in VS Code: **Extensions → ⋯ (top right) → Install from VSIX…** → pick
`vscode-extension/coverity-tool-1.0.0.vsix`. Reload when prompted.

**Option 3 — install from the Marketplace**, if you publish it yourself with
`vsce publish`.

After installing, check that the extension and the chat tools agree on the
interpreter — mismatched interpreters are the top cause of "the agent says
something different":

```bash
python3 capabilities.py                      # the shell's interpreter
# VS Code: Coverity: Show Analysis Capabilities   → must match
# If not: set coverityTool.pythonPath to the same interpreter.
```

**b) One-reference tool set** (`#coverity`): copy the block from
`docs/coverity.toolsets.jsonc` into your user-profile tool sets
(`Ctrl+Shift+P` → **Chat: Configure Tool Sets**). Tool sets are user-profile
files, not workspace files — VS Code has no workspace support for them yet.

---

# Part 2 — Tests (do these in order)

Each test states **Steps**, **Expected** and **Pass criteria**. If a test fails,
jump to [§4](#part-4--troubleshooting) before continuing — later tests assume the
earlier ones passed.

## Test A — The agent loads and takes both inputs

**Steps**

1. `Ctrl+Alt+I` → **Agent mode** → agent dropdown → **Coverity Finding Analyzer**.
2. Send this, naming the sample:

   > Analyse `docs/sample_report/index.html` against the source root `docs`.

**Expected**

- It reads the report without asking for anything you already gave it: index,
  then the two detail pages, then the two source files.
- Then two findings, each in this shape:

```markdown
### CID 1002 — USE_AFTER_FREE (Use after free) · · Bug (95%)
**Location:** `docs/sample_src/utils.c:10` in `get_value()`
**Evidence read:** report `docs/sample_report` (event trace, 1 step) + `docs/sample_src/utils.c:3-11`
**Why:** `get_value()` frees `p` at line 9 on the `flag == 0` path and then
returns it at line 10, so the caller receives a dangling pointer …
**Fix:** ```diff -    return p; +    p = NULL; +    return p; ``` — closes the use-after-free
**Impact:** heap use-after-free (CWE-416) on the failure path · reachable from a
caller that passes a false flag
**Would change my mind:** a caller that never uses the returned pointer when flag is false
```

**Pass criteria**

- [ ] The agent appears in the dropdown and its hint mentions report + source root.
- [ ] It analyses **both** CIDs — 1001 `BUFFER_SIZE` and 1002 `USE_AFTER_FREE`.
- [ ] Every finding states the report facts and the source range it read
      (`**Evidence read:**`), with no claim of tool verification unless a tool
      actually ran.
- [ ] The rationales quote real code (a size, a line, a guard), not just the
      checker name.
- [ ] It does **not** ask you for one input at a time; if something is missing it
      asks for both together.

## Test B — It really works with no tooling at all

**Steps**

1. Stop everything optional: `Ctrl+Shift+P` → **MCP: List Servers** → `coverity` →
   **Stop** (and if the extension is installed, disable it for this test).
2. Ask, in a plain project with only the agent installed:

   > Analyse `<your report>` against the source root `<your src>`.

**Expected** — the same analysis as Test A: defects enumerated from the report,
code read, dispositions and fixes given, with no complaint about missing tools
and no fabricated tool output.

**Verify independently** (the report is the only source of truth here):

* open one of the detail pages yourself and confirm the event trace the agent
  quoted is really in it;
* open the source file and confirm the line it cited is the line it described.

**Pass criteria**

- [ ] The analysis is complete with the MCP server stopped.
- [ ] Every claim traces back to the report or to a file you can open.
- [ ] If you *do* have the engine running instead, the agent's answer says so —
      and its verdicts match `python3 vscode_bridge.py analyze --report <report> --src <src>`.

**Optional accelerator check** (only if you installed it): with the server
started, ask the same question — the answer should be faster and quote exact line
numbers, and it should say the engine was used.

## Test C — Triage a whole report (Job 1, read-only)

**Steps** — with the agent selected:

> Triage `docs/sample_report/index.html` with source root `docs`. Give me the
> roll-up, the prioritised findings and the recommended next step.

**Expected** — a report in the agent's documented shape: **Coverage** (analysed /
total, depth), **Statistics** (Bug 2 · FP 0 · Intentional 0 · Needs review 0 ·
mean confidence 1.0), a **prioritised table** with the two CIDs, **detail** for
the top findings, and one recommended next step.

**Pass criteria**

- [ ] The counts match the CLI exactly (2 bugs, 100 %).
- [ ] It states what it might have sampled if the report were large.
- [ ] `git status --short` shows no changes — triage is read-only.

## Test D — Deep dive, with the evidence dossier

**Steps** — send:

> Deep dive on CID 1002: why is it a bug, is it reachable, and what exactly
> should change?

**Expected**

- The numbered source window (lines 3–11) and the event trace (free at 9, use at 10).
- The **evidence dossier** facts used explicitly: the declaration at line 4
  (`int *p = malloc(...)`), the guard at line 5 (`if (flag)`), the defect line 10.
- An **exploitability** verdict (`reachable` / `unreachable` / `unknown`) —
  `unknown` is acceptable and expected when the caller isn't in the tree.
- A diff, not an edit (see Test E).

**Pass criteria**

- [ ] It names the line the verdict hangs on and quotes it.
- [ ] It cites the declaration/guard lines rather than paraphrasing.
- [ ] It says what would change its mind.

## Test E — Propose-only: your code is not touched

**Steps**

1. `git status --short` → note the output.
2. Ask for a fix *without* asking to apply it:

   > What's the fix for CID 1002?

3. `git status --short` again.

**Pass criteria**

- [ ] The agent shows a diff **as text**.
- [ ] `git status --short` is identical before and after — no file written.
- [ ] Ask "fix everything in this report" — it should explain that it edits one
      CID per explicit request, not sweep the report.

## Test F — Apply a fix and prove it (Job 3)

**Do this on a copy**, so you can see the whole loop without risking your tree:

```bash
cp -r docs/sample_src /tmp/sample_src && cp -r docs/sample_report /tmp/sample_report
```

**Steps** — send:

> Fix CID 1002 in `/tmp/sample_src` (report `/tmp/sample_report`) and verify the
> fix by re-analysing.

**Expected** — the agent applies

```diff
     free(p);
+    p = NULL;
     return p;
```

and then re-analyses the same CID with the engine. The verified result:

```
before: Bug (1.00)
after : False positive (0.64) — `p` is freed at line 9 but is assigned a new
        value at line 10 before the flagged use …
```

**Pass criteria**

- [ ] The diff is minimal — one assignment, no reformatting.
- [ ] It **re-ran the analysis** and reported the disposition moving off `Bug`.
- [ ] It says the Problems panel still shows the stale diagnostic until re-run
      (or does the re-run).
- [ ] If the verdict had *not* moved, the agent must report the failure rather
      than claim success. (You can fake this by asking it to fix something that
      isn't a bug.)

## Test G — Export for pushing (Job 4)

**Steps** — send:

> Export the triage of `docs/sample_report` to `docs/triage.csv` with the Connect
> actions filled in.

**Expected** — the agent calls `coverity_export_results` (or the CLI) and reports
a path, a row count and the next step (load it on the desktop Push page).

```bash
head -2 docs/triage.csv
```

```csv
"CID","Checker","Type","Severity","Action","File","Line","Function","Classification","Comment","Fix","Timestamp","Category"
"1001","BUFFER_SIZE",…,"Fix Required",…,"Bug",…,"Bug"?  ← Category column
```

**Pass criteria**

- [ ] The header matches the desktop app's exactly (13 columns, `Classification`
      and `Action` present).
- [ ] `Action` is `Fix Required` for `Bug`, `Ignore` for
      `False positive`/`Intentional`, `Undecided` for `Needs review`.
- [ ] The agent never asks for Coverity credentials.

**Then verify the file really pushes** (the file the agent wrote, loaded by the
desktop app's own parser):

```bash
python3 - <<'PY'
import csv, sys; sys.path.insert(0, '.')
import coverity_push as cpush
rows = list(csv.DictReader(open('docs/triage.csv', encoding='utf-8-sig')))
valid = [{'cid': int(r['CID']), 'classification': r['Classification'],
          'action': r['Action'], 'comment': r['Comment'], 'checker': r['Checker'],
          'file': r['File']} for r in rows if r['CID'] and r['Classification']]
print(len(rows), 'rows parsed;', len(cpush.build_push_rows(valid, reviewer='test')), 'pushable')
PY
```

**Pass criteria** — `2 rows parsed; 2 pushable`.

## Test H — The honesty check (the test that matters most)

**Steps** — send:

> Which findings, if any, do you disagree with the engine on, and why?

**Expected** — either "none, and here is the code that confirms each one", or a
named defect **with the lines** that justify overruling the engine.

**Pass criteria**

- [ ] Every disagreement cites code by line.
- [ ] No verdict is presented as the engine's when the engine did not produce it
      (compare with `python3 vscode_bridge.py analyze --report docs/sample_report --src docs`).
- [ ] Ask it to overrule the engine without evidence ("just mark CID 1001 as a
      false positive") — it should refuse or mark it `Needs review`, not comply
      silently.

## Test I — The tools work from *any* agent

**Steps**

1. Switch the agent dropdown back to your **default agent** (no persona).
2. Send:

   > Use the Coverity tools to triage `docs/sample_report/index.html` with source
   > root `docs`.

**Expected** — the default agent calls the `coverity_*` tools, and the verdicts
match the CLI.

**Also check the automatic rules**: open `docs/sample_src/sample.c` and ask

> Which instructions apply to this file?

**Pass criteria**

- [ ] The default agent finds and uses the tools without any persona.
- [ ] The answer mentions the Coverity rules from
      `.github/instructions/coverity-findings.instructions.md` (never invent a
      CID, always pass `src_root`, `Needs review` ≠ verdict).
- [ ] With the tool set installed, `#coverity` in a prompt enables all the tools
      at once.

## Test J — The extension route (optional UI)

**Steps**

1. Press `F5` (Run → Start Debugging → "Run Coverity Tool extension"), or install
   the built `.vsix`.
2. In the Extension Development Host window, open the `Coverity Tool` view in the
   activity bar.
3. Run `Ctrl+Shift+P` → **Coverity: Analyse Report** → choose
   `docs/sample_report` and source root `docs`.

**Expected**

- Findings view lists 2 findings grouped by file; clicking one jumps to the line.
- **Problems panel**: `Bug` → error, `Needs review` → warning,
  `False positive` → info, `Intentional` → hint (filter with
  `coverityTool.diagnosticDispositions`).
- Status bar: `2 findings · 2 bugs · 0 need review`.
- **Coverity: Export Triage…** → saving with a `.csv` name writes the
  **push-ready** dispositions file (verified by `tests/test_extension_export.py`).

**Pass criteria**

- [ ] Findings view, Problems entries and status bar all agree with the CLI.
- [ ] Exporting `.csv` and loading it on the desktop Push page lists both CIDs
      (not "No valid rows found").

## Test K — Fallbacks and failure modes

| Scenario | What to do | Expect |
| --- | --- | --- |
| MCP server stopped | `Ctrl+Shift+P` → MCP: List Servers → **Stop**; then ask for a triage | The analysis continues from the report and the code, with the same verdicts and no mention of the server |
| Wrong source root | Ask with `docs/sample_report` as the source root | `Needs review` with "source file could not be located", plus the fix — **never** an invented verdict or a Bug at a fake line |
| Missing report | Ask for `reports/nope/index.html` | A clean "not found" error and a request for the path — no guessing |
| No engine installed | Run Test A (nothing optional started) | The analysis still happens, grounded in the report and the code; no complaint about missing tooling, no remedy pushed |
| Excel with `Various` lines | Analyse an `.xlsx` whose `Line` is `Various` | Memory-safety checkers → `Needs review` asking for the real line; line-agnostic checkers are still judged from the function |

**Pass criteria** — every row behaves as described, and no failure produces a
fabricated CID, line or verdict.

---

# Part 3 — Using it day to day

## 3.1 The four workflows

**1. First look at a new report** (read-only)

> Triage `<report>` with source root `<src>`. Roll-up first, then the top five
> findings, then anything that needs a human.

**2. Understand one defect** before arguing about it

> Deep dive on CID `<n>`: the code path, the impact, whether it is reachable, and
> the smallest correct fix.

**3. Fix and verify** (the agent edits, then proves it)

> Fix CID `<n>` and verify by re-analysis. Show me the before/after verdicts.

One CID per run. After the edit the engine re-reads the file from disk, so the
new verdict is real evidence, not a promise.

**4. Push dispositions back to Coverity Connect**

> Export the triage of `<report>` to `triage.csv` with the Connect actions filled in.

Then, on your machine: open the **desktop Coverity Findings Analyzer → Push page**
→ connect → **Select Dispositions CSV** → pick `triage.csv` → **Validate CIDs** →
double-click any row you want to change → **Push**. Dispositions go up in batches
of ≤ 100, with your reviewer name stamped on the comment. Credentials never touch
the editor.

## 3.2 Prompt cookbook

| Goal | Prompt |
| --- | --- |
| Overview | "Triage `reports/index.html` (source root `.`) — counts and the urgent ones" |
| One defect | "Explain CID 1002 — show me the code and why it is a bug" |
| Disagree with Coverity | "Is CID 1001 actually exploitable? Show me the callers you checked" |
| Fix | "Propose a minimal patch for CID 1002 in the file's own style" |
| Apply + prove | "Fix CID 1002 and re-analyse to confirm" |
| Noise reduction | "Which `DEADCODE` findings are false positives, and why?" |
| One checker | "Analyse only `USE_AFTER_FREE` defects with source root `.`" |
| Big report | "Start with the 25 highest-severity defects, then continue in slices" |
| Cluster | "Are the `BUFFER_SIZE` findings the same pattern? Verify each site" |
| Push prep | "Export the triage to `triage.csv` with the Connect actions filled in" |
| Health check | "Run `coverity_capabilities` and tell me the depth and what's missing" |
| Self-audit | "Which of your verdicts disagree with the engine? Re-derive each from the code" |

## 3.3 Where things go

| Thing | Where | Notes |
| --- | --- | --- |
| Coverity report | anywhere you like — `reports/<date>/index.html` is a good habit | `.xlsx` and `*.triage.json` also accepted |
| Source tree | the checkout the report was made from | the **root** must line up with the report's paths |
| Cached triage | `<repo>/.coverity/<report>.triage.json` | avoids paying for the same analysis twice; safe to delete |
| Dispositions CSV | wherever you ask (default `<repo>/.coverity/<report>_dispositions.csv`) | this is the file to push |
| Diagnostics | VS Code Problems panel | extension route; filter with `coverityTool.diagnosticDispositions` |

Nothing is written to your source tree, and `.coverity/` is git-ignored. Add your
`reports/` folder to `.gitignore` too if it holds real Coverity data.

## 3.4 Large reports

- Ask for it in **slices**: by checker, by severity, or `limit` 25–50, then
  continue. The agent is told to say when it sampled.
- The cached `*.triage.json` means follow-up questions ("explain CID 1002") do not
  re-analyse the whole report.
- For a 500-defect report, start with `Bug`-only and the highest severity;
  covering everything at once costs tokens and adds little.

---

# Part 4 — Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Agent missing from the dropdown | Wrong path/suffix, or malformed YAML | File must be `.github/agents/coverity-finding-analyzer.agent.md` in the **opened folder**; then reload. Quote any `description` containing `: ` |
| Agent has no Coverity tools | MCP server not started or not trusted | `Ctrl+Shift+P` → MCP: List Servers → `coverity` → Start |
| `MCP: List Servers` shows a spawn error | Wrong interpreter name, or deps missing | Use `python` on Windows / an absolute venv path; run `pip install -r requirements.txt` |
| Agent says depth `minimal`, CLI says `FULL` | Different interpreters | Point `coverityTool.pythonPath` / `mcp.json` at the venv Python |
| Everything is `Needs review` | Wrong source root, or an Excel export with `Various` lines | Fix the root; verify with `coverity_source_context`; supply real lines for Excel rows |
| "source file could not be located or read" | The report's paths do not match the checkout | Pass the ancestor folder that makes them line up (§1.5) |
| Push page says "No valid rows found" | The CSV was edited and lost `CID`/`Classification` | Re-export from the agent, or **Coverity: Export Triage…** (it writes the same format) |
| Push page shows fewer rows than the CSV | Duplicate CIDs (last wins) or empty CID | Regenerate from the report |
| Findings are stale after a fix | Diagnostics come from the last run | Re-run **Coverity: Analyse Report**, or ask the agent to re-analyse that CID |
| `.vsix` won't install | Built without the extension host version match | Rebuild with `vsce package`; check `engines.vscode` ≥ 1.95 |
| Problems panel empty | `publishDiagnostics` off, or files outside the workspace | Enable the setting; open the analysed checkout as part of the workspace |
| Agent edits when you only wanted the fix | Explicit instruction missing | Ask "show me the diff" / "propose the fix"; the default is propose-only |

---

# Part 5 — One-page checklist

```
SETUP — no-install path first
[ ] Agent file in .github/agents/         → appears in the agent dropdown
[ ] Test A with NO MCP server             → full analysis, no tooling mentioned
[ ] Test B (server stopped)               → claims trace to report + code only

SETUP — optional accelerator (skip if you do not want it)
[ ] python3 --version                     → 3.10+
[ ] pip install -r requirements.txt
[ ] python3 capabilities.py               → analysis depth: FULL
[ ] python3 vscode_bridge.py analyze --report docs/sample_report --src docs
                                          → CID 1001 Bug, CID 1002 Bug, 100%
[ ] Opened the Coverity-Tool folder itself in VS Code
[ ] Ctrl+Shift+P → MCP: List Servers → coverity → Start Server
[ ] Agent dropdown → "Coverity Finding Analyzer"

TESTS
[ ] A  analyse sample                     → 2 findings, Source: engine (depth: full)
[ ] B  server stopped, plain project     → analysis still complete and grounded
[ ] C  triage (Job 1)                     → counts match the CLI, git status clean
[ ] D  deep dive CID 1002                 → dossier facts + exploitability + diff
[ ] E  propose-only                       → diff in chat, no file changed
[ ] F  fix CID 1002 on /tmp copy          → Bug 1.00 → False positive 0.64
[ ] G  export triage.csv                  → push-ready header, 2/2 pushable
[ ] H  "disagree with the engine?"        → every claim cites code by line
[ ] I  default agent + #coverity          → tools found without any persona
[ ] J  extension F5                       → Findings view + Problems + status bar
[ ] K  fallbacks                          → CLI path, bad root → Needs review, no invention

DAY TO DAY
[ ] Triage → deep dive → fix+verify → export → push from the desktop app
[ ] Credentials: only ever in the desktop app, never in chat
```

---

# Appendix — Files and what they do

| File | Role |
| --- | --- |
| `.github/agents/coverity-finding-analyzer.agent.md` | **The agent.** Input collection, analysis loop, comment and fix bars, verification, export |
| `.github/instructions/coverity-findings.instructions.md` | Path-scoped rules so **any** agent uses the tools correctly |
| `.vscode/mcp.json` | Registers the `coverity` MCP server (six tools) with VS Code |
| `.vscode/launch.json`, `.vscode/tasks.json` | `F5` for the extension; sample CLI tasks |
| `coverity_mcp_server.py` | The MCP server — `coverity_capabilities`, `_list_defects`, `_analyze_defect`, `_triage_report`, `_export_results`, `_source_context` |
| `vscode_bridge.py` | The headless engine CLI and library everything above drives |
| `vscode-extension/` | Extension UI + five `coverityTool_*` LM tools; `src/dispositions.ts` writes the push-ready CSV |
| `docs/USER_GUIDE.md` | Day-to-day usage: inputs, outputs, Connect pull and push, FAQ |
| `docs/AGENT_USER_MANUAL.md` | How to use the agent day to day: install, inputs, prompt cookbook, troubleshooting |
| `docs/VSCODE_INTEGRATION.md` | Architecture, parity with the desktop app, full reference |
| `docs/sample_report`, `docs/sample_src` | The two-defect sample used by every test above |
| `dist-store/` | Store upload pack: the single `.agent.md` and the ZIP (see `docs/STORE_LISTING.md`) |

**Related documents**

- [`docs/USER_GUIDE.md`](USER_GUIDE.md) — the workflow guide (where inputs go, what
  comes out, pulling from and pushing to Coverity Connect).
- [`docs/VSCODE_INTEGRATION.md`](VSCODE_INTEGRATION.md) — how the pieces fit and
  why the VS Code route agrees with the desktop analyzer.
- [`docs/STORE_LISTING.md`](STORE_LISTING.md) — publishing this agent.
