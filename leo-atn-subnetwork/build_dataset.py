#!/usr/bin/env python3
"""Single source of truth for the LEO-ATN-subnetwork prior-art dataset.

Run:  python3 leo-atn-subnetwork/build_dataset.py
Writes PRIOR_ART_DATASET.csv and PRIOR_ART_DATASET.json next to this file.
"""
from __future__ import annotations

import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

META = {
    "title": "Prior art dataset - LEO broadband as a CMU ATN/IPS subnetwork (performance-earned admission)",
    "search_date": "2026-10-14",
    "sources": ["Google Patents (patent pages + xhr/query endpoint)", "Justia Patents", "public web / standards bodies"],
    "clusters": {
        "A": "Safety / ATS traffic over non-safety or broadband IP links (closest art)",
        "B": "CMU / router multi-subnetwork selection, preference tiers, policy routing",
        "C": "RCP/RSP performance measurement and performance-triggered link (re)configuration; IPS multilink scoring",
        "D": "LEO / satellite architectures and terminals for aviation",
        "N": "Non-patent literature (standards, regulator papers, trade press)",
    },
    "disclaimer": "Automated landscape screen, not a legal opinion. Dates marked n/v were not verified against the register. "
                  "Pending applications have an 18-month publication blind window: filings after ~2025-04 are invisible.",
}

REFS = [
    # ---------------------------------------------------------------- A: safety over non-safety / broadband
    dict(id=1, pub="EP4513465A1", title="Air ground communication method for transmitting safety messages over non safety infrastructure",
         assignee="Rockwell Collins France SAS", inventors=["Frederic Trincal", "Stephane Pelleschi", "Jeremie Liverneaux", "Frederic Maison", "Laurent Leonardon"],
         priority="2023-08-21", published="2025-02-26", family=["US 18/809,014 -> US20250069511A1"], status="Pending", cluster="A",
         cpc=["H04B7/18506", "H04W4/42", "H04L", "G08G"], overlap="CRITICAL",
         disclosure="Virtual Safety Radio (VSR) exposed to the ACD router (CMU/ATSU) through a cross-router (X-router) interface to AISD/PIESD routers. "
                    "VSR determines by active and/or passive link probing that a non-safety media link (cellular 5G, cabin SATCOM) is available; a Multi-Link Engine "
                    "selects the best non-safety media from media status + probe result; messages are secured by cryptography and tagged with metadata; a ground "
                    "tunnel endpoint / ground gateway decapsulates, verifies and routes to ACARS / ATN-OSI endpoints; if no acknowledgement within a time threshold "
                    "the VSR reports link failure and the ACD router re-sends over a safety media (HF/VDL/SATCOM). Spec explicitly covers SNDCF frames and A618 blocks "
                    "over the AISD network, states applicability to ATN/IPS, cites RCP/RSP (DO-350A/ED-228A) and the EASA/FAA Hyperconnected ATM white paper, and "
                    "notes the ACD router may 'select which kind of ACARS and/or ATN/OSI traffic it will convey via the AISD/PIESD'.",
         differentiation="Reactive (ack-timeout) fallback and a single availability determination. No per-traffic-class / per-airspace statistical RCP admission "
                         "state machine, no shadow dual-cast evidence building, no constellation-aware prediction, no RCP-budget hedge timing, no composite-availability "
                         "construction from multiple LEO links, no signed on-board evidence record bound to admission decisions.",
         verification="Full text (description + 15 claims) read on Google Patents"),
    dict(id=2, pub="US20250069511A1", title="Air ground communication method for transmitting safety messages over non safety infrastructure",
         assignee="Rockwell Collins France SAS", inventors=["Frederic Trincal", "Stephane Pelleschi", "Jeremie Liverneaux", "Frederic Maison", "Laurent Leonardon"],
         priority="2023-08-21", published="2025-02-27", family=["EP4513465A1"], status="Pending", cluster="A", cpc=["H04B7/18506"], overlap="CRITICAL",
         disclosure="US member of ref 1 (filed 2024-08-19). Same abstract: VSR via X-router; determine non-safety media link available; send ACD application message via it.",
         differentiation="As ref 1.", verification="Abstract and bibliographic data from Justia"),
    dict(id=3, pub="US10425149B1", title="ACARS over IP system for non-safety messages",
         assignee="Honeywell International Inc.", inventors=["Thomas D. Judd", "Thomas F. McGuffin", "Scott James Redmond", "Justin Schassler"],
         priority="2018-08-22", published="2019-09-24", family=["EP19192684.9", "CN201910667811.X"], status="Granted", cluster="A",
         cpc=["H04W4/42", "H04B7/18506", "H04L67/12"], overlap="HIGH",
         disclosure="CMU coupled to safety subnetworks (VHF/SATCOM/HF) and to an AOIP computing device coupled to a non-safety IP broadband subnetwork (Wi-Fi, cellular, "
                    "broadband SATCOM). AOIP device classifies ACARS messages as safety / non-safety, forwards non-safety over IP, and signals availability / unavailability "
                    "to the CMU so that safety messages are never stranded on the non-approved link; discusses DO-178B level and 10-12 min NO COMM problem.",
         differentiation="Hard split: safety traffic never uses the broadband link. Our idea is the opposite - earn admission of ATS classes with measured performance.",
         verification="Description chunks read on Google Patents"),
    dict(id=4, pub="EP3654548B1", title="Vehicle multi-communication message type communication system",
         assignee="Honeywell International Inc.", inventors=["Andrew James Fraser", "Thomas D. Judd"], priority="2018-11-13", published="2021-05-12",
         family=["US 16/189,871"], status="Granted", cluster="A", cpc=["H04W88/16", "H04L12/40"], overlap="MODERATE-HIGH",
         disclosure="CMU routes some ACARS (non-safety) messages to a data gateway which returns a pseudo-acknowledgement per block to the CMU and converts the message to "
                    "an IP message for a faster broadband path; cites FR2920622 and WO2006/026632 (ACARS over TCP/IP).",
         differentiation="Non-safety only; pseudo-ack trick. No performance qualification of the IP path for ATS.", verification="Description read on Google Patents"),
    dict(id=5, pub="US20260006496A1", title="Communications management systems and methods",
         assignee="Rockwell Collins France SAS", inventors=["Frederic Trincal", "Stephane Pelleschi"], priority="2024-06-28", published="2026-01-01",
         family=["EP24306052.2"], status="Pending", cluster="A", cpc=["n/v"], overlap="MODERATE-HIGH",
         disclosure="Aerospace communications router fed by per-media microservice controllers (HF/VHF/UHF, Wi-Fi, cellular, satellite); each controller normalises link status, "
                    "speed, latency, signal quality, media cost into a common format and only relays it to the router once the media policy governing that device is fulfilled; "
                    "may use sensor data in that determination.",
         differentiation="Policy gate on *media information*, not a statistical RCP admission of *traffic classes*; no evidence collection, no prediction, no hedging.",
         verification="Summary read on Justia"),
    dict(id=6, pub="US10412051B2", title="System and method for satellite communications link",
         assignee="Honeywell International Inc.", inventors=["Radek Zaruba", "David Whittleton", "Andrew James Fraser"], priority="2017-02-08", published="2019-09-10",
         family=["EP17200290.9", "US20180227272A1"], status="Granted", cluster="A", cpc=["H04L63/08", "H04L69/16"], overlap="MODERATE",
         disclosure="Separate secure communications processor installed between the aircraft router and an existing SwiftBroadband satcom radio so that legacy radios can use the "
                    "encrypted SB-Safety service; routes ACARS, ATN/OSI and ATN/IPS.",
         differentiation="Precedent for a 'bolt-on' certified adapter that upgrades an IP bearer to safety use - supports obviousness of E1; nothing on admission logic.",
         verification="Background/summary read on Google Patents"),
    dict(id=7, pub="US8774795B2", title="Reconfigurable satcom avionics radio",
         assignee="Honeywell International Inc.", inventors=["Radek Zaruba"], priority="2011-05-20", published="2014-07-08", family=["EP", "CN", "CA"], status="Granted",
         cluster="A", cpc=["H04B7/185"], overlap="MODERATE",
         disclosure="Reconfigurable radio unit providing simultaneously at least one safety-certified cockpit channel and one cabin-services channel.",
         differentiation="Hardware partitioning of one radio; no CMU-side qualification of a cabin bearer.", verification="Claim snippet from Google Patents query"),
    dict(id=8, pub="US20250253929A1", title="EFB or AID communication media for datalink message transmission and reception",
         assignee="Honeywell International Inc.", inventors=["Divya Swarup Giriyappa Srinivasan"], priority="2024-02-01", published="2025-08-07", family=[], status="Pending",
         cluster="A", cpc=["n/v"], overlap="MODERATE",
         disclosure="Communications management system forwards downlink messages to an EFB and/or Aircraft Interface Device which transmits them over its own (non-certified) "
                    "link, and receives uplinks the same way.",
         differentiation="Another 'borrow a non-certified link' architecture; no performance admission, class ladder or evidence.", verification="Summary read on Google Patents"),
    dict(id=9, pub="US20150215899A1", title="Secure aircraft data transmission using multiple communication channels",
         assignee="The Boeing Company", inventors=[], priority="n/v", published="2015-07-30", family=[], status="n/v", cluster="A", cpc=["n/v"], overlap="MODERATE",
         disclosure="Communication channel manager on the aircraft allocates ACD / AISD / PIESD data domains to available channels (BPL, Ethernet, Wi-Fi, cellular, satellite) by channel "
                    "security level, cost, speed and available duration; same domain may be split across channels.",
         differentiation="Security-level matching at the gate; not in-flight RCP qualification.", verification="Abstract/summary from Google Patents"),
    dict(id=10, pub="EP2315367B1", title="Aeronautical security management over broadband air/ground network",
         assignee="Honeywell International Inc.", inventors=["Aloke Roy"], priority="2009-10-22", published="2013-08-28", family=["US", "CN"], status="Granted",
         cluster="A", cpc=["n/v"], overlap="LOW-MODERATE",
         disclosure="Security parameters established with ground entities before take-off over broadband and reused in flight for protected message exchange along the flight path.",
         differentiation="Security bootstrap only.", verification="Claim snippet from Google Patents query"),
    dict(id=11, pub="US7395344B2", title="Method for ACARS application communication over an IP network",
         assignee="The Boeing Company", inventors=[], priority="n/v", published="2008-07-01", family=[], status="Granted (likely expired)", cluster="A", cpc=["n/v"], overlap="LOW",
         disclosure="ARINC 619 ACARS messages packaged for Ethernet/AFDX using TFTP; on-board router-to-end-system transport, not air-ground.",
         differentiation="Transport detail only.", verification="FreePatentsOnline summary"),
    dict(id=12, pub="US6677888B2", title="Secure aircraft communications addressing and reporting system (ACARS)",
         assignee="Honeywell International Inc.", inventors=["Aloke Roy"], priority="n/v", published="2004-01-13", family=[], status="Expired", cluster="A", cpc=["n/v"], overlap="LOW",
         disclosure="End-to-end cryptographic protection and compression of ACARS payloads between CMU and ground FEP.",
         differentiation="Background for 'secure the payload, not the bearer'.", verification="PDF front page"),
    # ---------------------------------------------------------------- B: CMU multi-subnetwork selection
    dict(id=13, pub="US7027812B2", title="Channel selection in aircraft communications system by determining zone load and selecting alternate carrier",
         assignee="Honeywell International Inc.", inventors=[], priority="2000-07-05", published="2006-04-11", family=["WO2002003572A1", "US20020009993A1"], status="Expired",
         cluster="B", cpc=["H04B7/18506"], overlap="HIGH",
         disclosure="CMU/MU selects the preferred air/ground subnetwork and VHF frequency from a user-loadable (AMI) database of channel preferences per region; preference codes "
                    "SAT/HF/VHF-n/NONE; 'easily supports the addition of new channels or subnetworks by defining new subnetwork codes in the preference tables'; dynamic reordering on status.",
         differentiation="Directly anticipates 'register LEO as its own CMU preference tier'. That element cannot carry the filing.", verification="Description read on Google Patents"),
    dict(id=14, pub="US7729263B2", title="Aircraft data link network routing",
         assignee="Honeywell International Inc.", inventors=[], priority="2007-08-08", published="2010-06-01", family=["US20090041041A1", "EP2023685A1"], status="Granted",
         cluster="B", cpc=["H04B7/18506"], overlap="HIGH",
         disclosure="CMU message-routing function with programmable routing and network-selection rules over ACARS VHF/SATCOM, Wi-Fi, WiMAX, cellular WAN and ATN, keyed on flight "
                    "phase, OOOI state, position/trajectory, message priority, availability and cost; re-assigns routes as prescribed criteria change.",
         differentiation="Rule-table selection by aircraft state; no measured-performance admission, no statistical criteria, no prediction of bearer outages.",
         verification="Description table read on Google Patents"),
    dict(id=15, pub="US8433817B2", title="Routing-profile-based ACARS routing system",
         assignee="Thales", inventors=[], priority="n/v", published="2013-04-30", family=[], status="Granted", cluster="B", cpc=["n/v"], overlap="MODERATE-HIGH",
         disclosure="Avionic application attaches per-message media permissions and preference order (e.g. HF forbidden; VHF then SATCOM); routing profiles include emulated VHF "
                    "over ATN via GACS and new media such as WiMax, WiFi, GSM, UMTS; cost ordering.",
         differentiation="Static, application-declared preferences.", verification="Description read on Google Patents"),
    dict(id=16, pub="US8484384B2", title="ACARS router for remote avionic applications",
         assignee="Thales", inventors=[], priority="n/v", published="2013-07-09", family=["EP2188974A1", "CN101803328B"], status="Granted", cluster="B", cpc=["n/v"], overlap="MODERATE",
         disclosure="ACARS router on AFDX with dynamic application registration; routes over HF/VHF/SATCOM 'or even WiMAX or Wi-Fi subnetworks' by priority and routing-strategy indications.",
         differentiation="Router architecture only.", verification="Description read on Google Patents"),
    dict(id=17, pub="US11146329B1", title="Systems and methods for multilink aircraft communication",
         assignee="Rockwell Collins, Inc.", inventors=["William T. Greenleaf"], priority="2018-06-08", published="2021-10-12", family=[], status="Granted", cluster="B",
         cpc=["H04B7/18506"], overlap="HIGH",
         disclosure="On-board supervisory controller receives dynamic performance measurements from radios (SNR in both directions per link: VHF, HF, SATCOM, ...), uses link quality, "
                    "cost at current position and message classification/priority to pick the link; ground message manager fronts ACARS, ATN/OSI and IP end systems; ad-hoc air-air relay.",
         differentiation="Instantaneous quality + cost + priority selection. No transaction-level RCP statistics, no qualification states, no evidence output.",
         verification="Summary/description read on Google Patents"),
    dict(id=18, pub="US20050286452A1", title="Method and system for bi-directional exchange of data based on user-defined policies for the selection of a preferred datalink",
         assignee="Hardgrave, Steve (applicant)", inventors=["Steve Hardgrave"], priority="2004-05-18", published="2005-12-29", family=[], status="n/v", cluster="B", cpc=["n/v"], overlap="LOW-MODERATE",
         disclosure="User-defined policies select the preferred datalink for bidirectional aircraft data exchange.", differentiation="Policy routing background.",
         verification="Citation list of US8433817B2"),
    dict(id=19, pub="FR2787658A1", title="Ground/aircraft digital exchange management with multiple communication links and cost/zone dependent routing",
         assignee="Sextant Avionique", inventors=[], priority="1998-12-18", published="2000-06-23", family=[], status="Expired", cluster="B", cpc=["n/v"], overlap="LOW",
         disclosure="Calculator automatically determines transmission routing over multiple links by cost and zone.", differentiation="1998 background.",
         verification="Citation list of US8433817B2"),
    dict(id=20, pub="US8045977B2", title="Method for maintaining datalink network throughput by delaying lower priority messages",
         assignee="Honeywell International Inc.", inventors=[], priority="n/v", published="2011-10-25", family=["US8200213B2"], status="Granted", cluster="B", cpc=["n/v"], overlap="MODERATE",
         disclosure="CMU measures round-trip message time and channel occupancy; delays low-priority messages when congestion thresholds are exceeded.",
         differentiation="Per-link congestion control; evidence that on-board RTT measurement in a CMU is old.", verification="Metadata / abstract"),
    # ---------------------------------------------------------------- C: performance monitoring & triggered reconfiguration, IPS multilink
    dict(id=21, pub="US20250260475A1", title="Systems and methods for aircraft datalink performance monitoring",
         assignee="Satcom Direct, LLC", inventors=["Nicholas Cook", "Daniel Sundby"], priority="2024-02-09", published="2025-08-14", family=["PCT/US2025/015174"], status="Pending",
         cluster="C", cpc=["H04B7/18506", "H04B17/364"], overlap="HIGH",
         disclosure="Ground/cloud real-time monitoring of CPDLC/ADS-C exchanges against PBCS benchmarks (RCP 240 / RSP 180, 95 % and 99.9 % criteria), per-step timestamps, "
                    "identification of the step causing delay, NOC alerting and reconfiguration of the datalink (VHF <-> satellite).",
         differentiation="Ground-side, after-the-fact, per-aircraft reconfiguration; not an on-board per-class admission state machine for a non-certified bearer.",
         verification="Full text (see ../datalink-ai package)"),
    dict(id=22, pub="US10453347B2", title="Method and systems for increasing capacity and safety of aeronautical safety-of-life services and data links",
         assignee="Thales Alenia Space Italia S.p.A.", inventors=["Roberto Winkler"], priority="2015-10-22", published="2019-10-22",
         family=["CN108140327A", "BR112018008054B1", "EP16730703.2", "JP2018520431A", "IL258353"], status="Granted", cluster="C", cpc=["H04W72/542", "G08G5/00"], overlap="MODERATE-HIGH",
         disclosure="Distributed safety-of-life datalink system (terrestrial + satellite AMS(R)S) receives quality measurement data for a SoL service/data link used by an aircraft together "
                    "with the aircraft's 4-D position/trajectory and adapts communication resources / bearer provisioning for performance-based, trajectory-based operations.",
         differentiation="Ground-centric resource adaptation of *certified* AMS(R)S bearers using 4-D trajectory; no admission of a non-certified LEO path, no constellation handover prediction.",
         verification="Description read on Google Patents (CN member)"),
    dict(id=23, pub="CN120856635B", title="ATN/IPS-oriented aviation mobility and multilink management method",
         assignee="Beijing Tianhua Hangtong Technology Center (LP)", inventors=["Li Silei"], priority="2025-09-23", published="2026-04-21", family=[], status="Granted (CN)", cluster="C",
         cpc=["n/v"], overlap="MODERATE-HIGH",
         disclosure="Airborne IPS router monitors each link (active + passive): signal strength, delay jitter, packet loss, throughput; marks unavailable links; computes a link state value "
                    "vs calibration reference / history / environmental factor; normalises, entropy-weights and ranks links; builds an airborne routing table (IP range, link instance ID, "
                    "traffic classifier, status, priority) and signals it to the ground agent in AGMI messages.",
         differentiation="Generic metric scoring and IPS mobility signalling; no PBCS statistical thresholds per class/airspace, no shadow dual-cast, no LEO ephemeris prediction. CN only.",
         verification="Description read on Google Patents"),
    dict(id=24, pub="CN118200224A", title="Method for selecting aviation data transmission links based on VIKOR decision",
         assignee="Beihang University", inventors=["Wang Zhipeng"], priority="2024-04-26", published="2024-06-14", family=[], status="Pending (CN)", cluster="C", cpc=["n/v"], overlap="MODERATE",
         disclosure="Multi-attribute (VIKOR) utility matrix over heterogeneous air-ground links to select a link.", differentiation="Decision-theory scoring; no safety admission concept.",
         verification="Snippet from Google Patents query"),
    dict(id=25, pub="CN121483092A", title="ATN B2 application system and method for broadband communication in civil aviation",
         assignee="Beihang University", inventors=["Wang Zhipeng"], priority="2025-11-10", published="2026-02-06", family=[], status="Pending (CN)", cluster="C", cpc=["n/v"], overlap="MODERATE",
         disclosure="ATN B2 (CM/CPDLC/ADS-C) applications carried over a civil-aviation broadband link with CM login via onboard terminal and user management.",
         differentiation="Shows the trend 'B2 over broadband' is being filed in CN; no admission/fallback logic visible in the snippet.", verification="Claim snippet from Google Patents query"),
    dict(id=26, pub="CN120050214A", title="LISP protocol-based ATN ground-air data link switching delay test method",
         assignee="CAAC Second Research Institute", inventors=["Zhang Zhongjin"], priority="2024-09-04", published="2025-05-27", family=[], status="Pending (CN)", cluster="C", cpc=["n/v"], overlap="LOW-MODERATE",
         disclosure="Test bench measuring link-switching delay for LISP-based ATN/IPS air-ground mobility.", differentiation="Test method only.", verification="Snippet"),
    # ---------------------------------------------------------------- D: LEO / satellite architectures
    dict(id=27, pub="EP4572182A1", title="Aircraft datalink based on a terrestrial to LEO satellite cellular transceiver and associated spectrum",
         assignee="Rockwell Collins, Inc.", inventors=["James P. Mitchell"], priority="2023-12-15", published="2025-06-18", family=["US"], status="Pending", cluster="D",
         cpc=["H04B7/185"], overlap="MODERATE",
         disclosure="Radio + phased-array antenna inside the nose radome establishes a LEO link in L-band / 3GPP bands (direct-to-cell style) and an air-to-ground link; radio selects between "
                    "them by connectivity; links may carry ACARS messages; router coupled via wireless bridge.",
         differentiation="Hardware / installation patent; selection is binary connectivity. Confirms LEO-for-ACARS is in the record.", verification="Description read on Google Patents"),
    dict(id=28, pub="US9356686B1", title="Polar satcom system and related method",
         assignee="Rockwell Collins, Inc.", inventors=["James P. Mitchell"], priority="2013-12-20", published="2016-05-31", family=[], status="Granted", cluster="D", cpc=["H04B7/185"], overlap="LOW-MODERATE",
         disclosure="GEO satcom extended to polar regions via a relay satellite in LEO/MEO/HEO.", differentiation="Space-segment topology.", verification="Claim snippet"),
    dict(id=29, pub="CN114337793A", title="Airborne data link communication system and method supporting multi-protocol stack and cross-domain communication",
         assignee="CETC Avionics Co., Ltd.", inventors=["Liu Tianhua"], priority="2022-01-28", published="2022-04-12", family=[], status="n/v (CN)", cluster="D", cpc=["n/v"], overlap="MODERATE",
         disclosure="Airborne datalink system combining ACARS and ATN/OSI stacks with cross-domain communication.", differentiation="Architecture; no LEO or admission logic visible.",
         verification="Claim snippet"),
    dict(id=30, pub="CN114500370A", title="Airborne ATN/IPS router supporting 4D tracking",
         assignee="CETC Avionics Co., Ltd.", inventors=["Lin Jing"], priority="2022-01-25", published="2022-05-13", family=[], status="n/v (CN)", cluster="D", cpc=["n/v"], overlap="LOW-MODERATE",
         disclosure="Airborne ATN/IPS router architecture for 4-D trajectory operations.", differentiation="Architecture only.", verification="Snippet"),
    dict(id=31, pub="US11509675B2", title="Systems and methods for cyber monitoring and alerting for connected aircraft",
         assignee="Honeywell International Inc.", inventors=["Amit Srivastav"], priority="2020-09-25", published="2022-11-22", family=[], status="Granted", cluster="D", cpc=["n/v"], overlap="LOW",
         disclosure="Connected-aircraft cyber monitoring; mentions ATN/IPS routers with QoS as communication gateways.", differentiation="Context only (security monitoring of IPS gateways).",
         verification="Snippet"),
    # ---------------------------------------------------------------- N: non-patent literature
    dict(id=32, pub="NPL-1", title="Future Connectivity for Aviation - EU/US Task Force White Paper (EASA/FAA with Airbus/Boeing)",
         assignee="EASA / FAA", inventors=[], priority="2022-11", published="2022-11-09", family=[], status="Published", cluster="N", cpc=[], overlap="CRITICAL (concept)",
         disclosure="Defines 'Hyperconnected ATM': offload AOC from safety links to non-safety links (cabin SATCOM, A2G), names LEO/MEO constellations as the cost-effective, future-proof option, "
                    "requires 'appropriate security protections' and 'adequate link status and performance monitoring', and calls for performance-based standards for Hyperconnected ATM; "
                    "lists the IPS roadmap, B2/EPP milestones (2027) and Boeing ecoDemonstrator IPS CMU trials.",
         differentiation="Destroys novelty of the *concept* (broadband for ATM traffic). It does not describe any admission mechanism - it asks for one to be standardised.",
         verification="PDF excerpts via search (easa.europa.eu/en/downloads/137252/en)"),
    dict(id=33, pub="NPL-2", title="EASA webinar 'Future Connectivity for Aviation' - Hyperconnected ATM overview", assignee="EASA", inventors=[], priority="2023-02-01", published="2023-02-01",
         family=[], status="Published", cluster="N", cpc=[], overlap="HIGH (concept)",
         disclosure="Roadmap slides: communications not subject to RCP offloaded from safety links; 'Ground SATCOM Performance Class B'; transparent integration of multiple datalinks; ACARS-over-IP standardisation.",
         differentiation="Concept only.", verification="Slide text via search (easa.europa.eu/en/downloads/137554/en)"),
    dict(id=34, pub="NPL-3", title="ICAO Doc 9896 - Manual on the ATN using IPS Standards and Protocols (3rd ed.)", assignee="ICAO", inventors=[], priority="n/a", published="2022 (ed.3)",
         family=[], status="Published", cluster="N", cpc=[], overlap="HIGH (substrate)",
         disclosure="IPv6-based ATN/IPS with mobility, multilink operation, DTLS security, naming/addressing; link state signalled for multilink. Defines the very notion of an IPS 'access network' / subnetwork.",
         differentiation="Our LEO adapter is an instance of an IPS access network; novelty must come from the admission/scheduling logic, not from carrying IPS over IP.",
         verification="NASA NTRS 20190001799 summary; RFC 9372 references"),
    dict(id=35, pub="NPL-4", title="ICAO Doc 9869 PBCS Manual / RTCA DO-350A - EUROCAE ED-228A (PBCS SPR)", assignee="ICAO / RTCA / EUROCAE", inventors=[], priority="n/a", published="2017 / 2016",
         family=[], status="Published", cluster="N", cpc=[], overlap="HIGH (thresholds)",
         disclosure="RCP 240: ET 240 s (99.9 %), nominal TT 210 s (95 %); technical allocation ACTP <= 120 s @95 % and <= 150 s @99.9 %; RSP 180: ASP <= 90 s @95 %, <= 180 s @99.9 %; "
                    "availability and continuity parameters; monitoring and alerting criteria.",
         differentiation="The thresholds are public standards and not protectable; using them as *admission gates for a non-certified bearer, measured on board* is the claimable step.",
         verification="FAA PARC 2018 letter tables; CASA/Bahamas PBCS guidance"),
    dict(id=36, pub="NPL-5", title="ARINC 858 Part 1 (2024), Part 2 IPS Gateway (2024), Part 3 Common IPS Radio Interface Protocol (2023)", assignee="AEEC / SAE ITC", inventors=[],
         priority="n/a", published="2023-2024", family=[], status="Published", cluster="N", cpc=[], overlap="HIGH (substrate)",
         disclosure="Avionics requirements for IPS for aeronautical safety services, ACARS/IPS gateway interoperability and a common radio-to-IPS-router interface (link status, QoS).",
         differentiation="Defines how a radio presents itself to an IPS router; a LEO terminal presenting through this interface is an obvious step - again, claim the admission logic.",
         verification="Normadoc listing; RTCA SC-223 minutes"),
    dict(id=37, pub="NPL-6", title="ARINC 771 (LEO aviation satcom), ARINC 781 (L-band), ARINC 791/792 (Ku/Ka cabin satcom)", assignee="AEEC", inventors=[], priority="n/a", published="various",
         family=[], status="Published", cluster="N", cpc=[], overlap="MODERATE",
         disclosure="Installation / interface standards for LEO (Iridium) cockpit satcom and for Ku/Ka cabin terminals (Ethernet ports, power, antenna).",
         differentiation="Shows LEO *cockpit* satcom (Iridium Certus) is already a certified safety bearer and that cabin terminals expose IP ports.", verification="RTCA SC-223 minutes"),
    dict(id=38, pub="NPL-7", title="RFC 9372 - L-band Digital Aeronautical Communications System (LDACS)", assignee="IETF", inventors=["N. Maeurer", "T. Graeupl", "C. Schmitt"], priority="n/a",
         published="2023-03", family=[], status="Published", cluster="N", cpc=[], overlap="MODERATE",
         disclosure="Describes the Future Communications Infrastructure multilink concept: 'depending on link quality, communication can be switched seamlessly from one data link technology to another'; "
                    "link state (up/down) reported via the ATN/IPS Aircraft Protocol (AIAP) mandated by ICAO WG-I for multilink; appendix summarises DO-350A RCP/RSP parameters.",
         differentiation="Concept-level multilink; no non-certified bearer admission.", verification="RFC text via search"),
    dict(id=39, pub="NPL-8", title="IETF draft-templin-atn-aero-interface (AERO/OMNI) and NASA NTRS 20190001799 'ICAO ATN/IPS' briefing", assignee="Boeing / NASA", inventors=["Fred L. Templin"],
         priority="n/a", published="2019", family=[], status="Published", cluster="N", cpc=[], overlap="MODERATE",
         disclosure="IPv6 'aero' interface over multiple ANET data links with dynamic link selection, multilink, QoS signalling, mobility and route optimisation for ATN/IPS.",
         differentiation="Protocol machinery for multilink IPS; no RCP admission.", verification="IETF datatracker; NTRS PDF"),
    dict(id=40, pub="NPL-9", title="Airbus FAST article 'Cockpit SATCOM - Light Cockpit Satcom (LCS)'", assignee="Airbus", inventors=[], priority="n/a", published="2022-04",
         family=[], status="Published", cluster="N", cpc=[], overlap="MODERATE",
         disclosure="Physical/logical segregation of ACD, AISD, PIESD; PKI mutual authentication and VPN tunnel to the ground gateway; cockpit satcom with 'cabin capability' as backup for cabin satcom "
                    "(the inverse direction of our idea); IP-based cockpit connectivity ~200 kbps on SB-S 2.0.",
         differentiation="Shows industry's current direction is cockpit-grade GEO L-band, with segregation; our idea reverses the direction with an admission gate.",
         verification="PDF via search"),
    dict(id=41, pub="NPL-10", title="Aviation Week 'Multi-Orbit Inflight Connectivity Gains Momentum' (Panasonic/OneWeb, Hughes Fusion, Stellar Blu ESA)", assignee="Aviation Week", inventors=[],
         priority="n/a", published="2025-04-08", family=[], status="Published", cluster="N", cpc=[], overlap="MODERATE (obviousness)",
         disclosure="In-flight switching between LEO and GEO networks by location and network conditions; LEO polar coverage; forward 193 Mbps / return 36 Mbps in flight test.",
         differentiation="Cabin multi-orbit switching is product reality; claiming 'switch LEO<->GEO on quality' alone is obvious.", verification="Article via search"),
    dict(id=42, pub="NPL-11", title="FAA PARC CWG recommendations on FANS-1/A over SwiftBroadband (letter to AVS, 2018-07-03)", assignee="FAA PARC", inventors=[], priority="n/a",
         published="2018-07-03", family=[], status="Published", cluster="N", cpc=[], overlap="MODERATE (regulatory precedent)",
         disclosure="Regional PBCS monitoring tables (ACP/ACTP 95 % and 99.9 % benchmarks, ASP for RSP 180) used to recommend operational approval of a new IP-based satcom bearer for FANS.",
         differentiation="Precedent that admission of a new bearer is decided on monitored PBCS statistics - our idea automates this per flight, per class, on board.",
         verification="PDF via search"),
    dict(id=43, pub="NPL-12", title="Aerospace Tech Review 'CPDLC Coming of Age' - Iris ATN/IPS flight trials; European multilink switch (LDACS, satcom, AeroMACS)", assignee="Trade press", inventors=[],
         priority="n/a", published="2022-04-24", family=[], status="Published", cluster="N", cpc=[], overlap="LOW-MODERATE",
         disclosure="Boeing/Inmarsat Iris trials of ATN/IPS; European future datalink to include a multilink switch; crew data traffic impacting ATN-B2 exchanges.",
         differentiation="Context.", verification="Article via search"),
    dict(id=44, pub="NPL-13", title="Iridium 'Satellite Communications & Commercial Aviation' (FANS over Iridium, ATS Safety Voice, Certus)", assignee="Iridium", inventors=[], priority="n/a",
         published="2025-12-16 (page)", family=[], status="Published", cluster="N", cpc=[], overlap="LOW-MODERATE",
         disclosure="LEO L-band (Iridium) already carries FANS CPDLC/ADS-C and ATS voice under ICAO rules with priority/pre-emption.",
         differentiation="Clarifies that 'LEO' per se is not new to safety services - what is new is *broadband Ku/Ka LEO without AMS(R)S status* earning admission.",
         verification="Web page"),
]

CSV_FIELDS = ["ref_id", "publication_number", "title", "assignee", "priority_date", "publication_date", "legal_status", "cluster", "overlap_vs_our_idea",
              "what_it_discloses", "differentiation_hook_for_our_filing", "verification"]


def main() -> None:
    csv_path = os.path.join(HERE, "PRIOR_ART_DATASET.csv")
    json_path = os.path.join(HERE, "PRIOR_ART_DATASET.json")
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for r in REFS:
            w.writerow({
                "ref_id": r["id"], "publication_number": r["pub"], "title": r["title"], "assignee": r["assignee"],
                "priority_date": r["priority"], "publication_date": r["published"], "legal_status": r["status"],
                "cluster": f"{r['cluster']} - {META['clusters'][r['cluster']]}", "overlap_vs_our_idea": r["overlap"],
                "what_it_discloses": r["disclosure"], "differentiation_hook_for_our_filing": r["differentiation"],
                "verification": r["verification"],
            })
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump({"meta": META, "references": REFS}, fh, indent=2, ensure_ascii=False)
    print(f"wrote {len(REFS)} references -> {csv_path}, {json_path}")


if __name__ == "__main__":
    main()
