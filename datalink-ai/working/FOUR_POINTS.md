# The Four Points — DATALINK AI (simple pitch version)

**Prepared:** 2026-10-10 · **Basis:** fresh research on existing datalink predictive methods (ICAO/FAA PBCS practice 2025–26, Honeywell Forge / CSP dashboards, ML research) compared against the idea in `Datalink_AI_Live_Architecture.docx`.

## Research snapshot: what "prediction" exists today

| Existing method | What it actually does | Its limit |
|---|---|---|
| **PBCS monitoring** (ANSP/FAA/ICAO, e.g. Airways NZ, fans-cra.com) [1](https://www.faa.gov/media/97231) [4](https://www.scottipc.com/news/38-scott-ipc-blog/67-performance-based-communication-and-surveillance) | Monthly extraction of CPDLC/ADS-C records → CSV/Excel → compliance report (RCP 240 / RSP 180 met: yes/no) | Backward-looking, monthly, manual; no cause, no prediction |
| **CSP/OEM dashboards** (Honeywell Forge PBCS widget, Satcom Direct, Collins ARINC) [2](https://aerospace.honeywell.com/us/en/about-us/news/2022/01/fans-datalink-update) | After each flight: where an exceedance happened, message logs, trend sorting; alerts after landing | Post-flight, not in-flight; shows *where*, never *why*; nothing about the aircraft's own computer |
| **ICAO problem-report loop** (FIT-Asia 2025–26) [1](https://www.icao.int/sites/default/files/APAC/Meetings/2025/2025%20FITAsia15/3-Working%20Papers/WP08-Data-Link-Performance-Report-for-Malaysia.pdf) [4b](https://www.icao.int/sites/default/files/APAC/Meetings/2026/2026%20RASMAG-31/03-Working%20Papers/WP02-FIT-Asia-Meeting-Outcomes.pdf) | States report failures → cause found over months/years → fix (e.g. RAT1 procedure; Boeing AIMS software upgrades) | The diagnosis loop runs at months-to-years speed |
| **Connectivity prediction research** (SkyNetPredictor 2025 [3](https://arxiv.org/html/2504.14443v1); CNR/handover ML [3b](https://arxiv.org/html/2508.00877); MPC handover) | ML predicts link signal quality / handovers / pre-flight network score along a route | Predicts **the link** (cabin-connectivity world); not requirement conformance, not the aircraft's own platform, no evidence |
| **Aircraft health management** (Boeing AHM, Airbus Skywise, OEM health) | LRU failure trends, maintenance alerts | Equipment-level, not per-transaction; not requirement-mapped |

**The comparison in one line:** every existing method either reports the past (monitoring), predicts the link (research), or tracks the equipment (health) — **nobody predicts requirement conformance, nobody attributes to the aircraft's own computer, and nobody produces evidence.**

---

## 1. What is the current situation

Aircraft fly safety-critical messages (CPDLC clearances, ADS-C reports) against hard requirements — e.g. **RCP 240: a clearance transaction must complete within 240 seconds, 95% of the time**. Today the world handles this with **monthly, manual, backward-looking checks**: ANSPs and dashboards tell you *whether* you complied last month and *where* an exceedance happened — after landing. When something goes wrong, the cause is chased by hand in a loop that takes **months to years** (ICAO problem reports, OEM software bulletins). Meanwhile the aircraft's own datalink computer — message queues, partition overruns, configuration and database changes after every load — is **invisible**, so its delays look like network problems. Result: complaints instead of causes, parts removed with no fault found, compliance proved by sampling, and "prediction" limited to link signal quality in research papers. **0 of 128 in-scope requirements have a per-flight evidence record today.**

## 2. Who is the target

- **Primary buyer: the airline** — reliability/engineering, flight operations (PBCS/A056 compliance) and OCC teams on datalink-equipped fleets (e.g. any fleet with a Honeywell CMU Mark II+ / FANS 1/A+).
- **Co-buyer: the OEM** (e.g. Honeywell Aerospace) — product support, warranty and engineering teams for the datalink product line.
- **Users who benefit without paying:** ANSPs and CSPs (better data for PBCS performance discussions).
- **The first beachhead:** one airline fleet + one OEM programme on the CMU Mark II+ (7,000+ aircraft installed base).

## 3. What is the proposed solution

A **ground platform that watches every datalink transaction live and makes it self-proving**:

1. **Real cause, per transaction** — split every delay across network leg / radio link / **the aircraft's own computer** (queue, partition, configuration) / crew, instead of stopping at the network.
2. **Prediction that matters** — track each requirement's *margin* per tail and load; alarm on **margin decay while still compliant**, with a projected violation date (like design-time MIPS margin, but alive in service).
3. **Evidence, not dashboards** — every verdict stored as a replayable, hash-chained conformance record mapped to requirement IDs, plus a coverage account (which requirements a route/load has stopped exercising).
4. **AI that can be trusted** — deterministic verdicts decide; ML only proposes, passes an admission gate (OOD/uncertainty/robustness), and every accept *and* reject is recorded. No change to certified software; the aircraft's existing data is enough.
5. **SW and HW issues found from the same live data** — OS task latency, partition scheduling, queue and fault counters are compared against **metrics we anchor to the requirements** (e.g. queue-residence share of the 240 s budget, partition overruns inside a transmit window); **AI creates new SW/HW metrics and finds issue patterns** in communication, links and OS task latency — advisory only, through the gate — and every confirmed pattern becomes a permanent monitor plus a label (the maintenance flywheel).

## 4. Who benefits from this idea — and how (with one example)

| Who | How they benefit |
|---|---|
| **Airline** | Issues found in minutes, not weeks; no-fault-found removals avoided (20–30% of removals test good today); one avoided AOG/diversion (USD 30–80k) can pay for the service; PBCS compliance proved per flight instead of sampled |
| **OEM** (e.g. Honeywell) | Learns about its own product's defects **before the customer reports them**; warranty spend bounded with evidence; fixes limited to affected loads/databases instead of fleet-wide actions (USD 0.5–3M each); new services revenue on the same contract |
| **ANSP / CSP** | Evidence-backed performance data instead of anecdote; problem reports arrive pre-diagnosed |
| **Everyone** | Safer datalink: degradation caught before the requirement breaks |

**One example (the AI102 case):** Flight AI102 (A350, Chennai→London) sends a CPDLC clearance reply that takes **310 seconds against a 240-second requirement**. Today this appears — three weeks later — as a complaint saying "the datalink was slow", the network gets escalated, maybe a working radio gets swapped, and nothing is proved. With our platform: within minutes the system shows the delay was **180 seconds of queuing inside the aircraft's own datalink computer**, co-occurring with a partition overrun inside the transmit window, while the network was clean (proved by ground-station data). The finding is attributed to **the aircraft platform, not the network**, tied to a specific software load and database revision across three tails, and saved as a replayable evidence record. The maintenance action is raised **while the aircraft is still in the air** — and the same record is what the airline, the OEM and the auditor all need.

---

*Sources: FAA FIT/27 (Airways NZ monthly PBCS monitoring) [1](https://www.faa.gov/media/97231); Honeywell Forge PBCS/Datalink widget [2](https://aerospace.honeywell.com/us/en/about-us/news/2022/01/fans-datalink-update); SkyNetPredictor [3](https://arxiv.org/html/2504.14443v1); CNR prediction [3b](https://arxiv.org/html/2508.00877); ICAO APAC FIT-Asia data-link performance reports 2025–26 [1](https://www.icao.int/sites/default/files/APAC/Meetings/2025/2025%20FITAsia15/3-Working%20Papers/WP08-Data-Link-Performance-Report-for-Malaysia.pdf) [4b](https://www.icao.int/sites/default/files/APAC/Meetings/2026/2026%20RASMAG-31/03-Working%20Papers/WP02-FIT-Asia-Meeting-Outcomes.pdf); A056/PBCS compliance practice [4](https://www.scottipc.com/news/38-scott-ipc-blog/67-performance-based-communication-and-surveillance). Money figures: `Datalink_AI_Live_Architecture.docx` §8 (indicative estimates).*
