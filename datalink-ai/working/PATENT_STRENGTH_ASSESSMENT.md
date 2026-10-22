# Patent Strength Assessment — DATALINK AI, after the deep 28-patent search

**Prepared:** 2026-10-10 · **Subject:** `Datalink_AI_Live_Architecture.docx` (Rev 3, 8 Oct 2026), Section 10 hooks, assessed against `PREDICTIVE_PATENTS_AI_vs_NON_AI.md` (28 entries) plus the earlier landscape in `PATENT_LANDSCAPE_REPORT.md` and the draft claims in `DRAFT_CLAIM_SET.md`.

> ⚠️ Engineering assessment, not a legal opinion. No validity, infringement or FTO opinion is expressed. Scores are judgement aids for deciding where to spend filing budget.

---

## 1. Bottom line

**Yes — the idea is still patent-worthy, and the deep search strengthened rather than weakened the defensible core.** But only as a portfolio of **narrow, specific hooks**. The broad concept ("predict or monitor datalink performance with data/AI") is dead — the search confirmed 28 patents occupying that lane, several of them granted and recent. What survived untouched is exactly what `Datalink_AI_Live_Architecture.docx` §10 says the filing is about:

| Verdict | Item |
|---|---|
| **File this** | Cross-layer attribution to the **aircraft host platform** (E4 / Claim 1), with deterministic replay |
| **File this** | Admission-gated advisory AI producing **certification-evidence records** (E6–E8 / Claim 2) |
| **File this (second filing)** | Label flywheel + signed advisory threat-model distribution (Invention 3 / Family 3) |
| **Strong dependent claims** | Conformance record: content hash, ledger, deterministic replay, late-data verdict revisions |
| **Cover but do not claim alone** | Requirement-mapped findings with deterministic verdict (the "AI explains, never judges" line) |
| **Trade secret / defensive publication** | ACMS report definitions as the in-flight route to partition/OS evidence |
| **Never claim** | Predicting link quality, outage, handover or channel state with or without ML; latency-vs-threshold monitoring; generic dashboards and alerting |

**Candid worth:** worth a **provisional now** (low cost, secures a priority date that is getting more valuable as this lane fills). Worth a **full non-provisional/PCT** if (a) nothing has been publicly disclosed without a filing, (b) a test bed can produce the worked numbers in §7 below, and (c) the claims stay on the hooks and never drift toward "predict the link". As a business asset the moat is the **certification-evidence angle**, which is what regulators will demand and what none of the 28 (or the older art) produces.

**Strength score: 7/10 for the hooks as drafted, 3/10 for the idea if claimed broadly.** Before the search the defensible share was estimated at 30–40%; the search confirmed that estimate — nothing found closes the gap hypothesis, but the combination risk against Family 1 rose one notch (see §5).

---

## 2. What was assessed

The idea, in the five §10 hook groups plus the two disclosure families they map onto:

1. **Lead claim hook** — pattern findings mapped back to **requirement identifiers**, verdict remaining deterministic (AI explains, does not judge). `Datalink_AI_Live_Architecture.docx` §4.1 and §10.
2. **Invention 2 hook** — **coverage erosion**: the not-exercised requirement set drifting over routes and software loads; the operational coverage account (verification credit owed, not health evidence). §4.1 Figure 6, §10.
3. **Invention 3 hook** — **label flywheel**: maintenance confirmations become validated labels for ground-learned advisory threat/interference models; signed advisory data only; roll-back. §4.2–4.3, §10.
4. **Dependent-claim hook** — **conformance record**: content hash, append-only ledger, deterministic replay, late-data verdict revisions. §10.
5. **Secret hook** — ACMS report definitions as the practical route to partition/OS evidence. §10.
6. **Family 1** (`INVENTION_DISCLOSURE.md`, `DRAFT_CLAIM_SET.md` Claim 1) — cross-layer attribution of a datalink transaction to ground-network leg / air-ground link leg / **aircraft host-platform** condition (partition scheduling, comms-app starvation, stack/driver faults), with per-leg delay budget, time alignment, content hash, deterministic re-execution.
7. **Family 2** (Claim 2) — dual path (deterministic verdict + advisory ML), **admission gate** (OOD score, calibrated uncertainty, robustness perturbation), evidence record mapped to DO-178C/DO-254/DO-330 objectives, objective-by-objective evidence bundle.

---

## 3. Scorecard vs. the 28-patent search

Score: novelty of the hook against everything found, and resistance to an obviousness combination. 8+ = file confidently; 6–7 = file with the dependent narrowing; <6 = dependent claim or second-tier only.

| # | Hook | Score | Closest prior art (new search) | What is still ours | Main risk |
|---|---|---|---|---|---|
| 1 | Host-platform attribution (E4, Claim 1) | **7.5** | NA-07 US 10,380,899 (Honeywell — ground-side datalink selection, "best result"); AI-04 US 11,465,779 (Rockwell — ML over avionics Ethernet for LRU health) | Three-way attribution of a **single transaction's delay budget** to network / link / **host platform**, with partition-overlap timing and **deterministic replay**. NA-07 selects a datalink; it never attributes a symptom to OS/partition state. AI-04 prognosticates equipment health; it never decomposes a transaction. | Examiner combines Satcom Direct US 2025/0260475 (per-step delay attribution) + AI-04 (ML on avionics network telemetry). Counter: the combination still attributes only to transmission steps or to equipment health, not to the host platform as a cause of a *link symptom*; our telemetry types, alignment and replay are absent from both. |
| 2 | Admission-gated advisory AI + evidence records (E6–E8, Claim 2) | **7.5** | None of the 28. Older: Honeywell US 10,839,401 (verify unqualified data → pass to qualified system) | The **gate** (OOD + calibrated uncertainty + robustness against a defined ODD) and the **certification-evidence record** (model hash, input-window hash, gate decision, explanation artifact, objective ID, replay recipe). The 28 only show that ML on links is generic (AI-01/02 Panasonic, AI-03 Intel, AI-05 Qualcomm) — which helps us: "use ML" is noise, the gate-and-evidence mechanism is the claim. | §101 abstract-idea rejection if the claims lose the remediation/evidence outputs; §112 if the gate is not frozen into the spec. |
| 3 | Coverage erosion → operational coverage account (Invention 2) | **8** | **Nothing anywhere near it.** Closest conceptually: none of the 28 concerns requirements, verification credit or coverage. | A monitor whose output is "requirements no longer exercised on this route/software load", tracked over time, used for test-case selection. It is a certification tool, not a link tool. This is the cleanest novelty in the whole package. | Thin on §103 combination risk; the risk is §101 ("organising test information") unless the claim recites the technical effect (route/load-specific verification credit driving test selection and the maintenance/ops decision). Moderate commercial framing work. |
| 4 | Label flywheel → ground-learned, envelope-gated threat models (Invention 3 / Family 3) | **6** | AI-05 Qualcomm (ML channel prediction); older: Honeywell US 11,488,063 (cloud-trained models to FMS), Aerospace Corp US 11,212,015 (ML interference suppression). NA-06 Ericsson shows even non-ML UAV links already carry anti-spoofing logic. | The **closed loop with admission**: engineer-confirmed labels → ground training → frozen-regression + envelope validation → **signed advisory data only** (never a change to certified airborne software) → certified deterministic airborne decision → provenance/roll-back. None of the references has the certification-gated, advisory-only, rollbackable distribution loop. | Honeywell 11,488,063 is the base; the delta must be claimed as the gating and provenance mechanism, not "self-learning threat models". Hold for second filing until the regression suite exists (as §10 says). |
| 5 | Conformance record: hash, ledger, replay, late-data revisions | **5.5 alone / 7 as dependents** | None of the 28. Generic event-sourcing and hash-chaining are well known outside this domain. | Late-data **verdict revision** semantics (a verdict can be revised when late data arrives, with both versions in the ledger) is the non-obvious part. | Never claim hash chaining alone. Claim it bound to verdict revision + requirement mapping. |
| 6 | Requirement-mapped findings, deterministic verdict (lead claim hook) | **6.5** | None of the 28 maps findings to requirement IDs. But "deterministic core + AI advisory" as an architecture is anticipated by Simplex-family literature and NVIDIA US 2023/0176577. | The combination: findings traceable to **requirement identifiers**, verdict deterministic, AI explanation attached as evidence. Claim as a mechanism with the evidence output, never as "hybrid AI architecture". | §103 over Simplex + any traceability tool (LDRA-class products). The claim must recite the specific requirement-mapped verdict record and what the system does with it. |
| 7 | ACMS as evidence route (secret hook) | n/a | US 2025/0260475 uses ACMS-class monitoring for performance; NA-17/NA-18 show airborne position-driven link switching. | Keeping the ACMS partition/OS-evidence route as **trade secret** is the right call per §10. A defensive publication still makes sense so no third party patents it against you. | If a competitor files on "ACMS-configured partition evidence", a defensive publication is your only cheap shield. Do it early. |

---

## 4. What the deep search changed

**Strengthened:**

- **The gap hypothesis held.** Not one of the 28 predicts CPDLC/ADS-C/ACARS delivery from message-level data, and not one pairs a deterministic verdict with a gated advisory ML layer, requirement-mapped findings, coverage accounting, or certification-evidence records. The 28 cluster tightly around: outage prediction (AI-01, AI-02), channel/link-state prediction (AI-03, AI-05, AI-09, AI-10), equipment health (AI-04, AI-06, AI-07), availability forecasting and handover (NA-01–NA-04, NA-09, NA-14–NA-18), and link management (NA-05–NA-07). All of it is **about the link**. Your hooks are **about the evidence and the verdict**.
- **The "AI" in your idea is not the claim.** Panasonic (two grants), Intel, Qualcomm (now **granted** US 12,652,602 B2, June 2026) and Rockwell all claim ML on connectivity or avionics data. That is crowded — which is precisely why your claim should never recite "using machine learning to predict datalink behaviour" and should always recite the gate, the record and the deterministic verdict. The search validates §10's design rule as a *patent* strategy, not just an engineering one.
- **Coverage erosion / operational coverage account is genuinely open.** 18 non-AI patents, several of them certification-adjacent in domain (Honeywell, Rockwell, Boeing), and none concerns requirement coverage in service. File Invention 2 with confidence.

**Weakened / sharpened:**

- **Family 1's combination risk rose one notch.** AI-04 (US 11,465,779, Rockwell) is the item to worry about: ML algorithms stored in LRUs, telemetry over avionics Ethernet networks, equipment-health prediction. An examiner asked to reject your host-platform attribution claim will reach for **US 2025/0260475 + US 11,465,779**. The dependent limitations in `DRAFT_CLAIM_SET.md` (partition-scheduling statistics; overrun interval overlapping the transaction in-flight time; three-way attribution with confidence as a function of clock-offset uncertainty) are now load-bearing, not optional polish — keep all of them.
- **Never drift toward link prediction.** Qualcomm US 12,652,602 B2 is now a *granted* patent on ML channel-state prediction driving path selection. Gogo US 12,273,783 B2 claims link-loss likelihood tables; Rockwell US 11,423,789 B2 claims a C2 link-quality model from historical data with corrective action. Any claim of yours that reads "predict link quality and act on it" walks into live, granted art. Section 4.1's margin-decay pattern is safe only because it is measured against a **requirement acceptance criterion** (a projected *conformance* violation date, not a predicted link state) and is deterministic (CUSUM) — keep that framing in the spec.
- **Satcom Direct is the strategic patent holder to watch.** Between US 2025/0260475 (monitoring), NA-01 (US 10,939,304, availability forecasting) and NA-02 (US 11,398,158, provider selection), one competitor covers ingest, measurement, forecasting, selection and alerting of datalink performance. Your differentiation must always be stated as: *we attribute to the aircraft and produce evidence; they characterise the network*. That sentence is the §103 rebuttal and the FTO boundary in one.

---

## 5. The §103 battleground — three combinations an examiner will try

| # | Combination | Attacks | Our rebuttal |
|---|---|---|---|
| 1 | Satcom Direct US 2025/0260475 (per-step delay attribution) + Rockwell US 11,465,779 (ML over avionics networks for health) | Claim 1's host-platform attribution | 0260475 attributes delay to a **transmission step** (network artifact) and stops; 11,465,779 predicts **equipment health**, not transaction delay. Neither correlates host telemetry with a per-leg delay budget over a time-aligned transaction window; neither does three-way attribution; neither replays the attribution for audit. The combination teaches "monitor steps" and "predict LRU failure", not "the partition overrun is why this CPDLC uplink missed RCP 240". |
| 2 | Honeywell US 10,839,401 (verify unqualified data → qualified system) + EASA CoDANN / AMLAS literature (ML assurance) | Claim 2's admission gate + evidence record | 10,839,401 is generic as to *how* integrity is verified and its output is **qualified data**, not a certification artifact. The literature is non-patent and describes goals (OOD, uncertainty, assurance) without the concrete binding {input-window hash, model hash, gate decision, explanation artifact, objective ID} record, the rejection logging, and the objective-by-objective bundle. Claim the gate **mechanism** and the **record**, per `DRAFT_CLAIM_SET.md` Part D. |
| 3 | Panasonic AI-01/AI-02 (ML outage prediction) + Boeing AI-07 (maintenance-message prediction) | The margin-decay / projected-violation pattern (§4.1) | Those predict **link outage probability** from route/regulation history and **maintenance messages** from fault history. Margin decay predicts violation of a **requirement acceptance criterion** while the system is still conforming, from the requirement's own margin series, and produces a requirement-mapped maintenance trigger. Frame the pattern as conformance forecasting, never as failure prediction. Keep it deterministic in the independent claim; learned thresholds stay in dependents. |

If these three rebuttals hold in drafting, the families survive first examination with amendments at worst. If drafting drifts broad, combination 1 alone can take Family 1 apart.

---

## 6. Eligibility and enablement — the two non-novelty gates

- **§101 (Alice).** "Collect data, analyse, display" is abstract; the closest reference (0260475) survived by reciting **physical transmission steps** and **link reconfiguration**. Every independent claim needs a concrete technical effect: the reconfiguration/maintenance action in Claim 1, the gate changing what enters an operational path and the evidence bundle in Claim 2, the test-case/maintenance decision in the coverage-account claim. Part D of `DRAFT_CLAIM_SET.md` already says this; the deep search did not soften it.
- **§112 (enablement).** The gate algorithm, evidence schema and one worked example with numbers must be frozen into the spec. The 28-patent search is irrelevant to this gate — it is a drafting-discipline problem.
- **Disclosure bar (the clock).** `Datalink_AI_Live_Architecture.docx` is Rev 3 dated **8 Oct 2026**. If any version of this architecture has been shown outside a confidentiality context (conference, partner meeting with slides left behind, webinar), the US 12-month grace period and EP/IN/CN absolute novelty are already running. **Answer the §1 disclosure question in `INVENTION_DISCLOSURE.md` before anything else.** If a disclosure is imminent, file the provisional first, then present.

---

## 7. Is it a *worthy* patent? — the honest answer

**Worth filing: yes, conditionally.** Three tests:

1. **Novelty — passed on the hooks.** 28 targeted patents plus the 44-entry dataset plus the certification-lane references (10839401, 3651022, 11580009, IBM surrogate) do not disclose: host-platform attribution of datalink transaction delay; admission-gated advisory ML with certification-evidence records; coverage erosion as an operational account; engineer-confirmed label flywheel with envelope-gated signed advisory distribution and roll-back.
2. **Inventive step — contested but winnable.** The combinations in §5 are real; the counters exist and are already sketched as dependent claims. The claims must be drafted narrow-first from day one. This is a **7/10** if drafted to the hooks and a **3/10** if drafted to the vision.
3. **Commercial worth — real, in the right lane.** The value is not "a patent on AI for datalink". The value is: (a) a moat around **certification-grade evidence generation** for datalink operations — the thing LDRA/VectorCAST/Ketryx-class tooling does not do at runtime on live datalink data, and the thing an EASA/FAA assurance argument will require once AI advisory functions appear in ops; (b) a **defensive position** against Satcom Direct's expanding ground-side portfolio; (c) licensing leverage to OEMs and CSPs who will need objective-mapped evidence for AI-assisted datalink functions. If the product ships, the patent prevents copying of the *evidence architecture*, which is the part competitors cannot bolt on later.

**What would make it unworthy (be honest with yourself):** filing broad claims on monitoring/prediction (instantly anticipated); filing before the gate and schema are frozen (§112 death); filing after an unmanaged public disclosure (bar death); or filing with no path to the worked numbers examiners expect for technical-effect proof.

**Verdict: File a provisional now on Families 1–2 with the hooks above as claim anchors and the §5 rebuttals drafted into the specification. Hold Family 3 for the second filing. Defensive-publish the ACMS route. Re-score after a claim-level Espacenet/PatBase search on the hooks (see §8) — if that search also comes back empty on host-platform attribution and coverage accounting, convert to PCT with confidence.**

---

## 8. Action list (priority order)

1. **Answer the public-disclosure question** (`INVENTION_DISCLOSURE.md` §1). Everything else is sequenced by this date.
2. **Run the one search this sandbox could not:** full-text claim search in Espacenet or PatBase on the hooks — CPC G08C/G08G + B64D/ B64U with (attribution AND (partition OR "operating system" OR "host platform")), (coverage AND requirement AND (route OR "software load")), (evidence AND (DO-178C OR DO-254 OR DO-330 OR "objective identifier")). User-side access required; roughly a day of work. This is the single largest remaining unknown.
3. **File the provisional** (Families 1–2) within 2–4 weeks, with the evidence-schema table and one worked example (even synthetic-but-labeled) inside the spec. Preferably before any external presentation.
4. **Instrument the test bed** for the numbers: "partition scheduling overruns overlapping the transaction window account for Y% of CPDLC exchanges exceeding 180 s; the admission gate rejected W% of advisory diagnoses, each rejection logged with model hash and input-window hash; the coverage account showed N requirements unexercised on route R / load L."
5. **Defensive publication** for the ACMS partition-evidence route and the dashboard UX.
6. **Calendar re-checks:** re-run the landscape when US 2025/0260475 gets a first office action or claim amendment (its claims can still move), and when filings from the ~April-2025+ blind window publish. Watch Satcom Direct, Panasonic Avionics, Honeywell and Rockwell Collins as the four portfolios that matter.
7. **Do not spend filing budget on:** any link-quality/outage/handover prediction claim; latency-vs-threshold monitoring; dashboards; generic "explainable AI"; the Simplex-style dual-path architecture in the abstract.

---

## 9. Caveats

- Not legal advice. Scores are engineering judgement. Counsel must verify every claim chart, especially the §5 rebuttals.
- The 28-entry search was web-limited: Google Patents page fetches were blocked; Espacenet and PatBase were unreachable; 7 entries are snippet-level; EP/CN/WO claims were not read (AI-08–AI-10, NA-08, NA-13, NA-15–NA-18). The claim-level Espacenet run in §8.2 is the mitigation.
- Pending applications filed from roughly **April 2025** onward may not be visible. Expect the real landscape to be somewhat more crowded than this assessment shows — which is an argument for filing sooner, not for filing broader.
- Legal statuses and assignees are machine-derived; verify before relying on them.
