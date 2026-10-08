# Invention Disclosure — Datalink AI Diagnostic & Certification Platform

> Pre-filled from the submitted idea plus the landscape findings. Complete the bracketed fields, sign, and route to IP/legal. Attach `PATENT_LANDSCAPE_REPORT.md` as the prior-art annex and `PRIOR_ART_DATASET.csv` as the search results annex.

---

## 1. Administrative

| Field | Value |
|---|---|
| Title (working) | Cross-layer datalink attribution with certification-gated AI augmentation and evidence generation |
| Inventor(s) | [names — see §7] |
| Employer / owner | [entity] |
| Date of conception | [approx. date] |
| Date reduced to practice | [first working prototype / test bed date, or “not yet”] |
| **Has this been publicly disclosed?** | **[YES / NO]** — if YES: venue, date, audience, and whether a recording or slides were distributed. ***This determines the filing deadline; answer it before anything else.*** |
| Related filings | US2025/0260475A1 (third party, Satcom Direct) — not ours |
| Intended jurisdiction(s) | [US first; consider EP/IN/CN] |

## 2. Problem being solved

Operators and OEMs can today see *that* a datalink transaction was slow, but not *why*. Existing ground monitoring attributes delay to a network leg, so an **aircraft host-platform defect** — partition scheduling overruns, comms-application resource starvation, data-link stack or driver faults — presents as an unexplained network problem and is chased in the wrong system. Separately, AI/ML cannot be placed in a certified datalink path because its outputs are not explainable, not bounded, and not admissible as certification evidence, and no existing monitoring output is structured as DO-178C / DO-254 / DO-330 evidence.

## 3. The inventive concept (one paragraph, for the cover sheet)

A ground-based datalink diagnostic platform that (i) **correlates** per-leg transaction timing with **aircraft host-platform telemetry** to attribute a datalink symptom to a network cause, a link cause, or an **aircraft platform cause**, and **deterministically replays** the attribution for audit; (ii) runs AI **only in an advisory path**, admitting a machine-learning diagnosis to an operational output only through a **behavioural admission gate** (out-of-distribution score, calibrated uncertainty, robustness perturbation) and, on admission, writing a **tamper-evident evidence record mapped to a certification objective**; and (iii) learns **interference/threat signature models on the ground** and distributes them to aircraft as **signed advisory data only**, inside a certified operational envelope, with roll-back.

## 4. Element list and status (tick what is implemented today)

| # | Element | Prototype status | Notes |
|---|---|---|---|
| E1 | Ground ingest of live CMU/ACARS/CPDLC/ADS-C transaction records | [ ] built [ ] designed | DMZ/hosting, data rights with CSP |
| E2 | Per-leg delay budget and end-to-end latency | [ ] built [ ] designed | — |
| E3 | Network-leg attribution | [ ] built [ ] designed | — |
| **E4** | **Host-platform (OS/partition/resource) telemetry correlation and attribution** | [ ] built [ ] designed | **lead inventive element** |
| E5 | Pilot-action analytics (PORT-style), human vs technical attribution | [ ] built [ ] designed | — |
| E6 | AI advisory path + admission gate (OOD / uncertainty / robustness) | [ ] built [ ] designed | **strategic element** |
| E7 | Evidence records + objective mapping + evidence bundle generator | [ ] built [ ] designed | **strategic element** |
| E8 | Deterministic replay / audit verification | [ ] built [ ] designed | enables E7 |
| E9 | Ground-learned, envelope-validated, signed advisory threat models | [ ] built [ ] designed | second filing |

## 5. Closest known prior art (from our own search — must be disclosed)

1. **US 2025/0260475 A1** — Satcom Direct — ground-side real-time datalink performance monitoring with per-step timestamps, benchmark comparison, greatest-delay-step identification, NOC alerting, link reconfiguration, ACTP/PORT.
2. **US 10,839,401 B2 / US 2018/0211261 A1** — Honeywell — verifying integrity of data from an unqualified system and providing qualified data to a qualified system.
3. **EP 3 651 022 A1 / CN 111 176 978 A** — GE Aviation Systems — verifying an unqualified component against a previously-qualified set of communications.
4. **US 11,488,063 B2** — Honeywell — cloud-trained ML models served to a connected FMS/avionics.
5. **US 2023/0007564 A1** — ML prediction of future wireless channel state driving path selection.
6. **US 11,212,015 B2** — The Aerospace Corporation — ML interference suppression.
7. **US 2020/0167677 A1** — IBM — surrogate-model explanations of neural networks.
8. Non-patent: ICAO Doc 9869 (PBCS metrics), EUROCONTROL DPMF reports, EASA CoDANN I/II, NASA NTRS ML-certification papers, Simplex/RTA literature (Sha 2001 → NASA DASC 2024), arXiv SkyNetPredictor.

## 6. Differentiators we assert

1. Attribution extends to the **aircraft host platform**, not only to network legs.
2. The attribution is **deterministically replayable** and hash-chained — an audit asset, not just a dashboard.
3. AI output is **admission-gated** by behavioural tests, and only admitted output enters the operational path; a rejection is itself recorded.
4. The platform emits **objective-mapped certification evidence**, which no prior reference produces.
5. Threat/interference learning is confined to the **ground** and distributed as **signed advisory data**, leaving certified airborne software unmodified and therefore certifiable.

## 7. Inventorship prompts (answer honestly — this decides validity)

- Who first conceived the **host-platform correlation** idea? [name/date]
- Who first conceived the **admission gate** limitation (OOD + calibrated uncertainty + robustness)? [name/date]
- Who first conceived the **evidence-record → certification-objective mapping**? [name/date]
- Who first reduced any of the above to a working demonstration? [name/date]
- Was any element contributed by a contractor, airline partner, university, or another company? [yes/no → if yes, ownership must be settled before filing]

## 8. Filing recommendation

| Step | Item | Timing |
|---|---|---|
| 1 | Confirm public-disclosure status (§1) | immediately |
| 2 | File **provisional** on Family 1 (E1–E4, E8) | within 2–4 weeks |
| 3 | Freeze gate design + evidence schema; convert to **non-provisional / PCT** adding Family 2 (E6, E7) | before provisional expiry (12 months) |
| 4 | Second filing on Family 3 (E9) once the frozen regression suite exists | 6–12 months |
| 5 | Defensive publication for non-filed UX elements | as needed |

## 9. Attachments

- `PATENT_LANDSCAPE_REPORT.md` — full analysis and element-by-element risk table
- `PRIOR_ART_DATASET.csv` / `.json` — 44 patent references + 10 non-patent references
- `DRAFT_CLAIM_SET.md` — draft claims, claim chart, spec outline
- `SEARCH_PROTOCOL.md` — what was searched, what was not, and the blind window

**Signature:** ______________________  **Date:** ____________
