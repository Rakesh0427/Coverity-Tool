# Invention disclosure — Performance-earned admission of LEO broadband as an ATN/IPS subnetwork

| Field | Entry |
|---|---|
| Working title | Graduated, evidence-based admission of a non-certified broadband link to ATS datalink traffic classes, with constellation-aware scheduling and RCP-budget hedged dispatch |
| Technical field | Aeronautical air/ground datalink (ACARS, ATN/OSI, ATN/IPS); CMU/ATSU routing; PBCS (RCP/RSP) |
| Date of conception | prior to 2026-10-14 (idea v1); v2 refinement 2026-10-14 |
| Status | Not disclosed publicly; not offered for sale |
| Related internal work | `datalink-ai/` (AI-assisted PBCS monitoring) — the evidence record of this disclosure is a natural input |

## 1. Problem

Commercial LEO broadband (Starlink, OneWeb, Kuiper) offers two orders of magnitude more capacity and far lower latency than
VDL Mode 2 or L-band SATCOM, but has no AMS(R)S status, no priority/pre-emption, and no published performance evidence
acceptable for RCP/RSP allocation. Known approaches either (a) restrict such links to non-safety traffic (Honeywell AOIP), or
(b) let the ACD router send safety messages over them when a probe says they are "available" and fall back after an
acknowledgement timeout (Collins France VSR). Neither produces the per-airspace statistical evidence a regulator needs, neither
bounds the RCP exposure while that evidence is being built, and neither exploits the fact that LEO outages (handovers, gateway
switches, coverage gaps) are predictable.

## 2. Summary of the invention

1. **Per-(link × traffic class × airspace) admission state machine** OFF → SHADOW → PROBATION → ADMITTED ⇄ SUSPENDED.
   In SHADOW, idempotent traffic already carried on a certified link is duplicated on LEO (transaction IDs; ground de-dup)
   so that transaction-time / continuity percentiles are measured with zero operational dependence. Admission requires the
   measured statistics to meet the RCP/RSP matrix for the FIR being flown over N_min samples; classes form a monotonic ladder.
2. **Hedged dispatch:** in PROBATION / ADMITTED, a certified-link copy is launched at
   t_hedge = ACTP_99.9(class, FIR) − P99.9(certified, measured) − margin, so the RCP window is met even if LEO fails silently.
3. **Constellation-aware predictive scheduling:** terminal telemetry + ephemeris + 4-D flight plan → predicted-unavailability
   calendar; transactions whose RCP window overlaps a predicted outage are started on, or moved to, a certified link in
   advance; long predicted outages suspend the class pre-emptively.
4. **Composite multi-constellation subnetwork** with independence monitoring.
5. **Signed per-transaction evidence record** exported to PBCS monitoring; ground gateway mirrors admission state for uplinks;
   capability signalling to ADS-C / EPP end systems.

## 3. Detailed description pointers

* Architecture: `figures/fig1_architecture.png`; state machine: `figures/fig2_admission_state_machine.png`;
  hedge timeline: `figures/fig3_hedged_dispatch.png`. Narrative: `IDEA_LEO_ATN_SUBNETWORK_v2.md` §3.
* Worked example (RCP 240, North Atlantic): ACTP threshold 150 s @ 99.9 %; measured SB-S P99.9 = 95 s; margin 10 s → hedge at
  45 s. Typical LEO transaction 2–30 s, so > 99 % of transactions complete before the hedge fires; the certified link carries
  only the residue.
* Class ladder: C0 AOC bulk, C1 AOC ops, C2 ADS-C periodic/event, C3 ADS-C EPP / FIS / D-ATIS, C4 CPDLC non-time-critical,
  C5 CPDLC clearances / urgent (policy-gated).
* Embodiments: software partition on IPS-capable CMU; ACD LRU retrofit between CMU and terminal port; Starlink / OneWeb /
  Kuiper; composite; 5G ATG / LDACS; fleet-pooled evidence via ground gateway.

## 4. Advantages over the closest prior art

| Prior art | Our difference |
|---|---|
| EP4513465A1 (Collins France VSR, pending) | Statistical per-class / per-FIR admission with shadow evidence instead of binary availability; hedge timed from RCP budget instead of reactive ack timeout; LEO outage prediction; composite links; signed evidence; no cross-router dependency |
| US10425149B1 / EP3654548B1 (Honeywell AOIP) | ATS classes can be admitted — graduated, not hard-split |
| US7027812B2 / US7729263B2 (Honeywell CMU selection) | Admission is earned from measured performance, not configured |
| US11146329B1 (Collins multilink) | Transaction-level PBCS statistics and states, not instantaneous SNR |
| US10453347B2 (TAS-I) | On board, for a non-certified bearer, constellation handover / gateway prediction feeding transaction scheduling |
| US20250260475A1 (Satcom Direct) | On-board, real-time, decision-bound; ground monitoring becomes a consumer of our evidence |

## 5. Known prior art to cite

EP4513465A1 / US20250069511A1; US20260006496A1; US10425149B1; EP3654548B1; US7027812B2; US7729263B2; US8433817B2;
US11146329B1; US10453347B2; US20250260475A1; US10412051B2; EP4572182A1; CN120856635B; EASA/FAA *Future Connectivity for
Aviation* (2022); ICAO Doc 9896, Doc 9869; RTCA DO-350A / EUROCAE ED-228A; ARINC 858, 771; RFC 9372.

## 6. Commercial relevance

Airlines (AOC / bulk ATS offload without recertification; vendor-neutral LEO adoption), CMU/ATSU vendors (software feature),
CSP/DSPs (ground gateway + evidence service), ANSPs / regulators (performance-based bearer admission matching the EASA/FAA
Hyperconnected-ATM roadmap). Standards leverage: ARINC 858 / ICAO WG-I contribution on "candidate access network admission".

## 7. Inventor notes / open questions

* Access to LEO terminal telemetry (handover schedule, beam / gateway IDs) depends on operator APIs; passive inference fallback described.
* N_min and percentile estimators for thin routes — fleet pooling embodiment.
* Confirm whether the ground gateway should be CSP-operated or ANSP-operated (both claimed).
* Track EP4513465A1 prosecution; obtain FTO opinion before product disclosure.
