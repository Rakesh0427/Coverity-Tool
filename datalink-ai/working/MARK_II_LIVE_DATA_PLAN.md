# Getting Live Data from the Honeywell CMU Mark II+ and Finding the Actual Issues in the Flow

**Prepared:** 2026-10-10 · **Companion to:** `Datalink_AI_Live_Architecture.docx` (Rev 3) §2–§4 · **Product under observation:** Honeywell **CMU Mark II+** Communications Management Unit.

> This answers "how do we get live data from the Mark II+ product and compare it against requirements and code to find the real issues in the flow". It maps directly onto the architecture's data sources S1–S9, the transaction-record data contract, and the §4.1 pattern library.

---

## 1. What the box actually is (so the data plan fits it)

The Honeywell **CMU Mark II+** is the avionics **data router** at the centre of the aircraft datalink system. Verified product facts:

| Fact | Detail | Why it matters to us |
|---|---|---|
| Lineage | CMU Mark II in service since **1994**, upgraded to **Mark II+ in 2011**; **7,000+ aircraft** equipped; "most popular datalink units in the market" [1](https://www.honeywellaerospace.com/content/dam/aerobt/en/documents/learn/products/navigation-and-radios/brochures/N61-2375-000-000_ES_CMU_Mark_II-bro.pdf) [3](https://www.honeywellaerospace.com/us/en/insights/articles/honeywell-radios-keep-airline-pilots-connected) | Huge fleet = the statistical base your pattern engine needs; fleet-wide patterns are the OEM selling point (docx §8.3) |
| Protocols | FANS 1/A+ CPDLC, **ATN PM-CPDLC** (Eurocontrol White List, "best in class" PM-CPDLC in Europe), ACARS over POA, **VDL Mode 2 Multi-Frequency** (AOA), optional satcom (SDCS) [1](https://www.honeywellaerospace.com/content/dam/aerobt/en/documents/learn/products/navigation-and-radios/brochures/N61-2375-000-000_ES_CMU_Mark_II-bro.pdf) [2](https://www.honeywellaerospace.com/us/en/products-and-services/products/cabin-and-cockpit/satellite-communications/cockpit-satcom/mark-ii-communications-management-unit) [4](https://www.honeywellaerospace.com/content/dam/aerobt/en/documents/landing-pages/read-more/FANS-1A-PM-CPDLC-Upgrade-for-Business-Aircraft-Mk-II-Plus.pdf) | These are exactly the CPDLC/ADS-C/ACARS transactions the verdict engine scores against RCP 240 / RSP 180 |
| Software | **Partitioned software architecture; each partition software-loadable on-wing** (data loader or PCMCIA) [1](https://www.honeywellaerospace.com/content/dam/aerobt/en/documents/learn/products/navigation-and-radios/brochures/N61-2375-000-000_ES_CMU_Mark_II-bro.pdf) [5](https://www.eirtechaviation.ie/files/8815/3795/6992/Honeywell_Mark_II_Communications_Management_Unit_Brochure.pdf) · DO-178B DAL C [2](https://www.honeywellaerospace.com/us/en/products-and-services/products/cabin-and-cockpit/satellite-communications/cockpit-satcom/mark-ii-communications-management-unit) | This IS the E4 host-platform hook: partitions and load mix are observable, comparable, and versionable. Confirm with Honeywell the exact partitioning scheme and what timing/health data each partition exposes |
| Configurability | **AOC database is user-reconfigurable** via the PC-based **ACARS Reconfiguration Tool (ART)**; hundreds of AOC functions (report formats, triggers, MCDU interfaces, message encryption, conditional logic) [1](https://www.honeywellaerospace.com/content/dam/aerobt/en/documents/learn/products/navigation-and-radios/brochures/N61-2375-000-000_ES_CMU_Mark_II-bro.pdf) [5](https://www.eirtechaviation.ie/files/8815/3795/6992/Honeywell_Mark_II_Communications_Management_Unit_Brochure.pdf) | The AOC database is **programmable airline logic inside the certified box** — a first-class source of "actual issues in the flow" and a changeable configuration, not software (docx §2 S3) |
| Routing behaviour | Air/ground links assignable per **global region**; non-critical messages can be **queued until a low-cost link is available**; patented ACARS compression cuts non-safety messages up to **40%** [1](https://www.honeywellaerospace.com/content/dam/aerobt/en/documents/learn/products/navigation-and-radios/brochures/N61-2375-000-000_ES_CMU_Mark_II-bro.pdf) | Queueing and compression are **platform-side delay contributors** your delay-budget allocation must separate from network delay |
| PBCS | Supports **A056 LOA/OpsSpec PBCS** demonstration incl. a **Latency Timer** function [4](https://www.honeywellaerospace.com/content/dam/aerobt/en/documents/landing-pages/read-more/FANS-1A-PM-CPDLC-Upgrade-for-Business-Aircraft-Mk-II-Plus.pdf) | The box already measures something RCP-shaped on board — cross-check your ground-computed values against it |
| Ground tools | **AirSim** PC datalink simulator (CMU Mark II+ + ATSU) for crew training and **database verification before fleet deployment** [5](https://www.eirtechaviation.ie/files/8815/3795/6992/Honeywell_Mark_II_Communications_Management_Unit_Brochure.pdf); **ART** reconfiguration tool [2 of product page resources](https://aerospace.honeywell.com/en/products/navigation-and-sensors/mark-ii-communications-management-unit); **Honeywell Datalink Services** build/test custom AOC databases [1](https://www.honeywellaerospace.com/content/dam/aerobt/en/documents/learn/products/navigation-and-radios/brochures/N61-2375-000-000_ES_CMU_Mark_II-bro.pdf) | **Your zero-aircraft-access test bed and the OEM engagement door.** AirSim + ART lets you develop the monitors before any live feed exists |
| Recording | Datalink recording (DLR) mandate support to HFR5 / Lightweight CVR [4](https://www.honeywellaerospace.com/content/dam/aerobt/en/documents/landing-pages/read-more/FANS-1A-PM-CPDLC-Upgrade-for-Business-Aircraft-Mk-II-Plus.pdf) | On-board message-set records retrievable post-flight through the airline's readout process — evidence when ground feeds missed the event |
| Wiring variants | ARINC 724B PN 965-0758-005 / ARINC 758 PN 965-0758-006; APM (Aircraft Personality Module) PN 964-0465-001 [2](https://www.honeywellaerospace.com/us/en/products-and-services/products/cabin-and-cockpit/satellite-communications/cockpit-satcom/mark-ii-communications-management-unit) [5](https://www.eirtechaviation.ie/files/8815/3795/6992/Honeywell_Mark_II_Communications_Management_Unit_Brochure.pdf) | The **APM is the aircraft's personality/config identity** — part of the certified-baseline comparison (S9) |
| Ecosystem | FMS provides pilot interface (CDU); FANS enabled from FMS 6.1.1/6.2.1; companion VDR TR-866B, satcom MCS-7120 / Aspire SSU 300, GoDirect datalink services network [4](https://www.honeywellaerospace.com/content/dam/aerobt/en/documents/landing-pages/read-more/FANS-1A-PM-CPDLC-Upgrade-for-Business-Aircraft-Mk-II-Plus.pdf) | CPDLC path is FMS → CMU → VDR/satcom → CSP ground. Every hop is a leg in the delay budget. GoDirect may already be the airline's CSP |

---

## 2. The flow you want to observe (and where each timestamp lives)

One CPDLC uplink exchange, end to end, with the observability points:

```
FMS/CDU (crew or uplink display)                 [A] pilot-visible event (PORT leg)
   │
CMU Mark II+ accept → AOC/ATS logic → queue      [B] platform queue time, partition activity, routing-preference decision
   │                                              (compression applied here for non-safety msgs)
VDR TR-866B (VDL2 POA/AOA) or Satcom (SDCS)      [C] radio TX; MF frequency selection
   │
CSP ground (SITA / ARINC / Viasat / GoDirect)    [D] ground receipt, network forward
   │
ANSP / ATC host + response                       [E] response window (RCP 240 clock semantics)
   │
back down the same chain to the crew             [F] response delivery; end event
```

- **RCP 240** concerns the technical transaction (aviation system response) [4](https://www.honeywellaerospace.com/content/dam/aerobt/en/documents/landing-pages/read-more/FANS-1A-PM-CPDLC-Upgrade-for-Business-Aircraft-Mk-II-Plus.pdf); **PORT** is the crew response leg. The docx already splits ACTP/PORT; the Mark II+ story adds **[B] the platform leg** — queueing, routing preferences, compression — which is invisible to network-only monitors (this is the E4 attribution gap and your patent hook).
- The unit of work is the architecture's **transaction record** (docx §3.2 `norm.transactions`): per-leg timestamps + source + clock-offset uncertainty + tail + software-load identity.

---

## 3. Where the live data comes from — ranked by how soon you can have it

| # | Channel | What you get | How to get it | Start |
|---|---|---|---|---|
| **A** | **Own VDL2/ACARS receivers** (architecture S8) | Live over-the-air ACARS/VDL2 traffic: message text, timestamps as heard, station IDs, RF features (noise floor, signal quality, retransmissions) | SDR + VHF air-band antenna running open decoders (e.g. dumpvdl2 for VDL Mode 2 / ACARS decode; ACARSdeco2). Position via ADS-B on the same receiver | **Days.** No contract needed. Check local spectrum law (118–137 MHz air band receive rules vary by country) |
| **B** | **CSP messaging feed** (S1) | The same transactions as the network sees them: ground receipt timestamps, per-hop data if the CSP exposes it, delivery/ack outcomes | Subscribe with the airline to SITA, ARINC/Collins, Viasat or Iridium messaging feeds (MQTT/AMQP/REST/drop); **if the airline already uses Honeywell GoDirect datalink services** [4](https://www.honeywellaerospace.com/content/dam/aerobt/en/documents/landing-pages/read-more/FANS-1A-PM-CPDLC-Upgrade-for-Business-Aircraft-Mk-II-Plus.pdf), that relationship is the shortest path. Start with a sandbox or replay sample | **2–8 weeks** (data-use rights, tenancy, retention — negotiate per docx §2 notes) |
| **C** | **Airline AOC gateway** (S1/S9) | Everything the CMU sends to ops: OOOI, position reports, custom AOC messages, tail/flight identity | The airline's existing AOC gateway integration; you are a consumer of an existing feed | **2–6 weeks** (one airline relationship) |
| **D** | **AOC database-defined monitoring reports** (the Mark II+ version of S3 ACMS) | **In-flight platform evidence**: CMU status, queue depths, link-state transitions, error counters, routing decisions — downlinked on your own triggers over ACARS | With airline engineering, define report parameter sets **in the AOC database via ART** (it is a changeable configuration, not software load); **verify in AirSim before deployment** [5](https://www.eirtechaviation.ie/files/8815/3795/6992/Honeywell_Mark_II_Communications_Management_Unit_Brochure.pdf); deploy as a PCMCIA/data-loader database update per fleet policy | **4–12 weeks** (airline engineering approval + flight-ops sign-off) |
| **E** | **AirSim + ART ground test bed** (your own lab) | Simulated CMU Mark II+ / ATSU behaviour: full message flows for scenario replay, AOC database verification | Buy/obtain AirSim through Honeywell Datalink Services [2 of product resources](https://aerospace.honeywell.com/en/products/navigation-and-sensors/mark-ii-communications-management-unit) [5](https://www.eirtechaviation.ie/files/8815/3795/6992/Honeywell_Mark_II_Communications_Management_Unit_Brochure.pdf) | **Weeks.** Use it to build and validate the verdict engine against synthetic-but-realistic transactions before live data lands |
| **F** | **QAR/FDR offload + datalink recording (DLR)** (S4) | High-rate parameters per flight; the DLR message sets recorded to the CVR per mandate [4](https://www.honeywellaerospace.com/content/dam/aerobt/en/documents/landing-pages/read-more/FANS-1A-PM-CPDLC-Upgrade-for-Business-Aircraft-Mk-II-Plus.pdf) | Airline flight-data-monitoring programme (governed: programme approval, crew de-identification, access logging); gate offload or existing airline offload — reuse, don't duplicate | **4–12 weeks** (FDM governance) |
| **G** | **AID / CMS read-only** (S5) | Near-live avionics bus data | OEM or STC holder partnership; or the airline's existing AID installation. Long lead — never make the MVP depend on it (docx §2) | **Months** |
| **H** | **OEM track: Honeywell Datalink Services + engineering** (S6) | Partition health events, deeper CMU diagnostics, ICD/CMM documentation, the partitioning scheme and what each partition logs | Partnership pitch — the docx §8.3 benefit is exactly theirs: *"in-service issues identified before the customer reports them"*. Start the conversation with this plan and a demo on their own AirSim | **Strategic, months** |

**Commercial sequence (from docx §2, now Mark II+-specific):** A + E immediately (zero rights issues) → B + C (one CSP + one airline) → D (airline engineering; the AOC database is the practical in-flight route to platform evidence) → F → G/H strategic. **S9 config data is mandatory from day one:** tail, APM part number, partition software part numbers, AOC database version, routing-preference set, modem, subscription, route — without it the requirement monitors instantiate against the wrong baseline.

---

## 4. Compare against REQUIREMENTS

**4.1 Build the requirement table (one row per requirement ID):**

| Requirement source | Requirements it gives you | Acceptance criterion examples |
|---|---|---|
| ICAO Doc 9869 / PBCS (A056 LOA/OpsSpec world [4](https://www.honeywellaerospace.com/content/dam/aerobt/en/documents/landing-pages/read-more/FANS-1A-PM-CPDLC-Upgrade-for-Business-Aircraft-Mk-II-Plus.pdf)) | **RCP 240** (CPDLC), **RSP 180** (ADS-C), operational continuity/availability criteria | 95th-percentile technical transaction time ≤ 240 s; availability 99.9% continuity tests |
| EU IR 29/2009 + "best in class" PM-CPDLC performance [1](https://www.honeywellaerospace.com/content/dam/aerobt/en/documents/learn/products/navigation-and-radios/brochures/N61-2375-000-000_ES_CMU_Mark_II-bro.pdf) | ATN PM-CPDLC ground/air performance expectations in European airspace | Per the implementing rule's technical annexes |
| RTCA DO-258A (FANS 1/A+) and ARINC 618/620/623, ARINC 724B/758 | Protocol-level requirements: message transfer, ack/NAK/abort behaviour, DCDU interaction, interface timing | Response windows, retry/abort limits, formatting rules |
| Product requirements (Honeywell-side): DO-178B DAL C objectives for the CMU partitions [2](https://www.honeywellaerospace.com/us/en/products-and-services/products/cabin-and-cockpit/satellite-communications/cockpit-satcom/mark-ii-communications-management-unit) | Timing budgets the code promised: partition windows, queue service times, compression rules (non-safety only [1](https://www.honeywellaerospace.com/content/dam/aerobt/en/documents/learn/products/navigation-and-radios/brochures/N61-2375-000-000_ES_CMU_Mark_II-bro.pdf)) | Design-timing budgets vs observed |
| Airline ops requirements | AOC report triggers, response-time expectations for AOC messaging, routing preferences per region [1](https://www.honeywellaerospace.com/content/dam/aerobt/en/documents/learn/products/navigation-and-radios/brochures/N61-2375-000-000_ES_CMU_Mark_II-bro.pdf) | Per the airline's own AOC spec |

**4.2 Per transaction:** map to requirement IDs → allocate the delay budget to legs [A]–[F] → compute **margin** vs the acceptance criterion → verdict (conforming / non-conforming / not-exercised) → evidence pointer. Cross-check RCP-shaped values against the Mark II+ **PBCS Latency Timer** output where the airline exposes it.

**4.3 Then run the §4.1 pattern library** exactly as the docx defines it: recurring requirement failure per tail; co-occurrence (frequent-itemset over verdict vectors); route/airspace clustering; time-of-day periodicity; **margin decay** (CUSUM change-point on the margin series → projected violation date while still conforming); link flapping (subnetwork transitions/hour); message-loss bursts; crew-response clustering; **configuration drift** (config snapshot vs certified baseline per requirement); **coverage erosion** (not-exercised set per route and software load).

---

## 5. Compare against CODE

The Mark II+ source is Honeywell's DO-178B DAL C asset — you compare at three levels depending on who you are:

**Level 1 — Configuration vs certified baseline (anyone; do this first).**
The product's behaviour is heavily configuration-defined: APM identity, **partition software load mix** (each partition loadable on-wing [1](https://www.honeywellaerospace.com/content/dam/aerobt/en/documents/learn/products/navigation-and-radios/brochures/N61-2375-000-000_ES_CMU_Mark_II-bro.pdf)), AOC database version and content, region routing preferences, compression settings. Compare the live snapshot per tail against the certified/designed baseline per requirement. Misfires found here are real and frequent in practice: an AOC trigger that fires on the wrong condition, a routing preference that queues non-critical traffic until a low-cost link (and then a latency spike on a "slow" route), a partition mix inconsistent across the fleet after partial load campaigns. **Many "network problems" in a Mark II+ fleet are AOC database or routing-preference problems.**

**Level 2 — Behavioural comparison against the code's declared timing (ground platform + live data).**
Without source access, infer code-path behaviour from timing signatures: queue residence time vs message class (compression applies to non-safety only [1](https://www.honeywellaerospace.com/content/dam/aerobt/en/documents/learn/products/navigation-and-radios/brochures/N61-2375-000-000_ES_CMU_Mark_II-bro.pdf) — a safety message delayed behind compressed traffic is a platform finding); response-timer expiry → abort/NAK sequence vs the ARINC/DO-258A-defined behaviour; VDL2-MF frequency-change events vs link-flapping bursts; PORT vs ACTP decomposition (docx §4) plus the platform leg [B]. Attribute per transaction: ground-network leg / air-ground link leg / **host-platform condition** / human — the three-way attribution of `DRAFT_CLAIM_SET.md` Claim 1.

**Level 3 — Requirement → partition → code traceability (OEM-side; the Honeywell partnership).**
With the DO-178B artifacts (requirements spec, design description, traceability matrix, partition schedule), map each requirement ID to its implementing partition and code path, then check the runtime evidence hits the expected path at the expected time. **Partition scheduling statistics** (window overruns, deadline misses) overlapping the transaction in-flight time are the E4 evidence the claim set names. When Honeywell loads new partition software, **re-run deterministic replay** on recorded transactions and diff verdicts (regression); when late QAR/AOC data arrives after a verdict, issue a **late-data verdict revision** with both versions in the ledger (docx §10 conformance record).

> Note: the brochure says "partitioned software architecture" and does not state ARINC 653 by name [1](https://www.honeywellaerospace.com/content/dam/aerobt/en/documents/learn/products/navigation-and-radios/brochures/N61-2375-000-000_ES_CMU_Mark_II-bro.pdf). The claim set's "ARINC-653-style partition timing" limitation should be kept generic in claims and confirmed against the actual CMU design in the OEM conversation.

---

## 6. Actual issues in the flow — what this setup finds

| Issue class | Signature in the data | Attribution | Example action |
|---|---|---|---|
| CMU queueing under routing preferences | Delay concentrated in leg [B]; message class non-critical; region = low-cost-link preference active; compression on | **Platform/config** | Change routing preference or AOC rule; not a CSP ticket |
| AOC database logic error | Trigger fires outside intended condition; wrong report format; bursts of redundant reports eating bandwidth | **Platform/config** | ART database fix; verify in AirSim; redeploy database |
| Fleet load-mix drift | Recurring requirement failure on one tail; config snapshot differs from baseline partition set | **Platform/config** | Reload partitions to standard; re-run replay |
| VDL2-MF / handover instability | Subnetwork transitions/hour high; loss bursts at frequency changes; route/airspace clustered | **Link** | Radio/maintenance; network escalation with evidence |
| CSP/ground-station congestion | Delay in legs [D]–[E]; co-occurs with time-of-day periodicity; fleet-wide on a region | **Network** | CSP escalation with per-step timestamps (evidence, not anecdote) |
| Host-platform resource starvation (OEM track) | Partition overrun window overlaps transaction in-flight time; stack error counters rising; CPU/memory pressure in comms partition | **Platform (code)** | OEM bug report with replayable record |
| Crew-response limits | PORT distribution clustering near the limit on specific message types/phase | **Human factors** | Display/training/procedure review |
| PBCS erosion | RCP 240 95th percentile drifting on route R / load L; requirement not exercised on other route/load combinations | **Conformance** | Test-case selection; coverage account report; ops approval risk flag |
| Silent non-conformance after load change | Verdict diff after partition reload replay (regression) | **Platform** | Hold the load; open issue with hash-chained evidence |

Every finding is written as the docx's **conformance record**: content hash over inputs, verdict + margin + requirement ID, attribution, append-only ledger, deterministic replay recipe — which is also the patent's enablement worked example (assessment §7).

---

## 7. Worked mini-example (one uplink, one issue)

1. CPDLC uplink on tail VT-XXX, route BOM–LHR, load L-2026.09: end-to-end technical time 310 s vs RCP 240 → non-conforming, margin −70 s.
2. Delay budget: [A] crew display 8 s · **[B] CMU queue 180 s** · [C] radio 4 s · [D] ground 70 s · [E] response window 48 s.
3. Pattern engine: leg-[B] excess co-occurs with AOC DB version 12.4 routing preference "queue non-critical until low-cost link" active over Central Asia; 23 similar transactions this month on 3 tails with DB 12.4, none on tails with DB 12.3.
4. Attribution: **platform/config**, not network — confidence rises with sample count and falls with clock-offset uncertainty; record hashed and replayable; CSP escalation is *not* opened.
5. Action: AOC database change via ART (verified in AirSim) → fleet DB 12.5; replay the month: verdicts flip to conforming; margin-decay alarm for the RCP 240 95th percentile on that route cleared; coverage account shows RCP 240 unexercised on the new polar route — flagged for test-case selection.

That single example is simultaneously: the demo, the airline/OEM pitch, and the patent spec's "worked example with numbers".

---

## 8. Rights, safety and legal constraints

- **Read-only, non-interfering** is architectural law (docx §2 S4–S5): never write to the aircraft through any channel in the diagnostic platform. AOC database changes are an **airline maintenance action** under their own approval, not a platform command.
- **Data rights:** CSP feeds need use/retention/tenancy terms; FDM data is heavily governed (programme approval, crew de-identification, access logging) — see `Datalink_AI_Live_Architecture.docx` §2.
- **Own receivers:** legal for air-band monitoring in many jurisdictions, restricted in others — confirm local spectrum law before deploying SDRs; RF observation feeds the threat-model work, so handle as export-control-relevant data (docx §6 risk table).
- **OEM relationship:** ICD/CMM/partition documentation and S6 health events are partnership assets — start with the AirSim-based demo and the §8.3 value case rather than a data request.
- **Crew privacy:** PORT analytics must be aggregated/de-identified (docx §2 S4 notes apply to any human-factor measure).

---

## 9. 30/60/90-day sequence

| Window | Do | Outcome |
|---|---|---|
| **Days 0–30** | Stand up SDR receivers (A) + AirSim/ART lab (E); freeze the transaction-record and requirement-table schemas (docx §3.2 data contracts); open the airline conversation for the AOC gateway feed (C) and the CSP feed (B); open the Honeywell Datalink Services conversation (H) | Replayable synthetic corpus + live RF visibility + contracts in motion |
| **Days 31–60** | Ingest B + C into the adapter/bus pipeline (docx §3.1 topics); instantiate requirement monitors per tail with S9 config keys; run the pattern library on real traffic; define the D-channel AOC monitoring reports with airline engineering and verify in AirSim | First real verdicts and findings; the mini-example of §7 becomes real |
| **Days 61–90** | Deploy AOC database reports on a small tail set (D); integrate QAR/DLR (F); first deterministic-replay audit and coverage-account export; first month of worked numbers (margin decay, gate rejects if the ML layer is on, N records / M objectives) | MVP on the Mark II+ fleet; the numbers that make both the product and the patent provisional concrete |

**Tie-back to the patent work (`PATENT_STRENGTH_ASSESSMENT.md` §8.3–8.4):** this plan *is* the enablement path — the 90-day worked numbers are what the provisional's spec needs, and the Level-1/2/3 comparisons are the Family 1 claim read in product terms. Any public demo of these results should follow the provisional, not precede it.
