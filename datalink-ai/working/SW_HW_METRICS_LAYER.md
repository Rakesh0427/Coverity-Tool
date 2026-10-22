# The SW/HW Metrics + AI Pattern Layer — deep analysis, patent comparison, and how to add it to the solution

**Prepared:** 2026-10-10 · **Question:** with the live data, can we find SW and HW issues by comparing against metrics, and use AI to create SW/HW metrics and find issue patterns (communication, links, OS task latency, and other important classes)? What do existing predictive-system patents cover, and how do we add this to the proposed solution effectively?

---

## 1. Deep think — what this point actually is

The idea has **three metric layers and one pattern layer**. The value (and the patent) is in *which* metrics and *what they are anchored to*, not in "using AI on metrics":

| Layer | Content | Example |
|---|---|---|
| **L1 — Raw runtime telemetry** (built-in counters) | OS **task latency and jitter**, partition-scheduling overruns, queue depth, watchdog/restart events, stack/driver error counters, CPU/memory pressure, link-state and subnetwork transitions, retransmissions, noise floor | "Comms partition missed its window twice inside one transmit window" |
| **L2 — Requirement-anchored derived metrics** (computed by us) | Metrics whose *definition comes from the requirement structure*, not from the vendor's counter list: **queue-residence share of the RCP budget**, **transmit-window overlap of a partition overrun**, **margin-decay slope per requirement per tail/load**, clock-offset uncertainty, PORT share of the 240 s | "180 s of the 240 s budget was consumed in the CMU queue — 75% budget share" |
| **L3 — AI-proposed metrics and patterns** (advisory) | Unsupervised anomaly scores per tail/route/time-of-day; sequence novelty (unexpected event order); **learned thresholds per equipment type**; interference/threat signatures; candidate attribution; *new derived-metric candidates* discovered from correlation structure | "Surprise: subnetwork switch at an unexpected flight phase on 6 tails with DB 12.4" |
| **L4 — Decision + evidence** | Deterministic verdict against the requirement; AI proposals enter only through the admission gate; every accepted/rejected pattern recorded; **metric flywheel** — a maintenance-confirmed pattern becomes a validated label and (optionally) a new deterministic monitor | Pattern → engineer confirms → permanent monitor + label for the threat models |

**Key insight:** "AI creates metrics" is the right instinct, but the patentable and product-valuable form is **requirement-anchored metric synthesis** — the AI proposes; the requirement margin decides; maintenance confirms. Generic AIOps "anomaly on metrics" is a commodity (see §2). The aircraft-specific, requirement-specific, evidence-producing version is not.

## 2. Patent comparison — this exact lane

| Existing work / patent | What it covers | Verdict vs our layer |
|---|---|---|
| **ARINC 653 health monitoring** (standard practice in every IMA system) [1](https://grokipedia.com/page/ARINC_653) | On-board error detection/reporting at process/partition/module level; error handlers; restarts | **Standard.** Reactive, on-board, single-aircraft. Streams nothing to ground, correlates with no link transaction, maps to no requirement ID. Do not claim "partition health monitoring" |
| **InsightFinder patents** (US, granted) [2](https://insightfinder.com/products/patents-prove-accuracy/) — "Unsupervised behavior learning… predicting performance anomalies in distributed computing"; "…predict a future failure… generate a **ranked set of system-level metrics** which are contributors"; "ML incident prevention… pattern extraction from metrics, syscall traces, logs… remediation reuse" | Predict failure from system metrics + ranked contributor metrics + RCA patterns + remediation flywheel | **The closest generic art — treat as blocking for generic claims.** "AI predicts failure from HW/SW metrics and ranks contributing metrics" is *taken*. Same for "learned patterns from machine data feed back into remediation" |
| **OpsCruise US 11,126,493** [4](https://www.businesswire.com/news/home/20211012005207/en/OpsCruise-Receives-Patent-on-Machine-Learning-Based-Observability-for-Better-Visibility-Monitoring-and-Management-of-Cloud-Native-Applications) | ML behavioural baselines, predictive anomaly detection **without threshold tuning**, causal-domain isolation | Generic cloud observability. Kills "learned thresholds + causal isolation" as a standalone claim |
| **ε-Diagnosis (WWW'19)** [4b](https://netman.aiops.org/~peidan/ANM2023/8.AnomalyLocalization/LectureCoverage/2019WWW_%CF%B5-diagnosis.pdf) · **Reveal (2025)** [1b](https://arxiv.org/pdf/2510.26008) · microservice RCA frameworks [2b](https://computer-life.org/index.php/ojs/article/download/10/10) | Root-cause **metrics** identification for latency outliers; **derived metric** curation from hardware telemetry; anomaly + dependency graph + causal inference | Establishes "root-cause metric" and "derived metrics" as known ideas in IT. Literature/§103 risk, not aviation |
| **Rockwell US 11,465,779** (our AI-04) | ML in LRUs, telemetry over avionics Ethernet, **equipment-health prediction** | Closest avionics patent. Predicts LRU health; does not correlate runtime telemetry with **per-transaction requirement margins**; no gate, no evidence record, no requirement IDs |
| **Boeing US 10,457,423** (AI-07) · **Honeywell US 9,550,583** (AI-06) | Maintenance-message prediction; LRU failure prediction with wireless offload | Fleet maintenance level. Not OS-task-latency ↔ link-transaction correlation; no conformance anchor |
| **ACARS/CMU fault diagnosis** (CN 106516159 A, landscape dataset) | CMU fault diagnosis/health management | Fault diagnosis, not requirement-margin attribution; snippet-level |

**The gap in one line:** nobody correlates **airborne OS/task/partition runtime metrics with datalink transaction requirement margins** (cross-layer, air+ground, per requirement ID), synthesizes **requirement-anchored derived metrics**, and turns gated AI pattern discoveries into **replayable certification evidence** with a maintenance-confirmed label loop.

## 3. Problem statements for this layer (use these in the pitch)

1. **SW/HW behaviour is invisible where it matters.** OS task latency, partition scheduling and queue behaviour are the real cause of a large class of datalink symptoms — but they sit in on-board health monitors and post-flight QAR, disconnected from the link transaction. So a software slowdown looks like a network problem, and the wrong system is chased.
2. **Vendor metrics don't answer requirement questions.** The counters that exist (CPU, memory, error codes) were never designed to answer "how much of the 240-second budget did the platform consume?" Nobody computes requirement-anchored metrics, so raw telemetry can't produce a verdict or evidence.
3. **Generic AI on metrics can't be trusted here.** IT AIOps can flag anomalies and rank metrics — but in a safety-certified workflow its outputs are unexplainable, unbounded and inadmissible; false alarms cost credibility. AI needs a gate, and its findings must become evidence — or they are useless to this industry.
4. **Patterns are found late and by hand.** The industry's diagnostic loop (ICAO problem reports → OEM software fix) runs at months-to-years speed. Fleet-wide issue patterns in communication, links and OS task latency should surface in days, and each confirmed pattern should permanently improve the monitors — that loop does not exist.

## 4. How to add it to the proposed solution (effective wording)

**Add to `FOUR_POINTS.md` §3 as a fifth bullet (now edited in):**

> 5. **SW/HW issue hunting from live data** — collect OS task latency, partition scheduling, queue, fault and link counters; compute **requirement-anchored metrics** (e.g. queue-residence share of the RCP budget, overrun-in-transmit-window counts, margin-decay slope); let AI propose new metrics and issue patterns (comm, link, OS task latency) as **advisory findings** that pass the admission gate; every confirmed pattern becomes a permanent monitor and a label via the maintenance flywheel.

**Architecturally it is already designed** — this is `Datalink_AI_Live_Architecture.docx` §4.1–4.3 (pattern library, ML layer, label flywheel) plus S6 (partition health events). The addition makes it explicit as a **product capability** in the pitch: *"the same live data also finds the SW and HW issues — compared against metrics we define against the requirements, with AI creating the metrics and the patterns."*

**Claim hooks (adds to Family 1 dependents and supports a new independent concept):**

- … wherein a **derived metric** is computed from the host-platform telemetry and the transaction delay budget, the derived metric comprising a share of the budget consumed by the platform leg, and the attribution uses the derived metric.
- … wherein an AI-proposed pattern in OS task-latency or scheduling telemetry is admitted through the gate, written to the evidence record, and, on maintenance confirmation, instantiated as a deterministic monitor with a label for the threat models (**metric flywheel**).
- … wherein thresholds for the monitors are learned per equipment type from runtime telemetry and validated against requirement outcomes before replacing fixed thresholds.

**Do NOT claim:** anomaly detection on system metrics; ranked contributor metrics; learned thresholds; metric discovery; remediation reuse — all generic-taken (§2). Claim only the **requirement-anchored, air-ground correlated, gated-and-evidenced** versions.

## 5. Effect on the pitch and the patent

- **Product story:** the proposed solution now answers the full question — *finds issues in the flow AND in the SW/HW, by comparing live data against requirement-anchored metrics, with AI discovering the metrics and the patterns.*
- **Patent story:** E4 (already 7.5/10) gains two more dependent hooks and the metric-flywheel concept strengthens Family 3; the §5 examiner combination (Satcom Direct + Rockwell 11,465,779) is now answered even more directly: neither reference has requirement-anchored derived metrics or the gate/evidence loop.
- **Pitch honesty line:** *"IT industry patents cover AI on generic metrics; avionics patents cover equipment-health prediction. The open, valuable space is the one we claim: metrics anchored to the requirement, correlated across aircraft and ground, AI gated and recorded."*
