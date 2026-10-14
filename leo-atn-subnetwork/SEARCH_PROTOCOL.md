# Search protocol — LEO ATN/IPS subnetwork landscape (2026-10-14)

## 1. Idea decomposition (search elements)

| ID | Element | Search intent |
|---|---|---|
| E1 | LEO link as a separate CMU/ATSU subnetwork or preference tier | CMU preference tables, media selection, new subnetwork codes |
| E2 | ATN/IPS or SNDCF-over-IP across a cabin terminal's IP path, ACD-terminated security | ACARS/ATN over IP, VSR, secure gateway, domain segregation |
| E3 | AOC and bulk ATS first; CPDLC stays certified | AOC over IP, pseudo-ack gateway, AOIP, traffic-kind selection |
| E4 | RCP/RSP probing and automatic fallback | probing, multilink engine, ack timeout fallback, PBCS monitoring |
| E5 | Per-(class × airspace) graduated admission state machine | trial / probation / qualification of a link; per-region thresholds |
| E6 | Shadow dual-cast to build evidence | duplicate transmission, parallel transmission, de-duplication |
| E7 | Constellation-aware predictive scheduling | ephemeris, handover prediction, gateway, coverage gap, 4-D trajectory |
| E8 | Hedged dispatch at RCP budget | redundant transmission timing, expiration time, hedging |
| E9 | Composite constellations; signed evidence record | multi-constellation, availability aggregation, evidence log |

## 2. Sources

* Google Patents: individual publication pages and the `xhr/query` endpoint (keyword + CPC + assignee filters).
* Justia Patents (US publications with full bibliographic data).
* FreePatentsOnline (older US patents).
* Non-patent: EASA, FAA, ICAO, RTCA/EUROCAE, AEEC/SAE ITC listings, IETF datatracker / RFC Editor, NASA NTRS, Airbus FAST,
  Aviation Week, Aerospace Tech Review, Iridium, Starlink Aviation, CASA / Bahamas CAA PBCS pages.

## 3. CPC groups swept

`H04B7/18506` (aeronautical satellite / air-ground), `H04B7/185`, `H04W4/42` (vehicle-to-infrastructure, aircraft),
`H04W36/*` (handover), `H04L45/24`, `H04L45/302`, `H04L47/*` (multipath / QoS), `H04L67/12`, `G08G5/00`, `G08G5/0013`,
`H04W72/542`, `H04B17/364`.

## 4. Query log (representative; noise queries omitted)

| # | Query / target | Result |
|---|---|---|
| 1 | "communications management unit" "preference" subnetwork satellite VHF HF | US7027812B2, US7729263B2 |
| 2 | ACARS router "routing profile" WiMAX WiFi GSM | US8433817B2, US8484384B2, FR2787658A1, US20050286452A1 |
| 3 | "ACARS over IP" non-safety CMU availability | US10425149B1, EP3654548B1, US7395344B2 |
| 4 | safety messages "non safety" infrastructure aircraft control domain router | **EP4513465A1**, US20250069511A1 |
| 5 | assignee:"Rockwell Collins France" 2024–2026 | US20260006496A1 |
| 6 | multilink aircraft communication link quality SNR cost priority | US11146329B1 |
| 7 | datalink performance monitoring RCP RSP PBCS | US20250260475A1 |
| 8 | safety-of-life data link quality trajectory capacity satellite | US10453347B2 + family |
| 9 | ATN/IPS multilink router link state entropy | CN120856635B, CN118200224A, CN121483092A, CN120050214A |
| 10 | LEO satellite aircraft datalink transceiver ACARS radome | EP4572182A1, US9356686B1 |
| 11 | satcom radio cockpit cabin channel safety reconfigurable | US8774795B2, US10412051B2 |
| 12 | EFB AID datalink media CMU | US20250253929A1 |
| 13 | aircraft domains channel manager security level cost | US20150215899A1, EP2315367B1, US6677888B2 |
| 14 | "shadow" / "probation" / "duplicate transmission" qualify link aircraft | **no relevant hits** (noise) — E5/E6 appear open |
| 15 | ephemeris handover prediction aircraft datalink expiration | no relevant on-board hits; US10453347B2 nearest |
| 16 | hedged / redundant transmission timing "required communication performance" | no hits beyond EP4513465A1 ¶[0041] |
| 17 | multi-constellation composite availability aircraft safety link | none; commercial multi-orbit IFC press only |
| 18 | Future Connectivity for Aviation EASA FAA white paper LEO | NPL-1, NPL-2 |
| 19 | RCP 240 ACTP 120 150 RSP 180 ASP 90 180 allocation | NPL-4, NPL-11 (numbers confirmed) |
| 20 | ARINC 858 Part 3 radio interface; ARINC 771 LEO; Doc 9896 | NPL-5, NPL-6, NPL-3 |
| 21 | Starlink aviation ATS CPDLC approval | nothing public — no safety approval found |

Citation chasing performed forward/backward from refs 1, 3, 13, 14, 17, 22.

## 5. Limits

* 18-month publication blind window: filings after ~2025-04 are invisible.
* CN documents assessed from machine-translated snippets; full translations recommended before filing.
* Legal status not verified against national registers (marked n/v where unknown).
* Not a freedom-to-operate opinion.

## 6. Re-run schedule

Repeat queries 4, 5, 7, 9, 14–17 at +6 and +12 months; set alerts on assignees Rockwell Collins France SAS, Honeywell,
Thales, Satcom Direct, SpaceX, Beihang University, CETC Avionics, and on CPC H04B7/18506 ∩ (RCP OR "performance based").
