#!/usr/bin/env python3
"""
coverity_report_text.py — turn a Coverity HTML report into text an LLM can read.

WHY THIS EXISTS
---------------
A Coverity HTML export is a folder with an ``index.html`` table of defects plus
one detail page per defect, where the detail page holds the event trace and the
code excerpt. That is readable by a language model directly, but on a report with
hundreds of defects the markup is a large share of the tokens.

This script flattens the report into plain text (or JSON) using only the Python
standard library — no BeautifulSoup, no lxml, and **no part of the Coverity Tool
engine**. It is a reading aid for a model, not an analyser: it never judges a
defect, so there is nothing here that could be mistaken for a verdict.

USAGE
-----
    python3 coverity_report_text.py <report-folder-or-index.html>
    python3 coverity_report_text.py <report> --cid 1002
    python3 coverity_report_text.py <report> --limit 25
    python3 coverity_report_text.py <report> --json --out defects.json
    python3 coverity_report_text.py --version

Exit codes: 0 success, 1 no defects found, 2 bad usage.
"""
from __future__ import annotations

import argparse
import html as html_module
import json
import os
import re
import sys

__version__ = "1.0.0"

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]+")
_ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.I | re.S)
_LINK = re.compile(r"""<a\b[^>]*href\s*=\s*["']([^"']+)["'][^>]*>(.*?)</a>""",
                   re.I | re.S)
_CELL = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.I | re.S)
_PRE = re.compile(r"<pre\b[^>]*>(.*?)</pre>", re.I | re.S)


def _text(fragment: str) -> str:
    """HTML fragment → single-line text."""
    stripped = _TAG.sub(" ", fragment)
    stripped = html_module.unescape(stripped)
    return _WS.sub(" ", stripped.replace("\r", "")).strip()


def _block(fragment: str) -> str:
    """HTML fragment → text with line structure preserved (for <pre>)."""
    stripped = _PRE.sub(lambda m: m.group(1), fragment)
    stripped = re.sub(r"<br\s*/?>", "\n", stripped, flags=re.I)
    stripped = _TAG.sub("", stripped)
    return html_module.unescape(stripped).replace("\r", "").strip("\n")


def resolve_index(path: str) -> str:
    """Accept a report folder, an index.html, or a single detail page."""
    target = os.path.abspath(os.path.expanduser(path))
    if os.path.isdir(target):
        for name in ("index.html", "index.htm"):
            candidate = os.path.join(target, name)
            if os.path.isfile(candidate):
                return candidate
        raise FileNotFoundError(f"no index.html in {target}")
    if os.path.isfile(target):
        return target
    raise FileNotFoundError(path)


def parse_index(index_path: str) -> list[dict]:
    """Read the defect table. Column order is taken from the header row."""
    with open(index_path, encoding="utf-8", errors="replace") as handle:
        markup = handle.read()

    rows = _ROW.findall(markup)
    if not rows:
        return []

    header: list[str] = []
    defects: list[dict] = []
    base = os.path.dirname(index_path)

    for row in rows:
        cells = _CELL.findall(row)
        if not cells:
            continue
        labels = [_text(cell).lower() for cell in cells]
        if not header and ("cid" in labels or "checker" in labels):
            header = labels
            continue
        if header and len(cells) == len(header) and labels == header:
            continue                                    # a repeated header row

        link = _LINK.search(row)
        values = [_text(cell) for cell in cells]
        if not any(values):
            continue

        defect: dict = {"raw_columns": values}
        if header and len(values) == len(header):
            defect.update({name: value for name, value in zip(header, values)})
        elif values:
            # No header we recognise: Coverity's own order, which is what the
            # sample and most exports use.
            for name, value in zip(("cid", "checker", "file", "function", "type"),
                                   values):
                defect.setdefault(name, value)

        cid_match = re.search(r"\d+", str(defect.get("cid", "")) or "")
        if cid_match:
            defect["cid"] = cid_match.group(0)
        if link:
            href = html_module.unescape(link.group(1))
            defect["detail_page"] = os.path.normpath(os.path.join(base, href))
            defect["detail_href"] = href
        defects.append(defect)

    return defects


def parse_detail(path: str) -> dict:
    """Event trace + code excerpt from a defect detail page."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        markup = handle.read()
    blocks = [_block(part) for part in _PRE.findall(markup)]
    body = "\n\n".join(part for part in blocks if part)
    if not body:
        # Some exports use tables/code blocks rather than <pre>.
        body = _block(markup)
    events: list[str] = []
    code: list[str] = []
    for line in body.splitlines():
        if re.match(r"^\s*\(?\d*\)?\s*(Event|event)\b", line) or \
           re.search(r"\b(Event|event)\s+\w+:", line):
            events.append(line.strip())
        else:
            code.append(line.rstrip())
    return {"events": events, "code": "\n".join(code).strip("\n"),
            "text": body}


def collect(path: str, cid: str = "", limit: int = 0) -> list[dict]:
    index = resolve_index(path)
    defects = parse_index(index)
    if not defects and not index.endswith(("index.html", "index.htm")):
        # A single detail page handed in directly.
        defects = [{"cid": "", "detail_page": index}]
    if cid:
        wanted = str(cid).strip()
        defects = [d for d in defects if str(d.get("cid", "")) == wanted]
    if limit:
        defects = defects[:limit]
    for defect in defects:
        page = defect.get("detail_page", "")
        if page and os.path.isfile(page):
            defect["detail"] = parse_detail(page)
            defect["detail_page"] = os.path.relpath(page, os.path.dirname(index))
        else:
            defect["detail"] = {"events": [], "code": "", "text": ""}
    return defects


def render(defects: list[dict], report: str) -> str:
    lines = [f"# Coverity report digest — {report}",
             f"# {len(defects)} defect(s). Facts from the report only: this is not an analysis.",
             ""]
    for defect in defects:
        lines.append(f"## CID {defect.get('cid') or '?'} — {defect.get('checker') or '?'}")
        for label, key in (("Type", "type"), ("Severity", "severity"),
                           ("File", "file"), ("Function", "function"),
                           ("Detail page", "detail_page")):
            value = defect.get(key)
            if value:
                lines.append(f"- {label}: {value}")
        if defect.get("raw_columns") and not defect.get("checker"):
            lines.append(f"- Columns: {' | '.join(defect['raw_columns'])}")
        detail = defect.get("detail") or {}
        for event in detail.get("events") or []:
            lines.append(f"- {event}")
        if detail.get("code"):
            lines += ["", "```c", detail["code"], "```"]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Flatten a Coverity HTML report for reading (stdlib only).")
    parser.add_argument("report", nargs="?", help="report folder or index.html")
    parser.add_argument("--cid", default="", help="only this defect id")
    parser.add_argument("--limit", type=int, default=0, help="at most N defects")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--out", default="", help="write to a file instead of stdout")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args(argv)

    if args.version:
        print(json.dumps({"ok": True, "name": "coverity_report_text",
                          "version": __version__, "schema": 1}))
        return 0
    if not args.report:
        parser.print_usage(sys.stderr)
        return 2

    try:
        defects = collect(args.report, cid=args.cid, limit=args.limit)
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "error": f"not found: {exc}"}), file=sys.stderr)
        return 2

    if args.json:
        output = json.dumps({"ok": True, "report": os.path.abspath(args.report),
                             "count": len(defects), "defects": defects},
                            indent=2, ensure_ascii=False)
    else:
        output = render(defects, os.path.abspath(args.report))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(output + ("" if output.endswith("\n") else "\n"))
    else:
        sys.stdout.write(output if output.endswith("\n") else output + "\n")
    return 0 if defects else 1


if __name__ == "__main__":
    sys.exit(main())
