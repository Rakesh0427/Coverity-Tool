# IDEA CORE — sharpened (v2)

**Prepared:** 2026-10-10 · **Supersedes the framing in earlier docs where they differ; consistent with `PATENT_STRENGTH_ASSESSMENT.md` and `SW_HW_METRICS_LAYER.md`.**

## The core, in one paragraph (use this everywhere)

> **In-service requirement assurance for aircraft datalink.** Every datalink transaction is checked against the requirement it must meet (RCP 240, RSP 180, response windows) — not just pass/fail, but with its **margin** and its **real cause** (network, radio, the aircraft's own computer, or crew). Because every verdict carries a margin, the same system **predicts**: margins tracked per tail, software load and route decay before any violation, and the alarm fires while the aircraft is still compliant. Because every verdict is recorded with its evidence, the same system **proves**: replayable conformance records, a coverage account, and audit-grade bundles — with AI only proposing patterns, gated and logged. **Check → predict → attribute → prove — one mechanism, not four products.**

## The key unification: prediction is margin tracking, not link forecasting

| The crowded prediction lane (taken) | Our prediction (open) |
|---|---|
| Predicts **the link**: outage probability (Panasonic AI-01/02), channel state (Qualcomm AI-05), handover (Ericsson AI-08, Hughes NA-09), signal quality (CNR research) | Predicts **the requirement**: the trend of the margin against an acceptance criterion |
| Statistical/ML forecast of a physical quantity | Deterministic margin arithmetic + change-point (CUSUM) on the margin series; ML only proposes what to inspect |
| Output: a probability or a switch decision | Output: alarm **while still conforming** + projected violation date + evidence record |

The 28-patent search's real message: **link prediction is walled off by granted patents — good. Requirement-conformance prediction, with attribution and evidence, is empty — that is ours.** Prediction is not a second feature; it is what requirement checking produces when margins are tracked over time.

## What is patentable in "checking requirements"

Taken (never claim): comparing transactions to PBCS thresholds; per-step delay comparison; dashboards/alerts; generic pass/fail monitoring (Satcom Direct US 2025/0260475 and others).

Open (claim this):
1. **Margin per requirement per transaction** — conforming-with-how-much-room-left, per tail / software load / route.
2. **Three-way attribution of the budget** — network leg / link leg / **aircraft host platform** (queue, partition, config) / crew, with time alignment and clock-uncertainty.
3. **Conformance records** — content hash, ledger, deterministic replay, late-data verdict revisions.
4. **Coverage account** — requirements not exercised on a route/load = verification credit owed.
5. **Margin-decay projection** — change-point on the margin series → projected violation date (dependent claim on 1–4).
6. **Gated AI layer** — admission gate + evidence record + metric flywheel (Family 2/3).

## Why this version is more reasonable

- **Start with 3 requirements, not 128:** RCP 240, RSP 180, response window. Measurable from day one (CSP feed + own receivers + AirSim); the 128-requirement baseline grows with the product.
- **Deterministic-first:** MVP needs no ML — margin arithmetic, attribution rules, records. AI is advisory forever, by design rule and by claim.
- **Mechanism, not magic:** "we compute each requirement's margin per transaction and track its trend" — believable, specific, and defensible.

## Why this version is more effective

- **The margin is the product:** pass/fail is free everywhere; margin decay lets maintenance act before the violation (alarm at flight 14, not failure at flight 25).
- **Evidence compounds:** flywheel (maintenance confirmation → label → monitor), coverage account, and audit bundles are deliverables dashboards cannot copy.
- **The crowded lane is the moat:** granted link-prediction patents block competitors from pivoting into requirement-conformance prediction once our claims are on file.

## Consequences

- **Pitch order:** problem (nobody checks the requirement in service, nobody can say whose fault, nobody can prove it) → mechanism (margin per transaction) → prediction falls out → evidence falls out.
- **Claims:** Family 1 = margin + attribution + record + replay (independent); margin-decay projection = dependent; never "predicting link performance".
- **Name:** *The Datalink Witness* (see naming analysis) — the witness that checked, predicted and can testify.

## The claim we would own (plain-language sketch, 2026-10-10)

> A ground system that, **for each datalink transaction**: computes a verdict against a named requirement (e.g. RCP 240) **together with its margin**; allocates the delay budget across network leg / radio leg / **aircraft host-platform leg** (queue, partition, configuration) / crew; writes a **hash-chained, deterministically replayable evidence record** mapped to the requirement ID, revisable when late data arrives; tracks margin per tail/software-load/route and raises an alarm on **margin decay with a projected violation date while still conforming**; and reports **which requirements a route/load has stopped exercising** (coverage account) — with ML only proposing patterns behind an admission gate.

Each bolded limitation is technical and concrete. The combination is undisclosed in 40+ references reviewed. File this as Family 1's independent claim; margin-decay projection as a dependent on the combination.

## Additional prior art found 2026-10-10 (disclose to counsel)

| Reference | What it covers | Effect |
|---|---|---|
| **US 2011/0161048 A1** — "Method to Optimize Prediction of Threshold Violations Using Baselines" [1](https://patents.google.com/patent/US20110161048A1/en) | IT metric monitoring: predict a metric will cross a threshold when values leave a baseline band and the trend heads toward the threshold | **Narrows margin-decay claims.** Never claim "predicting a metric will cross a threshold". Claim margin relative to a *requirement acceptance criterion per transaction*, with attribution and the evidence record; projection is dependent on that combination |
| **FAA "conformance monitoring"** — UAS BVLOS NPRM, 14 CFR Part 108 (2025) [5](https://www.federalregister.gov/documents/2025/08/07/2025-14992/normalizing-unmanned-aircraft-systems-beyond-visual-line-of-sight-operations) | Real-time conformance to operational intent, conformance-rate tracking over time | The *term* is public regulatory vocabulary; claims must name the mechanism, never "conformance monitoring" as a category |
| **US 2002/0123915 A1 / EP 1237 110 A2** — aviation nonconformance component management | Parts vs manufacturing tolerances, nonconformance capture, historical trending | Different field (hardware quality, post-inspection); no live transactions, no attribution, no replay. Non-blocking; cite in landscape |
