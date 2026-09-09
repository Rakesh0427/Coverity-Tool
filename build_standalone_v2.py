#!/usr/bin/env python3
"""
build_standalone_v2.py — 2-slide standalone deck:

  1. Why teams adopt it  (tool highlights, push feature first — no VS-Code-agent talk)
  2. Future estimated saving across the four programs (user-supplied table)

Built on top of the 7-slide deck's template masters, then the original 7 slides are
dropped so the standalone contains only these two. Re-runnable.
"""
from __future__ import annotations

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Pt

import build_deployment_slides as B

RATE = B.RATE_PER_HR
PROGRAMS = [
    ("EPIC EPP Core", 1023, 7161, 1023),
    ("NG-FMS ATS Core EPP", 143, 1001, 143),
    ("AIMS BPv19", 574, 4018, 574),
    ("787 BPv7", 1610, 11270, 1610),
]
T_DEF = sum(r[1] for r in PROGRAMS)
T_ANA = sum(r[2] for r in PROGRAMS)
T_UP = sum(r[3] for r in PROGRAMS)
T_TOT = T_ANA + T_UP
T_HRS = T_TOT / 60.0
AVG_HRS = T_HRS / len(PROGRAMS)
T_USD = T_HRS * RATE
AVG_USD = AVG_HRS * RATE


def slide_highlights(prs):
    s = B.new_slide(prs, 1)
    B.tag(prs, s)
    B.title(s, "Why Teams Adopt the Coverity Findings Analyzer")
    B.subtitle(s, "One local, offline tool that turns a Coverity report into "
                   "review-ready dispositions \u2014 and pushes them back for you.",
               size=13)

    cards = [
        ("One-click push to Coverity Connect",
         "Batch-pushes classification + comment + Action for every defect. "
         "NG-FMS: 143 min by hand \u2192 ~2 min with the tool.", True),
        ("Automated source context",
         "tree-sitter extracts the exact function, callers and callees \u2014 "
         "no manual code hunting.", False),
        ("Explainable classification",
         "Per-checker rules + Z3 path proofs + cppcheck \u2192 Bug / False positive / "
         "Intentional / Needs review, with confidence.", False),
        ("Reviewer-grade comments & fixes",
         "Code-fact-based comments, CWE / CERT / OWASP mapping and context-aware "
         "fix suggestions.", False),
        ("100% offline & air-gapped",
         "No cloud, no credits, no licence. Source never leaves the PC \u2014 "
         "export-control friendly.", False),
        ("Audit-ready by default",
         "dispositions, final decisions and audit.jsonl log every decision, "
         "reason and confidence.", False),
        ("Maps to recognised standards",
         "CWE id/name, CERT C rule, OWASP and a CVSS score per checker \u2014 ties "
         "dispositions to DO-326A / DO-356A.", False),
        ("AI-built, human-validated",
         "AI coding assistants compressed the build \u2014 analysis engine, GUI and "
         "Connect integrations iterated with AI.", False),
        ("AI-drafted rules, engineer-checked",
         "AI drafted the ~20 per-checker rules and Z3 / cppcheck corroboration; "
         "engineers validated on real reports.", False),
    ]
    gap = 0.16
    cw = (B.USABLE - 2 * gap) / 3
    ch = 1.38
    for i, (head, body, hot) in enumerate(cards):
        col = i % 3
        row = i // 3
        x = B.MARGIN + col * (cw + gap)
        y = 1.02 + row * (ch + 0.12)
        c = B.card(s, x, y, cw, ch,
                   fill=RGBColor(0xFE, 0xF2, 0xF2) if hot else B.LIGHT,
                   line_color=B.RED if hot else B.BORDER,
                   line_w=Pt(1.75) if hot else Pt(1))
        B.card_text(c, head, body, head_size=12, body_size=10,
                    head_color=B.RED if hot else B.DARK)

    B.band(s, B.MARGIN, 5.62, B.USABLE, 0.5,
           "No credits, no licence, unlimited runs \u2014 AI built the tool, but every "
           "decision it makes is deterministic and audit-ready.",
           size=12, bold_lead="It compounds:  ")
    return s


def slide_future_saving(prs):
    s = B.new_slide(prs, 2)
    B.tag(prs, s)
    B.title(s, "Future Estimated Saving \u2014 Four Programs \u00d7 Four RL Releases")
    B.subtitle(s, "Per defect: manual 7 min analysis + comment + 1 min upload = 8 min; "
                   "tool \u22481 min (engineer review). Saved \u22487 min per defect.", size=12.5)

    RELEASES = 4
    MAN_MIN, TOOL_MIN, SAVE_MIN = 8.0, 1.0, 7.0
    def hrs(per_defect_min, d):
        return per_defect_min * d * RELEASES / 60.0
    tot_man = hrs(MAN_MIN, T_DEF); tot_tool = hrs(TOOL_MIN, T_DEF); tot_save = hrs(SAVE_MIN, T_DEF)
    usd = tot_save * RATE

    stats = [
        (f"{MAN_MIN:.0f} min", "manual effort per defect (7+1)", B.RED),
        (f"~{TOOL_MIN:.0f} min", "with tool per defect (review)", B.GREEN),
        (f"~{SAVE_MIN:.0f} min", "saved per defect", B.DARK),
        (f"{tot_save:,.0f} hrs", f"saved over 4 RL releases (\u2248 ${usd:,.0f})", B.SLATE),
    ]
    gap = 0.16
    cw = (B.USABLE - 3 * gap) / 4
    for i, (big, lab, col) in enumerate(stats):
        B.stat_card(s, B.MARGIN + i * (cw + gap), 1.00, cw, 1.18, big, lab,
                    accent=col, big_size=22)

    rows = [["Program (defects / release)", "Manual (4 RL)", "With tool (4 RL)", "Saved (4 RL)"]]
    for n, d, a, u in PROGRAMS:
        rows.append([f"{n} ({d:,})", f"{hrs(MAN_MIN, d):,.0f} hrs",
                     f"{hrs(TOOL_MIN, d):,.0f} hrs", f"{hrs(SAVE_MIN, d):,.0f} hrs"])
    rows.append([f"TOTAL ({T_DEF:,})", f"{tot_man:,.0f} hrs", f"{tot_tool:,.0f} hrs",
                 f"{tot_save:,.0f} hrs"])
    B.panel_heading(s, B.MARGIN, 2.40, B.USABLE,
                    "Manual effort vs tool hours, over 4 RL releases per program")
    B.make_table(s, B.MARGIN, 2.72, B.USABLE, rows,
                 [3.90, 2.90, 2.90, 3.073], row_h=0.50)

    B.band(s, B.MARGIN, 5.82, B.USABLE, 0.55,
           f"Over 4 RL releases the tool returns \u2248 {tot_save:,.0f} hrs (\u2248 ${usd:,.0f} at "
           f"${RATE:.0f}/hr): manual effort falls from \u2248 {tot_man:,.0f} hrs to \u2248 {tot_tool:,.0f} hrs.",
           size=12.5, bold_lead="Bottom line:  ")
    return s


