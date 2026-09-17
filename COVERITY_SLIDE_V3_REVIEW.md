# Review — `Coverity_Slide_v3.png`

**Reviewed:** 17 Sep 2026 · **File:** `Coverity_Slide_v3.png` (5665 × 2945 px, single-slide poster)
**Cross-checked against:** `heuristic_analyzer.py`, `checker_categories.py`, `README.md`, `COVERITY_TOOL_MANUAL.md`,
`COVERITY_SLIDES_FINAL.md`, `build_slide.py`, `slide_specs.py`, and the previous deck renders
(`Coverity_Final_Slide_Updated_preview.png`, `Coverity_latest_slide.png`).

**Annotated version:** `Coverity_Slide_v3_review_annotated.png` — every number below matches a red marker on that image.

**Verdict:** the layout, hierarchy and visual design are strong and presentation-ready.
The problems are all in the **numbers and the evidence behind them** — four of them will not survive
a review question. Fix items **1–5** before this goes in front of anyone; items 6–17 are polish.

---

## 1. Blockers — fix these before presenting (numbers are wrong)

| # | On the slide | Problem | What to put instead |
|---|---|---|---|
| **1** | `RL1 (1,000 defects): 250 hrs → 217,867 hrs saved` | **Typo.** Two figures collapsed into one number — it reads as *217,867 hours saved* from a 250-hour baseline (817× the manual effort, impossible). Every other artefact in the repo says **217 hrs** (`build_slide.py:204`, `slide_specs.py:96`, `COVERITY_SLIDES_FINAL.md:36`). | `RL1 (1,000 defects): 250 hrs → 33 hrs = 217 hrs saved` |
| **2** | `Program (4,000 defects): 1000 hrs → 140 hrs saved` | **Wrong figure**, and the arithmetic is missing. The tool side should be **133 hrs**; `1000 → 140` implies a 86% cut, while the repo's figure is **867 hrs saved** (1000 − 133). Also there is no `=` so "1000 hrs → 140 hrs saved" is ambiguous. | `Program (RL1–RL4, 4,000 defects): 1,000 hrs → 133 hrs = 867 hrs saved` |
| **3** | Two glowing chips `($7k)` and `($30k)` | **Not self-explanatory** — no label of what they are, which row they belong to, or the rate used. They are $7,595 and $30,345 (217 hrs × $35 and 867 hrs × $35), but a reader cannot tell that. Note the **legacy slides/notes say `$30/hr`** while the $ figures are derived at **$35/hr** — the rate must be stated. | `$7,595 (RL1) · $30,345 (4,000 defects) — at $35/hr` (one labelled line under the two rows) |
| **4** | `($84)` chip + `(+98% faster, 2.3 hrs)` | **Same problem plus a type/case error**: $84 is 2.3 hrs × ~$35/hr, but the rate is not shown anywhere on the slide, and `+98%` should be `~98%`. The parenthetical mixes two different units (a percentage and a duration). | Chip: `$84 (2.3 hrs @ $35/hr)` · Text: `Push time: 143 min → ~3 min (one batch) · ~98% faster` |
| **5** | `143 defects pushed to the Coverity Connect` | Grammar — **drop "the"**. Also say *what* was pushed (dispositions, not defects) and for which scope. | `143 dispositions pushed to Coverity Connect (RL1 batch)` |

> Suggested corrected savings block (paste-ready):
>
> ```
> COST SAVINGS PER PROGRAM
> RL1 (1,000 defects):        250 hrs  → 33 hrs  = 217 hrs saved
> Program (RL1–RL4, 4,000): 1,000 hrs  → 133 hrs = 867 hrs saved
> Cost avoided @ $35/hr: $7,595 (RL1)  ·  $30,345 (program)
>
> Deployed in — NG-FMS ATS Core EPP (pull + push against Coverity Connect)
> 143 dispositions pushed to Coverity Connect (RL1 batch)
> Manual push: 143 min (≈1 min/defect) → Tool push: ~3 min (one batch) → ~140 min saved = $84
> ```

---

## 2. High — unsupported or over-stated claims (say the true thing)

| # | On the slide | Problem | Suggested wording |
|---|---|---|---|
| **11** | `Reduces SME Dependency — 80% reduction` | **Nothing in the repo supports 80%.** It appears only in the slide generators (`build_slide.py:129`, `slide_specs.py:68`), never in the manual, analysis code or test results. It is the easiest number in the room to challenge. | Either show the derivation (e.g. *"82 of 102 dispositions accepted without SME edit"*) or soften to `Most findings auto-triaged; SME reviews the "Needs review" tail` — the manual documents a real **4-way outcome incl. a "Needs review" tail**, so a hard 80% conflicts with the tool's own documented behaviour. |
| **12** | `CORE FEATURES → Aerospace Compliance — DO-178C, MISRA, CERT` | Reads as **"the tool certifies compliance"**. What the tool actually does is *map Coverity checkers to CWE / CERT IDs and emit DO-178C-style objective evidence* (`cwe_mapping.py`, `comment_style.py`). Claiming DO-178C/MISRA/CERT compliance for a triage helper is a compliance-audit exposure in an aerospace review. | `Standards-aware evidence` / `– CWE, CERT & MISRA mapping in comments` / `– DO-178C objective evidence, auto-generated` |
| **13** | `No AI Tokens Required — Runs 100% offline` | Correct for **analysis**, but the slide's own flow includes *Pull from Coverity Connect* and *push dispositions*, which are network operations. `README.md` also documents **cppcheck corroboration** running on by default. "100% offline" invited a gotcha. | `Runs fully offline — source never leaves the machine (network used only for optional Coverity Connect pull/push)` |
| **10** | `Rule Engine — 20+ Checker Rules` | The repo maps **38 Coverity checkers** for categorisation (`checker_categories.py`) while the manual states **~20 checkers have dedicated decision rules**. Both statements are true, but a reviewer comparing the slide with the code will see 38 and ask which is right. | Keep `20+ checker-specific decision rules` and add `— 38 Coverity checkers categorised`, or make the manual say the same number as the slide. |

---

## 3. Medium — clarity and internal consistency

| # | On the slide | Problem | Suggested fix |
|---|---|---|---|
| **6** | `WORK DETAILS` table | Every "WITH TOOL" cell is qualitative (Automated Analysis / One Controlled Flow / Higher Quality) while every "MANUAL" cell is specific and painful. That asymmetry weakens the argument exactly where it matters — and the hours actually exist: 4,000 defects × 1–2 min = **67–133 hrs** vs 667–1,000 hrs manual. | Add the counter-figures: `10–15 min/defect` → `1–2 min/defect (4,000 defects: 1,000 → 133 hrs)`; and mirror the MANUAL column so each row compares like with like. |
| **7** | `~90% Time Reduction` call-out | **Floats in the middle of the slide** under the table — it is not attached to the table, the cost block, or the flow diagram, and it has no derivation. | Either move it inside the cost block as the headline (`~90% less triage effort: 1,000 hrs → 133 hrs`) or add `(10–15 min → 1–2 min per defect)`. |
| **8** | `Processing Stage 1` / `Processing Stage 2` | Numbering implies a Stage 3 that does not exist — **Smart Dispositions** (the output box) is unnumbered, and the orange arrows have no stage labels at all. The previous deck explicitly removed "Processing Stage 3" (`build_slide.py` header note), so this is leftover numbering. | Drop the numbers: `Source Parser (tree-sitter)` → `Rule Engine` → output box. |
| **9** | Flow diagram arrows | **The dotted line from Source Parser turns into a second arrow pointing back into the Rule Engine**, which reads as a loop back into stage 2. `Processing Stage 2` is also the only label without a box behind it. | Make the path strictly left→right into the Rule Engine, one arrow into the output box; give `Rule Engine` the "Processing Stage 2" label inside its box. |
| **17** | Right-hand graphic | Occupies roughly **45% of the slide width** to convey a 3-box pipeline (input → parse → rules → disposition), while the quantified content — the part that convinces — is confined to the left half. | Either shrink the pipeline to ~35% and promote the cost block to a band, or split this into two slides: "how it works" and "what it saves". |
| **14** | `Future Targeted Programs: Datalink (787, AIMS, EPIC), TXD across all CNS products…` | `HonAero` is slang on a customer-facing slide; the list is inconsistent (`Datalink (787, AIMS, EPIC)` — one program, one aircraft, two systems); and there is **no timeline**, which is the first question a targeted program will ask. | `Next (Q4 FY26): 787 Datalink · AIMS · EPIC · TXD — across CNS products` |
| **15** | Subtitle `AI-Developed, Rule-Based Static Analysis` | The old slide carried the necessary footnote `* AI used to DEVELOP, analysis is RULE-BASED` twice. **v3 dropped it**, right next to a robot icon — the exact thing that makes a rule-based tool look like an LLM wrapper. | Restore one footnote: `* AI used during development; analysis is deterministic & rule-based` |

---

## 4. Low — polish / packaging

| # | On the slide | Note |
|---|---|---|
| **16** | No title-bar branding, no confidentiality marking, no date, **no slide number/footer** | `Coverity_latest_slide.png` had `Honeywell Aerospace`, `CNS AI Day 2026` and a `Confidential` footer. `build_slide.py` deliberately removed them — fine for an internal AI-Day submission, but add back at least `Confidential` + date + slide x/y if this becomes part of a deck. |
| — | Terminology | The slide says *Coverity*; the tool and manual say **Coverity Connect** and the older deck said *Coverity Findings Analyzer*. One product name, used everywhere — including the `RL1–RL4` / `NG-FMS ATS Core EPP` labels (`RL` is jargon; spell it out once: "Red Label (RL) releases 1–4"). |
| — | Rate consistency across files | The $ figures are computed at **$35/hr**, but `COVERITY_SLIDES_FINAL.md:41` says `(at $30/hr)` and `Coverity_Final_Slide_Updated_preview.png` says `(at $30/hr)`. Pick one rate, state it on the slide, and correct the older files so no two artefacts disagree. |
| — | Claims that *should* be on the slide | Two differentiators are missing and both are verifiable: **second-opinion corroboration (cppcheck, offline)** and **full audit trail (`audit.jsonl`, context hash)**. Those are stronger than "Higher Quality". |

---

## 5. What is right — keep it

- Overall layout and the orange-on-dark theme: clean, readable, consistent with the CNS AI Day styling.
- `10–15 min/defect → 1–2 min/defect` and `~90%` time reduction — matches the manual and every prior slide version.
- `250 → 33 hrs = 217 hrs` and `1,000 → 133 hrs = 867 hrs` — internally consistent **once the 217/867 printing is fixed**.
- The **push** efficiency block (143 dispositions, 143 min → ~3 min in one batch) is the most credible evidence on the slide, because it is an observed result rather than a projection. Give it a stronger label, e.g. *"Measured on RL1"*.
- The input → parse → rule → disposition pipeline is the correct architecture (tree-sitter really is the parser; the rule engine really is deterministic).
- Removing the tool-owner name/date footer was a deliberate choice and is fine.

---

## 6. Fix list, in order

1. `217,867` → `217` **(typo, blocking)**.
2. `1000 hrs → 140 hrs saved` → `1,000 hrs → 133 hrs = 867 hrs saved` **(wrong figure, blocking)**.
3. Label the `$7k` / `$30k` chips and state the **$35/hr** rate **(blocking)**.
4. `($84)` → label the rate; `+98%` → `~98%`; drop "the" in *pushed to the Coverity Connect* **(blocking)**.
5. `80% reduction` → show the basis or soften **(high)**.
6. `Aerospace Compliance` → `Standards-aware evidence / CWE-CERT-MISRA mapping` **(high)**.
7. `Runs 100% offline` → qualify the Coverity Connect network path **(high)**.
8. Reconcile `20+ Checker Rules` with the 38 mapped checkers **(high)**.
9. Balance the `WORK DETAILS` columns with the 67–133 hrs counter-figures **(medium)**.
10. Remove the orphaned `~90%` call-out, the Stage 1/2 numbering, and the loop-back arrow **(medium)**.
11. Restore the `* analysis is rule-based` footnote; re-add confidentiality/date/slide number; fix `HonAero`; add a timeline **(polish)**.
12. Sync the `$30/hr` vs `$35/hr` rate across `COVERITY_SLIDES_FINAL.md` and the older deck renders **(polish)**.

---

*Review basis: figures verified against the tool's own source and documentation in this repository; nothing in this review
is derived from external sources.*
