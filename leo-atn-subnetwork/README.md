# LEO broadband as a CMU ATN/IPS subnetwork — research & improved idea package

Deep patent / prior-art research on the idea *"register LEO broadband (Starlink / OneWeb / Kuiper) as its own CMU ATN
subnetwork tier, carry ATN/IPS over it, use it for AOC and bulk ATS first, probe RCP/RSP and fall back to certified links"*,
and a rewritten version of the idea that moves its centre of gravity to what is actually unclaimed.

## Headline

* **As originally stated, the idea is anticipated.** Honeywell's CMU preference-table patents (US7027812B2, US7729263B2),
  Honeywell AOIP (US10425149B1), the EASA/FAA *Future Connectivity* white paper (2022) and above all **Rockwell Collins France's
  "Virtual Safety Radio" application EP4513465A1 / US2025/0069511A1 (priority Aug 2023, pending)** already cover LEO/cabin-IP
  as a CMU subnetwork, ATN over it, AOC-first use, probing and fallback with an RCP/RSP rationale.
* **White space found:** (1) per-(traffic class × airspace) graduated admission driven by shadow dual-cast PBCS statistics,
  (2) LEO constellation-aware predicted-outage scheduling on board, (3) hedged dispatch timed from the RCP budget,
  (4) composite multi-constellation virtual subnetwork, (5) signed on-board evidence record bound to admission decisions.
* **Action:** file on (1)–(5) promptly; monitor EP4513465A1 prosecution for FTO (its claim 1 requires a cross-router interface;
  a dedicated-port embodiment is a candidate design-around — counsel to confirm).

## Files

| File | Purpose |
|---|---|
| `IDEA_LEO_ATN_SUBNETWORK_v2.md` | **The improved idea** — the user's four sections (Situation, Target, Proposed solution, Benefits) rewritten, with a "what changed and why" map |
| `PATENT_LANDSCAPE_REPORT.md` | Landscape: executive summary, element-by-element verdict, closest art, risk register, recommendations |
| `PRIOR_ART_DATASET.csv` / `.json` | 44 references (31 patents, 13 non-patent), with overlap rating and differentiation hook per row |
| `DRAFT_CLAIM_SET.md` | Three claim families (23 claims) + claim charts vs the six closest references |
| `INVENTION_DISCLOSURE.md` | Internal disclosure form for counsel |
| `SEARCH_PROTOCOL.md` | Sources, CPC groups, query log, limits, re-run schedule |
| `figures/` | Fig. 1 architecture, Fig. 2 admission state machine, Fig. 3 hedged dispatch, Fig. 4 prior-art verdict map |
| `build_figures.py`, `build_dataset.py` | Regenerate figures and dataset (`pip install matplotlib` needed for figures) |

## Caveats

Automated landscape screen, not a legal opinion. 18-month publication blind window (filings after ~2025-04 invisible).
Chinese documents assessed from machine-translated snippets. Legal status marked *n/v* where not verified.
