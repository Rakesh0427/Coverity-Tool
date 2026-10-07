# Coverity Finding Analyzer — store listing copy

Paste these fields into the store's contribution form. Everything here is also
written into the upload bundle as `README.md`.

> **What this upload is.** One agent that takes a Coverity report plus your
> source tree and produces, per defect, a disposition, a reviewer-grade comment
> and a proposed fix. The agent's own model does the analysis; the bundled
> **Coverity Tool** engine supplies the facts it reasons over (event traces,
> exact file/line, numbered source, checker evidence). The agent is the
> deliverable; the engine is its instrument.

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

- **You supply two things** — the Coverity report (`index.html` folder, `.xlsx`
  export, or a previous run's JSON) and the root of the source tree. If the
  report's paths do not line up with your checkout, the agent resolves the
  correct root (or tells you which files are missing) instead of guessing.
- **It reads your code, not just the report.** One tool call hands it an
  **evidence dossier** — the line the verdict hangs on, the declarations that
  fix capacities, the guards already in the function, the callers that supply
  the data, the callees that decide the size or the lock — and it reads those
  files itself. The checker's question — is the bound right, is the object still
  alive, can this pointer be null — is answered from the code.
- **It decides, and shows its work.** One of four dispositions, with the
  evidence quoted by line: `Bug`, `False positive`, `Intentional`, or
  `Needs review` when a human genuinely has to decide. Disagreement with the
  underlying engine is allowed — but only with code to back it, never by
  assertion.
- **It says where every verdict came from.** Each finding is labelled
  `engine (depth: full)`, `degraded`, or `model-only, unverified`, so you always
  know whether a claim was checked by the analyser or read by the model.
- **It works on machines with no engine installed.** If the Python backend is
  missing, it degrades honestly: still analyses the report and the code, labels
  every verdict as unverified, and tells you the one command that upgrades it.
- **It writes the comment a reviewer needs** — what is wrong, the numbers that
  prove it, what happens at runtime — instead of restating the checker's name.
- **It writes the fix**: minimal, compilable, in your file's own style, with one
  line on why it closes the defect, plus an alternative when there is a real
  trade-off.
- **It proposes; you decide.** By default it hands you the comment and the diff
  as text and never touches the working tree. It edits only when you ask it to
  change the code — then one defect per run, followed by re-analysis through the
  engine to prove the fix, with the before/after dispositions and the diff.
- **It prepares the write-back.** Paste-ready Coverity Connect text, and a
  dispositions CSV your existing push tooling can load — with the standard
  mapping (`Bug` → Fix Required, `False positive` / `Intentional` → Ignore,
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
| Engine checkout | This repository, installed with `pip install -r requirements.txt` |
| Without the engine | Still works, in `engine_missing` mode: every verdict is labelled *model-only, unverified* |
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

**Then connect it to the engine** (so the facts are real, not modelled):

```bash
pip install -r requirements.txt      # in the Coverity Tool checkout
python capabilities.py               # expect: analysis depth: FULL
```

and start the MCP server once per session:

> `Ctrl+Shift+P` → **MCP: List Servers** → `coverity` → **Start Server**

Full walkthrough: `docs/VSCODE_AGENTS.md`. Day-to-day usage (where the report
and source go, what lands where, Connect pull and push): `docs/USER_GUIDE.md`.

## First test

In agent mode, pick **Coverity Finding Analyzer**, then:

> Analyse `docs/sample_report/index.html` against the source root `docs`.

Expected: it reports the analysis depth, then two defects — CID 1001
(`BUFFER_SIZE`) and CID 1002 (`USE_AFTER_FREE`) — each with a location, a
disposition and confidence, a rationale citing CWE-120 / CWE-416, and a proposed
fix. Ask "fix CID 1002 and verify" and it should patch the copy, re-analyse that
defect, and report the disposition moving off `Bug`.

## Version history

- **1.0.0** — first release: report + source as input; model-driven analysis
  loop with checker-family playbooks; disposition comment and fix quality bars;
  fix-and-verify through engine re-analysis; Connect write-back mapping and
  dispositions-CSV export; source-root resolution; self-audit for engine
  disagreements.
