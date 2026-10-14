#!/usr/bin/env python3
"""Generate the figures used by the LEO-ATN-subnetwork idea package.

Run:  python3 leo-atn-subnetwork/build_figures.py
Writes PNGs into leo-atn-subnetwork/figures/ (matplotlib only, no other deps).
"""
from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "figures")
os.makedirs(OUT, exist_ok=True)

NAVY = "#1b2a49"
BLUE = "#2e6fdb"
TEAL = "#1f8a70"
AMBER = "#d98e04"
RED = "#c0392b"
GREY = "#8a8f98"
LIGHT = "#f3f5f9"


def box(ax, xy, w, h, text, fc=LIGHT, ec=NAVY, fs=9, bold=False, lw=1.4):
    x, y = xy
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                       fc=fc, ec=ec, lw=lw)
    ax.add_patch(p)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
            color=NAVY, fontweight="bold" if bold else "normal", wrap=True)


def arrow(ax, a, b, color=NAVY, style="-|>", lw=1.4, ls="-", text=None, tpos=0.5, toff=(0, 0.12), fs=8):
    p = FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=12, color=color, lw=lw, linestyle=ls)
    ax.add_patch(p)
    if text:
        x = a[0] + (b[0] - a[0]) * tpos + toff[0]
        y = a[1] + (b[1] - a[1]) * tpos + toff[1]
        ax.text(x, y, text, ha="center", va="center", fontsize=fs, color=color,
                bbox=dict(fc="white", ec="none", pad=1.0))


# --------------------------------------------------------------------------- fig 1
def fig1_architecture():
    fig, ax = plt.subplots(figsize=(13, 7.2))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 7.2)
    ax.axis("off")
    ax.set_title("Fig. 1 — LEO broadband as a performance-earned ATN/IPS subnetwork of the CMU",
                 fontsize=13, color=NAVY, fontweight="bold", loc="left")

    # Aircraft domains
    ax.add_patch(FancyBboxPatch((0.3, 0.4), 7.9, 6.1, boxstyle="round,pad=0.02,rounding_size=0.15",
                                fc="white", ec=GREY, lw=1, ls="--"))
    ax.text(0.45, 6.3, "AIRCRAFT", fontsize=9, color=GREY, fontweight="bold")

    # ACD block
    ax.add_patch(FancyBboxPatch((0.5, 2.3), 4.4, 3.8, boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc="#e9f0fb", ec=BLUE, lw=1.4))
    ax.text(0.65, 5.85, "Aircraft Control Domain (ACD) — certified", fontsize=9, color=BLUE, fontweight="bold")

    box(ax, (0.7, 4.6), 1.9, 1.0, "ATS / AOC\napplications\n(CPDLC, ADS-C/EPP,\nFIS, AOC)", fs=8)
    box(ax, (2.8, 4.6), 1.9, 1.0, "CMU / ATSU\nrouter\n(ACARS, ATN/OSI,\nATN/IPS)", fs=8, bold=True)

    box(ax, (0.65, 2.5), 4.15, 1.7,
        "LEO Subnetwork Adapter (new)\n"
        "• Qualification state machine per (link × traffic class × FIR)\n"
        "• RCP/RSP measurement + evidence record\n"
        "• Constellation-aware scheduler (handover / gateway prediction)\n"
        "• Hedged dispatch with RCP budget accounting\n"
        "• Crypto endpoint (DTLS/IPsec) — cabin path is an untrusted pipe",
        fc="#fff6e5", ec=AMBER, fs=7.2)

    # certified radios
    box(ax, (5.3, 5.1), 1.4, 0.75, "VDR\nVDL Mode 2", fs=8)
    box(ax, (5.3, 4.1), 1.4, 0.75, "SDU\nL-band SATCOM\n(SB-S / Certus)", fs=7.5)
    box(ax, (5.3, 3.1), 1.4, 0.75, "HFDR\n(HFDL)", fs=8)

    # cabin domain
    ax.add_patch(FancyBboxPatch((0.5, 0.6), 7.5, 1.4, boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc="#f7f7f7", ec=GREY, lw=1.2))
    ax.text(0.65, 1.78, "PIESD / AISD — non-certified", fontsize=9, color=GREY, fontweight="bold")
    box(ax, (0.9, 0.75), 1.9, 0.8, "Passenger Wi-Fi /\nIFE", fs=8, ec=GREY)
    box(ax, (3.1, 0.75), 2.0, 0.8, "Cabin router /\nserver", fs=8, ec=GREY)
    box(ax, (5.5, 0.75), 2.3, 0.8, "LEO terminal\n(Starlink · OneWeb · Kuiper)\nESA antenna", fs=7.5, ec=GREY)

    # arrows CMU -> radios
    arrow(ax, (4.7, 5.3), (5.3, 5.45))
    arrow(ax, (4.7, 5.0), (5.3, 4.5))
    arrow(ax, (4.7, 4.8), (5.3, 3.5))
    # CMU <-> adapter
    arrow(ax, (3.75, 4.6), (3.75, 4.2), style="<|-|>")
    # adapter -> terminal (dedicated port / VLAN)
    arrow(ax, (4.4, 2.5), (6.2, 1.55), color=AMBER, style="<|-|>",
          text="dedicated port / VLAN\n(authenticated tunnel)", tpos=0.6, toff=(1.1, 0.05), fs=7.5)
    # terminal to router (cabin path alternative)
    arrow(ax, (3.1, 1.15), (2.8, 1.15), color=GREY, style="<|-|>")
    arrow(ax, (5.5, 1.15), (5.1, 1.15), color=GREY, style="<|-|>")

    # Space / ground
    box(ax, (8.6, 5.3), 1.6, 0.8, "VGS\n(VDL2 ground)", fs=8)
    box(ax, (8.6, 4.2), 1.6, 0.8, "GEO L-band\nsatellite + GES", fs=8)
    box(ax, (8.6, 0.8), 1.6, 0.9, "LEO constellation\n+ gateways", fs=8, ec=AMBER)

    arrow(ax, (6.7, 5.5), (8.6, 5.7), color=BLUE)
    arrow(ax, (6.7, 4.5), (8.6, 4.6), color=BLUE)
    arrow(ax, (7.8, 1.2), (8.6, 1.25), color=AMBER, lw=2.0)

    # ground side
    ax.add_patch(FancyBboxPatch((10.5, 0.5), 2.3, 5.9, boxstyle="round,pad=0.02,rounding_size=0.15",
                                fc="white", ec=GREY, lw=1, ls="--"))
    ax.text(10.65, 6.2, "GROUND", fontsize=9, color=GREY, fontweight="bold")
    box(ax, (10.7, 4.9), 1.9, 0.9, "CSP / DSP\n(ACARS, ATN)", fs=8)
    box(ax, (10.7, 3.6), 1.9, 0.9, "ANSP\nCPDLC / ADS-C", fs=8)
    box(ax, (10.7, 2.3), 1.9, 0.9, "Airline AOC", fs=8)
    box(ax, (10.7, 0.8), 1.9, 1.1, "IPS / LEO ground\ngateway (new)\n• dedup • probe peer\n• evidence collector", fs=7.3, fc="#fff6e5", ec=AMBER)

    arrow(ax, (10.2, 5.7), (10.7, 5.4), color=BLUE)
    arrow(ax, (10.2, 4.6), (10.7, 5.2), color=BLUE)
    arrow(ax, (10.2, 1.25), (10.7, 1.3), color=AMBER, lw=2.0)
    arrow(ax, (11.65, 1.9), (11.65, 2.3), color=AMBER)
    arrow(ax, (12.3, 1.9), (12.3, 3.6), color=AMBER)
    arrow(ax, (11.65, 4.5), (11.65, 4.9), color=NAVY, style="<|-|>")

    # legend
    ax.text(0.5, 0.1, "Blue = certified safety subnetworks (unchanged).  Amber = new elements.  "
                      "Cabin IP path never terminates security; the ACD adapter does.",
            fontsize=8, color=NAVY)
    fig.savefig(os.path.join(OUT, "fig1_architecture.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- fig 2
def fig2_state_machine():
    fig, ax = plt.subplots(figsize=(13, 7.4))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 7.4)
    ax.axis("off")
    ax.set_title("Fig. 2 — Qualification state machine, instantiated per (LEO link × traffic class × airspace)",
                 fontsize=12.5, color=NAVY, fontweight="bold", loc="left")

    W, H = 2.6, 1.7
    states = {
        "OFF": ((0.3, 3.0), GREY, "OFF\nlink absent, or policy\ndisables this class"),
        "SHADOW": ((3.4, 3.0), BLUE, "SHADOW\nduplicate idempotent traffic\n(ADS-C, probes) on LEO;\nground de-duplicates;\ncollect T95 / T99.9"),
        "PROBATION": ((6.6, 3.0), AMBER, "PROBATION\ncarry class traffic on LEO\nwith hedged fallback;\nevidence window of N tx"),
        "ADMITTED": ((9.9, 3.0), TEAL, "ADMITTED\nLEO is the preferred tier\nfor this class; fallback\narmed at RCP budget"),
        "SUSPENDED": ((6.6, 0.3), RED, "SUSPENDED\nclass back on certified link;\nLEO carries probes only;\nhold-down timer"),
    }
    for name, ((x, y), c, label) in states.items():
        box(ax, (x, y), W, H, label, fc="white", ec=c, fs=8, lw=2)

    def mid(name, side):
        (x, y), _, _ = states[name]
        return {"r": (x + W, y + H / 2), "l": (x, y + H / 2), "b": (x + W / 2, y), "t": (x + W / 2, y + H),
                "bl": (x + 0.4, y), "br": (x + W - 0.4, y)}[side]

    arrow(ax, mid("OFF", "r"), mid("SHADOW", "l"), text="link up +\nmutual auth OK", toff=(0, 1.1), fs=7.5)
    arrow(ax, mid("SHADOW", "r"), mid("PROBATION", "l"), color=BLUE,
          text="shadow stats meet class spec\n(e.g. ACTP ≤120 s @95 %, ≤150 s @99.9 %,\nN ≥ N_min, in this FIR)", toff=(0, 1.3), fs=7.2)
    arrow(ax, mid("PROBATION", "r"), mid("ADMITTED", "l"), color=AMBER,
          text="probation window clean\n(continuity ≥ spec, 0 expiries)", toff=(0, 1.15), fs=7.2)
    arrow(ax, mid("ADMITTED", "bl"), (9.2, 1.15), color=RED,
          text="breach: expiry, continuity < spec,\nauth failure, predicted outage > budget", toff=(1.5, -0.15), fs=7.2)
    arrow(ax, mid("PROBATION", "b"), mid("SUSPENDED", "t"), color=RED, text="breach", toff=(0.4, 0))
    arrow(ax, (6.6, 1.15), (4.3, 3.0), color=RED, text="hold-down expired\n→ re-shadow", toff=(-0.95, 0.0), fs=7.5)
    arrow(ax, mid("SHADOW", "b"), (2.2, 1.6), color=GREY, ls="--")
    ax.text(1.6, 1.3, "link lost /\npolicy off", fontsize=7.5, color=GREY, ha="center")
    arrow(ax, (2.2, 1.6), mid("OFF", "b"), color=GREY, ls="--")

    ax.text(0.3, 6.75, "Traffic-class ladder — one state-machine instance per class; a class may be ADMITTED only if every class below it is ADMITTED:",
            fontsize=8.5, color=NAVY)
    ladder = ["C0  AOC bulk\n(QAR, EFB sync)", "C1  AOC ops\n(OOOI, flight plan)", "C2  ADS-C\nperiodic / event", "C3  ADS-C EPP,\nFIS, D-ATIS", "C4  CPDLC\nnon-time-critical", "C5  CPDLC clearances,\nurgent, emergency"]
    cols = [TEAL, TEAL, TEAL, AMBER, AMBER, RED]
    w, gap, x = 1.9, 0.22, 0.3
    for i, (lab, c) in enumerate(zip(ladder, cols)):
        ax.add_patch(FancyBboxPatch((x, 5.75), w, 0.8, boxstyle="round,pad=0.02,rounding_size=0.08", fc="white", ec=c, lw=1.6))
        ax.text(x + w / 2, 6.15, lab, ha="center", va="center", fontsize=7.4, color=NAVY)
        if i < len(ladder) - 1:
            arrow(ax, (x + w, 6.15), (x + w + gap, 6.15), color=GREY)
        x += w + gap
    ax.text(0.3, 5.4, "Admission thresholds come from an RCP/RSP matrix keyed by the FIR being flown (PBCS oceanic: RCP 240 / RSP 180; "
                      "continental ATN B2 values; AOC classes: airline policy).", fontsize=7.8, color=GREY)
    fig.savefig(os.path.join(OUT, "fig2_admission_state_machine.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- fig 3
def fig3_hedged_dispatch():
    fig, ax = plt.subplots(figsize=(12, 4.6))
    ax.set_xlim(0, 260)
    ax.set_ylim(0, 5)
    ax.set_yticks([])
    ax.set_xlabel("seconds since CPDLC uplink/downlink transaction start", color=NAVY)
    ax.set_title("Fig. 3 — Hedged dispatch with RCP budget accounting (RCP 240 example, ACTP allocation)",
                 fontsize=12.5, color=NAVY, fontweight="bold", loc="left")
    for s in ["top", "right", "left"]:
        ax.spines[s].set_visible(False)

    # budget bars
    ax.barh(4, 240, left=0, height=0.5, color="#e9f0fb", edgecolor=BLUE)
    ax.text(120, 4, "RCP 240 expiration time ET = 240 s (99.9 %)", ha="center", va="center", fontsize=8.5, color=NAVY)
    ax.barh(3.3, 150, left=0, height=0.5, color="#fff6e5", edgecolor=AMBER)
    ax.text(75, 3.3, "ACTP allocation: ≤150 s @99.9 %, ≤120 s @95 %", ha="center", va="center", fontsize=8.5, color=NAVY)

    # LEO attempt
    ax.barh(2.3, 28, left=0, height=0.45, color=TEAL)
    ax.text(14, 2.3, "LEO attempt", ha="center", va="center", fontsize=8, color="white", fontweight="bold")
    ax.text(30, 2.3, "typical LEO transaction 2–30 s (measured P99.9 stored per FIR)", va="center", fontsize=8, color=TEAL)

    # hedge point
    t_h = 150 - 95 - 10
    ax.axvline(t_h, color=RED, ls="--", lw=1.4)
    ax.text(t_h + 2, 1.55, f"t_hedge = ACTP_99.9 − P99.9(certified link) − margin\n= 150 − 95 − 10 = {t_h} s",
            fontsize=8, color=RED, va="center")
    ax.barh(1.2, 95, left=t_h, height=0.45, color=BLUE)
    ax.text(t_h + 47, 1.2, "certified-link copy (same transaction ID)", ha="center", va="center", fontsize=8, color="white", fontweight="bold")
    ax.text(t_h + 97, 1.2, "ground / CMU dedups → first good copy wins", va="center", fontsize=8, color=BLUE)

    ax.barh(0.4, 240, left=0, height=0.08, color=GREY)
    for t, lab in [(0, "start"), (t_h, "hedge"), (150, "ACTP 99.9%"), (240, "ET")]:
        ax.plot([t], [0.4], marker="|", color=NAVY, ms=14)
        ax.text(t, 0.05, lab, ha="center", fontsize=7.5, color=NAVY)

    ax.text(0, 4.6, "If LEO is in SHADOW or PROBATION, t_hedge = 0 (dual-cast). If ADMITTED, t_hedge is computed per class from stored distributions.",
            fontsize=8, color=GREY)
    fig.savefig(os.path.join(OUT, "fig3_hedged_dispatch.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- fig 4
def fig4_prior_art_map():
    fig, ax = plt.subplots(figsize=(12.5, 7))
    ax.set_xlim(0, 12.5)
    ax.set_ylim(0, 7)
    ax.axis("off")
    ax.set_title("Fig. 4 — Where the idea sits against the patent record (screen as of 2026-10-14)",
                 fontsize=12.5, color=NAVY, fontweight="bold", loc="left")

    cols = [
        ("Element of the idea", 0.2, 3.1),
        ("Closest art", 3.4, 4.6),
        ("Verdict", 8.1, 1.4),
        ("What to claim instead", 9.6, 2.7),
    ]
    for lab, x, w in cols:
        ax.add_patch(FancyBboxPatch((x, 6.1), w, 0.5, boxstyle="round,pad=0.01,rounding_size=0.05", fc=NAVY, ec=NAVY))
        ax.text(x + w / 2, 6.35, lab, ha="center", va="center", color="white", fontsize=9, fontweight="bold")

    rows = [
        ("LEO as its own CMU preference tier",
         "US7027812B2 (preference tables, new subnetwork codes)\nUS7729263B2 · US8433817B2 · US11146329B1",
         "Anticipated", RED, "— (substrate only)"),
        ("ATN/IPS or SNDCF over the terminal IP path",
         "EP4513465A1 / US2025/0069511A1 ¶[0039] (SNDCF over AISD,\nIPS foreseen) · US10425149B1 (AOIP) · ARINC 858",
         "Anticipated", RED, "— (substrate only)"),
        ("Probe link; on failure move to L-band / VDL2",
         "EP4513465A1 (active/passive probing, MLE,\nack-timeout → ACD resends on safety media)\nUS2025/0260475A1 (benchmark → reconfigure)",
         "Anticipated", RED, "Only as part of the admission\nstate machine (below)"),
        ("AOC + bulk ATS first, CPDLC later 'until RCP proven'",
         "EASA/FAA White Paper 2022 (offload AOC) · EP4513465A1\n¶[0038] (ACD chooses traffic kinds) — but NO mechanism,\nno per-class statistical admission, no FIR awareness",
         "White space", TEAL, "Per-(link × class × FIR)\nqualification state machine with\nshadow dual-cast evidence"),
        ("Automatic fallback when LEO quality drops",
         "EP4513465A1 (reactive, after ack timeout)\nCN120856635B (metric scoring)",
         "Partly", AMBER, "Constellation-aware prediction\n(handover / gateway / polar gaps\n× 4D trajectory) → pre-emptive\nscheduling + hedged dispatch"),
        ("Starlink / OneWeb / Kuiper embodiments",
         "EP4572182A1 (LEO datalink HW) · multi-orbit IFC products",
         "Not inventive", GREY, "Composite subnetwork from ≥2\nindependent LEO links (optional\nFamily 3)"),
    ]
    y = 5.55
    for el, art, verdict, c, claim in rows:
        ax.add_patch(FancyBboxPatch((0.2, y - 0.4), 12.1, 0.86, boxstyle="round,pad=0.01,rounding_size=0.05", fc=LIGHT, ec="white"))
        ax.text(0.3, y, el, fontsize=8.3, va="center", color=NAVY, fontweight="bold")
        ax.text(3.5, y, art, fontsize=7.4, va="center", color=NAVY)
        ax.add_patch(FancyBboxPatch((8.2, y - 0.2), 1.2, 0.4, boxstyle="round,pad=0.01,rounding_size=0.1", fc=c, ec=c))
        ax.text(8.8, y, verdict, fontsize=8, va="center", ha="center", color="white", fontweight="bold")
        ax.text(9.7, y, claim, fontsize=7.6, va="center", color=NAVY)
        y -= 0.98

    fig.savefig(os.path.join(OUT, "fig4_prior_art_map.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    fig1_architecture()
    fig2_state_machine()
    fig3_hedged_dispatch()
    fig4_prior_art_map()
    print("figures written to", OUT)
