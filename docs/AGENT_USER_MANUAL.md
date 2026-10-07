# Coverity Finding Analyzer — user manual

**What it is.** One VS Code agent that takes a Coverity report and your source
tree, decides what each defect really is, and writes — per defect — a
disposition, a reviewer-grade comment you could paste into Coverity Connect, and
a proposed fix.

**What it needs.** VS Code with Copilot Chat, and a model you have picked in the
model dropdown. That is all. It runs on the **VS Code model**, not on the local
Coverity Tool engine: the model reads the report's detail pages and your source
files itself. No Python, no engine, no MCP server, no Coverity licence, and the
report never has to leave your machine.

**Where it lives.**

| | |
| --- | --- |
| The agent file | `.github/agents/coverity-finding-analyzer.agent.md` |
| Store upload | `dist-store/coverity-finding-analyzer.agent.md` (same file) |
| Test runbook (step-by-step with expected results) | [`docs/VSCODE_AGENTS.md`](VSCODE_AGENTS.md) |
| Optional accelerator (engine, MCP, extension) | [`docs/VSCODE_INTEGRATION.md`](VSCODE_INTEGRATION.md) |

---

## 1. Install it (two minutes)

Pick one route:

| Route | Do this | Then |
| --- | --- | --- |
| **Store** | Install **Coverity Finding Analyzer** from your AI store | Reload VS Code |
| **Copy the file** | Copy `coverity-finding-analyzer.agent.md` into your project's `.github/agents/` folder | Reload VS Code |
| **This repo** | Nothing — the folder is already committed | — |

Then: open **Chat** → switch to **Agent** mode → click the agent picker (the
dropdown next to the model name) → choose **Coverity Finding Analyzer**.

**Sanity check.** Ask it:

> What do you need from me before you can analyse a Coverity report?

It should answer with exactly two things — the report location and the source
root — and say it needs nothing installed. If it asks you to install something,
you are talking to the wrong agent, or to a stale copy of this one.

---

## 2. The two inputs, and how to give them

Everything else is optional. Get these two right and the answers are good.

### 2.1 The report

Any of these work; the first is best:

| You have | Give it | Notes |
| --- | --- | --- |
| A Coverity HTML export folder | the folder containing `index.html` | Event traces and code excerpts — the richest input |
| A single detail page | the `.html` file | One defect's worth of facts only |
| A CSV export | the `.csv` | Columns vary by template; no event trace |
| An Excel export | the `.xlsx` | Needs one conversion step (the agent gives you the exact snippet); `Line` is often `Various` |

### 2.2 The source root

The source root is **the folder the report's file paths are relative to**. That
is the one thing people get wrong, and it is the difference between a verdict
and `Needs review`.

The report says `sample_src/utils.c`; on disk that file is
`docs/sample_src/utils.c` — so the source root is `docs`.

Two more examples:

| Report's `File` column | File on disk | Source root to give |
| --- | --- | --- |
| `src/net/tcp.c` | `/work/myproj/src/net/tcp.c` | `/work/myproj` |
| `/build/bob/agent/src/a.c` | `/home/me/agent/src/a.c` | `/home/me/agent` + the mapping (below) |

Never guess: if you give the wrong root, say so and ask again — the agent is
supposed to say which file it could not find rather than invent a verdict.

### 2.3 How to phrase it

One line, both paths, explicit:

> Analyse `docs/sample_report/index.html` against the source root `docs`.

For build-machine paths, add the mapping in words:

> Analyse `coverity/report/index.html` against source root `~/repo/agent`.
> The report's `/build/bob/agent/...` paths map to `src/...` under that root.

---

## 3. The five jobs

Ask for one job at a time. The agent recognises these five.

| Job | Example prompt | You get |
| --- | --- | --- |
| **1. Triage a report** | *"Analyse `report/index.html` against source root `src`. Only severity High and above."* | Roll-up, prioritised table, detail for the top findings, the `Needs review` list with reasons, one recommended next action |
| **2. Deep dive one defect** | *"Deep dive on CID 1002: is it reachable from input a user controls?"* | Event trace, the code lines read, the path from input to defect in one sentence, a reachability verdict (`reachable` / `unreachable` / `unknown`), impact, fix |
| **3. Fix and verify** | *"Fix CID 1002 and verify it."* | One-CID patch as a diff, then a re-check of that defect against the changed code — and the plain statement that only a fresh Coverity scan re-certifies it |
| **4. Write-back and export** | *"Export the dispositions CSV for the Desktop Push page."* | A 13-column CSV you can load in the desktop app, plus paste-ready Connect text |
| **5. Diagnose and improve** | *"Half of these came back Needs review — why, and what would fix it?"* | The source-root resolution, the files it could not find, and the levers that would sharpen the analysis |

---

## 4. Prompt cookbook

Copy these. The bracketed parts are the only things you change.

### 4.1 First run, on the shipped sample

```
Analyse docs/sample_report/index.html against the source root docs.
```

**You should get** CID 1001 `BUFFER_SIZE` in `sample_src/sample.c`
(`vulnerable_copy`) and CID 1002 `USE_AFTER_FREE` in `sample_src/utils.c`
(`get_value`), each with its location, the code lines it read, a disposition, a
rationale and a fix — and no mention of any tool, server or installation.

**If the model still has to read a big report**, hand it a flat digest instead —
this exact command works on the shipped sample, and works on your report the same
way: `python3 coverity_report_text.py docs/sample_report --limit 40`.

### 4.2 Triage your own report

```
Analyse the Coverity report at <report/index.html> against the source root <src>.
Give me the roll-up, then a table sorted by severity. Work through the top 25
in detail and list the rest.
```

### 4.3 Triage a slice

```
From <report/index.html>, triage only the memory-safety and buffer checkers
against <src>. Skip anything in generated/ or third_party/.
```

### 4.4 One defect, in depth

```
Deep dive CID <12345>: what is the exact path from input to defect, is it
reachable in production, and what is the impact? Read the callers before you
answer the reachability question.
```

### 4.5 Ask it to justify itself

```
For CID <12345>, quote the exact lines you relied on and say what would change
your mind.
```

This is the cheapest quality check there is: a verdict with no quotable lines,
or with no answer to "what would change your mind", is the one to re-check.

### 4.6 Fix one defect

```
Fix CID <12345> and verify it.
```

One CID per run, deliberately: patches land one at a time, and the verification
is about that defect, not a bundle.

### 4.7 Fix it but do not touch the file

```
Show me the diff for CID <12345> but do not apply it — I want to hand it to a
reviewer.
```

By default the agent proposes only; it edits files when you ask it to (*"apply
it"*, *"fix it"*, *"make the change"*, *"patch the file"*).

### 4.8 Push-ready output

```
Write the dispositions CSV for these CIDs — <list> — to coverity-dispositions.csv,
using the 13-column Push-page layout.
```

```
Draft the Coverity Connect comment for CID <12345> so I can paste it into the
Triage page.
```

### 4.9 Big report, no context blow-up

```
<report/index.html> has about 400 findings. Slice it: analyse CIDs <1000>-<1050>
now, and tell me the roll-up counts for the whole report first so I can plan the
rest.
```

```
Summarise the whole report as a table only — CID, checker, severity, file — then
deep-dive CID <12345>.
```

### 4.10 Challenge the result

```
Which of the verdicts in this run are you least sure about? Re-derive the two
weakest ones from the code alone and tell me what changed.
```

```
You marked CID <12345> as False positive. Make the strongest possible case that
it is a real bug, then tell me which side the evidence supports.
```

### 4.11 Design context changes the answer

```
CID <12345> is in code that only ever runs on a trusted, in-process buffer — we
established that in review. Does that change the disposition? If it does, say
which line of the report or code you were weighing.
```

Give the agent what the report cannot know. It is allowed to use it — but it
should say so in the comment, not quietly upgrade the verdict.

### 4.12 Explain a checker to the team

```
Explain in three sentences what BUFFER_SIZE looks for and how a reviewer should
judge it, then rate our four findings from that checker.
```

### 4.13 Two findings that look identical

```
CID <111> and CID <222> are both NULL_RETURNS. Why did you treat them
differently — or should they have the same disposition?
```

### 4.14 Reviewer hand-off

```
Write these findings up as a review note for the team: one paragraph per defect,
harshest first, ending with what needs a human decision.
```

---

## 5. Six prompting rules that change the result most

1. **Both paths, explicitly, in the first message.** Vague locations cost you a
   round trip and invite guessing. `report/index.html` + source root `src` beats
   "the report in my workspace".
2. **One CID per fix.** Multi-CID fix requests get refused or split for a
   reason: each patch needs its own verification.
3. **Ask for the evidence you intend to check.** "Quote the lines you relied on"
   turns an opinion into something you can audit in ten seconds.
4. **Say what you know.** A trusted input, a deliberate non-termination, a
   wrapper that always null-checks — tell it. Report facts cannot contain that,
   and it changes `Bug` into `Intentional` legitimately.
5. **Push back once.** "Make the strongest case for the opposite" is how you find
   the verdicts that were assumptions.
6. **Triage first, export second.** Get the dispositions right, then ask for the
   CSV. Exporting from an unreviewed run just makes bad verdicts loadable.

### Prompts that waste your time

| Instead of | Why it is weak | Better |
| --- | --- | --- |
| "Is this code safe?" (no report, no CID) | No defect to anchor to | "Analyse CID 1002 in `<report>` against (`<src>`)" |
| "Find all bugs in my project" | Not a Coverity job; the agent does not scan | "Triage the report at `<report>`; here is the source root" |
| "Fix everything" | No verification is possible per defect | "Fix CID 1002 and verify it" |
| "Mark all of these False positive" | Invites rubber-stamping | "Which of these are genuinely false positives, and what is the proof for each?" |
| "Just give me the CSV" | Export of unreviewed verdicts | Triage → review → then export |

---

## 6. Reading the answer

Each finding arrives in this shape:

```markdown
### CID 1002 — USE_AFTER_FREE (Use after free) · utils.c:10 · Bug (95%)
**Location:** docs/sample_src/utils.c:10 in `get_value()`
**Evidence read:** report docs/sample_report (event trace, 1 step) + utils.c:3-11
**Why:** `free(p)` runs on the `flag == 0` path (line 9) and line 10 returns the
freed pointer, so the caller holds a dangling pointer into the heap block …
**Fix:** diff shown inline — `free(p); p = NULL; return p;`
**Impact:** heap use-after-free (CWE-416), reachable whenever `get_value(0)` is called
**Would change my mind:** a caller that clears the pointer before using it
```

What the fields mean:

| Field | Read it as |
| --- | --- |
| **Location** | The file and line in *your* checkout — the line the verdict hangs on |
| **Evidence read** | Exactly what the agent inspected: report facts and the source ranges. If this is thin, the verdict is thin. |
| **Why** | The reasoning, with the values (sizes, guards, lines) that decide it |
| **Fix** | A minimal, compilable change, or an honest statement that the fix depends on intent you do not have |
| **Impact / reachability** | `reachable`, `unreachable` or `unknown` — `unknown` is a valid, honest answer |
| **Would change my mind** | The cheapest way to see whether the verdict rests on an assumption |

**Dispositions** are a closed set of four: `Bug`, `False positive`,
`Intentional`, `Needs review`. `Needs review` means "the evidence does not
decide it" — it is not a soft Bug, and it must not be pushed as one. Each one maps
onto Coverity Connect like this, in the CSV and in your triage:

| Disposition | Connect classification | Suggested action |
| --- | --- | --- |
| `Bug` | `Bug` | `Fix Required` |
| `False positive` | `False Positive` | `Ignore` |
| `Intentional` | `Intentional` | `Ignore` |
| `Needs review` | `Pending` | `Undecided` |

**Trust levels.** The answer always tells you where it came from. If it says it
read the report and the code, that is the model's reading — good, auditable, and
not a Coverity scan. If your workspace also has the optional engine installed
and the agent used it, the answer will say so and quote its numbers. Nothing is
ever presented as tool-verified when no tool ran.

---

## 7. Worked example, end to end

Four prompts, using the sample that ships in this repo.

**1 — Triage**

```
Analyse docs/sample_report/index.html against the source root docs.
```

Expected: two findings. CID 1001 `BUFFER_SIZE` in `sample_src/sample.c` — the
`strncpy(buf, input, sizeof(buf))` on line 9 leaves `buf` without a NUL
terminator, and line 10 prints it. CID 1002 `USE_AFTER_FREE` in
`sample_src/utils.c` — `free(p)` on line 9, `return p` on line 10.

**2 — Deep dive**

```
Deep dive CID 1001. Is it reachable from an attacker-controlled input?
```

Expected: it reads `main()` in the same file, sees `argv[1]` flowing into
`vulnerable_copy`, and rates it `reachable` — the argument comes from the command
line.

**3 — Fix**

```
Fix CID 1001 and verify it.
```

Expected: a diff on the line 9 copy (bounded to `sizeof(buf) - 1`, plus an
explicit terminator), then a re-check: re-read of the changed lines and a walk of
the original event trace through them, with the statement that only a fresh
Coverity scan re-certifies the defect.

**4 — Export**

```
Export the dispositions CSV to coverity-dispositions.csv.
```

Expected: exactly this header, one row per CID:

```
"CID","Checker","Type","Severity","Action","File","Line","Function","Classification","Comment","Fix","Timestamp","Category"
```

Then load it in the desktop **Coverity Findings Analyzer** → **Push** page →
**Select Dispositions CSV** → **Validate CIDs**. Keep any `Needs review` rows for
a human; they are exported as `Undecided`.

---

## 8. Big reports

A 5,000-finding export is not a one-prompt job — it is a slicing job.

| Situation | Do this |
| --- | --- |
| Hundreds of findings | "Roll-up table only, all CIDs" → then "deep-dive CIDs `<a>`-`<b>`" in slices of ~25–50 |
| One checker dominates | "All the `RESOURCE_LEAK` findings in `src/net/`, one by one" |
| You only care about the crash risks | "Only the memory-safety checkers, severity High+" |
| The HTML is huge | `python3 coverity_report_text.py <report-folder> --limit 40` prints a flat digest (CIDs, files, event traces, code) you can paste in, and `--cid 1002` narrows to one |
| Excel export | Ask the agent for the conversion snippet; it uses `openpyxl`, and warns you that `Line` is often `Various` |
| Report-only facts are thin | Ask for the HTML export instead of the spreadsheet — detail pages carry the event trace |

---

## 9. What it writes, and where

| Default | When you ask |
| --- | --- |
| Nothing. Verdicts, comments and diffs come back **as text** in the chat. | *"Apply it"* / *"Fix CID X"* edits **one** CID's code. *"Export the CSV"* writes the path you name — say `coverity-dispositions.csv` and it lands in your workspace root. |

Two things it never does: contact Coverity Connect, or ask for credentials.
Write-back stays your step, in the desktop app or the CLI, where you can see
exactly what is sent.

---

## 10. When something looks wrong

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| The agent is not in the picker | File not in `.github/agents/`, or VS Code not reloaded | Check the path, reload the window |
| "I need the source root" | It only got a report path | Give both paths in one line (§2.3) |
| Everything is `Needs review` | Wrong source root, or the files are not in the workspace | Answer with the mapping; check the file the agent named |
| A verdict looks wrong | Thin evidence | Ask it to quote the lines and what would change its mind (§4.5) |
| "File not found" for every path | Build-machine absolute paths | Give the mapping explicitly (§2.3) |
| Excel export has `Various` lines | Line-agnostic rows are normal in spreadsheets | Export HTML for those CIDs, or ask the checker's own question from the function |
| The report is too big to read | Context budget | Slice it, or use `coverity_report_text.py` |
| A file changed and you did not ask | It understood an instruction as "apply" | Say *"propose only, do not edit"*; check the diff before committing |
| The CSV will not load in the Push page | Header or column order | Ask it to rewrite the file using the 13-column layout verbatim |
| It mentions a tool you do not have | Stale copy of the agent | Update to the current `coverity-finding-analyzer.agent.md` |

---

## 11. The optional accelerator

If your workspace also contains the Coverity Tool engine, install its
requirements and start the MCP server, and the agent will use it for exact line
numbers and an AST-anchored first pass:

```bash
pip install -r requirements.txt      # in the Coverity Tool checkout
python capabilities.py               # expect: analysis depth: FULL
```

Then `Ctrl+Shift+P` → **MCP: List Servers** → `coverity` → **Start Server**.

This is a precision and speed upgrade, never a requirement — the agent works
identically without it and will not mention it if it is not there. Details:
[`docs/VSCODE_INTEGRATION.md`](VSCODE_INTEGRATION.md). Engine verdicts for the
sample and the desktop-app parity story: [`docs/USER_GUIDE.md`](USER_GUIDE.md).

---

## 12. Quick reference

| Ask this | To get |
| --- | --- |
| `Analyse <report> against the source root <src>.` | Full triage: roll-up, table, dispositions, fixes |
| `Deep dive CID <n>.` | The trace, the code, reachability, impact |
| `Why is CID <n> a Bug? Quote the lines.` | Auditable reasoning |
| `What would change your mind about CID <n>?` | The assumption underneath |
| `Fix CID <n> and verify it.` | One-CID patch + re-check |
| `Show the diff for CID <n>, do not apply it.` | Proposal only |
| `Which verdicts are you least sure about?` | Self-audit, weakest first |
| `Roll-up table only for all CIDs.` | A plan before the deep work |
| `Export the dispositions CSV to coverity-dispositions.csv.` | Push-ready file |
| `Draft the Connect comment for CID <n>.` | Paste-ready triage text |
