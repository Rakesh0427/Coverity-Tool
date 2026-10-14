#!/usr/bin/env python3
"""Combine the package into ONE document: COMPLETE_DOSSIER.md and COMPLETE_DOSSIER.docx (with figures embedded)."""
from __future__ import annotations

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
MD_OUT = os.path.join(HERE, "LEO_ATN_Subnetwork_Complete_Dossier.md")
DOCX_OUT = os.path.join(HERE, "LEO_ATN_Subnetwork_Complete_Dossier.docx")

PARTS = [
    ("Part A — Improved idea (v2): the four sections rewritten", "IDEA_LEO_ATN_SUBNETWORK_v2.md"),
    ("Part B — Patent & prior-art landscape report", "PATENT_LANDSCAPE_REPORT.md"),
    ("Part C — Draft claim set and claim charts", "DRAFT_CLAIM_SET.md"),
    ("Part D — Invention disclosure", "INVENTION_DISCLOSURE.md"),
    ("Part E — Search protocol", "SEARCH_PROTOCOL.md"),
]


def demote(md: str) -> str:
    out = []
    for line in md.splitlines():
        if line.startswith("#"):
            line = "#" + line
        out.append(line)
    return "\n".join(out)


def strip_title(md: str) -> str:
    """Remove the first H1 line (the part heading replaces it)."""
    lines = md.splitlines()
    for i, l in enumerate(lines):
        if l.startswith("# "):
            del lines[i]
            break
    return "\n".join(lines).lstrip("\n")


def dataset_appendix() -> str:
    data = json.load(open(os.path.join(HERE, "PRIOR_ART_DATASET.json"), encoding="utf-8"))
    rows = ["## Appendix — Prior-art dataset (44 references)", "",
            f"*{data['meta']['disclaimer']}*", "",
            "| # | Publication | Assignee | Priority → Published | Status | Cluster | Overlap | What it discloses | Differentiation hook |",
            "|---|---|---|---|---|---|---|---|---|"]
    for r in data["references"]:
        cell = lambda s: str(s).replace("|", "/").replace("\n", " ")
        rows.append(f"| {r['id']} | **{cell(r['pub'])}**<br>{cell(r['title'])} | {cell(r['assignee'])} | {cell(r['priority'])} → {cell(r['published'])} | "
                    f"{cell(r['status'])} | {r['cluster']} | {cell(r['overlap'])} | {cell(r['disclosure'])} | {cell(r['differentiation'])} |")
    rows += ["", "Cluster key: " + "; ".join(f"**{k}** = {v}" for k, v in data["meta"]["clusters"].items()), ""]
    return "\n".join(rows)


COVER = """# LEO broadband as a performance-earned ATN/IPS subnetwork of the CMU
## Complete dossier — prior-art landscape, improved idea, draft claims, disclosure

*Prepared 2026-10-14 · Automated landscape screen and drafting aid — not a legal opinion.*

### Headline

* **As originally stated, the idea is anticipated.** Honeywell CMU preference-table patents (US7027812B2, US7729263B2), Honeywell
  AOIP (US10425149B1), the EASA/FAA *Future Connectivity for Aviation* white paper (2022) and, above all, **Rockwell Collins
  France's "Virtual Safety Radio" application EP4513465A1 / US2025/0069511A1 (priority 2023-08-21, pending)** already cover
  LEO/cabin-IP as a CMU subnetwork, ATN over it, AOC-first use, probing, and fallback with an RCP/RSP rationale.
* **White space found and claimed in this dossier:** (1) per-(traffic class × airspace) graduated admission driven by shadow
  dual-cast PBCS statistics; (2) LEO constellation-aware predicted-outage scheduling on board; (3) hedged dispatch timed from
  the RCP budget; (4) composite multi-constellation virtual subnetwork; (5) signed on-board evidence record bound to admission
  decisions.
* **Action:** file on (1)–(5) promptly; monitor EP4513465A1 prosecution for freedom-to-operate (its claim 1 requires a
  cross-router interface; a dedicated-port/VLAN embodiment is a candidate design-around — counsel to confirm).

### Contents

1. Part A — Improved idea (v2): Situation · Target · Proposed solution · Benefits
2. Part B — Patent & prior-art landscape report
3. Part C — Draft claim set (3 families, 23 claims) and claim charts
4. Part D — Invention disclosure
5. Part E — Search protocol
6. Appendix — Prior-art dataset (44 references)

"""


def build_markdown() -> str:
    chunks = [COVER]
    for heading, fname in PARTS:
        md = open(os.path.join(HERE, fname), encoding="utf-8").read()
        md = strip_title(md)
        chunks.append(f"\n\n---\n\n# {heading}\n\n{demote(md)}\n")
    chunks.append("\n\n---\n\n" + dataset_appendix())
    return "\n".join(chunks)


# ----------------------------------------------------------------------------- markdown -> docx
def build_docx(md: str) -> None:
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor, Cm

    doc = Document()
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(1.8)
    sec.top_margin = sec.bottom_margin = Cm(1.6)
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10)
    for lvl, size in ((1, 18), (2, 14), (3, 12), (4, 11)):
        hs = doc.styles[f"Heading {lvl}"]
        hs.font.name = "Calibri"
        hs.font.size = Pt(size)
        hs.font.color.rgb = RGBColor(0x1F, 0x2A, 0x44)

    def shade(cell, hexcolor):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), hexcolor)
        tcPr.append(shd)

    inline_re = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)")

    def add_runs(par, text, size=None):
        text = text.replace("<br>", "\n")
        for tok in inline_re.split(text):
            if not tok:
                continue
            if tok.startswith("**") and tok.endswith("**"):
                r = par.add_run(tok[2:-2]); r.bold = True
            elif tok.startswith("`") and tok.endswith("`"):
                r = par.add_run(tok[1:-1]); r.font.name = "Consolas"
            elif tok.startswith("*") and tok.endswith("*") and len(tok) > 2:
                r = par.add_run(tok[1:-1]); r.italic = True
            else:
                r = par.add_run(tok)
            if size:
                r.font.size = Pt(size)

    def add_table(rows):
        header = [c.strip() for c in rows[0].strip().strip("|").split("|")]
        body = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows[2:]]
        ncol = len(header)
        t = doc.add_table(rows=1, cols=ncol)
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        fs = 8 if ncol <= 5 else 7
        for i, h in enumerate(header):
            c = t.rows[0].cells[i]
            c.text = ""
            add_runs(c.paragraphs[0], f"**{h}**", size=fs)
            shade(c, "DCE6F1")
        for row in body:
            row = (row + [""] * ncol)[:ncol]
            cells = t.add_row().cells
            for i, val in enumerate(row):
                cells[i].text = ""
                add_runs(cells[i].paragraphs[0], val, size=fs)
        doc.add_paragraph()

    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1; continue
        if s == "---":
            doc.add_page_break(); i += 1; continue
        m = re.match(r"^(#{1,6})\s+(.*)", s)
        if m:
            lvl = min(len(m.group(1)), 4)
            h = doc.add_heading("", level=lvl)
            add_runs(h, m.group(2))
            i += 1; continue
        m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)", s)
        if m:
            path = os.path.join(HERE, m.group(2))
            if os.path.exists(path):
                doc.add_picture(path, width=Cm(17.4))
                doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                cap = doc.add_paragraph()
                add_runs(cap, f"*{m.group(1)} — {os.path.basename(path)}*", size=8)
                cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            i += 1; continue
        if s.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i]); i += 1
            if len(block) >= 2:
                add_table(block)
            continue
        if s.startswith("> "):
            p = doc.add_paragraph(style="Intense Quote")
            txt = [s[2:]]
            i += 1
            while i < len(lines) and lines[i].strip().startswith(">"):
                txt.append(lines[i].strip().lstrip("> ")); i += 1
            add_runs(p, " ".join(txt))
            continue
        m = re.match(r"^(\s*)([*\-]|\d+\.)\s+(.*)", line)
        if m:
            indent = len(m.group(1))
            numbered = m.group(2)[0].isdigit()
            style = "List Number" if numbered else "List Bullet"
            if indent >= 2:
                style += " 2"
            text = m.group(3)
            i += 1
            # continuation lines
            while i < len(lines) and lines[i].strip() and not re.match(r"^(\s*)([*\-]|\d+\.)\s+", lines[i]) \
                    and not lines[i].strip().startswith(("#", "|", "!", ">")) and lines[i].strip() != "---":
                text += " " + lines[i].strip(); i += 1
            p = doc.add_paragraph(style=style)
            add_runs(p, text)
            continue
        # paragraph (merge continuation lines)
        text = s
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith(("#", "|", "!", ">", "---")) \
                and not re.match(r"^(\s*)([*\-]|\d+\.)\s+", lines[i]):
            text += " " + lines[i].strip(); i += 1
        p = doc.add_paragraph()
        add_runs(p, text)

    doc.save(DOCX_OUT)


def main() -> None:
    md = build_markdown()
    open(MD_OUT, "w", encoding="utf-8").write(md)
    build_docx(md)
    print("wrote", MD_OUT, "and", DOCX_OUT)


if __name__ == "__main__":
    main()
