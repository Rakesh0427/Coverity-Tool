# DATALINK — start here

## Read one file

**→ [`FINAL_PITCH.md`](FINAL_PITCH.md)** — the whole idea in plain English: problem, solution, why it's different, who benefits, what we ask for, and the answers to the six questions you'll get.

Anything else is backup, and it lives in `working/` so it stops getting in the way.

---

## What's in the folders

| Folder / file | What it is | When to open it |
|---|---|---|
| `FINAL_PITCH.md` | The pitch. One document, plain English | Always — this is the deliverable |
| `figures/fig_pitch_flow.png` | The one-slide block diagram (SVG copy alongside it for decks) | When you present |
| `figures/fig1_architecture.png` | The detailed engineering architecture | Only if an engineer asks how it's built |
| `dashboard/` | A sample of what the customer screen looks like | When someone asks "what do I actually see?" |
| `working/` | All earlier drafts and research | Only when you need a specific fact |

## Inside `working/`

**Pitch drafts (superseded by `FINAL_PITCH.md`)**
`PITCH_PACK.md` · `TEAM_PRESENTATION.md` · `FOUR_POINTS.md` · `PITCH_PROBLEM_STATEMENT.md` · `HONEYWELL_SIDE_PITCH.md`

**The idea and the patent conversation**
`IDEA_CORE.md` (sharpest version of the concept) · `INVENTION_DISCLOSURE.md` · `DRAFT_CLAIM_SET.md` · `PATENT_STRENGTH_ASSESSMENT.md`

**The patent research**
`PATENT_LANDSCAPE_REPORT.md` · `PREDICTIVE_PATENTS_AI_vs_NON_AI.md` + `.csv` (28 predictive patents) · `PRIOR_ART_DATASET.csv` + `.json` (44 records) · `SEARCH_PROTOCOL.md`

**Technical planning**
`MARK_II_LIVE_DATA_PLAN.md` (how to get live data) · `SW_HW_METRICS_LAYER.md` (what metrics mean)

> Note: image links inside `working/` files point to `figures/…`; from that folder they are `../figures/…`.

---

## The five numbers, if you only remember five

1. **240 seconds** — the legal deadline for a datalink clearance.
2. **Once a month** — how often it is checked today. By hand. In a spreadsheet.
3. **20–50%** — avionics removed that turn out to be fine.
4. **USD 10,000–150,000** — the cost of one aircraft on ground, per hour.
5. **0** — flights we can show a per-flight compliance record for today.

**The idea in one line:** everyone else predicts the link or the health of the box — we predict, attribute and **prove the requirement**.
