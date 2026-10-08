# Search Protocol — Datalink AI Patent Landscape

Reproducible record of the searches behind `PRIOR_ART_DATASET.csv` / `.json`.
Search date: **2026-10-08**. Databases: Google Patents (incl. its `xhr/query` endpoint), Justia Patents, public web (academic + industry). No paid databases (no Derwent / PatBase / Orbit) were available.

---

## 1. Google Patents structured queries

The Google Patents XHR endpoint accepts an encoded `q=` parameter and returns JSON:

```
https://patents.google.com/xhr/query?url=q%3D<url-encoded-query>&exp=
```

Queries executed and their key yield:

| # | Query | Results | Notable yield |
|---|---|---|---|
| 1 | `"datalink performance" aircraft monitoring` | 2 | **US20250260475A1 (Satcom Direct)** — closest reference; US7936300B2 (Thales, multipath) |
| 2 | `"pilot response time" datalink aircraft` | 13 | EP3715793A1 (Honeywell), EP3444791A2 (IATAS) — no direct hit on PORT monitoring |
| 3 | `airborne software certification machine learning DO-178` | 252 | **EP3651022A1 (GE Aviation Systems)**, **US11580009B2 (Northrop Grumman)**, CN111176978A |
| 4 | `aircraft datalink anomaly detection machine learning ground` | 4,159 | Too broad — used only to confirm density; no single dominant reference |
| 5 | `in-flight connectivity monitoring performance aircraft satellite terminal ground` | 84,644 | US10321517B2 (Boeing), Harris engine-monitoring family |
| 6 | `explainable artificial intelligence avionics pilot explanation certification` | 107 | US11488063B2 (Honeywell FMS SaaS), US12211388B2 (Thales), JP6913106B2 (Aurora) |
| 7 | `"communication management unit" fault diagnostic aircraft monitoring` | 67 | CN106516159A (CETC Avionics ACARS health mgmt), CN121887829A (COMAC, 2026), US11716334B2 (FedEx) |
| 8 | `self-learning interference jamming mitigation aeronautical datalink cognitive` | 8 | US12149560B2 (Univ. North Dakota — avionics cyber-attack detection) |
| 9 | `neural network deterministic fallback safety monitor aircraft control certified` | 142 | US20230176577A1 (NVIDIA) — no aviation-datalink-specific RTA patent found |

## 2. Keyword / phrase searches (web)

- `patent aircraft datalink monitoring ground system latency anomaly detection machine learning ACARS VDL health`
- `patent GNSS interference jamming detection aircraft machine learning self-learning threat model aviation`
- `patent runtime assurance monitor simplex architecture neural network safety critical aviation deterministic fallback`
- `patent ground-based system analyzing aircraft datalink messages fault isolation airline maintenance "data link" message log analysis`
- `"US patent" aircraft crew pilot response time alert monitoring avionics human factors detection latency`
- `patent automated certification evidence generation DO-178C DO-330 tool qualification software lifecycle artifacts traceability`
- `patent machine learning predictive aircraft communication link selection channel quality avionics datalink VHF SATCOM`

## 3. CPC / IPC classes to search (and the ones that matter most)

**Core (aircraft data link)**
- `H04B7/185` — Space-based or airborne stations
- **`H04B7/18506`** — Communications with or from aircraft, i.e. aeronautical mobile service ← *where US2025/0260475A1 sits; start every search here*
- `H04B7/18502` — Airborne stations
- `H04B17/309` — Measuring/estimating channel quality parameters
- `H04B17/364` — Delay profiles
- `H04B17/345` — Interference detection
- `G08G5/0013`, `G08G5/0021` — Air traffic control / ATM data link arrangements
- `B64F5/60` — Testing or inspecting aircraft components or systems
- `B64D43/00`, `B64D45/00` — Aircraft instruments / indicators & protectors
- `G07C5/008` — Registering vehicle working; communicating to a remote station

**Network / service monitoring**
- `H04L43/00` — Arrangements for monitoring or testing packet switching networks
- `H04L41/14` / `H04L41/5009` — Network management, performance/service-level analysis
- `H04W24/08` — Wireless channel/quality supervision
- `H04L63/1416`, `G06F21/55` — Intrusion/anomaly detection

**AI / certification**
- `G06N20/00`, `G06N3/08` — Machine learning
- `G06N5/045` — Explanation of AI decisions (XAI)
- `G06F11/079`, `G06F11/3495` — Fault diagnosis/monitoring in data processing systems
- `G06F8/70`, `G06F11/3668` — Software maintenance / testing & validation
- `G06Q30/018` — Certifying business, products or processes (oddly where Honeywell's qualification patent was classified)

## 4. Non-patent prior art that must be cited too

Patent novelty is destroyed by publications as well as patents. These are directly material:

- **ICAO Doc 9869 (PBCS Manual)** — defines ACTP, PORT, ACP, ASP, RCP 240, RSP 180. The Satcom Direct claims are built on these definitions; the *metrics themselves are public standards*, not protectable.
- **EUROCONTROL DPMF / DPMG** — publishes monthly/annual datalink performance reports and dashboards; operational prior art for "ground-side datalink performance monitoring".
- **EASA CoDANN I & II concept papers (2020, 2024)** and the EASA "W-process" / learnable aspects; **RTCA SC-240 (AI assurance)**, SC-228. These set the AI-assurance baseline.
- **NASA "Toward Certification of Machine-Learning Systems…" (NTRS 20210019093 / 20210025705)** — DAL D ML workflow, PDI treatment.
- **Sha et al., "Using simplicity to control complexity" (IEEE Software, 2001)** and the entire Simplex / Neural Simplex / RTA literature (Stony Brook, NASA DASC 2024) — prior art for hybrid deterministic + AI.
- **arXiv 2504.14443 "SkyNetPredictor"** — ML prediction of in-flight network performance along a route (LSTM/KNN). Directly relevant to ML link-performance prediction.
- **Stanford GPS Lab, ION GNSS+ 2021** — GNSS interference detection in ADS-B data with NN/CNN.
- **Cambridge/JON 2024** — deep temporal semi-supervised one-class GNSS RFI detection on real aircraft data.

## 5. Watch list (monitor quarterly)

| Reference | Why it matters | Action |
|---|---|---|
| **US 2025/0260475 A1** (Satcom Direct) + PCT/US2025/015174 | Closest art; still **pending** — claim scope can change on prosecution | Track claim amendments; re-run FTO before any product launch in this space |
| **CN121887829A** (COMAC, published 2026-04-17) | Airborne network security event processing with log analysis + isolation control — newest crowding in the "threat model" lane | Monitor family expansion / PCT filing |
| **EP3651022A1 / CN111176978A** (GE Aviation Systems) | Qualifying an unqualified component by comparing communications to a qualified set | Escape route: your integrity-verification step must be structurally different |
| **US 2018/0211261 A1 → US10839401B2** (Honeywell) | Qualifying data generated by an unqualified system before feeding it to a qualified system | Foundational for any "certifiable AI output" claim — cite and design around |
| RTCA SC-240 outputs | If SC-240 publishes AI assurance guidance, it becomes prior art and may also define a compliance niche | Reassess the certification-toolchain claim after publication |

## 6. Search limitations (state these in any filing)

1. No commercial database, no non-Latin full-text corpora beyond machine-translated titles/abstracts (several CN/JP/KR hits were evaluated only on translated titles/abstracts).
2. Pending applications are invisible for ~18 months from filing — there is a blind window covering roughly **2025-01 → 2026-10** for unpublished filings, exactly the period in which competitors are most likely to have filed on this theme.
3. Legal status flags from Google Patents are machine-derived and are not conclusions of law.
4. No claim-by-claim infringement or validity opinion is given here; this is a landscape and novelty screen, not an FTO opinion.
