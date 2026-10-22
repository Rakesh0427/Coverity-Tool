# DATALINK — PITCH PACK
### Problem · Why we are different · Solution · Who benefits · How to say it

*One page to read before the meeting. Everything below is checkable — sources at the bottom.*

---

## 1 · THE PROBLEM — one sentence

> **Airlines are legally required to prove that every datalink clearance completes inside 240 seconds, and today nobody can prove it for a single flight — so the first sign of a problem is a pilot complaint, weeks later, aimed at the wrong system.**

### The four layers behind that sentence

**Layer 1 — the requirement is real, per-transaction, and hard.**
PBCS requires CPDLC to meet RCP 240 (95% within 240 s, 99.9% within the expiry time) and ADS-C to meet RSP 180. Reduced oceanic separation — 30 NM lateral, 23 NM lateral / 5 min longitudinal — is granted only if those numbers hold. If performance slips, separation is withdrawn and the fleet is pushed back to procedural separation. [1][2]

**Layer 2 — the measurement is retrospective, aggregate, and manual.**
FAA publishes monitoring as a **monthly spreadsheet per oceanic region**. ICAO's own PBCS manual, as SESAR summarises it, describes "only post-implementation monitoring programmes," in contrast to PBN, which "includes real time monitoring and alerting functionality in the aircraft capability." The industry itself has written down the gap: **PBCS has no real-time layer.** [3][4]

**Layer 3 — the sensor is the complaint.**
FAA's FIT/20 states it plainly: fleet performance below the RCP240/RSP180 95% criteria "will usually be accompanied by **controller complaints** of unacceptable performance by that fleet." Complaints are not a signal — they *are* the monitoring system, and they arrive after the damage. FIT/24 counted **6,205 airframes from 85 states** being monitored this way — monthly. [5][6]

**Layer 4 — when a cause is finally found, the fix takes months and lands on the wrong party.**
FIT recorded **98 problem reports in one year, 69 from a single region**; a B777 issue that blocked timely VHF→SATCOM transition was only fixed when the OEM shipped a new AIMS software block point. In Europe, avionics with a high failure rate get filtered off ANSP logon lists. Meanwhile NFF removals run **20–50%** of avionics removals — working boxes pulled because nobody could prove where the delay came from. [7][8][9]

### The cost of the gap

| Leak | Number |
|---|---|
| Maintenance per aircraft per year (IATA FY2024 benchmarking) | **USD 5.05 M**; avionics up to 30% of it |
| Avionics removals that are NFF | **20–50%** |
| Cost of one AOG hour | **USD 10 k – 150 k**, ~14 events per aircraft per year |
| Cost of disruption, industry-wide | **~USD 60 B/year** |
| How many of our 128 tracked requirements have per-flight evidence today | **0** |

### And the thing nobody says out loud
The aircraft's own computer is invisible. When a clearance takes 310 seconds, the CSP says "we delivered in 40," the radio says "I transmitted," and the CMU says nothing. So the network gets blamed, a serviceable radio gets swapped, and the real cause — a queuing delay inside the aircraft — keeps happening on 200 tails.

---

## 2 · WHY WE ARE DIFFERENT — the patents, read

We read the field before writing a claim. Five lanes already exist, and all five are busy. **None of them overlaps ours.**

| Lane | Who owns it | What they actually claim | Why it doesn't solve the problem |
|---|---|---|---|
| **Predicting the link** — outage, handover, channel state, availability | Panasonic **US 11,546,875** / **US 11,455,839**; Qualcomm **US 12,652,602**; Viasat **US 11,115,114**; Hughes **US 11,032,751**; Satcom Direct **US 10,939,304** + **US 11,398,158** | Forecast outage probability along the route, predict channel state, schedule handovers, forecast coverage holes from flight path × coverage maps | Predicts **the pipe**, not the requirement. A perfectly available link can still miss RCP 240 because of what happens inside the aircraft. 28 granted patents here — that's a moat, not a threat: it proves demand and leaves our lane empty |
| **Predicting the box's health** (predictive maintenance / RUL) | Rockwell **US 11,465,779**; Honeywell **US 9,550,583**; Boeing **US 10,457,423**, **US 2019/0100335**; Airbus **EP 3 106 952** | ML health scores, RUL, predicted maintenance messages, adaptive time-between-overhaul | Predicts a **hardware failure event**. Our problem is not a failure — it is *latency and functional conformance* across four parties, on a box that is working fine |
| **Ground-side datalink direction** | Honeywell **US 10,380,899** (+ EP 3 293 893) | Chooses which datalink and when to transmit, by cost/time/availability rules | **Sends** messages better. Doesn't measure, attribute or prove what happened to them |
| **Flight-deck / CPDLC UX** | Honeywell **US 2017/0124734**, **US 2012/0078494** | Displays, message handling, session management | Improves what the pilot sees. Produces no requirement verdict and no evidence |
| **Closest of all — datalink performance monitoring** | Satcom Direct **US 2025/0260475** (pending) | Per-step transmit/receive timestamps, comparison against PBCS RCP 240 / RSP 180 benchmarks, identifies the transmission step that is the greatest cause of delay, NOC alerts, dashboard | This is the one to respect — it already names **the slowest transmission step**. But it stops at the radio boundary. It has no host-platform attribution, no margin projection while still conforming, no evidence artefact, no coverage account |

### The four things nobody claims together

1. **A per-transaction requirement verdict *with the margin*** — not pass/fail, but *how much of the 240 seconds was consumed*. Margin is the predictive quantity; percentile summaries throw it away.
2. **Attribution that reaches inside the aircraft's own computer** — the CMU/ATSU host platform: partition overruns, task latency, queue depth, AOC database revision behaviour. Network, radio, host platform, crew — four-way, per transaction.
3. **Projection of a *requirement* breach from margin decay while the flight is still conforming** — Legal today, trending to illegal. Nobody predicts that; everybody predicts a cable, a satellite or a pump.
4. **A proof artefact plus a coverage account** — hash-chained, replayable evidence per transaction, and a live statement of which requirements the fleet has never exercised. Evidence is the product; the dashboard is just the window.

> **The one line to remember:** *Everyone else predicts the link or the health of the box. We are the only ones predicting and proving the requirement.*

*Claim discipline (for the patent conversation, not the pitch): projection is a dependent claim on the attribution+evidence combination; we never claim "predicting a metric will cross a threshold" (US 2011/0161048) and never claim the category term "conformance monitoring" (public since FAA Part 108).*

---

## 3 · THE SOLUTION — see the picture

![How it works: what we read → the verdict engine → what you get](figures/fig_pitch_flow.png)

*Also as `figures/fig_pitch_flow.svg` for slides, and `figures/fig1_architecture.png` for the engineering version.*

### One message, followed end to end

A controller uplinks a clearance. 310 seconds later the pilot responds. The requirement was 240.

1. **CHECK** — We open the transaction against RCP 240 and report: **failed, 310 s, 70 s over** — and for every *other* transaction that day: **passed, 148 s, 62% of budget used.** The margin is the number nobody else computes.
2. **ATTRIBUTE** — We split the 310 seconds across the four places it can go: network/ground segment, radio link, **aircraft host platform**, crew. In our worked case: **180 s sat queued inside the CMU**, the network was clean, the crew responded normally.
3. **PREDICT** — That tail's median transaction time has risen 12 s per week for six weeks. Projection: crosses 240 s in 11 days. **This warning fires while every single flight is still compliant.**
4. **PROVE** — Every verdict ships as a hash-chained, replayable record: inputs, rule, version, margin, attribution, timestamp. Airline, OEM and regulator can each re-run it and get the same answer.

### Why it is believable and not magic

- **Start with three requirements** — RCP 240, RSP 180, and the response window. Not 128.
- **No new hardware, no certified-software change.** We read timestamps the aircraft already sends (ACMS/QAR/CSP feeds) and run on the ground.
- **Deterministic engine decides; AI only explains and proposes.** The product delivers full value with the AI switched off — which is exactly why it can be certified-adjacent and sold to safety people.
- **40+ patents and the full PBCS rule set read before the claim was drafted.**

### The 90-day wedge
AirSim lab + our own SDR receivers + a three-requirement verdict engine on one airline's feed. If that doesn't show **≥60% of defects detected before any complaint, with evidence in under 15 minutes**, the idea is wrong and we say so.

---

## 4 · WHO BENEFITS

| Who | What they get | What it is worth |
|---|---|---|
| **Airline** — reliability, flight ops/PBCS, OCC | Defects found before the complaint; evidence in minutes not months; 20% fewer NFF removals; PBCS conformance proved per flight instead of per spreadsheet; protection against losing RCP 240 eligibility | **USD 1.4–5.0 M/year per 500 tails**; one avoided AOG can pay a year |
| **OEM (Honeywell)** — support, warranty, engineering | First to know how its own product behaves in service; warranty claims bounded by evidence, not argument; fleet actions targeted (23 tails, not 200); a new services line on installed base | **USD 1.7–6.5 M per programme per year**; comfortably funds sponsoring 30–60% of the airline's subscription |
| **ANSP / CSP** | Cause lands on the right party; fewer multi-month problem-report cycles; better data for separation safety cases | Avoided eligibility withdrawal and litigation; cheaper investigations |
| **Regulator / safety authority** | Objective, replayable evidence for monitoring programmes and safety assessments | Less reliance on complaint-driven monitoring |

**Market:** aircraft health monitoring **USD 4.9 B (2025) → 7.4 B (2030), 8.3% CAGR**, AI predictive maintenance the named driver. Our slice — datalink requirement assurance — **USD 100–150 M/year, and no product is in it.**

---

## 5 · HOW TO PITCH IT

### 30 seconds
> "Every oceanic clearance has a legal deadline — 240 seconds. Today that's checked once a month in a spreadsheet, after the fact. So when something goes wrong, the airline finds out from a controller complaint, weeks later, and blames the network. We check every transaction in real time against its deadline, work out how much of the 240 seconds went to the network, the radio, the aircraft's own computer, or the crew — and we can prove it, message by message. That catches the fault weeks earlier, stops working radios being swapped, and gives the OEM a number to defend its warranty with."

### 2 minutes — the four beats
1. **Hook (15 s):** the 240-second deadline and the monthly spreadsheet. One number, one contrast.
2. **Problem (30 s):** the aircraft's own computer is invisible → complaints are the sensor → wrong system blamed → NFF and AOG.
3. **Difference (30 s):** "28 patents predict the link. The closest one, Satcom Direct's, already names the slowest transmission step. **Nobody goes inside the aircraft's computer, and nobody projects a requirement breach while the flight is still legal.** That's our lane."
4. **Proof + ask (45 s):** the 737-8 example (23 tails, not 200), the commitment metric, the 90-day wedge.

### Slide order (five slides, nothing else)
1. The 240-second deadline vs the monthly spreadsheet.
2. What went wrong on one flight — 310 s, 180 s inside the CMU, network clean.
3. The block diagram (this document, §3).
4. Who benefits, with the two money numbers.
5. The 90-day ask.

### The six questions you will get

| Question | Answer |
|---|---|
| *"Isn't this just Satcom Direct / Honeywell Forge?"* | "They report the slowest transmission step and the network's view. We go one box further in — inside the aircraft's host platform — and we hand over a replayable record. Different claim, different buyer." |
| *"Why not just improve the monthly monitoring?"* | "Because monthly is after the fleet has already been downgraded. Performance below the 95% criteria is normally noticed through controller complaints — that's the FAA's own wording. We move the detection point in front of the complaint." |
| *"Is this certified? Do we touch the aircraft?"* | "No. Ground platform, existing data feeds, no STC, no change to certified software. That's why the 90-day wedge is possible." |
| *"Isn't AI doing the work?"* | "AI explains and proposes; a deterministic rule decides, and every AI output passes an admission gate and is recorded. Pull the AI out and the product still works." |
| *"How do you know the attribution is right?"* | "Because it's falsifiable: ground truth arrives — the box comes off, the bench test passes or fails, the software load fixes it or doesn't. Every outcome becomes a label, and the attribution gets sharper with each one." |
| *"Who pays first?"* | "The airline pays per tail; the OEM co-sponsors 30–60% because it is buying warranty and fleet-action savings it can't get today. We start with one fleet and one OEM programme." |

### Three things not to say
- Don't say **"we predict failures."** We predict *requirement breaches*. Failures are the crowded, patent-fenced lane.
- Don't say **"conformance monitoring"** as a feature name — it's public regulatory vocabulary since FAA Part 108 and it's not claimable.
- Don't lead with AI. Lead with the 240 seconds. AI is how we get faster, not why anyone buys.

---

## Sources

1. FAA AC 90-117, *Data Link Communications* — RCP 240 / RSP 180, ACP/ASP, performance monitoring chapters — https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC_90-117.pdf
2. ICAO Doc 9869 PBCS Manual (via FAA/NAARMO and Transport Canada AC 700-041) — RCP nominal vs expiry time, 95% / 99.9% criteria.
3. FAA PBCS monitoring (FIT/27 monthly spreadsheets) — https://www.faa.gov/media/97231
4. SESAR PJ.14-W2-76, *CNS Performance-based* — "ICAO PBCS Manual describes only PBCS concept post-implementation monitoring programmes… in comparison to the PBN concept that includes real time monitoring and alerting functionality in the aircraft capability" — https://www.sesarju.eu/sites/default/files/documents/solution/SolPJ14-W2-76%20CNS%20Performance-based.pdf
5. FAA FIT/20 report — "observed fleet performance below the specified RCP240/RSP180 95% criteria will usually be accompanied by controller complaints" — https://www.faa.gov/media/99666
6. FAA ISPACG/31 · FIT/24 — 6,205 unique airframes from 85 States — https://www.faa.gov/media/98296
7. FAA FIT report — 98 problem reports in a year (69 South Pacific); B777 VHF→SATCOM transition issue corrected in AIMS Block Point 14 — https://www.faa.gov/media/100331
8. EUROCONTROL DPMG / Maastricht UAC — logon-list filtering of avionics with high failure rates — https://www.eurocontrol.int/service/controller-pilot-datalink-communications-our-maastricht-uac
9. *Aerospace* 5(2):38, MDPI — avionics NFF 20–50% of removals; avionics up to 30% of maintenance cost — https://doi.org/10.3390/aerospace5020038
10. IATA FY2024 maintenance benchmarking via GFA — USD 5.05 M per aircraft/year, USD 1,522 per flight hour — https://gfa.aero/blog/aviation-updates/avionics-failures-are-not-component-failures
11. AOG cost USD 10k–150k/hour, ~14 events per aircraft/year — https://actionstreamer.com/blog/what-does-aog-mean-and-what-does-it-cost-airlines-per-hour
12. Aircraft health monitoring market USD 4.91 B (2025) → 7.36 B (2030) — https://www.thebusinessresearchcompany.com/report/aircraft-health-monitoring-global-market-report
13. Patent positions: `PREDICTIVE_PATENTS_AI_vs_NON_AI.md`, `PRIOR_ART_DATASET.csv`, `IDEA_CORE.md`, `PATENT_STRENGTH_ASSESSMENT.md` (28 predictive patents; Satcom Direct US 2025/0260475 the closest).

*Money figures are internal planning estimates from the architecture document (§8), to be validated in customer interviews. Patent statements are our reading of published claims — not a legal opinion.*
