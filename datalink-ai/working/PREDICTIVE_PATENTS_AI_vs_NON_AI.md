# Predictive datalink and connectivity patents: AI/ML vs. non-AI/ML

- **Search date:** 2026-10-09
- **Scope:** predictive datalink, satcom, air-to-ground (ATG) and UAS command-and-control (C2) link systems, read as the aviation datalink space of the `datalink-ai/` project. Generic cellular and vehicle items appear only as labelled background (tier T3).
- **Companion file:** `PREDICTIVE_PATENTS_AI_vs_NON_AI.csv` (same 28 entries, same IDs).
- **Status:** 28 records. Group A (AI/ML): 10. Group B (without AI/ML): 18. Unresolved: 0. Verification: 18 at claim level, 1 abstract/summary, 2 family-level (status from a snippet), 7 snippet-only. This is a deep sample, not a census (section 9).

## Bottom line

- **Claimed AI/ML in aviation connectivity prediction sits mainly in one family:** Panasonic Avionics' in-flight outage prediction (AI-01, AI-02). Other claimed-ML hits are generic cellular or 5G (AI-03, AI-05, AI-08) or aircraft maintenance prediction (AI-04, AI-07). AI-06 (Honeywell LRU) discloses ML only as an optional method.
- **Non-AI aviation and satcom prediction is the larger group:** Satcom Direct (NA-01, NA-02), Viasat (NA-03), Gogo (NA-04), Rockwell Collins UAS C2 (NA-05), Ericsson UAV handover (NA-06), Honeywell ground-side datalink selection (NA-07, NA-08, NA-13), Hughes (NA-09), and two aircraft satcom handover publications seen only in snippets (NA-17, NA-18).
- **Closest to the repo's ground-side datalink concept:** NA-07 and its EP family (rule-based datalink and transmit-timing selection; claims verified; no ML), and AI-06 (LRU fault prediction with a wireless data offload on landing; ML optional).
- **Gap hypothesis (test before relying on it):** no verified hit predicts CPDLC, ADS-C or ACARS delivery or latency from message-level data, or pairs a deterministic verdict with a gated, advisory ML layer (section 10).

## 1. Scope and definitions

- **Datalink:** air-ground and ground-air links: CPDLC, ADS-C, ACARS, satcom, ATG cellular, UAS C2, and ground-side datalink management. Generic cellular, vehicle and HF propagation items appear only where they are labelled.
- **Predictive:** the claimed system forecasts or pre-computes a future or unobserved link or service state (availability, quality, handover target or time, outage probability, failure) before it occurs.
- **AI/ML (test):** the prediction step is produced by a learned model.
  - **YES, claimed:** the claims recite machine learning, a neural network, LSTM/RNN, a random forest or a trained model.
  - **OPTIONAL:** the description discloses ML as one embodiment, and the claims read do not require it.
  - PCA compression alone does not count.
- **Non-AI/ML (test):** the prediction is deterministic or statistical: geometry or orbit, link budget, coverage overlay, flight-plan computation, averages or medians, thresholds, business rules, or a search or optimizer with no learning step. "No ML" means no ML in the claims read and in the description portion read.

## 2. Method and verification

- **Sources:** Justia Patents (primary for US records); FreePatentsOnline (secondary); Google Patents search snippets for EP, CN and WO records and for status and family links (Google Patents page fetches were blocked); the repo's `PRIOR_ART_DATASET.csv` for cross-checks; arXiv and web snippets for non-patent art.
- **Query families:** aircraft satcom and ACARS predictive datalink; HF datalink prediction; tactical datalink prediction; ACARS/VDL/satcom selection with ML; ML connectivity prediction for aircraft; predictive maintenance of avionics radios; UAV C2 link prediction; OEM predictive connectivity; satcom handover prediction; HF propagation prediction; Chinese airborne datalink fault prediction; the Satcom Direct, Gogo, Viasat and Honeywell families; Airbus, Thales, Intelsat, Anuvu and Inmarsat connectivity forecasts.
- **Verification levels:**
  - **Claim-level:** claim text read.
  - **Abstract/summary:** abstract or summary read; claims not read.
  - **Family-level:** status and family link from a snippet; claims not read.
  - **Snippet-only:** search-result text only.
- **Relevance tiers:**
  - **T1 (core):** aircraft, UAS or satcom/ATG link availability, quality, handover or outage prediction, or ground-side datalink selection.
  - **T2 (close):** generic wireless link prediction; predictive maintenance that uses datalink transport; older or HF propagation forecasting.
  - **T3 (background):** generic cellular or vehicle; planning rather than link prediction; aircraft maintenance prediction without a datalink.

## 3. Group A: using AI/ML

| ID | Patent and title | Assignee | Filed or priority → status | Predictive mechanism | AI/ML determination and basis | Tier | Verification |
|---|---|---|---|---|---|---|---|
| AI-01 | [US 11,546,875 B2](https://patents.justia.com/patent/11546875), Network connection outage prediction for commercial passenger vehicle | Panasonic Avionics Corporation (Justia lists "Panasonic") | Filed 2020-09-30 → issued 2023-01-03 | Predicts the probability of an in-flight satcom outage along the planned route (weather-related, polar, tail-blockage) from upcoming-travel information, route history and regulation information. | **YES, claimed.** The server applies a machine learning algorithm to determine the outage probability along the planned route. | T1 | Claims 1–20 read; title and dates verified |
| AI-02 | [US 11,455,839 B2](https://patents.justia.com/patent/11455839), Network connection outage prediction due to antenna failure using machine learning | Panasonic Avionics Corporation | Filed 2020-12-23 as CIP of 17/039,712 (filed 2020-09-30) → issued 2022-09-27 | Predicts the probability of an antenna-caused outage from flight information and antenna-related data (description: fault-trap data offloaded from logs). | **YES, claimed.** Claims 1 and 13 apply the ML algorithm to flight information to output the antenna-outage probability. | T1 | Claims 1 and 13 read (earlier session); title and dates verified |
| AI-03 | [US 11,159,408 B2](https://patents.justia.com/patent/11159408), Link performance prediction technologies | Intel Corporation | Filed 2019-06-25 (appl. 16/452,352) → issued 2021-10-26 | Layered prediction (cell load, intra-cell, geoposition, cell transition, topology) yields predicted metrics (bandwidth, latency, capacity, coverage holes). An LPP engine fuses them and sends the forecast to applications and network nodes. | **YES, in dependent claims.** Claim 1 (apparatus) is ML-neutral. Claims 8–9 recite ML algorithms per layer. Claims 13–22 recite ML models (LSTM/RNN; random-forest or CPT options). | T2 | Claims 1, 8–9 and 13–22 read. Continuation US 11,711,284 B2 (granted 2023-07-25) not checked |
| AI-04 | [US 11,465,779 B2](https://patents.justia.com/patent/11465779), Predictive maintenance system using avionics Ethernet networks | Rockwell Collins, Inc. | Filed 2019-08-14 (pub. US 2021/0047056 A1) → issued 2022-10-11 | LRU-resident ML algorithms assess equipment health from sensor telemetry. The telemetry is compressed by principal components and sent as payloads over real-time avionics networks to onboard or ground destinations. Predicts equipment health, not link state; the network is the transport. | **YES, claimed.** Claim 1 stores ML algorithms, each with an identifier and scalar parameters, used to assess system health. | T2 | Claim 1 read in part; title and dates verified |
| AI-05 | [US 12,652,602 B2](https://patents.justia.com/patent/12652602), Adaptive transmission and transmission path selection based on predicted channel state (grant of US 2023/0007564 A1, published 2023-01-05) | Qualcomm Incorporated | Filed 2021-06-30 (appl. 17/305,119) → issued 2026-06-09 | A transmitter node predicts a future channel state at a future instant with an ML model (weights, current and previous states), then selects transmission parameters for that instant. | **YES, claimed.** Claims 1 (method), 12, 20 (CRM) and 27 (apparatus) recite ML prediction of a future channel state. Claims 7 and 18 recite gate and layer updates. Detection of an ML outage event is also recited. | T2 | Claims 1–28 read; title, dates and status verified. Generic 5G; not aviation |
| AI-06 | [US 9,550,583 B2](https://patents.justia.com/patent/9550583) (pub. US 2016/0257429 A1), Aircraft LRU data collection and reliability prediction | Honeywell International Inc. | Filed 2015-03-03 → issued 2017-01-24. Continuation US 9,969,508 B2 (appl. 15/378,601, filed 2016-12-14) not checked | An LRU collects in-flight operational data. On landing it opens a wireless link to a ground station to offload the data. A remote system predicts LRU failure conditions by comparing data across LRUs and aircraft. | **OPTIONAL, not claimed.** Claims 1–8 recite a prediction "based on the operational data" with no ML. The description says the fault-prediction module "may rely on one or more rules, algorithms, or other suitable techniques" and gives a machine-learning module that develops rules from past operational data as one example. | T2 | Claims 1–8 read; description chunks 5–6 read. Classed here because the description discloses ML as a prediction method |
| AI-07 | [US 10,457,423 B2](https://patents.google.com/patent/US10457423B2/en), System and method for aircraft failure prediction | The Boeing Company | Filed 2017-09-22 → issued 2019-10-29 | An ML model classifies multidimensional operation data to predict a future maintenance message for an aircraft component (APU example). A partial-dependency output explains each prediction. Maintenance prediction, not a datalink. | **YES, claimed** (claim 1, earlier session). | T3 | Claim 1 read; abstract verified. Related: US 2019/0100335 A1 (ML-predicted maintenance messages from MEL-filtered history; status not checked) |
| AI-08 | [WO 2020/254859 A1](https://patents.google.com/patent/WO2020254859A1/en), Machine learning for handover | Telefonaktiebolaget LM Ericsson AB (inventors Hugo Tullberg, Johan Ottersten) | PCT/IB2019/055181 filed 2019-06-19 → published 2020-12-24; family status "ceased" | A sequential time-based ML model predicts the time of a UE handover to a target cell from radio-link-monitoring measurements and geographic positions. The handover is executed if enough time remains. | **YES** (abstract and snippet). Sequential ML (RNN/LSTM per the earlier summary). Generic cellular. | T3 | Abstract and snippet only; claims not read |
| AI-09 | WO 2022/000365 A1, ML downlink channel prediction (title not recorded) | Not verified (possibly Qualcomm) | Not checked | ML predicts downlink channel conditions for a generic wireless link. | **YES** (snippet). | T3 | Snippet only |
| AI-10 | US 2024/0106508 A1, AI-enabled link adaptation (title not recorded) | Not verified | Application publication (2024); status not checked | An AI model predicts a suitable modulation and coding scheme ahead of use (generic cellular). | **YES** (snippet). | T3 | Snippet only |

## 4. Group B: without AI/ML

| ID | Patent and title | Assignee | Filed or priority → status | Predictive mechanism | Non-AI basis | Tier | Verification |
|---|---|---|---|---|---|---|---|
| NA-01 | [US 10,939,304 B2](https://patents.justia.com/patent/10939304), System and method for forecasting availability of network services during flight | Satcom Direct, Inc. | Priority 2018-06-29 (US 62/691,883); filed 2019-07-01 (16/458,936) → issued 2021-03-02 (pub. US 2020/0008079 A1; PCT WO 2020/006559 A1) | Retrieves the flight plan (waypoints), couples the flight path with satellite-provider coverage data, and forecasts the route segments where service will be unavailable and when. | **NO.** Claim 1 is a geometric coupling of flight path and coverage data. | T1 | Claim 1 read; dates verified |
| NA-02 | [US 11,398,158 B2](https://patents.justia.com/patent/11398158), same title (continuation-in-part) | Satcom Direct, Inc. | CIP of 16/458,936 (= US 10,939,304); filed 2021-03-02 (appl. 17/190,315; pub. US 2021/0183254 A1) → issued 2022-07-26 | A connectivity forecast system ranks available connectivity providers by priority and segments the flight path by the highest-priority available provider. | **NO.** Claims 1–18 read; no ML. | T1 | Claims 1–18 read; dates verified |
| NA-03 | [US 11,115,114 B2](https://patents.justia.com/patent/11115114), Handover of a mobile terminal in a multi-beam satellite based on network conditions | Viasat, Inc. (inventor Fred Treesh) | Continuation of 16/368,307 (filed 2019-03-28), itself a continuation of 15/666,257 (filed 2017-08-01; pub. US 2019/0044611 A1). Filed 2020-04-13 → issued 2021-09-07 | Retrieves flight-plan data for aircraft. Scores each candidate beam by predicted beam utilization over the service timeframe, selects beams, and schedules handovers. | **NO** in the claims read. Claims 8 and 17 use "predicted spectral efficiency" as an input; no learned model is recited. | T1 | Claims read (claims 1, 8, 10 and 17 cited); dates verified |
| NA-04 | [US 12,273,783 B2](https://patents.justia.com/patent/12273783), Neighbor list and beam management for ATG systems | Gogo Business Aviation LLC | Filed 2022-05-11 → issued 2025-04-08 | An aircraft UE builds candidate cells from its location and a stored sitemap (cell locations and orientations), computes a link-loss metric (likelihood of establishing the ATG link), and beams to the best cell. | **NO.** Claim 1 uses sitemap geometry and antenna-gain tables; no learned model. | T1 | Claim 1 read; title and dates verified |
| NA-05 | [US 11,423,789 B2](https://patents.google.com/patent/US11423789B2/en), System and method for preventing inadvertent loss of command and control link to an unmanned aerial system | Rockwell Collins, Inc. | Filed 2019-12-05 → issued 2022-08-23 | Builds a C2-link quality model for a planned UAV route from historical data. Compares in-flight C2 link quality with the model. On deviation, triggers prescribed flight-plan maneuvers before C2 is lost. | **NO** in the claims read. | T1 | Claims read (earlier session); title verified |
| NA-06 | [US 10,952,113 B2](https://patents.justia.com/patent/10952113), Planned continuity of unmanned aerial vehicle (UAV) link connectivity in UAV traffic management systems | Telefonaktiebolaget LM Ericsson (per earlier search; Justia assignee field blank) | PCT/US2017/050046 filed 2017-09-05 → issued 2021-03-16 | On a handover condition, the controller picks the target cell from the UAV's flight path, sends a handover request with a time value, starts a timer, and caches data and spoofs keep-alive messages until the UAV reconnects or a loss is reported. | **NO.** Claims 1–17 (method, CRM, network device) recite flight-path cell selection, timers and spoofing. The description says only that the network "can learn how handovers are executed," with no ML. | T1 | Claims 1–17 read; description chunks 0 and 10 read; chunks 1–9 not read for ML |
| NA-07 | [US 10,380,899 B2](https://patents.justia.com/patent/10380899), Ground direction of aircraft datalinks | Honeywell International Inc. | Filed 2016-09-13 (appl. 15/264,549) → issued 2019-08-13 (pub. US 2018/0075756 A1) | A ground-side manager analyzes incoming data (aircraft location and flight mode, weather, maps, ATC) and assesses outgoing messages (urgency, size, priority) against datalink criteria (cost, time, availability by flight phase). A "best result" selection module picks the outgoing datalink and transmit timing by balancing these. Anticipatory selection; no forecasting model described. | **NO.** Claims 1, 8 and 17 recite the best-result algorithm. No ML in claims 1–20 or in description chunks 0–2 of 5. Honeywell lists this family as available for purchase or licence. | T1 | Claims 1–20 read; description chunks 0–2 of 5 read |
| NA-08 | EP 3 793 103 A1, Ground direction of aircraft datalinks (divisional) | Honeywell International Inc. | Priority 2016-09-13; filed 2017-09-06 (EP 20205226.2, divisional of EP 3 293 893) → published 2021-03-17; withdrawn 2021-06-09 | Same mechanism as NA-07 (family description). | **NO** (family description). | T1 | Google snippet for status and family link (12 claims); claims not read |
| NA-09 | [US 11,032,751 B2](https://patents.justia.com/patent/11032751), User terminal handover prediction in wireless communications systems with nonstationary communications platforms | Hughes Network Systems, LLC | Filed 2019-01-21 (pub. US 2019/0230568 A1) → issued 2021-06-08 | For each satellite beam and time instant, estimates the signal strength seen at the terminal from link budget and satellite ephemeris (earlier read), and predicts handover times between beams. | **NO** (abstract and summary). | T2 | Abstract and summary read; claims not read; aircraft use not confirmed |
| NA-10 | [US 5,943,629 A](https://patents.google.com/patent/US5943629A/en), Method and apparatus for real-time ionospheric mapping and dynamic forecasting | TCI International, Inc. | Filed 1997-03-31 → issued 1999-08-24; expired | Updates an ionospheric model from real-time propagation measurements and forecasts HF propagation conditions. | **NO** (claim 1). | T2 | Claim 1 read (FreePatentsOnline); expired |
| NA-11 | [US 9,858,824 B2](https://patents.justia.com/patent/9858824), Flight plan optimization for maintaining internet connectivity | Rockwell Collins, Inc. (per earlier search) | Filed 2015-07-14 → issued 2018-01-02 | Receives internet-connectivity data per airspace region and determines or adjusts flight plans that keep connectivity. Planning, not link prediction. | **NO.** | T3 | Summary and claim 14 read; title and dates verified |
| NA-12 | [US 7,912,490 B2](https://patents.google.com/patent/US7912490B2/en), Method for channel quality prediction for wireless communication systems | InterDigital Technology Corp. | Filed 2003-10-31 → issued 2011-03-22 | Predicts a future CQI from current and stored measurements (statistical). Generic cellular, old. | **NO** (claim 1). | T3 | Claim 1 read (FreePatentsOnline) |
| NA-13 | EP 3 293 893 B1, Ground direction of aircraft datalinks (parent of NA-08) | Honeywell International Inc. | Priority 2016-09-13; filed 2017-09-06 (EP 17189721.8) → grant date not checked; status "not in force" (Google) | Same description as NA-07. | **NO** (family description). | T1 | Google snippet only (status); claims not read. Honeywell licensing material lists the same title (EP3293893, CA2977498) |
| NA-14 | [US 11,223,969 B2](https://patents.justia.com/patent/11223969), Method and apparatus for predicting a quality of service for the communication about at least one communication link of at least one communication device (with server and computer program) | Volkswagen AG (per earlier search) | EP priority 2018-10-02 (EP 18198192.9) → issued 2022-01-11 | A device sends a QoS-prediction request for a planned travel route with capacity requirements. The server finds the cells along the route and predicts QoS on a 5G network-slicing basis, with channel-model, traffic-flow and surroundings prediction blocks (claims 7–9). | **NO** in claims 1–13 read. The prediction blocks are not recited as learned. Description not checked for ML. | T3 | Claims 1–13 read; automotive, not aviation |
| NA-15 | US 11,206,078 B2, satellite subbeam handover based on predicted user-terminal location (title not recorded) | Amazon (per earlier search) | Not checked → granted (B2) | Predicts the terminal location and orbital data to hand over subbeams in advance (LEO/NGSO). | **NO** (snippet). | T2 | Snippet only |
| NA-16 | CN 107852230 A, LEO satellite handover from ephemeris (title not recorded) | Not verified | Not verified | The terminal computes its handover schedule from satellite ephemeris. | **NO** (snippet). | T2 | Snippet only |
| NA-17 | CN 105591685 A, VSAT cross-beam switching for airborne vehicles (title not recorded) | Not verified | Not verified | Predicts cross-beam switching points for an airborne VSAT from GPS navigation data. | **NO** (snippet). | T1 | Snippet only |
| NA-18 | US 2017/0127323 A1, single-modem satellite handover for aircraft terminals (title not recorded) | Not verified | Application publication (2017); status not checked | Predicts when the serving satellite will set, so the handover can be scheduled with a single modem. | **NO** (snippet). | T1 | Snippet only |

## 5. Not placed in either group

No unresolved entries. The Honeywell LRU patent (AI-06) is in Group A because its description discloses ML as a prediction method. Its claims do not require ML, and it is marked OPTIONAL in the table.

## 6. Adjacent, excluded, or non-predictive

### 6a. Adjacent AI/ML (not datalink link prediction)

- **US 11,488,063 B2** (Honeywell): cloud-trained reinforcement learning served to a flight management system. AI/ML; not link prediction (repo dataset).
- **US 11,212,015 B2** (The Aerospace Corporation): ML interference suppression. AI/ML; not a predictive link (repo dataset).
- **US 12,211,388 B2** (Thales): ML anomaly detection on aircraft trajectories. AI/ML; not datalink (repo dataset).
- **CN 122389618 A** (2026): Transformer-based reliability prediction for airborne equipment. AI/ML; not datalink (snippet).
- **CN 101063643 A**: neural network plus fuzzy-expert aircraft fault diagnosis. Hybrid; not datalink (snippet).

### 6b. Adjacent monitoring (not prediction)

- **US 2025/0260475 A1** (Satcom Direct, "Systems and methods for aircraft datalink performance monitoring"; priority 2024-02-09; published 2025-08-14; pending). Ground-side monitoring of CPDLC and ADS-C timing against RCP/RSP benchmarks, identification of the delay-causing step, and VHF/satcom reconfiguration. This is monitoring, not prediction. The repo dataset rates it "Critical" overlap with the DATALINK AI monitoring concept.

### 6c. Reviewed and excluded

- **US 7,729,263 B2** (Honeywell, "Aircraft data link network routing"): reassigns message routes when network availability changes across flight phases. Reactive. Excluded.
- **US 6,308,045 B1** (wireless ground-link roaming; expired; reexamined): reactive link monitoring. Excluded.
- **US 2012/0214420 A1** (aircraft datalink network for training fleets): not predictive. Excluded.
- **US 12,652,603** (Gogo, "Traffic steering optimization"; title verified): routes aircraft traffic to gateways or APNs. Not predictive.
- **US 12,652,083** (Gogo, "Systems and methods for satellite selection using beamscanning techniques"; title verified): LEO satellite selection under ITU power-flux-density limits, from orbit and antenna-angle tables. Constraint-based. Borderline; excluded.
- **US 11,518,517** (Panasonic, "Predictive preference selection for in-vehicle entertainment systems"; title verified): content preference, not connectivity. Excluded.
- **EP 2 040 392 B1**: QAR data routed over the datalink for ground evaluation. Not predictive (repo dataset; assignee not verified).

## 7. Non-patent prior art

- **arXiv:2504.14443**, "SkyNetPredictor" (April 2025 ID): LSTM and KNN pre-flight network-performance prediction. **AI/ML.** Read in an earlier session; not re-read now.
- **arXiv:2508.00877**, "Satellite Connectivity Prediction for Fast-Moving Platforms" (August 2025 ID): ML predicts the GEO satellite CNR category for aircraft from flight logs; F1 about 0.97 (from the abstract). **AI/ML.** Abstract and conclusion read.
- **arXiv:2501.07743**, "The Reliability of Remotely Piloted Aircraft System Performance under Communication Loss and Latency Uncertainties" (January 2025): CTMC model of RCP availability and continuity, with Monte Carlo simulation. **Non-AI.**
- **ResearchGate**, "Handover Prediction for Aircraft Dual Connectivity Using Model Predictive Control": MPC plus a 2D genetic-algorithm optimizer. **Non-learning.** Borderline: a GA is a search heuristic, not ML. Authors and year not verified.
- **Springer (2026)**, "A handover strategy for air-to-ground communication based on a fast prediction model": method not verified.

## 8. Unverified leads (not counted)

- **Viasat parent application 16/368,307** (filed 2019-03-28; "Handover Based on Predicted Network Conditions"): the number and status were not found in search. It may be a separate grant in the NA-03 family.
- **Viasat family publication US 2019/0044611 A1** (appl. 15/666,257): not checked.
- **Intel continuation US 11,711,284 B2** (appl. 17/505,919; granted 2023-07-25): claims not checked. Family of AI-03.
- **Honeywell continuation US 9,969,508 B2** (appl. 15/378,601; filed 2016-12-14): not checked. Family of AI-06.
- **Honeywell CA 2 977 498** ("Ground direction of aircraft datalinks"): listed in Honeywell's licensing material; status not checked. Family of NA-07.
- **Satcom Direct PCT WO 2020/006559 A1** (family of NA-01 and NA-02): status "inactive" per a PitchBook listing; not checked further.
- **Hughes grants with inventors Arur, Ravishankar and Corrigan:** issued 2021-06-22 (filed 2019-12-18), 2023-04-04 (filed 2021-05-21) and 2023-11-07 (filed 2023-02-28). An inventor-page snippet describes blockage-based handover-time determination, but which grant it belongs to was not checked. Titles, claims and AI status not checked.
- **Boeing US 2019/0100335 A1** ("Aircraft maintenance message prediction"; ML on MEL-filtered maintenance messages): adjacent AI/ML; status not checked.
- **Galaxy Space (China, 2026):** ML-based predictive LEO handover, from a Patsnap blog summary only. Number unknown.
- **Huawei (China, 2025):** antenna-state switching precomputed from ephemeris (non-ML), from a Patsnap blog summary only.

## 9. Limitations and gaps

1. **Database access.** Google Patents page fetches were blocked. FreePatentsOnline returned HTTP 500 for several numbers, so Justia was the main US source. EP, CN and WO records were checked only from snippets. No Espacenet, Lens, PatBase or Derwent access.
2. **Recall.** Web search is not a patent full-text database. No CPC or claim-level query was possible. The result is a sample, not a census.
3. **Publication lag.** US applications publish about 18 months after filing. Filings from roughly April 2025 onward are generally not yet published, so pending applications in this area are a blind spot.
4. **Claim depth.** 18 entries are at claim level. 1 is abstract or summary only (NA-09). 2 are family-level (NA-08, NA-13). 7 are snippet-only (AI-08, AI-09, AI-10, NA-15, NA-16, NA-17, NA-18). Each row states its level.
5. **Assignee and status gaps.** AI-09 and AI-10 assignees not verified. NA-06's Justia assignee field is blank; attribution is from an earlier search. NA-08 and NA-13 status and family link come from Google snippets. NA-16 to NA-18 assignees not verified.
6. **Definitional calls.** "Predictive" and "AI/ML" are judgement calls. AI-06 is classed as OPTIONAL. NA-07 is classed as anticipatory selection, not forecasting. Averages, medians and link-budget computations are non-AI. A GA optimizer is treated as non-learning.
7. **Scope assumption.** "Datalink" is read as the aviation datalink and satcom, ATG and UAS C2 space. Generic cellular and vehicle items are included only as labelled T3 background. This comes from the repo and was not confirmed with the user. Coverage is mainly US.
8. **Not legal advice.** No freedom-to-operate, validity or infringement view is given. Legal status (expiry, maintenance fees) was checked only where noted.

## 10. Observations for the DATALINK AI filing (to validate)

- **Closest AI/ML overlaps:** AI-01 and AI-02 (ML outage prediction for aircraft satcom from flight and route data). AI-06 (LRU fault prediction from fleet data with a wireless ground offload; ML optional). AI-03 (layered predictions fused into one forecast; generic). AI-05 (ML channel-state prediction driving path selection; generic).
- **Closest non-AI overlaps:** NA-07, NA-08 and NA-13 (ground-side datalink selection and transmit timing from rules; closest to the ground-side datalink manager concept). NA-03 (flight-plan-driven beam scheduling). NA-05 (C2-link quality model with deviation triggers). NA-06 (predictive target-cell and timer-based UAV handover).
- **Mapping to the repo's claim hooks** (Datalink_AI_Live_Architecture.docx, Section 10):
  - **Requirement-mapped findings with a deterministic verdict:** no verified hit pairs these. NA-07 is the nearest rule-based selector, but it maps nothing to requirement identifiers.
  - **Coverage-erosion account (not-exercised set over routes and software loads):** no hit found.
  - **Label flywheel for safety-gated, ground-learned advisory models:** partial at best. AI-06 has an ML module that develops rules from past operational data, but no confirmation labels or gating are recited. AI-04 has no feedback loop in claim 1.
  - **Conformance record (content hash, ledger, deterministic replay) and ACMS report definitions:** not searched in this round.
- **Gap hypothesis:** no verified hit predicts CPDLC, ADS-C or ACARS delivery or latency from message-level data, or pairs a deterministic verdict with a gated advisory ML layer. Test this with a full-text search before relying on it.

## 11. Suggested next steps

1. Run a full-text claim search in Espacenet or PatBase: CPC H04B 7/18502 (airborne stations) and H04W 36/ (handover) with "aircraft" or "predict"; G06N 20/ with "datalink", "satcom" or "ACARS".
2. Sweep assignees: Panasonic Avionics, Satcom Direct, Viasat, Gogo, Rockwell Collins, Honeywell, Boeing, Thales, Airbus, Ericsson, Hughes, Intel, Qualcomm (generic).
3. Chase the leads in section 8: Viasat 16/368,307; Intel US 11,711,284; Honeywell US 9,969,508 and CA 2 977 498; the EP 3 293 893 grant and claims; the Hughes NGSO family; Boeing US 2019/0100335.
4. Read in full before drafting claims: AI-01, AI-02, AI-03, AI-05, and the description of NA-06 (chunks 1–9) for ML terms.
5. Confirm the scope with the user: aviation-only, or generic wireless as well.
