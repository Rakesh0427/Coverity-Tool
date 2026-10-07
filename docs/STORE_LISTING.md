# Coverity Finding Analyzer — store listing copy

Paste these fields into the store's contribution form. Everything here is also
written into the upload bundle as `README.md`.

> **What this upload is.** One agent that takes a Coverity report plus your
> source tree and produces, per defect, a disposition, a reviewer-grade comment
> and a proposed fix. **It runs on the language model you already have in VS
> Code — install nothing.** The model reads the report's detail pages (event
> trace, code excerpt) and your source files, and decides. If your project also
> contains the optional Coverity Tool engine, the agent will use it to fetch
> exact line numbers faster — never as a requirement.

---

## Title

**Coverity Finding Analyzer — analyse, decide and fix Coverity C/C++ findings**

## Short description (one line)

Give it a Coverity report and your source: it reads the code, decides whether
each finding is a bug or a false positive, and writes the comment and the fix.

## Long description

Coverity hands you a defect ID, a checker name and an event trace — and then the
work starts. Is it real? What is the impact? What is the smallest correct fix,
and how do you prove it closed the defect? Doing that by hand, defect after
defect, is where triage time goes.

**Coverity Finding Analyzer** does that pass for you:

- **No installation.** It works in any project with a Coverity HTML or CSV
  export: no Python, no engine, no MCP server, no Coverity licence.
- **You supply two things** — the Coverity report (`index.html` folder, a single
  HTML page, or a CSV export) and the root of the source tree. If the report's
  paths do not line up with your checkout, the agent resolves the correct root
  (or tells you which files are missing) instead of guessing. `.xlsx` exports
  need one conversion step, which the agent spells out.
- **It reads your code, not just the report.** For each defect it opens the
  enclosing function, the callees the event trace names, the callers that supply
  the data, the guards and the sizes — and quotes the lines it relied on. The
  checker's question — is the bound right, is the object still alive, can this
  pointer be null — is answered from the code.
- **It decides, and shows its work.** One of four dispositions, with the
  evidence quoted by line: `Bug`, `False positive`, `Intentional`, or
  `Needs review` when a human genuinely has to decide. Disagreement with the
  underlying engine is allowed — but only with code to back it, never by
  assertion.
- **It says what its evidence was.** Each finding states the report and the
  exact source range it read, and when the optional engine was used it says so —
  so you can always tell tool-verified facts from the model's reading.
- **It never stalls on a missing tool.** No engine, no server, no problem: the
  analysis still happens, and the agent does not mention tooling you never
  installed.
- **It writes the comment a reviewer needs** — what is wrong, the numbers that
  prove it, what happens at runtime — instead of restating the checker's name.
- **It writes the fix**: minimal, compilable, in your file's own style, with one
  line on why it closes the defect, plus an alternative when there is a real
  trade-off.
- **It proposes; you decide.** By default it hands you the comment and the diff
  as text and never touches the working tree. It edits only when you ask it to
  change the code — one defect per run — and then re-checks that defect and says
  plainly that only a fresh Coverity scan re-certifies it.
- **It prepares the write-back.** Paste-ready Coverity Connect text, and it
  writes the dispositions CSV itself — same 13 columns the desktop Coverity
  Findings Analyzer loads on its Push page, with the standard mapping
  (`Bug` → Fix Required, `False positive` / `Intentional` → Ignore,
  `Needs review` → Undecided). It never asks for your Connect credentials.

## What is in the bundle

`.github/agents/coverity-finding-analyzer.agent.md` — the agent itself, one file.

This project also contains the **Coverity Tool** engine (`vscode_bridge.py` and
its dependencies), and the agent's *capability* comes from it: the engine reads
the Coverity report and the C/C++ tree and returns deterministic facts — event
traces, source anchoring, checker mechanics, CWE/CERT references and a first-pass
verdict. Those facts are the agent's evidence base. The agent may confirm them,
and it may overrule them with code it has read, but it never invents what it
could not see. Install the engine's requirements for the deepest analysis
(`python capabilities.py` → `analysis depth: FULL`); without them the agent still
analyses, and labels its verdicts *model-only, unverified*.

## Tags

`coverity` · `triage` · `false positive` · `c-cpp` · `static analysis` ·
`code review` · `fix` · `agent`

## Requirements

| Requirement | Detail |
| --- | --- |
| Editor | VS Code with a language model available in agent mode |
| Model | Any model in the picker — the agent runs on your selection |
| Engine checkout | **Not required.** Optional accelerator: this repository with `pip install -r requirements.txt` |
| Coverity export | An HTML folder/`index.html`, a single HTML page, or a CSV (`.xlsx` needs one conversion) |
| Coverity licence | **Not required** to analyse an existing report |
| Coverity Connect access | **Not required** by the agent; only for pulling or pushing in your own tooling |

**Not included:** Coverity Connect credentials, the Coverity license, and any
operation that talks to your Coverity server. Pulling defects and pushing
dispositions stay in your own tooling and your own hands.

| Field | Value |
| --- | --- |
| Category | Code analysis / Developer tools |
| Version | 1.0.0 |
| Licence | MIT |
| Agent file | `.github/agents/coverity-finding-analyzer.agent.md` |

## Installation

**Option 1 — drop the file in (fastest).** Download
`coverity-finding-analyzer.agent.md`, put it in `.github/agents/` of your
project (create the folder if needed), and reload VS Code. The agent appears in
the chat agent picker as **Coverity Finding Analyzer**.

**Option 2 — the ZIP.** Download
`coverity-finding-analyzer-v1.0.0.zip`; its root already contains
`.github/agents/coverity-finding-analyzer.agent.md`. Unzip it over the root of
your project (or your user profile) and reload VS Code. `README.md` inside the
ZIP is this file.

That is all — there is nothing else to install. If you also keep a checkout of
this project in the workspace and want the faster, line-exact route, install its
requirements and start the MCP server once per session:

```bash
pip install -r requirements.txt      # in the Coverity Tool checkout
```

> `Ctrl+Shift+P` → **MCP: List Servers** → `coverity` → **Start Server**

Full walkthrough: `docs/VSCODE_AGENTS.md`. Day-to-day usage (where the report
and source go, what lands where, Connect pull and push): `docs/USER_GUIDE.md`.

## First test

In agent mode, pick **Coverity Finding Analyzer**, then:

> Analyse `docs/sample_report/index.html` against the source root `docs`.

Expected: it reads the report's two detail pages, then reports two defects — CID
1001 (`BUFFER_SIZE`, `sample.c`) and CID 1002 (`USE_AFTER_FREE`, `utils.c`) —
each with the location, the code lines it read, a disposition, a rationale, and
a proposed fix. Nothing needs to be installed for this, and the agent should not
mention any tooling. Ask "fix CID 1002 and verify" and it patches a copy,
re-reads the changed code, walks the original event trace through it, and states
that a re-scan is what re-certifies the defect.

## Version history

- **1.1.0** — model-driven by default: the VS Code LLM reads the report and the
  code and does the analysis with nothing installed; the engine becomes an
  optional accelerator; the agent writes the push-ready CSV itself; adds
  `coverity_report_text.py`, a dependency-free report digest.
- **1.0.0** — first release: report + source as input; model-driven analysis
  loop with checker-family playbooks; disposition comment and fix quality bars;
  fix-and-verify through engine re-analysis; Connect write-back mapping and
  dispositions-CSV export; source-root resolution; self-audit for engine
  disagreements.
