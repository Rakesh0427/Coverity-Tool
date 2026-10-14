# Draft claim set — performance-earned LEO ATN/IPS subnetwork

*Drafting aid for patent counsel, not a filing. Terminology follows ICAO Doc 9869 (PBCS), Doc 9896 (ATN/IPS) and ARINC 858.*

## Definitions used in the claims

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

## Family 1 — Graduated, evidence-based admission with hedged dispatch

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

## Family 2 — Constellation-aware predictive scheduling

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

## Family 3 — Composite multi-constellation subnetwork

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

## Claim charts against the closest art

Legend: ● disclosed · ◐ partially / arguably disclosed · ○ not disclosed

### Chart A — Claim 1 (Family 1)

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

### Chart B — Claim 3 (hedged dispatch)

| Element | EP4513465A1 | US11146329B1 | US8045977B2 (Honeywell RTT) |
|---|---|---|---|
| Transmit on candidate first | ● | ◐ | ○ |
| Duplicate on certified link if no completion by a **hedge time** | ◐ re-send after acknowledgement time threshold (reactive) | ○ | ○ |
| Hedge time = requirement threshold − measured P99.9(certified) − margin | ○ (¶[0041] only notes remaining time exists) | ○ | ○ (measures RTT for congestion delay) |
| Measured certified-link percentile updated in flight per region | ○ | ○ | ◐ RTT measured, not per region or percentile |

### Chart C — Claim 16 (Family 2)

| Element | US10453347B2 (TAS-I) | EP4513465A1 | EP4572182A1 (Collins LEO radio) | Aviation Week 2025 multi-orbit IFC |
|---|---|---|---|---|
| Constellation state (satellite / handover / gateway / elevation) obtained on board | ○ (ground receives quality data) | ○ | ◐ radio knows connectivity | ◐ terminal switches by conditions |
| 4-D trajectory used | ● (ground) | ○ | ○ | ○ |
| Predicted-unavailability calendar computed on board | ○ | ○ | ○ | ○ |
| Overlap test against transaction expiration time | ○ | ○ | ○ | ○ |
| Pre-emptive move / advance / defer before the interval | ◐ resource adaptation on ground | ○ (reactive) | ○ | ◐ reactive switching |

### Chart D — Claim 21 (Family 3)

| Element | US9356686B1 | EP4513465A1 Multi-Link Engine | ICAO Doc 9896 multilink |
|---|---|---|---|
| Two independent NGSO candidate subnetworks on one aircraft | ○ | ◐ "several non-safety media" | ◐ |
| Composite availability / continuity statistics for admission | ○ | ○ | ○ |
| Independence monitor with collapse to single link | ○ | ○ | ○ |

## Drafting notes

* Keep "candidate subnetwork" generic in independent claims; make LEO (claim 13) and 5G ATG / LDACS dependents.
* Claim 1(c) is the backbone — do not drop "duplicates ... transaction identifier ... de-duplication" in any broadening.
* Avoid reciting a "cross-router interface" anywhere; describe the dedicated port / VLAN embodiment prominently (FTO vs EP4513465A1).
* Include CRM and ground-gateway claims (claim 15) so that the CSP side is covered independently of the avionics vendor.
* Provide worked numbers in the description (RCP 240: 150 − 95 − 10 = 45 s; RSP 180 equivalent) and the state diagram (Fig. 2).
