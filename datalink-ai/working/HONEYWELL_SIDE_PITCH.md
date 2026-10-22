# From Honeywell's Side — Problem, Idea, and the Money

**Prepared:** 2026-10-10 · **Audience:** Honeywell Aerospace (Datalink business: CMU Mark II+/Mark III, 777/787 CMF, Forge network, Datalink Services) and its airline customers · **Companion to:** `Datalink_AI_Live_Architecture.docx` §8, `FOUR_POINTS.md`, `IDEA_CORE.md`. Money figures are the architecture's indicative 2026–2028 planning estimates — label them as such in any external use.

---

## 1. Problem statement — as Honeywell feels it

> **We build the world's most trusted datalink computers — and we find out how they actually behave in service from complaint tickets, weeks late, with no evidence.**

Honeywell's CMU Mark II+ family flies on **7,000+ aircraft** [1](https://www.honeywellaerospace.com/content/dam/aerobt/en/documents/learn/products/navigation-and-radios/brochures/N61-2375-000-000_ES_CMU_Mark_II-bro.pdf) — the most popular datalink units in the market — and the same communications function flies on Boeing widebodies as the 777/787 CMF. The product is certified to DO-178B DAL C, flight-tested, audited, delivered. **Then it flies for 15 years in a configuration space the certification programme never saw:** partitions reloaded on-wing, airline-edited AOC databases, routing preferences per region, mixed modems and subscriptions, aging hardware. And when something intermittent goes wrong in that space, here is what Honeywell experiences today:

1. **The defect reports itself through the customer.** A ticket arrives — "the datalink misbehaved on the Pacific crossing" — weeks to months after the first occurrence, with no synchronised timestamps, no raw records, and no way to tell avionics from radio from crew. **The direction of the information flow is wrong:** engineering is on defence, not diagnosis.
2. **Warranty and NFF burn money and credibility.** A communications product line of this size carries **USD 20–60M of warranty cost per year** in the installed base; **20–30% of LRU removals test good** on the bench. Each removal-and-refit cycle with logistics and a spare costs **USD 5–15k** — and the warranty board decides from anecdote because the evidence was never produced.
3. **Fixes are blunt because populations are invisible.** When a real defect is bounded — one software load, one database revision, one modem combination — the lack of fleet-wide visibility forces **blanket service bulletins (USD 0.5–3M per fleet action)** instead of a fix limited to the affected tails.
4. **Support absorbs the un-diagnosable.** A large share of technical-support volume is configuration and environment questions that would disappear if the fleet's behaviour were visible with evidence.
5. **The slow loop is industry-wide and public.** Regional PBCS failures (VHF↔SATCOM transitions, CSP internetworking, avionics-specific issues) surface through **monthly manual ANSP monitoring** and take **months to years** to resolve through ICAO problem reports — even Boeing airframer software upgrades (e.g. AIMS updates to fix PBCS performance) enter service through that slow loop [4b](https://www.icao.int/sites/default/files/APAC/Meetings/2026/2026%20RASMAG-31/03-Working%20Papers/WP02-FIT-Asia-Meeting-Outcomes.pdf).
6. **Reputation is decided in public.** In a segment where the customer talks to competitors, being told by an airline that "the Honeywell datalink is unreliable" — without proof either way — is more expensive than any engineering programme.

**In one sentence:** the product is proven at delivery and **blind in service** — and that blindness costs warranty dollars, support capacity, campaign money, and the customer relationship.

---

## 2. The proposed idea — as a Honeywell offering

**Deploy "The Datalink Witness" as an in-service requirement assurance service on Honeywell Forge / Datalink Services** — a fleet-wide ground platform that consumes data the aircraft already produces and makes every datalink transaction self-proving.

**What it does (the mechanism):**

| # | Capability | Honeywell-specific hook |
|---|---|---|
| 1 | **Check** — every CPDLC/ADS-C/ACARS transaction scored against the requirement it must meet (RCP 240, RSP 180, response windows), **with the margin**, not just pass/fail | Forge already carries the messages and hosts a PBCS widget [2](https://aerospace.honeywell.com/us/en/about-us/news/2022/01/fans-datalink-update) — this goes from post-flight report to live verdict + margin |
| 2 | **Attribute** — the delay budget split across network / radio / **the aircraft's own computer** (CMU queue, partition overrun, AOC database logic, load mix) / crew | Only the OEM knows the partition architecture, the AOC database semantics and the routing-preference behaviour — attribution to the platform is **Honeywell's home ground** |
| 3 | **Predict** — margin decay per tail, load and route; alarm **while still conforming**, with a projected violation date; resource-exhaustion signatures (overruns in transmit windows, queue growth) | This is "prediction of datalink product internal failure" — the design-time MIPS argument, alive in service |
| 4 | **Prove** — hash-chained conformance records, deterministic replay, late-data verdict revisions, coverage account, evidence packs mapped to requirement IDs | The evidence pack travels with every warranty decision, every fleet fix, every airline audit |
| 5 | **Learn** — fleet-wide issue patterns in days (communication, links, OS task latency); AI gated and recorded; maintenance confirmations become labels and permanent monitors | AirSim verifies AOC database fixes before fleet deployment; ART deploys them — Honeywell already owns the fix loop |

**Why Honeywell is the natural owner of this:** the data (Forge feeds, DLR, ACMS/AOC reports), the product knowledge (partitioned software, CMM/ICD, APM configuration), the tooling (AirSim simulator, ART reconfiguration), the certification standing (DO-178B DAL C pedigree), and the customer relationships (Datalink Services). **No new avionics, no STC, no change to the certified product** — the conversation inside Honeywell is a data-services agreement, not an engineering programme.

**Design rule (also the patent position):** verdicts are deterministic; AI is advisory, admission-gated and recorded; certified airborne software is untouched.

---

## 3. The money — how this pays Honeywell, and how the Boeing-fleet customer benefits

### 3.1 What Honeywell earns and saves (per datalink programme, per year — §8.8)

| Money line | Indicative range | Mechanism |
|---|---|---|
| Warranty + NFF cost removed | **USD 0.5–2.0M** | 1–3% of the USD 20–60M warranty load; removals attributed to a partition / database / modem / radio / crew instead of a part number |
| Support cases deflected | **USD 0.3–1.0M** | 15–30% of technical-support volume becomes platform-detected events with evidence |
| Fleet-wide fixes bounded | **USD 0.2–1.0M** | One avoided or population-limited fleet action is worth USD 0.5–3M |
| Campaigns targeted + upgrade pull-through | **USD 0.2–0.5M** | Fewer, better-directed upgrades on the right tails |
| **New services revenue** | **USD 0.5–2.0M** | "Reliability Intelligence" sold alongside the maintenance agreement — high margin, zero new hardware, data asset that grows with the 7,000+ installed base |
| **Total OEM benefit** | **USD 1.7–6.5M / programme / year** | Licence/priced below the benefit (USD 1–5M + NRE) — or internally, the platform costs a fraction of the savings |

Plus two unpriced lines: **reputation** (defect found, explained and bounded by Honeywell before any customer complaint) and **defence** (Satcom Direct and others are building the customer's trust layer right now; the first OEM to own in-service evidence keeps the customer relationship).

### 3.2 How the money reaches Honeywell — the commercial structure

The airline does not have to fund this alone. The structure that closes deals (§8.7): **Honeywell sponsors 30–60% of the airline subscription out of its own warranty and support savings** — the OEM pays USD 1 to save USD 2–5. The remainder is airline subscription (USD 3,600–6,000/tail/yr) plus engineering services (requirement baselines, AOC report definitions, onboarding, USD 150–400k per engagement). Result at maturity (§8.10): conservative USD 2.9M → base USD 11.4M → upside USD 36.5M per year for the platform business, against a USD 100–150M/yr addressable market — **and the OEM line is roughly half the revenue.**

### 3.3 How the Boeing-fleet customer benefits — and why they pay

Take the concrete customer: **an operator of ~200 Boeing aircraft** (737 MAX/NG fleet with CMU Mark II+, and/or 777/787 fleet with the Honeywell CMF), flying domestic VDL2 plus oceanic FANS/PBCS routes.

**What this customer loses today** (scaled indicatively from §8.7's 500-tail case: USD 1.4–5.0M/yr → roughly **USD 0.6–2.0M/yr** at 200 tails):

| Loss today | Money |
|---|---|
| Disruptions attributable to comms + investigation time | ~USD 0.2–0.8M/yr |
| No-fault-found removals (20–30% test good; USD 5–15k per cycle) | ~USD 0.1–0.5M/yr |
| Engineering/audit/warranty effort assembling evidence by hand | ~USD 0.1–0.3M/yr |
| AOG/diversion tail risk (1–5 events at USD 30–80k) | ~USD 0.15–0.5M/yr |

**What they get with the platform on their Boeing fleet:**

1. **Disruption protection.** ≥60% of comms issues detected before any crew/OCC report; evidence in under 15 minutes (§8.6 targets). One avoided AOG/diversion (USD 30–80k) is a visible slice of the annual fee; the product is sold against tail risk — *"one avoided AOG and the year is paid for."*
2. **NFF stopped at the shop door.** The evidence pack (requirement, measured value, margin, configuration) travels with the removal so the shop reproduces the conditions — 20% relative reduction in NFF rate is the month-6 target.
3. **PBCS eligibility protected per flight.** Oceanic reduced separations depend on demonstrated RCP 240/RSP 180 performance [4](https://www.scottipc.com/news/38-scott-ipc-blog/67-performance-based-communication-and-surveillance). Per-flight conformance records replace sampled monthly reports — the compliance argument becomes arithmetic, and the fuel value of preferred NAT/Pacific tracks is preserved.
4. **Configuration truth.** Which tails carry which partition loads, AOC database revision, modem and subscription — campaigns reach only the tails that need them, aircraft stay in service.
5. **The relationship flips.** The customer learns about an issue **from Honeywell, with the evidence**, before they file a ticket — support conversations move from dispute to joint diagnosis.

**What they pay:** USD 0.7–1.2M/yr list for 200 tails; with the OEM-sponsored structure, roughly **USD 0.4–0.8M/yr** net — against USD 0.6–2.0M/yr of avoidable cost and the tail-risk argument. **ROI case:** one avoided fleet action or a handful of avoided NFF removals plus one PBCS issue caught before an approval review pays the year.

### 3.4 One worked example — a 737 MAX fleet, Pacific routes

A 737-8 group shows RCP 240 misses on Pacific crossings. Today: monthly ANSP/Forge PBCS reports flag "non-compliant" weeks later [2](https://aerospace.honeywell.com/us/en/about-us/news/2022/01/fans-datalink-update); an ICAO problem report crawls for months; the airline blames the network; a working radio gets swapped. **With the platform:** within days, the pattern engine shows the misses cluster on tails carrying **AOC database revision 12.4** and coincide with **VHF↔SATCOM transitions** — and **180 of the 240-second budget is consumed inside the CMU queue** behind the "queue non-critical until low-cost link" routing rule, while ground-station data proves the network was clean. Attribution: **platform/configuration, not the network.** Honeywell verifies the fix (DB 12.5) in **AirSim**, deploys via **ART** to the 23 affected tails — not 200. The airline's PBCS position is restored with evidence; a warranty claim and a fleet action are avoided; the customer hears it from Honeywell first. That single case is simultaneously the demo, the warranty argument, and the patent's worked example.

### 3.5 The money slide (copy-paste)

> **Honeywell's problem:** we learn how our own product behaves in service from complaint tickets — and pay USD 20–60M/yr warranty on comms lines, 20–30% of it no-fault-found, with fleet actions costing USD 0.5–3M each.
> **Honeywell's idea:** the Datalink Witness on Forge — check every transaction against its requirement (with margin), attribute to the real cause including the aircraft's own computer, warn before violation, and produce the evidence. No new hardware. No change to certified software.
> **The money:** USD 1.7–6.5M/programme/yr to Honeywell (warranty + support + bounded fixes + a new services line), and USD 0.6–2.0M/yr back to a 200-tail Boeing-fleet customer (disruptions, NFF, AOG tail risk, PBCS proof) — with the OEM sponsoring 30–60% of the subscription out of its own savings. **One avoided AOG pays the year; one bounded fleet action pays the programme.**

---

*Caveats: all money figures are indicative planning estimates (Datalink_AI_Live_Architecture.docx §8) for 2026–2028, to be validated by customer interviews; 200-tail numbers are scaled from the 500-tail case and must be re-derived per operator. This is a commercial framing, not legal or FTO advice. "Boeing customer" is read as the airline operating Boeing aircraft with Honeywell datalink equipment; Boeing the airframer benefits secondarily (in-service evidence for AIMS/CMF software issues, faster and narrower upgrade cycles than the ICAO problem-report loop).*
