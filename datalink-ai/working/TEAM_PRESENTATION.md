# DATALINK: FROM COMPLAINTS TO PROOF
### Team brief — Situation · Target · Solution · Benefits

---

## 1 · SITUATION — checked like it's 1995

- Datalink is **mandated**: CPDLC/ADS-C, PM-CPDLC in Europe, PBCS RCP 240 on NAT/Pacific — **7,000+ aircraft** run on one CMU family alone.
- But performance is checked **monthly, by hand, in spreadsheets** — and dashboards work **after landing**. Nobody sees it live. Nobody sees it coming.
- Real causes hide **months to years** (ICAO problem reports → OEM software fixes). Meanwhile the **aircraft's own computer is invisible** — its delays look like network problems, so the network gets blamed and a working radio gets swapped.
- **The leak is proven:** avionics NFF **20–50%** of removals · maintenance **USD 5.05M per aircraft/year** (IATA) · AOG **USD 10k–150k per hour** · **0 of 128 requirements** have per-flight proof.
- 28 patents predict **the link**. Nobody predicts **the requirement**.

## 2 · TARGET — who pays, how big

- **Airline** (reliability, flight ops/PBCS, OCC) + **OEM** (support/warranty/engineering). ANSPs and CSPs benefit as users.
- **Beachhead:** one airline fleet + one OEM programme. 90-day demo — zero partnerships needed to start.
- **Market:** aircraft health monitoring **USD 5.4B → 7.4B by 2030** (8.3% CAGR). Our slice — datalink requirement assurance — **USD 100–150M/year, and it is empty.**

## 3 · SOLUTION — check → attribute → predict → prove

| | One line |
|---|---|
| **CHECK** | Every transaction against its requirement — **with the margin**, not just pass/fail |
| **ATTRIBUTE** | The delay budget split across network / radio / **the aircraft's own computer** / crew |
| **PREDICT** | Margin decay warns **while still compliant**, with a projected violation date |
| **PROVE** | Replayable evidence records + coverage account — the pack airline, OEM and auditor all need |
| **LEARN** | AI only proposes, gated and recorded — **the product works with AI switched off** |

*Believable because:* start with **3 requirements** (RCP 240, RSP 180, response window) · **no new hardware, no change to certified software** · patent space checked across 40+ references and confirmed open.

## 4 · BENEFITS — the money and the proof

| Who | Gets | Worth |
|---|---|---|
| **Airline** | ≥**60%** of issues caught before any complaint · evidence in **<15 min** · NFF **−20%** · PBCS proved **per flight** | **USD 1.4–5.0M/yr per 500 tails**; one avoided AOG (USD 10k–150k/hr) can pay the year |
| **OEM** | Defects known **before the customer complains** · warranty bounded · fleet actions targeted (23 tails, not 200) · new services line | **USD 1.7–6.5M/programme/yr** — sponsors 30–60% of the airline fee from its own savings |

**The example:** 737-8s miss RCP 240 on Pacific crossings. Reports flag it weeks later; the network gets blamed. **We find it in days:** AOC database rev 12.4 queues **180 of the 240 seconds inside the CMU** at VHF↔SATCOM transitions — network proved clean. Fix verified in AirSim, rolled to **23 tails, not 200**. Fleet action avoided. Warranty avoided. The airline hears it **from us, first.**

**Our commitment:** *if the pilot doesn't hit ≥60% before-complaint detection and <15-minute evidence — don't buy it.*

**The ask:** approve the **90-day wedge** — AirSim lab + own receivers + 3-requirement verdict engine on one airline feed. File the provisional before any external demo.

---
*Sources: FAA FIT/27 · Honeywell Forge PBCS · ICAO APAC FIT-Asia 2025–26 · MDPI Aerospace (NFF 20–50%) · IATA FY2024 benchmarking · AOG economics (Boeing/IATA cited) · TBRC AHM market. Commercial figures are our planning estimates (architecture §8), to be validated in customer interviews.*
