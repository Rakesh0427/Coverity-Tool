# LEO broadband as a performance-earned ATN/IPS subnetwork of the CMU
## Complete dossier — prior-art landscape, improved idea, draft claims, disclosure

*Prepared 2026-10-14 · Automated landscape screen and drafting aid — not a legal opinion.*

### Headline

* **As originally stated, the idea is anticipated.** Honeywell CMU preference-table patents (US7027812B2, US7729263B2), Honeywell
  AOIP (US10425149B1), the EASA/FAA *Future Connectivity for Aviation* white paper (2022) and, above all, **Rockwell Collins
  France's "Virtual Safety Radio" application EP4513465A1 / US2025/0069511A1 (priority 2023-08-21, pending)** already cover
  LEO/cabin-IP as a CMU subnetwork, ATN over it, AOC-first use, probing, and fallback with an RCP/RSP rationale.
* **White space found and claimed in this dossier:** (1) per-(traffic class × airspace) graduated admission driven by shadow
  dual-cast PBCS statistics; (2) LEO constellation-aware predicted-outage scheduling on board; (3) hedged dispatch timed from
  the RCP budget; (4) composite multi-constellation virtual subnetwork; (5) signed on-board evidence record bound to admission
  decisions.
* **Action:** file on (1)–(5) promptly; monitor EP4513465A1 prosecution for freedom-to-operate (its claim 1 requires a
  cross-router interface; a dedicated-port/VLAN embodiment is a candidate design-around — counsel to confirm).

### Contents

1. Part A — Improved idea (v2): Situation · Target · Proposed solution · Benefits
2. Part B — Patent & prior-art landscape report
3. Part C — Draft claim set (3 families, 23 claims) and claim charts
4. Part D — Invention disclosure
5. Part E — Search protocol
6. Appendix — Prior-art dataset (44 references)




---

# Part A — Improved idea (v2): the four sections rewritten

**Version 2 — rewritten after the patent / prior-art landscape of 2026-10-14**
(landscape: `PATENT_LANDSCAPE_REPORT.md`; dataset: `PRIOR_ART_DATASET.csv`; claims: `DRAFT_CLAIM_SET.md`)

> **One-line pitch (v2).** Treat Starlink / OneWeb / Kuiper not as "another radio in the preference table" but as a
> *candidate* ATN/IPS subnetwork that has to **earn** each class of ATS traffic, in each airspace, by producing on-board,
> signed, statistical RCP/RSP evidence — and that is kept honest by **constellation-aware outage prediction** and
> **RCP-budget hedged dispatch** rather than by reacting to missed acknowledgements.

#### Why the rewrite was necessary (read this first)

The original four sections were sound engineering but, as written, **every core element is already published**:

| Original bullet | Already disclosed by |
|---|---|
| "Register LEO as its own CMU preference tier, separate from GEO SATCOM and VDL2" | Honeywell **US7027812B2** (2000): CMU preference tables "easily support addition of new subnetworks by defining new subnetwork codes"; Honeywell **US7729263B2** (2007): rule-based selection incl. Wi-Fi / WiMAX / cellular / ATN; Thales **US8433817B2** |
| "Carry ATN/IPS (or SNDCF over IP) over the terminal's IP path" | ICAO Doc 9896 / ARINC 858 define IPS over any IP access network; **Rockwell Collins France EP4513465A1** (priority 2023-08-21) carries SNDCF / A618 safety traffic over cabin SATCOM or 5G and says the same applies to ATN/IPS |
| "Use LEO first for high-volume AOC and bulk ATS" | Honeywell **US10425149B1** (2018), **EP3654548B1** (2018), EASA/FAA *Future Connectivity* white paper (2022, "Hyperconnected ATM") |
| "Probe LEO RCP/RSP, fall back automatically to certified SATCOM / VDL2" | **EP4513465A1** claims active/passive probing, a Multi-Link Engine and ack-timeout fallback to a safety medium, and cites RCP/RSP (DO-350A); Collins **US11146329B1** (per-message link selection on measured quality); Collins France **US20260006496A1** (policy-gated media admission) |
| "Keep time-critical CPDLC on certified links until RCP is proven" | EP4513465A1 ¶[0038] (ACD router selects which kinds of traffic go via AISD); Satcom Direct **US20250260475A1** (PBCS monitoring vs RCP 240 / RSP 180 with reconfiguration) |

The closest single reference is the **Collins France "Virtual Safety Radio" family (EP4513465A1 / US2025/0069511A1, pending)**.
It is not yet granted, so its final claim scope is unknown; design freedom (FTO) must be re-checked when it issues.
What *nobody* discloses is the **mechanism that turns a non-certified broadband link into an admissible ATS subnetwork
without a recertification campaign**: a graduated, per-class, per-airspace, evidence-producing admission process coupled to
LEO-specific outage prediction. That is where v2 moves the centre of gravity.

![Fig. 1](figures/fig1_architecture.png)

---

### 1. Situation (updated)

* **Legacy bearers are saturating.** VDL Mode 2 (~31.5 kbps shared per frequency) and L-band GEO SATCOM (Classic Aero /
  SwiftBroadband-Safety, ~tens to ~200 kbps) remain the only ATS-approved air/ground paths for CPDLC and ADS-C.
  The ATN B2 / EPP roadmap (4-D trajectory downlinks, ~2027 mandates in Europe) and the growth of AOC data (EFB sync, QAR
  snapshots, predictive-maintenance uploads) put more volume on links that were sized for 200-byte messages.
* **Regulators already want the offload — and asked for a standard to govern it.** The EASA/FAA *Future Connectivity for
  Aviation* white paper (Nov 2022) and EASA's "Hyperconnected ATM" roadmap explicitly propose moving AOC and non-RCP traffic to
  cabin SATCOM / LEO-MEO links, provided there is "adequate link status and performance monitoring" and "appropriate security
  protections". No performance-based standard for admitting such a link to ATS exists yet; ICAO Doc 9896 (ATN/IPS) and
  ARINC 858 define *how* a link plugs in, not *when it may be trusted*.
* **Industry is already building the plumbing.** Honeywell (AOIP, US10425149B1), Collins France (VSR, EP4513465A1), Collins
  (LEO/3GPP transceiver EP4572182A1), Satcom Direct (ground PBCS monitoring), Thales Alenia Space (ground 4-D quality maps for
  safety-of-life links) and Chinese ATN/IPS router filings (CN120856635B) all exist. Cabin LEO (Starlink Aviation, OneWeb via
  Panasonic / Intelsat, Kuiper announced) gives 100+ Mbps, ~30–60 ms RTT and polar coverage, but **has no AMS(R)S status,
  no priority/pre-emption and no published availability/continuity figures acceptable for RCP/RSP allocation**.
* **The gap:** the certification problem is not "can the CMU send IPS packets over Starlink" (it can) but "how does an
  operator or ANSP obtain the per-airspace evidence that a commercial LEO service meets RCP 240 / RSP 180 (or continental
  B2 values) *for a given traffic class*, keep obtaining it continuously, and bound the consequence of being wrong".
  Today this is done by multi-year ground monitoring campaigns (cf. FAA PARC approving FANS over SwiftBroadband in 2018).

### 2. Target (updated)

1. **Qualify, don't just configure.** Make the LEO path a CMU/ATSU ATN/IPS subnetwork whose use for each traffic class
   (C0 AOC bulk → C5 urgent CPDLC) is *earned in flight* from measured transaction-time and continuity statistics against the
   RCP/RSP applicable to the FIR being flown, and *revoked automatically* on breach — with no change to the existing certified
   subnetworks or to the ATS end systems.
2. **Bound the risk of being wrong.** Any ATS transaction placed on LEO must still complete within its RCP expiration time if
   LEO silently fails — by hedged dispatch on a certified link timed from the measured certified-link P99.9, not by a fixed
   retry timer.
3. **Turn LEO's peculiarities into schedule knowledge.** Satellite handovers (~every 15 s on a shell), beam / gateway switches,
   no-gateway zones and low-elevation geometry are **predictable** from terminal telemetry and ephemeris; pre-empt them instead
   of discovering them through missed acknowledgements.
4. **Produce the approval evidence as a by-product.** Every LEO transaction leaves a signed per-transaction record
   (class, FIR, timestamps, outcome, link state) that the airline, CSP and PBCS monitoring agencies can consume; the
   admission decisions are reconstructible from it.
5. **Scale to several constellations.** Treat two independent LEO providers (e.g. Starlink + OneWeb / Kuiper) as one
   *composite* subnetwork whose combined availability/continuity is what is evaluated, with an independence check.
6. **Preserve the certified baseline.** VDL2 / HFDL / L-band SATCOM remain untouched and always-armed; the LEO adapter is
   additive (ARINC 858 Part 3 radio-interface semantics towards the IPS router) and fail-safe to "LEO off".

### 3. Proposed solution (updated)

**Architecture (Fig. 1).** A *LEO Subnetwork Adapter* (software partition in the CMU/ATSU, or a small ACD LRU on the
ACD side of the domain boundary) owns a dedicated Ethernet port / VLAN on the cabin LEO terminal. The cabin path is treated as
an untrusted pipe: DTLS / IPsec is terminated in the adapter and in an IPS / LEO ground gateway operated by the CSP/DSP, with
mutual PKI authentication (Doc 9896 / ARINC 858 security). The adapter presents itself to the CMU router as one more
subnetwork with ARINC 858 Part 3 link-status semantics — but with a **per-class, per-airspace admission state** instead of a
single "available / unavailable" flag.

**Element A — Graduated qualification state machine (Fig. 2; claim family 1).** For every tuple
(LEO link × traffic class × airspace / FIR) the adapter keeps a state **OFF → SHADOW → PROBATION → ADMITTED ⇄ SUSPENDED**:

* *SHADOW*: idempotent traffic already being sent on a certified link (periodic ADS-C reports, FIS, probes) is **duplicated**
  on LEO; the ground gateway de-duplicates by transaction ID; the adapter accumulates transaction-time (ACTP/ASP equivalents)
  and continuity percentiles **without any operational dependence on LEO**.
* *PROBATION*: once shadow statistics meet the class's thresholds (e.g. ACTP ≤ 120 s @ 95 %, ≤ 150 s @ 99.9 %, continuity
  ≥ spec, N ≥ N_min samples in this FIR), the class is carried on LEO *with hedged fallback* (Element C) for an evidence window.
* *ADMITTED*: LEO becomes the preferred tier for that class; fallback stays armed at the RCP budget.
* *SUSPENDED*: triggered by any expiry, continuity shortfall, authentication failure or a predicted outage longer than the
  class budget; class returns to certified links, LEO carries probes only, hold-down timer, then back to SHADOW.
* The **class ladder is monotonic**: C3 (ADS-C EPP / bulk ATS) can only be admitted while C0–C2 are admitted; CPDLC
  classes (C4/C5) require an airline/ANSP policy switch *and* a clean history, which is how "keep time-critical CPDLC on
  certified links until RCP is proven" becomes a mechanism rather than a sentence.
* Thresholds come from an **RCP/RSP requirement matrix keyed by FIR** (PBCS oceanic RCP 240 / RSP 180; continental ATN B2
  values; AOC classes by airline policy), so admission in the Shanwick OCA does not imply admission in the North Pacific.

![Fig. 2](figures/fig2_admission_state_machine.png)

**Element B — Constellation-aware predictive scheduling (claim family 2).** The adapter ingests LEO terminal telemetry
(serving satellite / beam ID, elevation, next handover time, gateway identity, obstruction / scheduled-maintenance flags) and,
where available, public ephemeris, and projects along the 4-D flight plan: handover instants, gateway-switch windows,
no-gateway / inter-satellite-link-only segments, low-elevation geometry near the poles, and regulatory "LEO not permitted"
regions. The result is a *predicted outage calendar*. Transactions whose remaining RCP budget overlaps a predicted outage
are **pre-emptively started on, or moved to, a certified link** (or delayed if the class tolerates it); the admission state
machine treats a predicted outage longer than the class budget as a breach *before* it happens. Nothing in the record does
this on board for a safety-service admission decision (Thales Alenia Space US10453347B2 is ground-side and for certified
AMS(R)S bearers).

**Element C — RCP-budget hedged dispatch (Fig. 3; claim family 1 dependents).** Each ATS transaction is given a transaction
ID and started on LEO. A certified-link copy is launched at
`t_hedge = ACTP_99.9(class, FIR) − P99.9(certified link, measured) − margin` (e.g. 150 − 95 − 10 = 45 s for RCP 240),
not at a fixed retry timeout. The ground gateway / CMU de-duplicates, first good copy wins, the late copy is cancelled where
the bearer allows. In SHADOW / PROBATION, `t_hedge = 0` (full dual-cast). This differs from EP4513465A1's
"re-send over a safety medium after an acknowledgement timeout" because the certified copy is scheduled from the **RCP
budget and the measured certified-link distribution**, and because the LEO attempt is never on the critical path of the RCP
requirement.

![Fig. 3](figures/fig3_hedged_dispatch.png)

**Element D — Composite multi-constellation subnetwork (claim family 3).** Where the aircraft carries terminals for two
independent LEO systems (different operators, orbits, gateways, spectrum), the adapter instantiates the state machine on a
*virtual* subnetwork whose availability / continuity are computed from the union of the two links, with an independence
monitor (correlated-outage detection: same weather cell, same regulatory region, shared aircraft power bus) that collapses the
composite back to the best single link when independence cannot be demonstrated.

**Element E — Signed PBCS evidence record and ground gateway.** Every LEO transaction (shadow or live) produces a signed
record {class, FIR, link state, serving satellite / beam, timestamps, outcome, hedge decision}; the record is uplinked over
whichever link is cheapest and exported in a PBCS-monitoring-agency-compatible format. The IPS / LEO ground gateway
performs de-duplication, probe peering, admission-state mirroring for uplinks (ground applies the same per-class state to
choose the uplink bearer), and evidence collection. This closes the loop with the `datalink-ai` package (AI-assisted PBCS
monitoring) already in this repository.

**Element F — Capability signalling to end systems.** When C2/C3 are ADMITTED the adapter advertises a higher permissible
reporting rate / message size to the ADS-C and EPP functions (and the ANSP contract can request it); on SUSPENDED the
advertised capability drops back, so end systems never over-commit to a bearer that just vanished.

**Embodiments.** 1) Starlink Aviation terminal, dedicated port to a CMU IPS partition (software-only on an IPS-capable CMU).
2) OneWeb / Kuiper. 3) Composite Starlink + OneWeb. 4) Retrofit: a small ACD LRU between CMU (ARINC 429 / Ethernet) and the
terminal, running the adapter — the same pattern Honeywell used to add SB-Safety to legacy radios (US10412051B2).
5) Military / state aircraft with proprietary LEO services. 6) The same state machine applied to 5G ATG or LDACS trials.

### 4. Benefits (updated)

| Stakeholder | Benefit | What makes it credible (and new) |
|---|---|---|
| **Pilot** | CPDLC / ADS-C latency on admitted classes drops from tens of seconds to seconds; fewer "LINK LOST" / timer expiries; no new HMI — the CMU still shows one datalink status | Admission is per class and per FIR; hedged dispatch guarantees the RCP window even if LEO silently fails |
| **Pilot** | Higher-rate ADS-C EPP and FIS/D-ATIS updates when LEO is admitted (capability signalling, Element F) | End systems only increase rates when the state machine says ADMITTED, and step down on SUSPENDED |
| **Pilot** | Polar / oceanic coverage where GEO is marginal; no manual media selection | Composite subnetwork + outage calendar keep a predictable bearer instead of flapping between media |
| **Airline** | Up to 80–90 % of AOC and bulk-ATS bytes off metered VDL2 / L-band SATCOM (airline-policy classes C0–C1 are admitted first and cheaply) | Same mechanism as Honeywell AOIP for AOC, but with a measured path to extending it to ATS classes |
| **Airline** | Avoids a per-fleet recertification campaign: certified subnetworks unchanged, LEO adapter is additive and fails to "LEO off"; software-only on IPS-capable CMUs | Adapter sits in the ACD, terminates security itself, uses ARINC 858 radio-interface semantics |
| **Airline / CSP** | Automatic, signed, per-FIR PBCS evidence usable for operational-approval dossiers and continuous monitoring; reduces the multi-year "monitor first, approve later" cycle | Evidence record (Element E) — nothing in the landscape produces on-board, decision-bound evidence |
| **Airline** | Vendor independence: Starlink, OneWeb, Kuiper or any future IP bearer qualifies through the same state machine; two providers can be pooled | Composite subnetwork (Element D) |
| **ANSP / regulator** | Performance-based, auditable admission of new bearers instead of bearer-by-bearer certification; gives the EASA/FAA Hyperconnected-ATM roadmap the missing admission mechanism | FIR-keyed RCP/RSP matrix; ground gateway mirrors admission state for uplinks |
| **Everyone** | Resilience: predicted outages are scheduled around; certified links are always armed; attacks on the cabin path cannot inject into the ACD because security terminates in the adapter | Elements B, C and the trust boundary in Fig. 1 |

#### Residual risks and open points (be honest in the disclosure)

* **Collins France EP4513465A1 is pending.** Its claim 1 currently requires a cross-router interface between the ACD router
  and the AISD/PIESD routers. An embodiment that connects the ACD adapter to a dedicated terminal port / VLAN *without passing
  through the cabin routers* is a possible design-around, but claims can be amended before grant — counsel must track it.
* **No commercial LEO service has AMS(R)S status or priority / pre-emption.** The invention does not fix that; it makes the
  consequence bounded and measurable. Regulators may still cap LEO at non-time-critical classes for years.
* **Statistical sufficiency.** N_min per FIR must be large enough that 99.9 % percentiles are meaningful; the shadow phase may
  take many sectors on thin routes — fleet-level pooling of evidence (via the ground gateway) is the mitigation and should be
  described as an embodiment.
* **Terminal telemetry access.** Element B depends on the LEO operator exposing handover / beam / gateway information through
  the terminal API; the fallback is passive inference from RTT / loss patterns plus public ephemeris.



---

# Part B — Patent & prior-art landscape report

*Search date: 2026-10-14 · Analyst: automated landscape screen (not a legal opinion) · Dataset: `PRIOR_ART_DATASET.csv` (44 refs)*

### 1. Executive summary

| Question | Answer |
|---|---|
| Is "LEO (Starlink) as a separate CMU preference tier carrying ATN/IPS, used first for AOC / bulk ATS, probed for RCP and falling back to certified SATCOM/VDL2" novel as stated? | **No.** Each element is individually disclosed, and the combination is substantially disclosed by Rockwell Collins France **EP4513465A1 / US2025/0069511A1** (priority 2023-08-21, pending) read with Honeywell **US7027812B2**, **US10425149B1** and the EASA/FAA 2022 *Future Connectivity* white paper. |
| Closest single reference | **EP4513465A1** — Virtual Safety Radio: ACD router sends ACARS / ATN safety messages over cabin SATCOM or 5G when probing says the non-safety link is available; multi-link engine; crypto + metadata; ground gateway; ack-timeout fallback to safety media; RCP/RSP motivation; explicit statement that ATN/IPS is covered. |
| Where is white space? | (1) **Per-(class × airspace) graduated admission** state machine driven by on-board PBCS statistics gathered by **shadow dual-cast**; (2) **LEO constellation-aware predictive scheduling** (handover / gateway / no-coverage calendar vs RCP budget); (3) **RCP-budget hedged dispatch** timed from the measured certified-link distribution; (4) **composite multi-constellation virtual subnetwork** with independence monitoring; (5) signed, decision-bound **PBCS evidence record** exported from the aircraft. None of these were found in patent or non-patent literature. |
| Recommended posture | File quickly (Collins France is actively filing in this exact space — second application US20260006496A1 published 2026-01-01). Independent claims on (1)+(3), (2), and (4); do **not** claim the preference tier, IPS-over-IP or generic probe-and-fallback. Watch EP4513465A1 prosecution for FTO. |
| Confidence | Moderate-high for patents published before ~2025-04; **blind window** for anything filed after that (18-month publication lag). CN filings are active in ATN/IPS multilink (Beihang, CETC Avionics, Tianhua Hangtong) and may contain more than the snippets show. |

![Fig. 4](figures/fig4_prior_art_map.png)

### 2. Scope and method

* Idea decomposed into 9 claimable elements (E1 LEO tier in CMU; E2 ATN/IPS or SNDCF over terminal IP; E3 AOC/bulk ATS
  first; E4 RCP/RSP probing + fallback; E5 per-class graduated admission; E6 shadow dual-cast evidence; E7 constellation-aware
  prediction; E8 hedged dispatch at RCP budget; E9 composite constellations / evidence record).
* Sources: Google Patents (page reads and `xhr/query` keyword / CPC searches, CPC H04B7/18506, H04W4/42, H04L45/*, G08G5/*),
  Justia, FreePatentsOnline, assignee-driven sweeps (Honeywell, Rockwell Collins / Collins France, Thales, Airbus, Boeing,
  Satcom Direct, Thales Alenia Space, Iridium, SpaceX, Beihang, CETC), citation chasing from the top hits, and non-patent
  literature (ICAO, RTCA/EUROCAE, AEEC, IETF, EASA/FAA, NASA, trade press). Full protocol in `SEARCH_PROTOCOL.md`.
* Reading depth: full description read for refs 1, 3, 4, 13, 14, 17, 22, 23, 27; abstract / claim-level for the rest.

### 3. Element-by-element verdict

| # | Element of the original idea | Verdict | Key references |
|---|---|---|---|
| E1 | LEO registered as its own CMU subnetwork / preference tier | **Anticipated** | US7027812B2 (preference tables accept new subnetwork codes), US7729263B2, US8433817B2, US8484384B2 |
| E2 | ATN/IPS or SNDCF-over-IP across the terminal's IP path, security terminated in the ACD | **Anticipated / obvious** | EP4513465A1 (SNDCF + A618 over AISD, "similar concept applies to ATN/IPS", crypto, ground tunnel endpoint), ICAO Doc 9896, ARINC 858, US10412051B2 (bolt-on secure adapter precedent), Airbus FAST 2022 (PKI tunnel pattern) |
| E3 | AOC and bulk ATS first, time-critical CPDLC stays on certified links | **Anticipated** | US10425149B1 and EP3654548B1 (AOC over IP, CMU-arbitrated), EP4513465A1 ¶[0038] (ACD router picks traffic kinds), EASA/FAA white paper 2022 |
| E4 | Probe LEO RCP/RSP; automatic fallback to L-band SATCOM / VDL2 | **Anticipated** | EP4513465A1 (active/passive probing, 3-step RTT probe, ack-timeout fallback, DO-350A rationale), US11146329B1 (measured quality selection), US20260006496A1 (policy-gated media info), US20250260475A1 (ground PBCS monitoring + reconfiguration), CN120856635B (IPS link scoring) |
| E5 | **Graduated per-(class × FIR) admission state machine** with PBCS percentile thresholds and monotonic class ladder | **Not found** | Nearest: EP4513465A1 binary availability; US20260006496A1 policy gate on media status; FAA PARC 2018 process (manual, ground, fleet-level) |
| E6 | **Shadow dual-cast** of idempotent ATS traffic to build evidence with zero operational dependence | **Not found** | Nearest: EP4513465A1 probing; US8045977B2 RTT measurement in CMU (congestion only) |
| E7 | **Constellation-aware predictive scheduling** (handover / gateway / no-coverage calendar vs RCP budget) on board | **Not found on board** | US10453347B2 (ground 4-D quality maps for certified SoL links — closest and must be distinguished); commercial multi-orbit IFC switching (Aviation Week 2025) is reactive and cabin-only |
| E8 | **Hedged dispatch** with t_hedge derived from RCP allocation − measured P99.9(certified) | **Not found** | EP4513465A1 ¶[0041] mentions remaining time via safety links after failure — reactive; must be distinguished explicitly in the claim |
| E9 | **Composite multi-constellation subnetwork** with independence monitor; signed on-board PBCS evidence record bound to admission decisions | **Not found** | US9356686B1 (space topology only); US20250260475A1 (ground evidence) |

### 4. Closest art in detail

#### 4.1 Rockwell Collins France — EP4513465A1 / US2025/0069511A1 (priority 2023-08-21, published 2025-02-26/27, **pending**)
*Air ground communication method for transmitting safety messages over non safety infrastructure.*

* **Claim 1 (EP, as published):** method for an aircraft with an ACD router and at least one non-safety-domain router; a
  *Virtual Safety Radio* is provided to the ACD router through a cross-router interface between the ACD router and the
  non-safety router(s); the VSR determines that a non-safety media link is available; the ACD application message is sent via it.
* **Dependents:** active and/or passive probing; Multi-Link Engine choosing the non-safety media from media status + probe
  result; cryptographic securing + metadata; ground tunnel endpoint decapsulation/verification; **if no acknowledgement is
  received within a time threshold, the VSR reports failure and the ACD router re-sends via a safety media**; uplink
  symmetric; system claim.
* **Description highlights relevant to us:** 5G and cabin SATCOM as the non-safety media; ACARS A618 blocks and ATN/OSI
  SNDCF frames; ¶[0039] "a similar concept may apply to ATN/IPS"; ¶[0038] ACD router selects which kinds of traffic it will
  convey via AISD/PIESD; ¶[0040–41] RCP/RSP (DO-350A/ED-228A) rationale and the remark that after failure there is still time
  left to use safety links; IPsec; ACD does not trust AISD-reported status.
* **What it lacks:** LEO specifics (handover / gateway / ephemeris), any statistical or percentile criterion, per-class or
  per-airspace states, shadow dual-cast, hedge timing from RCP budget, composite links, signed evidence, capability signalling.
* **FTO note:** claim 1 as published requires the cross-router interface between the ACD router and the non-safety router(s).
  An embodiment where the ACD adapter owns a dedicated terminal port / VLAN and no AISD/PIESD router is in the path arguably
  falls outside that wording — but this is a pending application and claims may be broadened or narrowed; flag for counsel.

#### 4.2 Rockwell Collins France — US20260006496A1 (priority 2024-06-28, published 2026-01-01, pending)
Media microservice controllers normalise link metrics and relay them to the router only when the media policy is fulfilled.
Shows Collins France is iterating on *policy-gated media admission*. Our per-class statistical admission with evidence record
and state transitions is a different axis (traffic-class qualification vs media-status gating) — claim it that way.

#### 4.3 Honeywell — US10425149B1 (2018) and EP3654548B1 (2018)
AOC/non-safety ACARS over cabin IP via an AOIP device that tells the CMU when the IP path is available; pseudo-ack gateway.
Establishes E1–E3 for AOC. Their hard safety/non-safety split is the opposite of our graduated admission.

#### 4.4 Honeywell — US7027812B2 (2000) and US7729263B2 (2007)
Preference tables and rule-based network selection in the CMU over any subnetwork, including Wi-Fi/WiMAX/cellular/ATN.
Kills E1 on its own.

#### 4.5 Rockwell Collins — US11146329B1 (2018)
Measured bidirectional SNR + cost + priority link selection by an on-board supervisory controller. Instantaneous, not
statistical; no admission states.

#### 4.6 Thales Alenia Space Italia — US10453347B2 (2015)
Ground system ingests quality measurements for safety-of-life links with the aircraft's 4-D trajectory and adapts resources.
Closest to E7 — distinguish by (a) on-board, (b) non-certified bearer, (c) constellation handover / gateway prediction as
input to an admission state and to transaction scheduling.

#### 4.7 Satcom Direct — US20250260475A1 (2024)
Ground PBCS monitoring vs RCP 240 / RSP 180 with NOC-triggered reconfiguration. Ground-side and after-the-fact; cite it to show
the thresholds and the "monitor then reconfigure" idea are known, and that moving them on board as a per-class gate is the step.

#### 4.8 Non-patent
EASA/FAA *Future Connectivity for Aviation* (2022) and EASA webinar (2023) anticipate the concept of LEO/MEO offload and
ask for performance monitoring; ICAO Doc 9896 / ARINC 858 provide the IPS substrate; DO-350A / ED-228A / Doc 9869 provide the
numbers (RCP 240: ACTP ≤ 120 s @95 %, ≤ 150 s @99.9 %; RSP 180: ASP ≤ 90 s @95 %, ≤ 180 s @99.9 %); FAA PARC 2018 letter shows
bearer admission (SwiftBroadband for FANS) being decided on monitored PBCS statistics — manually. Iridium / ARINC 771 show LEO
L-band already carries FANS, so "LEO" alone is not the differentiator; "broadband Ku/Ka LEO without AMS(R)S status earning
admission" is.

### 5. Landscape by cluster

| Cluster | Refs | Density | Takeaway |
|---|---|---|---|
| A — Safety traffic over non-safety / broadband IP | 12 | High and **active** (Collins France 2023, 2024; Honeywell 2024) | Concept is taken; mechanism of admission is open |
| B — CMU multi-subnetwork selection / preference | 8 | Mature (1998–2018), several expired | Nothing to claim here; cite as background |
| C — Performance measurement & triggered reconfiguration; IPS multilink scoring | 6 | Growing (Satcom Direct 2024, CN 2024–2025) | Ground-side or generic-metric; on-board per-class PBCS admission is open |
| D — LEO / satellite architectures | 5 | Hardware-oriented | Shows LEO for ACARS is being filed; no admission logic |
| N — Standards / regulators / press | 13 | — | Regulators want exactly this mechanism; no standard yet |

### 6. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| EP4513465A1 grants with claims broad enough to read on any ACD-side use of a cabin link with probing/fallback | Medium | Design-around (dedicated port / VLAN, no cross-router); narrower claims on E5–E9; monitor prosecution; consider third-party observations citing US10425149B1, US7729263B2 |
| Unpublished Collins / Honeywell / Thales filings (2025-04 → now) on LEO admission | Medium | File provisional now; re-search at 6 and 12 months |
| Examiner treats E5 as obvious over EP4513465A1 + US20250260475A1 (monitoring) + FAA PARC process | Medium | Emphasise shadow dual-cast with zero operational dependence, monotonic class ladder, FIR-keyed thresholds, decision-bound signed evidence, and the technical effect (bounded RCP exposure while qualifying) |
| E7 obvious over US10453347B2 + multi-orbit IFC switching | Low-medium | Claim ephemeris/handover calendar as input to *transaction scheduling against the RCP budget* and to the admission state, on board |
| CN prior art richer than snippets | Low-medium | Order full translations of CN120856635B, CN121483092A, CN118200224A before filing |

### 7. Recommendations

1. **Rewrite the invention around E5–E9** (done in `IDEA_LEO_ATN_SUBNETWORK_v2.md`); treat E1–E4 as the environment.
2. **File a provisional / first filing promptly**; Collins France has two publications in 18 months in this exact niche.
3. Independent claims: (i) per-(class × airspace) graduated admission with shadow dual-cast + hedged dispatch;
   (ii) constellation-aware predicted-outage calendar driving transaction scheduling and admission; (iii) composite
   multi-constellation virtual subnetwork with independence monitor. See `DRAFT_CLAIM_SET.md`.
4. Include method, apparatus (CMU / ACD adapter LRU), ground-gateway and CRM claims; describe software-only and retrofit
   embodiments; describe fleet-pooled evidence as an embodiment.
5. Cite EP4513465A1, US10425149B1, US7027812B2, US7729263B2, US11146329B1, US10453347B2, US20250260475A1 and the EASA/FAA
   white paper in the IDS / background.
6. Commission a professional FTO opinion on EP4513465A1 / US2025/0069511A1 before any product announcement.



---

# Part C — Draft claim set and claim charts

*Drafting aid for patent counsel, not a filing. Terminology follows ICAO Doc 9869 (PBCS), Doc 9896 (ATN/IPS) and ARINC 858.*

### Definitions used in the claims

* **certified subnetwork** — an air/ground subnetwork approved for ATS safety communications (e.g. VDL Mode 2, HFDL, AMS(R)S
  L-band SATCOM).
* **candidate subnetwork** — an IP-capable air/ground link not so approved (e.g. a Ku/Ka-band LEO broadband terminal installed
  for cabin connectivity).
* **traffic class** — a category of datalink messages sharing a required communication / surveillance performance
  (e.g. AOC bulk, AOC operational, ADS-C periodic, ADS-C EPP, CPDLC non-time-critical, CPDLC clearances).
* **performance requirement** — a set of transaction-time, continuity and availability thresholds associated with a traffic class
  and an airspace region (e.g. RCP 240 ACTP ≤ 120 s at 95 %, ≤ 150 s at 99.9 %; RSP 180 ASP ≤ 90 s at 95 %, ≤ 180 s at 99.9 %).
* **admission state** — one of at least a shadow state, an admitted state and a suspended state maintained for a tuple of
  (candidate subnetwork, traffic class, airspace region).

---

### Family 1 — Graduated, evidence-based admission with hedged dispatch

**1.** A method performed by an airborne communications management unit coupled to at least one certified subnetwork and to a
candidate subnetwork, the method comprising:
(a) storing performance requirements for a plurality of traffic classes indexed by airspace region;
(b) maintaining, for each tuple of candidate subnetwork, traffic class and airspace region, an admission state selected from
at least a shadow state, an admitted state and a suspended state;
(c) while a tuple is in the shadow state, transmitting messages of the traffic class over the certified subnetwork and
**additionally transmitting duplicates of said messages over the candidate subnetwork**, each duplicate carrying a transaction
identifier enabling de-duplication at a ground gateway, and measuring transaction-time and continuity statistics of the
duplicates on the candidate subnetwork;
(d) transitioning the tuple to the admitted state only when the measured statistics satisfy the performance requirement
stored for the traffic class and the airspace region currently being flown over at least a minimum number of transactions;
(e) while the tuple is in the admitted state, selecting the candidate subnetwork as the preferred subnetwork for messages
of the traffic class; and
(f) transitioning the tuple to the suspended state, and reverting messages of the traffic class to the certified subnetwork,
upon detecting a breach of the performance requirement.

**2.** The method of claim 1, wherein the admission states further comprise a probation state between the shadow state and the
admitted state, in which messages of the traffic class are transmitted over the candidate subnetwork and a duplicate is
transmitted over the certified subnetwork at a hedge time computed from the performance requirement.

**3.** The method of claim 1 or 2, wherein, for a message of a traffic class whose tuple is in the admitted state, the method
comprises transmitting the message over the candidate subnetwork at a first time and, **if no completion is observed by a hedge
time, transmitting a duplicate over the certified subnetwork, the hedge time being computed as the transaction-time threshold
of the performance requirement minus a measured upper-percentile transaction time of the certified subnetwork minus a margin.**

**4.** The method of claim 3, wherein the measured upper-percentile transaction time of the certified subnetwork is updated
from transactions carried on the certified subnetwork during the current flight and indexed by airspace region.

**5.** The method of any preceding claim, wherein the traffic classes are ordered, and a tuple for a higher-ordered traffic class
is prevented from entering the admitted state unless the tuples for all lower-ordered traffic classes for the same candidate
subnetwork and airspace region are in the admitted state.

**6.** The method of claim 5, wherein the ordered traffic classes comprise, from lowest to highest, airline operational
communications, periodic ADS-C reports, extended-projected-profile ADS-C reports, non-time-critical CPDLC messages and
time-critical CPDLC messages, and wherein entry of a CPDLC traffic class into the admitted state further requires a stored
operator or air-navigation-service-provider authorisation for the airspace region.

**7.** The method of any preceding claim, wherein the breach comprises at least one of: a transaction exceeding an expiration
time; a continuity statistic falling below the requirement; an authentication failure on the candidate subnetwork; and a
predicted unavailability of the candidate subnetwork of duration exceeding a budget associated with the traffic class.

**8.** The method of any preceding claim, wherein transitioning to the suspended state starts a hold-down timer, during which
only probe traffic is transmitted over the candidate subnetwork, and upon expiry of which the tuple returns to the shadow state.

**9.** The method of any preceding claim, further comprising generating, for each message transmitted over the candidate
subnetwork, a **digitally signed evidence record** comprising the traffic class, the airspace region, the admission state at the
time of transmission, timestamps, an outcome, and a candidate-subnetwork link descriptor, and transmitting the evidence records
to a ground system for performance-based communication and surveillance monitoring.

**10.** The method of claim 9, wherein the transition of claim 1(d) is computed from evidence records pooled across a plurality
of aircraft for the same candidate subnetwork and airspace region, received from the ground system.

**11.** The method of any preceding claim, wherein messages transmitted over the candidate subnetwork are encapsulated in an
Internet Protocol Suite tunnel whose security association is terminated in the communications management unit and in the
ground gateway, such that no device of a non-certified aircraft domain terminates the security association.

**12.** The method of any preceding claim, further comprising advertising to an ADS-C or CPDLC end system an increased
permissible reporting rate or message size when the tuple for its traffic class is in the admitted state and withdrawing the
advertisement when the tuple leaves the admitted state.

**13.** The method of any preceding claim, wherein the candidate subnetwork is a low-earth-orbit broadband satellite link
and the certified subnetwork is one of VDL Mode 2, HFDL and L-band aeronautical mobile satellite (route) service.

**14.** An airborne apparatus comprising a processor configured to perform the method of any of claims 1–13, the apparatus
being one of: a partition of a communications management unit; and a line-replaceable unit in the aircraft control domain
interposed between the communications management unit and a dedicated network port of a cabin broadband terminal.

**15.** A ground gateway configured to: receive messages and duplicates carrying transaction identifiers from an aircraft via a
certified subnetwork and a candidate subnetwork; forward a first-received copy and discard later copies; receive evidence
records according to claim 9; and, for uplink messages to the aircraft, select the candidate subnetwork or the certified
subnetwork according to the aircraft's reported admission state for the traffic class and airspace region.

---

### Family 2 — Constellation-aware predictive scheduling

**16.** A method performed by an airborne communications management unit coupled to a certified subnetwork and to a candidate
subnetwork provided by a non-geostationary satellite constellation, comprising:
(a) obtaining, from a terminal of the candidate subnetwork and/or from stored ephemeris, constellation state information
comprising at least one of a serving-satellite identifier, a next-handover time, a serving-gateway identifier, an elevation
angle and a coverage or regulatory restriction;
(b) obtaining a four-dimensional trajectory of the aircraft;
(c) computing, from (a) and (b), a **predicted-unavailability calendar** comprising future intervals during which the candidate
subnetwork is predicted to be unavailable or degraded;
(d) for a datalink transaction having a performance requirement with an expiration time, determining whether the interval
between the transaction's start and its expiration time overlaps a predicted-unavailability interval; and
(e) when an overlap is determined, **initiating the transaction on the certified subnetwork, or advancing or deferring the
transaction on the candidate subnetwork, before the predicted-unavailability interval begins**, instead of awaiting a failed
acknowledgement.

**17.** The method of claim 16, wherein the predicted-unavailability calendar is further used as an input to an admission state
maintained per traffic class and airspace region, a predicted-unavailability interval longer than a budget of the traffic
class causing the admission state to transition to a suspended state before the interval begins.

**18.** The method of claim 16 or 17, wherein the constellation state information is validated against passively measured
round-trip-time and loss patterns on the candidate subnetwork, and ephemeris-derived prediction is used when terminal-reported
information is unavailable.

**19.** The method of any of claims 16–18, wherein the predicted-unavailability calendar comprises intervals in which the
aircraft's trajectory crosses a region in which the constellation has no ground gateway and no inter-satellite relay, a region
in which operation of the candidate subnetwork is not permitted, or a region in which satellite elevation is below a threshold.

**20.** The method of any of claims 16–19, further comprising adjusting the hedge time of claim 3 by the duration of a
predicted-unavailability interval that overlaps the transaction window.

---

### Family 3 — Composite multi-constellation subnetwork

**21.** A method performed by an airborne communications management unit coupled to a certified subnetwork and to at least two
candidate subnetworks provided by mutually independent non-geostationary satellite systems, comprising:
(a) defining a composite candidate subnetwork whose availability and continuity statistics are computed from the union of the
at least two candidate subnetworks;
(b) maintaining admission states according to claim 1 for the composite candidate subnetwork;
(c) monitoring the statistical independence of unavailability events of the at least two candidate subnetworks; and
(d) when the monitored independence falls below a threshold, replacing the composite candidate subnetwork's statistics with
the statistics of the best-performing single candidate subnetwork for the purpose of the admission states.

**22.** The method of claim 21, wherein the independence monitoring comprises detecting correlated unavailability attributable
to a common cause selected from: a common weather cell along the trajectory; a common regulatory restriction region; a common
aircraft power or network segment; and a common ground gateway region.

**23.** The method of claim 21 or 22, wherein messages of a traffic class in the admitted state are transmitted over whichever
of the at least two candidate subnetworks has the earlier predicted-unavailability interval end according to claim 16.

---

### Claim charts against the closest art

Legend: ● disclosed · ◐ partially / arguably disclosed · ○ not disclosed

#### Chart A — Claim 1 (Family 1)

| Claim 1 element | EP4513465A1 (Collins France) | US10425149B1 (Honeywell) | US11146329B1 (Collins) | US20260006496A1 (Collins France) | US20250260475A1 (Satcom Direct) | US10453347B2 (TAS-I) |
|---|---|---|---|---|---|---|
| CMU coupled to certified + candidate subnetworks | ● VSR via X-router | ● CMU + AOIP | ● multilink controller | ● router + media controllers | ○ ground system | ○ ground system |
| Performance requirements per traffic class **indexed by airspace region** | ◐ cites RCP/RSP generally; no per-region table | ○ | ◐ cost by position | ◐ media policy | ● RCP 240/RSP 180 benchmarks (ground) | ◐ 4-D quality maps for certified links |
| Admission state per (candidate, class, region) with shadow / admitted / suspended | ○ binary "available" | ○ binary availability flag | ○ | ○ media-policy gate (no states) | ○ | ○ |
| **Shadow dual-cast** of class traffic with transaction IDs for ground de-dup, measuring statistics | ○ (probes only) | ○ | ○ | ○ | ○ | ○ |
| Transition to admitted only when measured stats meet requirement over N transactions | ○ | ○ | ○ | ◐ relay when policy fulfilled (status, not statistics) | ◐ alerting on benchmark breach | ○ |
| Candidate preferred while admitted | ● | ● (non-safety only) | ● | ● | ○ | ○ |
| Suspend + revert on breach | ◐ ack-timeout re-send via safety media | ◐ availability flag | ◐ | ○ | ◐ reconfiguration from NOC | ◐ resource adaptation |

**Takeaway:** the shadow dual-cast with de-duplicated transaction IDs, the statistical admission gate per airspace region and
the explicit admission state set are absent from all six. Expect an obviousness argument combining EP4513465A1 (probing +
fallback) with US20250260475A1 (PBCS statistics) — rebut with the technical effect (evidence gathered with **zero** operational
exposure, then bounded exposure via claim 3) and the FIR-indexed monotonic ladder (claims 5–6).

#### Chart B — Claim 3 (hedged dispatch)

| Element | EP4513465A1 | US11146329B1 | US8045977B2 (Honeywell RTT) |
|---|---|---|---|
| Transmit on candidate first | ● | ◐ | ○ |
| Duplicate on certified link if no completion by a **hedge time** | ◐ re-send after acknowledgement time threshold (reactive) | ○ | ○ |
| Hedge time = requirement threshold − measured P99.9(certified) − margin | ○ (¶[0041] only notes remaining time exists) | ○ | ○ (measures RTT for congestion delay) |
| Measured certified-link percentile updated in flight per region | ○ | ○ | ◐ RTT measured, not per region or percentile |

#### Chart C — Claim 16 (Family 2)

| Element | US10453347B2 (TAS-I) | EP4513465A1 | EP4572182A1 (Collins LEO radio) | Aviation Week 2025 multi-orbit IFC |
|---|---|---|---|---|
| Constellation state (satellite / handover / gateway / elevation) obtained on board | ○ (ground receives quality data) | ○ | ◐ radio knows connectivity | ◐ terminal switches by conditions |
| 4-D trajectory used | ● (ground) | ○ | ○ | ○ |
| Predicted-unavailability calendar computed on board | ○ | ○ | ○ | ○ |
| Overlap test against transaction expiration time | ○ | ○ | ○ | ○ |
| Pre-emptive move / advance / defer before the interval | ◐ resource adaptation on ground | ○ (reactive) | ○ | ◐ reactive switching |

#### Chart D — Claim 21 (Family 3)

| Element | US9356686B1 | EP4513465A1 Multi-Link Engine | ICAO Doc 9896 multilink |
|---|---|---|---|
| Two independent NGSO candidate subnetworks on one aircraft | ○ | ◐ "several non-safety media" | ◐ |
| Composite availability / continuity statistics for admission | ○ | ○ | ○ |
| Independence monitor with collapse to single link | ○ | ○ | ○ |

### Drafting notes

* Keep "candidate subnetwork" generic in independent claims; make LEO (claim 13) and 5G ATG / LDACS dependents.
* Claim 1(c) is the backbone — do not drop "duplicates ... transaction identifier ... de-duplication" in any broadening.
* Avoid reciting a "cross-router interface" anywhere; describe the dedicated port / VLAN embodiment prominently (FTO vs EP4513465A1).
* Include CRM and ground-gateway claims (claim 15) so that the CSP side is covered independently of the avionics vendor.
* Provide worked numbers in the description (RCP 240: 150 − 95 − 10 = 45 s; RSP 180 equivalent) and the state diagram (Fig. 2).



---

# Part D — Invention disclosure

| Field | Entry |
|---|---|
| Working title | Graduated, evidence-based admission of a non-certified broadband link to ATS datalink traffic classes, with constellation-aware scheduling and RCP-budget hedged dispatch |
| Technical field | Aeronautical air/ground datalink (ACARS, ATN/OSI, ATN/IPS); CMU/ATSU routing; PBCS (RCP/RSP) |
| Date of conception | prior to 2026-10-14 (idea v1); v2 refinement 2026-10-14 |
| Status | Not disclosed publicly; not offered for sale |
| Related internal work | `datalink-ai/` (AI-assisted PBCS monitoring) — the evidence record of this disclosure is a natural input |

### 1. Problem

Commercial LEO broadband (Starlink, OneWeb, Kuiper) offers two orders of magnitude more capacity and far lower latency than
VDL Mode 2 or L-band SATCOM, but has no AMS(R)S status, no priority/pre-emption, and no published performance evidence
acceptable for RCP/RSP allocation. Known approaches either (a) restrict such links to non-safety traffic (Honeywell AOIP), or
(b) let the ACD router send safety messages over them when a probe says they are "available" and fall back after an
acknowledgement timeout (Collins France VSR). Neither produces the per-airspace statistical evidence a regulator needs, neither
bounds the RCP exposure while that evidence is being built, and neither exploits the fact that LEO outages (handovers, gateway
switches, coverage gaps) are predictable.

### 2. Summary of the invention

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

### 3. Detailed description pointers

* Architecture: `figures/fig1_architecture.png`; state machine: `figures/fig2_admission_state_machine.png`;
  hedge timeline: `figures/fig3_hedged_dispatch.png`. Narrative: `IDEA_LEO_ATN_SUBNETWORK_v2.md` §3.
* Worked example (RCP 240, North Atlantic): ACTP threshold 150 s @ 99.9 %; measured SB-S P99.9 = 95 s; margin 10 s → hedge at
  45 s. Typical LEO transaction 2–30 s, so > 99 % of transactions complete before the hedge fires; the certified link carries
  only the residue.
* Class ladder: C0 AOC bulk, C1 AOC ops, C2 ADS-C periodic/event, C3 ADS-C EPP / FIS / D-ATIS, C4 CPDLC non-time-critical,
  C5 CPDLC clearances / urgent (policy-gated).
* Embodiments: software partition on IPS-capable CMU; ACD LRU retrofit between CMU and terminal port; Starlink / OneWeb /
  Kuiper; composite; 5G ATG / LDACS; fleet-pooled evidence via ground gateway.

### 4. Advantages over the closest prior art

| Prior art | Our difference |
|---|---|
| EP4513465A1 (Collins France VSR, pending) | Statistical per-class / per-FIR admission with shadow evidence instead of binary availability; hedge timed from RCP budget instead of reactive ack timeout; LEO outage prediction; composite links; signed evidence; no cross-router dependency |
| US10425149B1 / EP3654548B1 (Honeywell AOIP) | ATS classes can be admitted — graduated, not hard-split |
| US7027812B2 / US7729263B2 (Honeywell CMU selection) | Admission is earned from measured performance, not configured |
| US11146329B1 (Collins multilink) | Transaction-level PBCS statistics and states, not instantaneous SNR |
| US10453347B2 (TAS-I) | On board, for a non-certified bearer, constellation handover / gateway prediction feeding transaction scheduling |
| US20250260475A1 (Satcom Direct) | On-board, real-time, decision-bound; ground monitoring becomes a consumer of our evidence |

### 5. Known prior art to cite

EP4513465A1 / US20250069511A1; US20260006496A1; US10425149B1; EP3654548B1; US7027812B2; US7729263B2; US8433817B2;
US11146329B1; US10453347B2; US20250260475A1; US10412051B2; EP4572182A1; CN120856635B; EASA/FAA *Future Connectivity for
Aviation* (2022); ICAO Doc 9896, Doc 9869; RTCA DO-350A / EUROCAE ED-228A; ARINC 858, 771; RFC 9372.

### 6. Commercial relevance

Airlines (AOC / bulk ATS offload without recertification; vendor-neutral LEO adoption), CMU/ATSU vendors (software feature),
CSP/DSPs (ground gateway + evidence service), ANSPs / regulators (performance-based bearer admission matching the EASA/FAA
Hyperconnected-ATM roadmap). Standards leverage: ARINC 858 / ICAO WG-I contribution on "candidate access network admission".

### 7. Inventor notes / open questions

* Access to LEO terminal telemetry (handover schedule, beam / gateway IDs) depends on operator APIs; passive inference fallback described.
* N_min and percentile estimators for thin routes — fleet pooling embodiment.
* Confirm whether the ground gateway should be CSP-operated or ANSP-operated (both claimed).
* Track EP4513465A1 prosecution; obtain FTO opinion before product disclosure.



---

# Part E — Search protocol

### 1. Idea decomposition (search elements)

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

### 2. Sources

* Google Patents: individual publication pages and the `xhr/query` endpoint (keyword + CPC + assignee filters).
* Justia Patents (US publications with full bibliographic data).
* FreePatentsOnline (older US patents).
* Non-patent: EASA, FAA, ICAO, RTCA/EUROCAE, AEEC/SAE ITC listings, IETF datatracker / RFC Editor, NASA NTRS, Airbus FAST,
  Aviation Week, Aerospace Tech Review, Iridium, Starlink Aviation, CASA / Bahamas CAA PBCS pages.

### 3. CPC groups swept

`H04B7/18506` (aeronautical satellite / air-ground), `H04B7/185`, `H04W4/42` (vehicle-to-infrastructure, aircraft),
`H04W36/*` (handover), `H04L45/24`, `H04L45/302`, `H04L47/*` (multipath / QoS), `H04L67/12`, `G08G5/00`, `G08G5/0013`,
`H04W72/542`, `H04B17/364`.

### 4. Query log (representative; noise queries omitted)

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

### 5. Limits

* 18-month publication blind window: filings after ~2025-04 are invisible.
* CN documents assessed from machine-translated snippets; full translations recommended before filing.
* Legal status not verified against national registers (marked n/v where unknown).
* Not a freedom-to-operate opinion.

### 6. Re-run schedule

Repeat queries 4, 5, 7, 9, 14–17 at +6 and +12 months; set alerts on assignees Rockwell Collins France SAS, Honeywell,
Thales, Satcom Direct, SpaceX, Beihang University, CETC Avionics, and on CPC H04B7/18506 ∩ (RCP OR "performance based").



---

## Appendix — Prior-art dataset (44 references)

*Automated landscape screen, not a legal opinion. Dates marked n/v were not verified against the register. Pending applications have an 18-month publication blind window: filings after ~2025-04 are invisible.*

| # | Publication | Assignee | Priority → Published | Status | Cluster | Overlap | What it discloses | Differentiation hook |
|---|---|---|---|---|---|---|---|---|
| 1 | **EP4513465A1**<br>Air ground communication method for transmitting safety messages over non safety infrastructure | Rockwell Collins France SAS | 2023-08-21 → 2025-02-26 | Pending | A | CRITICAL | Virtual Safety Radio (VSR) exposed to the ACD router (CMU/ATSU) through a cross-router (X-router) interface to AISD/PIESD routers. VSR determines by active and/or passive link probing that a non-safety media link (cellular 5G, cabin SATCOM) is available; a Multi-Link Engine selects the best non-safety media from media status + probe result; messages are secured by cryptography and tagged with metadata; a ground tunnel endpoint / ground gateway decapsulates, verifies and routes to ACARS / ATN-OSI endpoints; if no acknowledgement within a time threshold the VSR reports link failure and the ACD router re-sends over a safety media (HF/VDL/SATCOM). Spec explicitly covers SNDCF frames and A618 blocks over the AISD network, states applicability to ATN/IPS, cites RCP/RSP (DO-350A/ED-228A) and the EASA/FAA Hyperconnected ATM white paper, and notes the ACD router may 'select which kind of ACARS and/or ATN/OSI traffic it will convey via the AISD/PIESD'. | Reactive (ack-timeout) fallback and a single availability determination. No per-traffic-class / per-airspace statistical RCP admission state machine, no shadow dual-cast evidence building, no constellation-aware prediction, no RCP-budget hedge timing, no composite-availability construction from multiple LEO links, no signed on-board evidence record bound to admission decisions. |
| 2 | **US20250069511A1**<br>Air ground communication method for transmitting safety messages over non safety infrastructure | Rockwell Collins France SAS | 2023-08-21 → 2025-02-27 | Pending | A | CRITICAL | US member of ref 1 (filed 2024-08-19). Same abstract: VSR via X-router; determine non-safety media link available; send ACD application message via it. | As ref 1. |
| 3 | **US10425149B1**<br>ACARS over IP system for non-safety messages | Honeywell International Inc. | 2018-08-22 → 2019-09-24 | Granted | A | HIGH | CMU coupled to safety subnetworks (VHF/SATCOM/HF) and to an AOIP computing device coupled to a non-safety IP broadband subnetwork (Wi-Fi, cellular, broadband SATCOM). AOIP device classifies ACARS messages as safety / non-safety, forwards non-safety over IP, and signals availability / unavailability to the CMU so that safety messages are never stranded on the non-approved link; discusses DO-178B level and 10-12 min NO COMM problem. | Hard split: safety traffic never uses the broadband link. Our idea is the opposite - earn admission of ATS classes with measured performance. |
| 4 | **EP3654548B1**<br>Vehicle multi-communication message type communication system | Honeywell International Inc. | 2018-11-13 → 2021-05-12 | Granted | A | MODERATE-HIGH | CMU routes some ACARS (non-safety) messages to a data gateway which returns a pseudo-acknowledgement per block to the CMU and converts the message to an IP message for a faster broadband path; cites FR2920622 and WO2006/026632 (ACARS over TCP/IP). | Non-safety only; pseudo-ack trick. No performance qualification of the IP path for ATS. |
| 5 | **US20260006496A1**<br>Communications management systems and methods | Rockwell Collins France SAS | 2024-06-28 → 2026-01-01 | Pending | A | MODERATE-HIGH | Aerospace communications router fed by per-media microservice controllers (HF/VHF/UHF, Wi-Fi, cellular, satellite); each controller normalises link status, speed, latency, signal quality, media cost into a common format and only relays it to the router once the media policy governing that device is fulfilled; may use sensor data in that determination. | Policy gate on *media information*, not a statistical RCP admission of *traffic classes*; no evidence collection, no prediction, no hedging. |
| 6 | **US10412051B2**<br>System and method for satellite communications link | Honeywell International Inc. | 2017-02-08 → 2019-09-10 | Granted | A | MODERATE | Separate secure communications processor installed between the aircraft router and an existing SwiftBroadband satcom radio so that legacy radios can use the encrypted SB-Safety service; routes ACARS, ATN/OSI and ATN/IPS. | Precedent for a 'bolt-on' certified adapter that upgrades an IP bearer to safety use - supports obviousness of E1; nothing on admission logic. |
| 7 | **US8774795B2**<br>Reconfigurable satcom avionics radio | Honeywell International Inc. | 2011-05-20 → 2014-07-08 | Granted | A | MODERATE | Reconfigurable radio unit providing simultaneously at least one safety-certified cockpit channel and one cabin-services channel. | Hardware partitioning of one radio; no CMU-side qualification of a cabin bearer. |
| 8 | **US20250253929A1**<br>EFB or AID communication media for datalink message transmission and reception | Honeywell International Inc. | 2024-02-01 → 2025-08-07 | Pending | A | MODERATE | Communications management system forwards downlink messages to an EFB and/or Aircraft Interface Device which transmits them over its own (non-certified) link, and receives uplinks the same way. | Another 'borrow a non-certified link' architecture; no performance admission, class ladder or evidence. |
| 9 | **US20150215899A1**<br>Secure aircraft data transmission using multiple communication channels | The Boeing Company | n/v → 2015-07-30 | n/v | A | MODERATE | Communication channel manager on the aircraft allocates ACD / AISD / PIESD data domains to available channels (BPL, Ethernet, Wi-Fi, cellular, satellite) by channel security level, cost, speed and available duration; same domain may be split across channels. | Security-level matching at the gate; not in-flight RCP qualification. |
| 10 | **EP2315367B1**<br>Aeronautical security management over broadband air/ground network | Honeywell International Inc. | 2009-10-22 → 2013-08-28 | Granted | A | LOW-MODERATE | Security parameters established with ground entities before take-off over broadband and reused in flight for protected message exchange along the flight path. | Security bootstrap only. |
| 11 | **US7395344B2**<br>Method for ACARS application communication over an IP network | The Boeing Company | n/v → 2008-07-01 | Granted (likely expired) | A | LOW | ARINC 619 ACARS messages packaged for Ethernet/AFDX using TFTP; on-board router-to-end-system transport, not air-ground. | Transport detail only. |
| 12 | **US6677888B2**<br>Secure aircraft communications addressing and reporting system (ACARS) | Honeywell International Inc. | n/v → 2004-01-13 | Expired | A | LOW | End-to-end cryptographic protection and compression of ACARS payloads between CMU and ground FEP. | Background for 'secure the payload, not the bearer'. |
| 13 | **US7027812B2**<br>Channel selection in aircraft communications system by determining zone load and selecting alternate carrier | Honeywell International Inc. | 2000-07-05 → 2006-04-11 | Expired | B | HIGH | CMU/MU selects the preferred air/ground subnetwork and VHF frequency from a user-loadable (AMI) database of channel preferences per region; preference codes SAT/HF/VHF-n/NONE; 'easily supports the addition of new channels or subnetworks by defining new subnetwork codes in the preference tables'; dynamic reordering on status. | Directly anticipates 'register LEO as its own CMU preference tier'. That element cannot carry the filing. |
| 14 | **US7729263B2**<br>Aircraft data link network routing | Honeywell International Inc. | 2007-08-08 → 2010-06-01 | Granted | B | HIGH | CMU message-routing function with programmable routing and network-selection rules over ACARS VHF/SATCOM, Wi-Fi, WiMAX, cellular WAN and ATN, keyed on flight phase, OOOI state, position/trajectory, message priority, availability and cost; re-assigns routes as prescribed criteria change. | Rule-table selection by aircraft state; no measured-performance admission, no statistical criteria, no prediction of bearer outages. |
| 15 | **US8433817B2**<br>Routing-profile-based ACARS routing system | Thales | n/v → 2013-04-30 | Granted | B | MODERATE-HIGH | Avionic application attaches per-message media permissions and preference order (e.g. HF forbidden; VHF then SATCOM); routing profiles include emulated VHF over ATN via GACS and new media such as WiMax, WiFi, GSM, UMTS; cost ordering. | Static, application-declared preferences. |
| 16 | **US8484384B2**<br>ACARS router for remote avionic applications | Thales | n/v → 2013-07-09 | Granted | B | MODERATE | ACARS router on AFDX with dynamic application registration; routes over HF/VHF/SATCOM 'or even WiMAX or Wi-Fi subnetworks' by priority and routing-strategy indications. | Router architecture only. |
| 17 | **US11146329B1**<br>Systems and methods for multilink aircraft communication | Rockwell Collins, Inc. | 2018-06-08 → 2021-10-12 | Granted | B | HIGH | On-board supervisory controller receives dynamic performance measurements from radios (SNR in both directions per link: VHF, HF, SATCOM, ...), uses link quality, cost at current position and message classification/priority to pick the link; ground message manager fronts ACARS, ATN/OSI and IP end systems; ad-hoc air-air relay. | Instantaneous quality + cost + priority selection. No transaction-level RCP statistics, no qualification states, no evidence output. |
| 18 | **US20050286452A1**<br>Method and system for bi-directional exchange of data based on user-defined policies for the selection of a preferred datalink | Hardgrave, Steve (applicant) | 2004-05-18 → 2005-12-29 | n/v | B | LOW-MODERATE | User-defined policies select the preferred datalink for bidirectional aircraft data exchange. | Policy routing background. |
| 19 | **FR2787658A1**<br>Ground/aircraft digital exchange management with multiple communication links and cost/zone dependent routing | Sextant Avionique | 1998-12-18 → 2000-06-23 | Expired | B | LOW | Calculator automatically determines transmission routing over multiple links by cost and zone. | 1998 background. |
| 20 | **US8045977B2**<br>Method for maintaining datalink network throughput by delaying lower priority messages | Honeywell International Inc. | n/v → 2011-10-25 | Granted | B | MODERATE | CMU measures round-trip message time and channel occupancy; delays low-priority messages when congestion thresholds are exceeded. | Per-link congestion control; evidence that on-board RTT measurement in a CMU is old. |
| 21 | **US20250260475A1**<br>Systems and methods for aircraft datalink performance monitoring | Satcom Direct, LLC | 2024-02-09 → 2025-08-14 | Pending | C | HIGH | Ground/cloud real-time monitoring of CPDLC/ADS-C exchanges against PBCS benchmarks (RCP 240 / RSP 180, 95 % and 99.9 % criteria), per-step timestamps, identification of the step causing delay, NOC alerting and reconfiguration of the datalink (VHF <-> satellite). | Ground-side, after-the-fact, per-aircraft reconfiguration; not an on-board per-class admission state machine for a non-certified bearer. |
| 22 | **US10453347B2**<br>Method and systems for increasing capacity and safety of aeronautical safety-of-life services and data links | Thales Alenia Space Italia S.p.A. | 2015-10-22 → 2019-10-22 | Granted | C | MODERATE-HIGH | Distributed safety-of-life datalink system (terrestrial + satellite AMS(R)S) receives quality measurement data for a SoL service/data link used by an aircraft together with the aircraft's 4-D position/trajectory and adapts communication resources / bearer provisioning for performance-based, trajectory-based operations. | Ground-centric resource adaptation of *certified* AMS(R)S bearers using 4-D trajectory; no admission of a non-certified LEO path, no constellation handover prediction. |
| 23 | **CN120856635B**<br>ATN/IPS-oriented aviation mobility and multilink management method | Beijing Tianhua Hangtong Technology Center (LP) | 2025-09-23 → 2026-04-21 | Granted (CN) | C | MODERATE-HIGH | Airborne IPS router monitors each link (active + passive): signal strength, delay jitter, packet loss, throughput; marks unavailable links; computes a link state value vs calibration reference / history / environmental factor; normalises, entropy-weights and ranks links; builds an airborne routing table (IP range, link instance ID, traffic classifier, status, priority) and signals it to the ground agent in AGMI messages. | Generic metric scoring and IPS mobility signalling; no PBCS statistical thresholds per class/airspace, no shadow dual-cast, no LEO ephemeris prediction. CN only. |
| 24 | **CN118200224A**<br>Method for selecting aviation data transmission links based on VIKOR decision | Beihang University | 2024-04-26 → 2024-06-14 | Pending (CN) | C | MODERATE | Multi-attribute (VIKOR) utility matrix over heterogeneous air-ground links to select a link. | Decision-theory scoring; no safety admission concept. |
| 25 | **CN121483092A**<br>ATN B2 application system and method for broadband communication in civil aviation | Beihang University | 2025-11-10 → 2026-02-06 | Pending (CN) | C | MODERATE | ATN B2 (CM/CPDLC/ADS-C) applications carried over a civil-aviation broadband link with CM login via onboard terminal and user management. | Shows the trend 'B2 over broadband' is being filed in CN; no admission/fallback logic visible in the snippet. |
| 26 | **CN120050214A**<br>LISP protocol-based ATN ground-air data link switching delay test method | CAAC Second Research Institute | 2024-09-04 → 2025-05-27 | Pending (CN) | C | LOW-MODERATE | Test bench measuring link-switching delay for LISP-based ATN/IPS air-ground mobility. | Test method only. |
| 27 | **EP4572182A1**<br>Aircraft datalink based on a terrestrial to LEO satellite cellular transceiver and associated spectrum | Rockwell Collins, Inc. | 2023-12-15 → 2025-06-18 | Pending | D | MODERATE | Radio + phased-array antenna inside the nose radome establishes a LEO link in L-band / 3GPP bands (direct-to-cell style) and an air-to-ground link; radio selects between them by connectivity; links may carry ACARS messages; router coupled via wireless bridge. | Hardware / installation patent; selection is binary connectivity. Confirms LEO-for-ACARS is in the record. |
| 28 | **US9356686B1**<br>Polar satcom system and related method | Rockwell Collins, Inc. | 2013-12-20 → 2016-05-31 | Granted | D | LOW-MODERATE | GEO satcom extended to polar regions via a relay satellite in LEO/MEO/HEO. | Space-segment topology. |
| 29 | **CN114337793A**<br>Airborne data link communication system and method supporting multi-protocol stack and cross-domain communication | CETC Avionics Co., Ltd. | 2022-01-28 → 2022-04-12 | n/v (CN) | D | MODERATE | Airborne datalink system combining ACARS and ATN/OSI stacks with cross-domain communication. | Architecture; no LEO or admission logic visible. |
| 30 | **CN114500370A**<br>Airborne ATN/IPS router supporting 4D tracking | CETC Avionics Co., Ltd. | 2022-01-25 → 2022-05-13 | n/v (CN) | D | LOW-MODERATE | Airborne ATN/IPS router architecture for 4-D trajectory operations. | Architecture only. |
| 31 | **US11509675B2**<br>Systems and methods for cyber monitoring and alerting for connected aircraft | Honeywell International Inc. | 2020-09-25 → 2022-11-22 | Granted | D | LOW | Connected-aircraft cyber monitoring; mentions ATN/IPS routers with QoS as communication gateways. | Context only (security monitoring of IPS gateways). |
| 32 | **NPL-1**<br>Future Connectivity for Aviation - EU/US Task Force White Paper (EASA/FAA with Airbus/Boeing) | EASA / FAA | 2022-11 → 2022-11-09 | Published | N | CRITICAL (concept) | Defines 'Hyperconnected ATM': offload AOC from safety links to non-safety links (cabin SATCOM, A2G), names LEO/MEO constellations as the cost-effective, future-proof option, requires 'appropriate security protections' and 'adequate link status and performance monitoring', and calls for performance-based standards for Hyperconnected ATM; lists the IPS roadmap, B2/EPP milestones (2027) and Boeing ecoDemonstrator IPS CMU trials. | Destroys novelty of the *concept* (broadband for ATM traffic). It does not describe any admission mechanism - it asks for one to be standardised. |
| 33 | **NPL-2**<br>EASA webinar 'Future Connectivity for Aviation' - Hyperconnected ATM overview | EASA | 2023-02-01 → 2023-02-01 | Published | N | HIGH (concept) | Roadmap slides: communications not subject to RCP offloaded from safety links; 'Ground SATCOM Performance Class B'; transparent integration of multiple datalinks; ACARS-over-IP standardisation. | Concept only. |
| 34 | **NPL-3**<br>ICAO Doc 9896 - Manual on the ATN using IPS Standards and Protocols (3rd ed.) | ICAO | n/a → 2022 (ed.3) | Published | N | HIGH (substrate) | IPv6-based ATN/IPS with mobility, multilink operation, DTLS security, naming/addressing; link state signalled for multilink. Defines the very notion of an IPS 'access network' / subnetwork. | Our LEO adapter is an instance of an IPS access network; novelty must come from the admission/scheduling logic, not from carrying IPS over IP. |
| 35 | **NPL-4**<br>ICAO Doc 9869 PBCS Manual / RTCA DO-350A - EUROCAE ED-228A (PBCS SPR) | ICAO / RTCA / EUROCAE | n/a → 2017 / 2016 | Published | N | HIGH (thresholds) | RCP 240: ET 240 s (99.9 %), nominal TT 210 s (95 %); technical allocation ACTP <= 120 s @95 % and <= 150 s @99.9 %; RSP 180: ASP <= 90 s @95 %, <= 180 s @99.9 %; availability and continuity parameters; monitoring and alerting criteria. | The thresholds are public standards and not protectable; using them as *admission gates for a non-certified bearer, measured on board* is the claimable step. |
| 36 | **NPL-5**<br>ARINC 858 Part 1 (2024), Part 2 IPS Gateway (2024), Part 3 Common IPS Radio Interface Protocol (2023) | AEEC / SAE ITC | n/a → 2023-2024 | Published | N | HIGH (substrate) | Avionics requirements for IPS for aeronautical safety services, ACARS/IPS gateway interoperability and a common radio-to-IPS-router interface (link status, QoS). | Defines how a radio presents itself to an IPS router; a LEO terminal presenting through this interface is an obvious step - again, claim the admission logic. |
| 37 | **NPL-6**<br>ARINC 771 (LEO aviation satcom), ARINC 781 (L-band), ARINC 791/792 (Ku/Ka cabin satcom) | AEEC | n/a → various | Published | N | MODERATE | Installation / interface standards for LEO (Iridium) cockpit satcom and for Ku/Ka cabin terminals (Ethernet ports, power, antenna). | Shows LEO *cockpit* satcom (Iridium Certus) is already a certified safety bearer and that cabin terminals expose IP ports. |
| 38 | **NPL-7**<br>RFC 9372 - L-band Digital Aeronautical Communications System (LDACS) | IETF | n/a → 2023-03 | Published | N | MODERATE | Describes the Future Communications Infrastructure multilink concept: 'depending on link quality, communication can be switched seamlessly from one data link technology to another'; link state (up/down) reported via the ATN/IPS Aircraft Protocol (AIAP) mandated by ICAO WG-I for multilink; appendix summarises DO-350A RCP/RSP parameters. | Concept-level multilink; no non-certified bearer admission. |
| 39 | **NPL-8**<br>IETF draft-templin-atn-aero-interface (AERO/OMNI) and NASA NTRS 20190001799 'ICAO ATN/IPS' briefing | Boeing / NASA | n/a → 2019 | Published | N | MODERATE | IPv6 'aero' interface over multiple ANET data links with dynamic link selection, multilink, QoS signalling, mobility and route optimisation for ATN/IPS. | Protocol machinery for multilink IPS; no RCP admission. |
| 40 | **NPL-9**<br>Airbus FAST article 'Cockpit SATCOM - Light Cockpit Satcom (LCS)' | Airbus | n/a → 2022-04 | Published | N | MODERATE | Physical/logical segregation of ACD, AISD, PIESD; PKI mutual authentication and VPN tunnel to the ground gateway; cockpit satcom with 'cabin capability' as backup for cabin satcom (the inverse direction of our idea); IP-based cockpit connectivity ~200 kbps on SB-S 2.0. | Shows industry's current direction is cockpit-grade GEO L-band, with segregation; our idea reverses the direction with an admission gate. |
| 41 | **NPL-10**<br>Aviation Week 'Multi-Orbit Inflight Connectivity Gains Momentum' (Panasonic/OneWeb, Hughes Fusion, Stellar Blu ESA) | Aviation Week | n/a → 2025-04-08 | Published | N | MODERATE (obviousness) | In-flight switching between LEO and GEO networks by location and network conditions; LEO polar coverage; forward 193 Mbps / return 36 Mbps in flight test. | Cabin multi-orbit switching is product reality; claiming 'switch LEO<->GEO on quality' alone is obvious. |
| 42 | **NPL-11**<br>FAA PARC CWG recommendations on FANS-1/A over SwiftBroadband (letter to AVS, 2018-07-03) | FAA PARC | n/a → 2018-07-03 | Published | N | MODERATE (regulatory precedent) | Regional PBCS monitoring tables (ACP/ACTP 95 % and 99.9 % benchmarks, ASP for RSP 180) used to recommend operational approval of a new IP-based satcom bearer for FANS. | Precedent that admission of a new bearer is decided on monitored PBCS statistics - our idea automates this per flight, per class, on board. |
| 43 | **NPL-12**<br>Aerospace Tech Review 'CPDLC Coming of Age' - Iris ATN/IPS flight trials; European multilink switch (LDACS, satcom, AeroMACS) | Trade press | n/a → 2022-04-24 | Published | N | LOW-MODERATE | Boeing/Inmarsat Iris trials of ATN/IPS; European future datalink to include a multilink switch; crew data traffic impacting ATN-B2 exchanges. | Context. |
| 44 | **NPL-13**<br>Iridium 'Satellite Communications & Commercial Aviation' (FANS over Iridium, ATS Safety Voice, Certus) | Iridium | n/a → 2025-12-16 (page) | Published | N | LOW-MODERATE | LEO L-band (Iridium) already carries FANS CPDLC/ADS-C and ATS voice under ICAO rules with priority/pre-emption. | Clarifies that 'LEO' per se is not new to safety services - what is new is *broadband Ku/Ka LEO without AMS(R)S status* earning admission. |

Cluster key: **A** = Safety / ATS traffic over non-safety or broadband IP links (closest art); **B** = CMU / router multi-subnetwork selection, preference tiers, policy routing; **C** = RCP/RSP performance measurement and performance-triggered link (re)configuration; IPS multilink scoring; **D** = LEO / satellite architectures and terminals for aviation; **N** = Non-patent literature (standards, regulator papers, trade press)
