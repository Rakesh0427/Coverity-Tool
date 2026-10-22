# Problem Statement — DATALINK AI (pitch pack)

**Prepared:** 2026-10-10 · **For:** idea shortlist / innovation pitch · **Sources:** `Datalink_AI_Live_Architecture.docx` Rev 3 (§6 worked example, §8 business case) — all money figures are that document's indicative 2026–2028 planning estimates, to be validated by customer interviews.

---

## 1. The one-line problem (this is slide 1)

> **When a datalink transaction misses its requirement, nobody can prove whose fault it was — the network, the radio, or the aircraft's own computer. So the wrong system gets chased, the wrong part gets removed, and the same defect flies on.**

Sharper product phrasing, if you want one line that also names the product gap:

> **Datalink issues are invisible until someone complains, unattributable when they happen, and unprovable afterwards — and the aircraft's own datalink computer is the one suspect nobody can see.**

---

## 2. The problem, stated properly (the 2-minute version)

Every modern aircraft runs safety-critical digital messaging — CPDLC clearances, ADS-C surveillance, ACARS operational traffic — through a datalink computer (e.g. the Honeywell CMU Mark II+ on 7,000+ aircraft). Regulators hold these transactions to hard performance requirements (**RCP 240**: a CPDLC transaction must complete within 240 seconds, 95% of the time). When a transaction misses that number, three things are true today:

1. **Visibility failure — the issue surfaces as a complaint, weeks later.** Intermittent comms behaviour reaches the OEM and the airline's engineering team as a support ticket that says "the datalink misbehaved" — no synchronised timestamps, no raw record, no configuration context. The OEM learns about its own product's defects **from its customer**, weeks to months after the first occurrence.

2. **Attribution failure — the wrong system gets chased.** Ground monitoring measures network transmission steps. The delay that looks like a network problem is often created **inside the aircraft** — a message queued behind a routing preference in the CMU, a partition overrun in a transmit window, a database-revision defect after a load campaign. Because nobody correlates link symptoms with aircraft-platform behaviour, the CSP gets escalated, the radio gets swapped, and the real cause flies on.

3. **Evidence failure — nothing can be proved.** Of the 128 requirements instantiated for a monitored configuration, **effectively zero have an evidence-complete, ledgered record per flight**. Warranty boards argue from anecdote. No-fault-found removals waste shop capacity. Airlines cannot demonstrate PBCS compliance per flight. And AI/ML — which could find these patterns — **cannot enter a certified operational path**, because its outputs are unexplained, unbounded and inadmissible as assurance evidence.

The worked example in the architecture (flight AI102, A350, MAA→LHR) is this problem in miniature: a non-conforming transaction, an apparently clean network, and a partition-health signature inside the transmit window — the defect is in the aircraft's own platform, found only because every source was collected and kept with provenance.

---

## 3. What we are solving — three named gaps, not a category

| # | Gap | Why it is unsolved today |
|---|---|---|
| **G1** | **Cross-layer attribution per transaction** — network leg / link leg / **aircraft host platform** / human | Existing monitoring attributes delay to transmission steps (network artifacts) and stops at the aircraft skin. Nothing correlates per-leg delay budgets with CMU partition/OS/queue/config behaviour |
| **G2** | **Prediction of the product's own internal failure** — before the customer sees anything | Health monitoring flags a crossed threshold or reports after the flight. Nobody tracks *margin decay against a requirement* — "conforming, with the margin running out" — per tail, per software load, per route |
| **G3** | **Certification-grade evidence from live operations** — conformance records, coverage account, gated AI outputs | No existing tool turns live datalink operations into objective-mapped, replayable evidence; no existing AI placement produces an admissible, gated, recorded output |

**One sentence:** *we make every datalink transaction self-proving — who was at fault, what is degrading, and what the requirement margin was — and we do it with AI that is gated and recorded rather than trusted.*

---

## 4. How the idea changes the product

### 4.1 For the airline's operation (the buyer's day)

| Today | With the platform |
|---|---|
| Defect found by crew report / delay / complaint, days–weeks later | **≥60% of issues detected by the platform before any crew, OCC or customer report**; evidence in **under 15 minutes** for message-class requirements (§8.6 targets) |
| "The datalink is unreliable" — no cause, no configuration context | "This build misbehaves on this database, on these tails" — cause bounded and replayable |
| No-fault-found removals: 20–30% of LRU removals test good | Evidence pack travels with the removal: requirement, measured value, margin, config — the shop reproduces the conditions |
| PBCS/RCP compliance argued from sampled reports | Per-flight conformance records + coverage account (which requirements are no longer exercised on a route/load) |
| Campaigns blanket the fleet | Config drift explicit → upgrades reach only the tails that need them |

### 4.2 For the OEM product line (the Mark II+/CMU story — this is the "change in product")

The idea does not change the certified box. **It changes what the product line is:** from a certified unit shipped and supported on tickets, to a unit with a **live conformance twin** in service.

1. **The product gains in-service telemetry it never had.** Partition execution vs budget, queue depth, watchdog/fault events, config identity (load mix, AOC database revision, modem) — tracked per tail, per load, per route, from data the aircraft already produces.
2. **The information flow reverses.** Defects are detected server-side at the moment evidence arrives — often while the aircraft is still airborne — and reach engineering with the transaction, timestamps and raw-record hash. Support moves from defence to diagnosis; this is the single largest commercial benefit in the idea (§8.1).
3. **Fixes become bounded.** The affected population is identified by software load / hardware PN / database revision — a service bulletin or retrofit limited to the affected configuration instead of a fleet-wide action (a fleet action costs USD 0.5–3M).
4. **The programmable AOC database gets a feedback loop.** Routing preferences and trigger logic — the configurable "airline logic" inside the CMU — become auditable, regression-tested (simulator-verified before deployment) and pattern-monitored in service.
5. **PBCS becomes provable per flight** (RCP 240/RSP 180 evidence for A056-style approvals), not sampled.
6. **A new product line appears on the same contract:** reliability intelligence delivered alongside the maintenance agreement — high margin, no new hardware, data asset that grows with the installed base (§8.3).
7. **Design rule that makes it certifiable and patentable:** the verdict engine is deterministic; AI is advisory, admission-gated and recorded. Certified airborne software is never modified.

### 4.3 For the certification story (the moat)

- First time an AI diagnostic can **enter a controlled operational record**: OOD + calibrated uncertainty + robustness gate → admitted output written as an evidence record mapped to DO-178C/DO-254/DO-330 objectives, with deterministic replay for auditors.
- The **coverage account** — verification credit still owed, per route and software load — is a capability that does not exist in any product today (§8.5).

---

## 5. How the idea changes cost

### 5.1 The cost of the problem today (per 500-tail operator per year — §8.7, indicative)

| Cost line | Conservative | Base | Basis |
|---|---|---|---|
| Disruption + in-service detection value | 0.5 M | 2.0 M | Avoided delays/diversions/cancellations + engineering time saved |
| No-fault-found removals avoided | 0.3 M | 1.2 M | 20–30% of removals test good; removal+refit+logistics+spare ≈ USD 5–15k each; 20–40 removals/yr |
| Engineering, audit, warranty effort | 0.2 M | 0.6 M | 2–4 FTEs moved from data collection to engineering |
| AOG / diversion tail risk | 0.4 M | 1.2 M | 1–5 events/yr at USD 30–80k each |
| **Total hard benefit** | **USD 1.4 M** | **USD 5.0 M** | Before intangibles (warranty position, reputation) |

### 5.2 The cost of the problem for the OEM (per programme per year — §8.8, indicative)

| Cost line | Indicative range | Basis |
|---|---|---|
| Warranty + NFF removed | 0.5–2.0 M | 1–3% of warranty spend; a comms product line carries USD 20–60M warranty cost/yr in the installed base |
| Support cases deflected | 0.3–1.0 M | 15–30% of technical-support volume, fully loaded |
| Fleet-wide fixes avoided / bounded | 0.2–1.0 M | One avoided fleet action can cost USD 0.5–3M |
| Campaigns targeted | 0.2–0.5 M | Fewer, better-directed upgrades + pull-through |
| New services revenue | 0.5–2.0 M | Reliability intelligence on the existing agreement |
| **Total OEM benefit** | **USD 1.7–6.5 M** | Licence priced **below** the benefit (USD 1–5M/programme/yr + NRE) |

### 5.3 What the change costs to make (the line that closes the deal)

> **No new avionics. No STC. No change to the certified product.** The platform consumes data the aircraft already produces. Implementation cost is data agreements and a ground platform — not aircraft hardware. That turns the OEM conversation from an engineering programme into a data-services agreement (§8.8).

- Price to the airline: **USD 3,600–6,000 per tail per year** (tiered by verdict depth); an **OEM-sponsored structure** (OEM funds 30–60% from its own savings) is the conservative-year close.
- **ROI anchors:** one avoided AOG/diversion (USD 30–80k) is a meaningful slice of a 500-tail fleet's annual subscription; **one avoided fleet action (USD 0.5–3M) pays for a programme licence outright**. Gross margin at scale: 70–80% (§8.9).
- Business at maturity (§8.10): conservative **USD 2.9M** (yr 3) → base **USD 11.4M** (yr 3–4) → upside **USD 36.5M** (yr 4), against an addressable market of roughly **USD 100–150M/yr**.

### 5.4 The commitment metric (put this on the cost slide)

> **If the pilot does not lift "issues detected before any crew/OCC report" from near-zero to ≥60%, and cut occurrence-to-evidence from days–weeks to under 15 minutes, don't buy it.** (§8.6 — every benefit line is measurable in week 1 of the pilot.)

---

## 6. Copy-paste pitch blocks

**30-second elevator:**
> "Aircraft send thousands of safety-critical datalink messages a day. When one misses its requirement, no one can prove whether the network, the radio or the aircraft's own computer was at fault — so the wrong system gets fixed, parts get removed for no fault found, and the OEM hears about its own defects from angry customers, weeks later. We fix that: we attribute every delay to its real cause across network, radio, aircraft and crew — and turn each transaction into certification-grade evidence. Deterministic verdicts; AI only where it is gated and recorded. No new hardware on the aircraft."

**60-second problem opener (start the pitch with this story):**
> "Flight AI102, Chennai to London. One clearance message takes 310 seconds against a 240-second requirement. The network looks clean. The radio is fine. The truth is 180 seconds of queuing inside the aircraft's own datalink computer, behind one configuration rule — and a partition overrun inside the transmit window. Today this surfaces as a complaint three weeks later with no timestamps, and the airline removes a working radio. We surface it in minutes, with the evidence, and the fix lands on the actual cause. Multiply that by a fleet, and you get the numbers on the next slide."

*(Adapt timings to your final worked example; the AI102 case in §6 is internally consistent and cross-checks against Figures 3, 4, 6 and the mock-up.)*

**Three-slide sequence:**

| Slide | Headline | Three bullets |
|---|---|---|
| **1. Problem** | "Datalink faults are unattributable — and unprovable" | · Complaint-driven discovery, weeks late · Cause hides inside the aircraft; wrong system chased · 0 of 128 requirements evidenced per flight |
| **2. Change** | "We make every transaction self-proving" | · Attribution: network / radio / aircraft platform / crew, per transaction · Prediction: margin decay → action before the violation · Evidence: gated AI, replayable conformance records, coverage account — no new hardware |
| **3. Cost** | "The problem costs USD 1.4–5.0M per 500 tails per year — and the same evidence is worth USD 1.7–6.5M per programme to the OEM" | · NFF + AOG + wasted engineering = the airline stack · Warranty + support + fleet actions = the OEM stack · Proof metric: 60% detection before complaint, or don't buy |

**Objection handling:**

| Objection | Answer |
|---|---|
| "Isn't this just monitoring?" | Monitoring tells you a number moved. We tell you **whose fault it was**, and produce the audit record. Satcom Direct measures the network; the aircraft platform is invisible to them — that gap is our lead patent claim. |
| "Where's the AI? Everything has AI." | The verdicts are deterministic — that is the product. AI is advisory, admission-tested and recorded; a rejected AI output is logged too. That is what makes it certifiable, and it's a patent family. |
| "Data rights will kill you." | Week 1 runs on data anyone can get: our own VHF/ACARS receivers + Honeywell's AirSim simulator. Contracts with CSP/airline add breadth, not existence. |
| "Too big for one team." | The wedge is one flight's transaction evidence (the AI102 demo). The platform is the roadmap. 90-day plan: demo on synthetic + RF data, then one airline feed. |
| "Why would Honeywell pay?" | Same evidence saves them USD 1.7–6.5M/programme/yr and reverses the defect-reporting flow; the licence is priced below that, and it requires no change to their certified product. |
| "The product is certified before delivery — MIPS analysis, flight test, DO-178C audits. What problem is left?" | Certification is a one-time proof of the **design**; the aircraft then flies 15 years while loads, databases, routes and hardware change — every process listed stops at delivery. In-service defects on certified products are real (20–30% NFF removals, USD 20–60M/yr warranty on comms lines): config drift after load campaigns, airline-edited AOC databases, airspace/CSP environment, aging. We are the **in-service half of the assurance chain** — per-flight conformance evidence certification cannot produce — and we never touch certified software. |

---

## 7. Number discipline (read before the pitch)

- Every money figure above is an **indicative planning estimate 2026–2028 from `Datalink_AI_Live_Architecture.docx` §8**, order-of-magnitude, to be validated by customer interviews — say so once, on the cost slide, in small print. The **mechanism** behind each line is hard (it traces to what the platform produces in §6); the magnitudes are assumptions.
- The pilot metrics (§5.4) are the bridge from assumption to forecast: buy the pilot against week-1 baselines and month-6 targets, not against the pitch.
- Do not quote NFF-rate, AOG-cost or warranty-spend industry averages as facts in Q&A unless sourced; the §8 basis columns are safer because they show the arithmetic.

---

**One-line version for the nomination form:**
> Datalink faults on commercial aircraft are discovered late from complaints, attributed to the wrong system because the aircraft platform is invisible, and provable by nobody — costing airlines USD 1.4–5.0M per 500 tails per year and OEMs USD 1.7–6.5M per programme per year. We make every datalink transaction self-proving: deterministic attribution across network, radio, aircraft and crew, prediction of product-internal failure before the customer sees it, and certification-grade evidence from an AI that is gated and recorded — with no new hardware on the aircraft.
