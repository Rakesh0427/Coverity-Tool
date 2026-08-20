# Coverity Findings Analyzer — User Manual

A local, privacy-preserving decision assistant for triaging **Coverity** and **Coverity Connect** defect reports. It analyses HTML report folders (or Excel exports and direct server pulls) **without uploading your source code anywhere**, extracts the exact surrounding function with tree-sitter, applies deterministic rules per checker, and produces a suggestion: **Bug / False positive / Intentional / Needs review**, with a confidence score, a written justification, and a proposed fix.

---

## 1. What it does

| Step | Where | Result |
|---|---|---|
| 0. Seed the stream *(only if Coverity Connect has no defects yet)* | **🔨 Build, Analyse & Commit to Coverity** on the Setup page, or `cov_commit.py` | `cov-build` → `cov-analyze` → `cov-commit-defects`; stream populated |
| 1. Get defects | HTML report folder, Excel export, or direct **Pull** from Coverity Connect | defect list with checker, file, line |
| 2. Analyse | tree-sitter parses the local source file once per file (cached); rule engine runs per checker | `coverity_dispositions.csv` with classification/comment/fix/confidence |
| 3. Review | Results page — double-click a row | see events, source, suggestion |
| 4. Decide | **Accept Suggestion** or **Override** | `coverity_final_decisions.csv` |
| 5. Push back | **Push these to Coverity** (Results toolbar, direct) or **Push to Coverity** (header, from CSV) | server dispositions updated |

Output files (in your chosen Output folder):

- `coverity_dispositions.csv` — machine suggestions for every defect.
- `audit.jsonl` — full decision log (events, reasoning, confidence, context hash).
- `coverity_final_decisions.csv` — the engineer-approved decisions (accepted or overridden).

---

## 2. Installation

### Prerequisites
- Python 3.10+ (`python --version`).
- Visual Studio Code with the Python extension.
- C/C++ build tools only if a wheel fails to build (tree-sitter ships pre-built wheels for common platforms).

### Steps
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows
# source .venv/bin/activate         # macOS / Linux

pip install -r requirements.txt
```
Verify:
```powershell
python -c "import bs4, lxml, openpyxl, zeep, tree_sitter_c; print('ok')"
```
If your network blocks PyPI, download the wheels on an internet machine and install with:
```powershell
pip install --no-index --find-links=./offline_packages -r requirements.txt
```

### Tool folder
```
coverity_triage/
├── requirements.txt
├── local_gui.py              # MAIN GUI (recommended)
├── coverity_triage.py        # CLI runner (same engine)
├── coverity_gui_excel.py     # alternate GUI
├── heuristic_analyzer.py     # analysis engine (checker rules)
├── decision_agent.py         # weighted-evidence decision logic
├── html_report_parser.py     # reads Coverity HTML / Excel exports
├── coverity_soap_client.py   # Pull/Push via REST + SOAP
├── coverity_push.py          # Push pipeline: select → build → validate → push
├── cov_cli.py                # Drives cov-build / cov-analyze / cov-commit-defects
├── cov_commit.py             # Headless CLI for build → analyse → commit
├── code_extractor.py         # tree-sitter function extraction (cached)
├── context_builder.py        # callees / callers / cross-file context
├── workspace_indexer.py      # workspace symbol + call-site index
└── Setup_Instructions.txt    # VS Code setup guide
```

---

## 3. Command-line (CLI) usage

Analyse an HTML report without the GUI:

```powershell
python coverity_triage.py --report "C:\path\to\report\index.html" --src-root "C:\path\to\source" --language cpp
```

| Flag | Meaning |
|---|---|
| `--report` | Path to the HTML report file, or the folder containing `index.html` |
| `--src-root` | (Recommended) root of your C/C++ source tree |
| `--language` | `c` (default) or `cpp` |
| `--limit N` | Process only the first N defects (testing) |
| `--dry-run` | Show what would be done, run no analysis |
| `--resume` | Skip CIDs already present in `dispositions.csv` |

On completion you get `coverity_dispositions.csv` and `audit.jsonl` in the current folder.

---

## 3b. Seeding an empty Coverity stream (build → analyse → commit)

If Coverity Connect has **no defects yet**, there is nothing to pull. Defects
must first be produced locally and committed to a stream. This is the standard
Coverity CLI pipeline, and the tool can drive it for you:

```
cov-build   --dir <idir> <your build command>   # capture the build
cov-analyze --dir <idir> --all                  # find defects
cov-commit-defects --dir <idir> --host ... --stream ...   # upload
```

**Prerequisites**

- Coverity Analysis (the `cov-*` command-line tools) installed locally. The GUI
  finds them on `PATH`, or you can point it at the install's `bin` folder.
- The **target stream must already exist** in Coverity Connect. Create it in the
  web UI, or with `cov-manage-im --mode streams --add --set name:MY_STREAM`.
- A **clean build**. `cov-build` only captures files that actually compile
  during the run — if everything is already built, it captures nothing.

### From the GUI

Setup page → **🔨 Build, Analyse & Commit to Coverity**:

1. **Coverity Analysis Tools** — leave blank if `cov-build` is on `PATH`,
   otherwise browse to the `bin` folder. The dialog reports whether it found the tools.
2. **Step 1 — Capture** — source folder, intermediate directory (`--dir`), and
   your build command (`make -j8`, `msbuild app.sln`, …). For non-compiled code
   tick *No build command* to scan the tree instead (`--no-command`).
3. **Step 2 — Analyse** — all checkers on by default; *Strip source path* keeps
   reported file paths portable.
4. **Step 3 — Commit** — host, port, stream, and either a username+password or
   (preferred) an **auth key file**.
5. Pick which **stages** to run, optionally tick **Dry run** to see the exact
   commands first, then **Run**. Output streams live into the log; **Cancel run**
   stops it.

When it finishes, use **⬇ Pull from Coverity** to bring the defects in, analyse
and disposition them, then push the dispositions back (section 4.4).

### From the command line (CI / build servers)

```bash
export COVERITY_PASSPHRASE='...'          # never passed as a flag
python cov_commit.py \
    --idir /work/cov-idir \
    --source /work/src \
    --build-command "make -j8" \
    --host coverity.example.com --port 443 \
    --stream MyStream --user rakesh
```

Useful options:

| Option | Purpose |
|---|---|
| `--dry-run` | Print the exact commands without running them. |
| `--stages commit` | Run a subset, e.g. commit an already-analysed `idir`. |
| `--auth-key-file PATH` | Use a key file instead of a password (preferred). |
| `--no-command` | Scan the source tree instead of wrapping a build. |
| `--strip-path P` | Strip a path prefix from reported files (repeatable). |
| `--bin-dir PATH` | Coverity `bin` folder if it is not on `PATH`. |

Exit codes: `0` success, `1` a stage failed, `2` bad configuration. The password
is read from `COVERITY_PASSPHRASE` and deliberately has no command-line flag,
because command lines are visible to other users via the process list.

### Common failures

| Message | Meaning / fix |
|---|---|
| "captured 0 files" / no files emitted | The build didn't recompile anything. Clean first, then re-run. |
| Stream does not exist | Create the stream in Coverity Connect before committing. |
| Authentication failed | Wrong user/password, or use `--auth-key-file`. |
| Certificate not trusted | Keep *Trust new certificate* ticked, or install the CA cert. |
| `cov-build` not found | Add the Coverity `bin` folder to `PATH` or set `--bin-dir`. |

---

## 4. Main GUI — step by step

Start it from the tool folder (venv active):

```powershell
python local_gui.py
```
(Or use `run_gui.bat` / `run_gui.ps1`, which pre-set the Tcl/Tk library paths.)

### 4.1 Setup page
1. **Coverity Report (HTML folder or Excel file)** — browse to the report folder containing `index.html` (or a single `.html` file, or an `.xlsx/.xls` export).
   - The **⬇ Pull from Coverity** button opens the Pull dialog (section 5).
2. **Source Code Root (required)** — the folder containing your actual `.c/.cpp/.h/.hpp` files. The tool refuses to use the report folder itself as the source root.
3. **Output Folder** — where the CSVs are written (default: `Documents`).
4. **Code Language** — `C++ (.cpp / .c)` or `C only (.c)`.
5. Click **▶ Start Disposition**.

### 4.2 Analysis page (automatic)
- Progress bar, **Elapsed / ETC (estimated time to completion)**, and a live log stream.
- At Start the tool first builds a one-time workspace call-site index — you will see *“Indexing source tree once (cached for this run)…”*. The ETA/ETC is computed for the defect loop only (after indexing), so the numbers you see are realistic.
- Every defect is analysed in a background thread; the UI stays responsive. A progress message “X / N analysing…” updates per defect.
- **Important performance note**: the index is built **once**; per-file tree-sitter parsing is cached, so defects in the same file do not re-parse it.
- If any defect cannot be analysed (no source file, no function, or the checker has no rule), it is honestly marked **Needs review** — see section 6.

### 4.3 Results page
- The tree groups defects by category (**Bug / False positive / Intentional / Needs review**) with a live count per category, plus an overall summary line.
- **Double-click a row** to open the detail panel, which shows:
  - Coverity **events** (when the report supplied them), or the synthetic single event for Excel exports;
  - the **source function** extracted by tree-sitter;
  - the **suggestion**: classification, confidence, written justification, and proposed fix.
- Buttons in the detail panel:
  - **✓ Accept Suggestion** — record the machine suggestion as your decision.
  - **✏ Override** — choose your own classification and add a comment, then **Save Override**.
  - **Full code view** — open the whole function in a resizable window (Copy with Ctrl+C works even on disabled text).
- Accepted/overridden rows are written to `coverity_final_decisions.csv` immediately; the summary updates live.
- Use the **filter** drop-down (All / Bug / False positive / Intentional / Needs review) to work through the most important tail first.

### 4.4 Push to Coverity

There are two ways to write dispositions back to Coverity Connect. Both end up
calling the same SOAP `updateTriageForCIDsInTriageStore` operation and both
write the **Classification** and **Comment** attributes into the project's
triage store.

#### A. Direct push from the Results page (no CSV) — recommended

The **⬆ Push these to Coverity** button in the Results toolbar pushes the
defects currently in the table, straight from memory:

1. **Step 1 — Server Connection** — host, port, username, password → **Connect**.
   Tick *Allow self-signed certificate* only for corporate servers whose
   certificate chain you trust.
2. **Step 2 — Project & Triage Store** — pick the project; the matching triage
   store is filled in automatically (you can still edit it).
3. **Step 3 — Which Defects to Push** — choose one of:
   - *Accepted / overridden only* (default, safest) — only defects you explicitly
     reviewed with **Accept** or **Override**.
   - *Everything except 'Needs review'* — every defect the tool classified.
   - *All analysed defects*.
4. **Validate CIDs against Server** — required before pushing. Rows turn
   **green** when the CID exists on the server and **red** when it does not.
   Because CIDs shift between analysis runs, a stale CID is automatically
   remapped by *file + checker* when that resolves to exactly one server defect;
   ambiguous matches stay red and are skipped rather than guessed.
5. **Push to Coverity** — confirm the summary. Tick **Dry run** first to see
   exactly what would be written without touching the server.

After a real push, rows in the Results table are coloured green (pushed) or
red (failed).

Notes:
- An *Accepted* defect pushes its underlying classification (Bug / False
  positive / …), never the literal word "Accepted" — that is a review state in
  this tool, not a Coverity classification.
- Comments get a `[Coverity Tool — user — date]` provenance marker appended so
  reviewers in Connect can see where the triage came from.
- Updates are batched: defects sharing a classification *and* comment go in one
  call, capped at 100 CIDs per request (the server limit).

#### B. Push from a CSV

The header **⬆ Push to Coverity** button opens the CSV-based dialog, useful when
you want to push decisions made in an earlier session or edited by hand:

1. **Connect** — host, port, username, password → **Test Connection**.
2. **Select Project** and **Stream** (streams load after project selection).
3. **Load CSV** — choose `coverity_final_decisions.csv` (or `dispositions.csv`),
   review the row count, then **Push**.

Pushed dispositions are written to the server triage store; any rows rejected by
the server are listed so you can fix and retry.

#### Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Every row fails | Wrong triage store name. It usually matches the **project** name, not `Default`. |
| "zeep library not installed" | Run `pip install zeep`. |
| All CIDs show NOT FOUND | Wrong project selected, or the report came from a different stream/server. |
| Push button stays greyed out | You must **Validate** first, and at least one CID must match. |
| SSL / certificate errors | Corporate self-signed cert — tick *Allow self-signed certificate* (only if you trust the chain). |

---

## 5. Pull defects directly from Coverity Connect

Use **⬇ Pull from Coverity** on the Setup page. This fetches defects with **real, current line numbers** (no “Various” entries) and saves a structured Excel file that the analyser reads directly.

1. **Section 1 — Server Connection**: Host, Port, Username, Password → **Test Connection**.
2. **Section 2 — Project & Stream**: pick the Project, then the Stream (all streams if “All” is offered).
3. **Options**: max defects to pull (default 5000), and **Fix current lines via REST** (recommended — overrides the older SOAP line numbers with the web-UI line numbers).
4. **Export data**: choose the output location and **Pull** — progress is shown; on success the generated Excel path is returned and pre-filled into the Setup page input.
5. Click **▶ Start Disposition** on the Setup page afterwards.

The client tries the REST v2 API first and automatically falls back to SOAP. The SOAP path paginates with the exact pageSpec element casing that Coverity 2025.9 requires (`sortAscending`, `pageSize`, `startIndex`, `sortField`), which avoids the previously-seen **“Missing element sortAscending”** fault.

---

## 6. Classifications and the “Needs review” tail

The engine assigns one of four dispositions for each defect:

| Disposition | Meaning | Reviewer action |
|---|---|---|
| **Bug** | Real defect at the flagged location | Fix it (see the proposed fix) or confirm and accept |
| **False positive** | A rule inspected the data/trace and concluded the behaviour is benign | Accept (no fix) |
| **Intentional** | The code consciously does this (`(void)` cast, ignore comment, `#if 0`, etc.) | Accept (no fix) |
| **Needs review** | No source/function, the checker has no rule, or the evidence is genuinely conflicting | Manual review |

Common reasons a finding ends up **Needs review** (all are expected/engineered, not failures):

- **No source file / no function** could be located for the defect (fix the `--src-root` / source-root path).
- **‘Various’ line numbers in an Excel export** for a memory-safety checker. The tool analyses line-agnostic (“function-scoped”) checkers even when the line is ‘Various’ (e.g. `CHECKED_RETURN`, `UNUSED_VALUE`, `DEADCODE`, `INTEGER_OVERFLOW`) and caps their confidence, but for memory-safety checkers (e.g. `OVERRUN`, `BUFFER_SIZE`, `FORWARD_NULL`) it asks you to provide the exact line rather than guess.
- **Checker with no dedicated rule** — add one in `heuristic_analyzer.py` (see section 8).
- **Truly contradictory evidence** within the function — the engine is conservative by design.

### Rule coverage (heuristic_analyzer.py)
Among the checkers with built-in rules (there are ~20): `OVERRUN`/`BUFFER_SIZE`, `INTEGER_OVERFLOW`, `FORWARD_NULL`, `REVERSE_INULL`, `UNINIT`, `USE_AFTER_FREE`, `DIVIDE_BY_ZERO`, `RESOURCE_LEAK`, `ARRAY_VS_SINGLETON`, `NEGATIVE_RETURNS`, `STRING_NULL`, `SIZEOF_MISMATCH`, `SHIFT_OVERFLOW`, `CONSTANT_EXPRESSION_RESULT`, `MISSING_BREAK`/`NO_BREAK`, `DEADCODE`, `UNUSED_VALUE`, and `CHECKED_RETURN` (with its `CHECKED_QRS` alias). Unlisted checkers use a generic evidence classifier, or fall to Needs review if there is nothing to reason from.

For example, `CHECKED_RETURN` is decided as:
- return explicitly cast `(void)` / ignore comment → **Intentional**;
- return is captured or tested (`rc = fn(...)`, `if (fn(...) < 0)`) → **False positive**;
- return discarded from a critical function (e.g. `connect`, `recv`, `read`, `malloc`, `pthread_mutex_lock`, `open`/`close`) → **Bug**;
- return discarded from a benign/cosmetic function (e.g. `printf`, `snprintf`, `memcpy`) → **False positive**.

---

## 7. Troubleshooting & performance

**Tool feels slow / stuck**
- The one-time workspace index is built at Start (visible in the log). It is cached for the session, so the **second run is fast**.
- Per-file tree-sitter parsing is cached, so many defects in the same file are cheap.
- If it genuinely hangs on a specific report, look at the log for the last `[Source] Loading:` line to see which file/checker it is stuck on, and report it to the tool owner.

**“No table found in HTML report”**
- The HTML layout differs from what the parser expects. Open `index.html`, find the table, and adjust `html_report_parser.py` (or provide a sample).

**“File not found” for source files**
- Your Coverity report paths must match the on-disk layout. Use `--src-root` / the **Source Code Root** field to point at the correct root; the tool also searches by filename suffix.

**tree-sitter fails to parse my C++ code**
- Use the **C++ (.cpp / .c)** language option. For mixed C/C++ projects run twice (once `c`, once `cpp`).

**Pull fails with a SOAP fault**
- Copy the log messages (the REST error and every `[shape, pageSize=…]` line). The most common one, `Missing element sortAscending`, is now handled, but if a different shape is rejected, the log tells us exactly which pageSpec your server wants.

**“Needs review” for everything**
- That is the intended behaviour for checkers that have no rule yet and no reliable evidence. See section 8 to add a rule.

**Re-running after editing source**
- Files are cached by mtime; if you edit a source file the file-parse cache is invalidated automatically on the next read. The workspace call-site index is rebuilt at the next analysis.

---

## 8. Extending the engine (adding a checker)

1. Open `heuristic_analyzer.py`; find `analyze_defect()` and its `dispatch = { … }` table.
2. Add `'YOUR_CHECKER': _analyze_your_checker,` and write `_analyze_your_checker(...)` returning `(classification, comment, fix, confidence)`.
3. `heuristic_analyzer.py` uses `decision_agent.build_evidence()` to accumulate weighted Bug/FP evidence, and `DecisionAgent.evaluate()` to pick a verdict — reuse these for consistent confidence scoring.
4. Restart `local_gui.py` — the new checker is analysed immediately.

Example micro-pattern (the CHECKED_RETURN rule ships with this shape):
```python
def _analyze_my_code_quality(code, sub_checker, events, *args, **kw):
    acc = EvidenceAccumulator()
    if re.search(r"\(void\)", code):
        acc.add(Evidence("explicit_void_cast", polarity="fp", weight=0.9,
                         description="Return deliberately ignored."))
    dec = DecisionAgent.evaluate(acc, 'MY_CHECKER')
    return "Intentional" if dec.classification in ("False positive", "Intentional") else "Needs review", \
           "reason", "fix", dec.confidence
```

---

## 9. Quick start (TL;DR)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python local_gui.py
```
1. Point **Coverity Report** at your `index.html` report folder (or **⬇ Pull from Coverity**).
2. Set **Source Code Root** to your C/C++ sources.
3. **▶ Start Disposition** → wait → double-click and **Accept / Override** each finding.
4. **⬆ Push to Coverity** to write decisions back, or **Export to Excel**.

*Source code never leaves your machine.*
