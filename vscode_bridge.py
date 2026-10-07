#!/usr/bin/env python3
"""
vscode_bridge.py — headless, machine-readable front end for the Coverity Tool.

Why this module exists
----------------------
`local_gui.py` and `coverity_triage.py` are tkinter applications: they need a
display, and the only way to drive them is a human clicking buttons.  Editors
and agents (VS Code language-model tools, MCP clients, CI jobs) need the *same*
analysis behind a non-interactive process that speaks a structured format.

This module is that process.  It runs exactly the pipeline the GUIs run

    parse report -> build_defect_context() -> analyze_defect()

and exposes it as a handful of subcommands that emit JSON on stdout:

    python vscode_bridge.py capabilities
    python vscode_bridge.py list      --report <report.html|report.xlsx>
    python vscode_bridge.py analyze   --report <...> --src <source-root> [--csv out.csv] [--jsonl]
    python vscode_bridge.py context   --report <...> --cid 12345 --src <...>

Consumers
---------
* ``coverity_mcp_server.py`` imports this module directly and re-exports the
  same operations as MCP tools (no subprocess, no re-parsing).
* The VS Code extension (``vscode-extension/``) shells out to it and parses the
  JSON, which keeps all analysis logic in Python — one implementation, not two.

Contract
--------
* **stdout carries JSON and nothing else.**  Human-readable progress goes to
  stderr, and while a command runs the process' own ``sys.stdout`` is pointed
  at stderr so a stray ``print()`` inside a deep analyzer cannot corrupt the
  payload the caller is parsing.
* Every payload has ``ok`` and ``schema``.  Failures are still JSON
  (``ok: false`` with ``error.message`` / ``error.hint``) and exit non-zero,
  so a caller never has to guess from a traceback.
* Optional heavy backends are reported, never required: a machine without
  tree-sitter/z3 still gets verdicts, and the payload says the analysis depth
  was reduced (:mod:`capabilities`).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------- #
# Make sibling modules importable no matter which cwd launched us
# --------------------------------------------------------------------------- #
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

#: Bumped whenever the JSON shape changes in a breaking way.
SCHEMA_VERSION = 1

# --------------------------------------------------------------------------- #
# Dispositions — the vocabulary shared with the GUIs, the Excel export and the
# VS Code diagnostics.  Do not introduce new spellings; the extension maps
# these exact strings onto VS Code severities.
# --------------------------------------------------------------------------- #
DISPOSITION_BUG = "Bug"
DISPOSITION_FALSE_POSITIVE = "False positive"
DISPOSITION_INTENTIONAL = "Intentional"
DISPOSITION_NEEDS_REVIEW = "Needs review"
DISPOSITIONS = (
    DISPOSITION_BUG,
    DISPOSITION_FALSE_POSITIVE,
    DISPOSITION_INTENTIONAL,
    DISPOSITION_NEEDS_REVIEW,
)

#: Checkers that can be judged from the whole function even when the report has
#: no concrete line (an Excel export often says "Various").  Mirrors
#: ``local_gui._LINE_AGNOSTIC_CHECKERS`` so both front ends agree.
LINE_AGNOSTIC_CHECKERS = frozenset({
    'CHECKED_RETURN', 'CHECKED_QRS', 'UNUSED_VALUE', 'DEADCODE', 'MISSING_BREAK',
    'NO_BREAK', 'CONSTANT_EXPRESSION_RESULT', 'IDENTICAL_BRANCHES', 'NEGATIVE_RETURNS',
    'SIZEOF_MISMATCH', 'ARRAY_VS_SINGLETON', 'STRING_NULL', 'SHIFT_OVERFLOW',
    'UNREACHABLE', 'MISSING_LOCK', 'INTEGER_OVERFLOW',
})

#: Extensions worth indexing when we have to find a source file by suffix.
_SOURCE_EXTS = frozenset({
    '.c', '.h', '.cc', '.cpp', '.cxx', '.hpp', '.hh', '.hxx', '.inl', '.ipp',
    '.tcc', '.C', '.H',
})

HTML_EXTS = frozenset({'.html', '.htm'})
EXCEL_EXTS = frozenset({'.xlsx', '.xlsm', '.xls'})
JSON_EXTS = frozenset({'.json'})


class BridgeError(Exception):
    """An error the caller can act on; rendered as JSON, never a traceback."""

    def __init__(self, message: str, hint: str = "", kind: str = "Error"):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.kind = kind


# --------------------------------------------------------------------------- #
# Lazy pipeline imports
#
# Importing this module must stay cheap and must not explode on a machine that
# installed only part of requirements.txt — the caller gets a JSON error naming
# the missing package instead.
# --------------------------------------------------------------------------- #
def _need(module_name: str, pip_name: str = ""):
    try:
        return __import__(module_name)
    except ImportError as exc:
        pkg = pip_name or module_name
        raise BridgeError(
            f"Required module '{module_name}' is not installed ({exc}).",
            hint=f"Install the tool's dependencies: pip install -r requirements.txt "
                 f"(or at least: pip install {pkg})",
            kind="MissingDependency",
        ) from exc


def assert_pipeline_importable() -> None:
    """Fail fast, with a good message, if the analysis stack is incomplete."""
    for mod, pkg in (("html_report_parser", "lxml beautifulsoup4"),):
        _need(mod, pkg)


# --------------------------------------------------------------------------- #
# Capabilities
# --------------------------------------------------------------------------- #
def capabilities_payload() -> Dict[str, Any]:
    """Which optional analysis backends are live in this interpreter."""
    try:
        import capabilities as caps
    except ImportError:
        return {"depth": "minimal", "mode": "engine_missing", "analyzer": False,
                "verdicts": ("The capabilities module is unavailable, so nothing "
                             "here is verified by the engine."),
                "backends": [], "banner": "",
                "missing": ["capabilities module unavailable"],
                "recommendation": "pip install -r requirements.txt"}

    probed = caps.probe()                       # cached after the first call
    backends = [{
        "key": c.key,
        "label": c.label,
        "available": bool(c.available),
        "detail": c.detail,
        "critical": bool(c.critical),
    } for c in probed.values()]
    try:
        banner = caps.format_banner()
    except Exception:
        banner = ""
    missing = [c["label"] for c in backends if c["critical"] and not c["available"]]
    depth = caps.analysis_depth()
    analyzer_live = _analyzer_importable()
    if not analyzer_live:
        mode, verdicts = "engine_missing", (
            "No verdicts are produced here. The report can still be listed, but "
            "any judgment must come from the model reading the code, and must be "
            "labelled model-only and unverified.")
    elif depth == "full":
        mode, verdicts = "engine", "Every verdict is engine-backed and AST-anchored."
    else:
        mode, verdicts = "degraded", (
            f"Verdicts are engine-backed at depth '{depth}'. Treat weak verdicts as "
            "provisional and say which backend was missing.")
    return {
        "depth": depth,
        "mode": mode,
        "analyzer": analyzer_live,
        "verdicts": verdicts,
        "backends": backends,
        "missing": missing,
        "banner": banner,
        "recommendation": ("" if not missing else
                           "pip install -r requirements.txt for full-strength analysis"),
    }


def _analyzer_importable() -> bool:
    """Can this interpreter actually analyse a defect (not just read a report)?

    Kept separate from the backend probe because it is the difference between
    "the engine judged this defect" and "the model read the code" — the two
    claims an agent must never confuse.
    """
    for module in ("context_builder", "heuristic_analyzer"):
        try:
            __import__(module)
        except Exception:
            return False
    return True


# --------------------------------------------------------------------------- #
# Report loading
# --------------------------------------------------------------------------- #
_REPORT_CACHE: Dict[Tuple[str, int, int], List[Dict[str, Any]]] = {}


def resolve_report_path(report_path: str) -> str:
    """Accept a report file *or* the folder that contains index.html."""
    if not report_path:
        raise BridgeError("No report path given.",
                          hint="Pass --report <index.html|report.xlsx|coverity.json>")
    path = os.path.abspath(os.path.expanduser(report_path))
    if os.path.isdir(path):
        path = os.path.join(path, "index.html")
    if not os.path.isfile(path):
        raise BridgeError(f"Report not found: {report_path}",
                          hint="Check the path; a Coverity HTML report is the "
                               "folder containing index.html.")
    return path


def _read_json_report(path: str) -> List[Dict[str, Any]]:
    """Accept a triage JSON produced by this tool (``{defects: [...]}``)."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        for key in ("defects", "findings", "issues", "results"):
            if isinstance(data.get(key), list):
                return [d for d in data[key] if isinstance(d, dict)]
        raise BridgeError(f"JSON report has no 'defects' list: {path}")
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    raise BridgeError(f"Unsupported JSON report shape in {path}")


def load_defects(report_path: str, use_cache: bool = True) -> List[Dict[str, Any]]:
    """Parse (and cache) the defect list for a report."""
    path = resolve_report_path(report_path)
    try:
        stat = os.stat(path)
        key = (path, int(stat.st_mtime), int(stat.st_size))
    except OSError as exc:
        raise BridgeError(f"Cannot stat report {path}: {exc}") from exc

    if use_cache and key in _REPORT_CACHE:
        return _REPORT_CACHE[key]

    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in HTML_EXTS:
            _need("html_report_parser")
            from html_report_parser import parse_coverity_html
            defects = parse_coverity_html(path)
        elif ext in EXCEL_EXTS:
            _need("html_report_parser")
            _need("openpyxl", "openpyxl")
            from html_report_parser import parse_coverity_excel
            defects = parse_coverity_excel(path)
        elif ext in JSON_EXTS:
            defects = _read_json_report(path)
        else:
            raise BridgeError(
                f"Unsupported report type '{ext}'. Expected .html, .xlsx or .json.",
                hint="Export the Coverity report as HTML/Excel, or run the tool's "
                     "Excel export first and pass that .xlsx.",
            )
    except BridgeError:
        raise
    except Exception as exc:
        raise BridgeError(f"Failed to parse {os.path.basename(path)}: {exc}",
                          kind=type(exc).__name__) from exc

    defects = [_normalise_defect(d) for d in defects or []]
    if use_cache:
        _REPORT_CACHE.clear()          # keep only the most recent report
        _REPORT_CACHE[key] = defects
    return defects


def _normalise_defect(d: Dict[str, Any]) -> Dict[str, Any]:
    """Fill in the fields every downstream step expects to exist."""
    out = dict(d)
    out.setdefault("cid", 0)
    out.setdefault("checker", "")
    out.setdefault("type", "")
    out.setdefault("severity", "")
    out.setdefault("file", "")
    out.setdefault("line", 0)
    out.setdefault("function", "")
    try:
        out["cid"] = int(out["cid"] or 0)
    except (TypeError, ValueError):
        out["cid"] = 0
    try:
        out["line"] = int(out["line"] or 0)
    except (TypeError, ValueError):
        out["line"] = 0
    if not isinstance(out.get("events"), list):
        out["events"] = []
    return out


# --------------------------------------------------------------------------- #
# Source lookup
#
# Coverity reports carry build-machine paths ("/home/ci/src/driver.c") that do
# not exist locally, so the file has to be matched against the local checkout
# by its trailing path components — the same idea as the GUI's
# _find_source_file(), kept here so headless callers get identical results.
# --------------------------------------------------------------------------- #
_SOURCE_INDEX_CACHE: Dict[str, Dict[str, str]] = {}


def _build_source_index(src_root: str) -> Dict[str, str]:
    """Map ``file.c`` and every trailing-suffix form to an absolute path."""
    root = os.path.abspath(src_root)
    if root in _SOURCE_INDEX_CACHE:
        return _SOURCE_INDEX_CACHE[root]

    index: Dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip the usual noise; keeps huge trees cheap.
        dirnames[:] = [d for d in dirnames
                       if d not in ('.git', '.svn', 'node_modules', '__pycache__',
                                    'build', 'dist', 'out', '.venv')]
        for name in filenames:
            if os.path.splitext(name)[1] not in _SOURCE_EXTS:
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace("\\", "/")
            parts = [p.lower() for p in rel.split("/") if p]
            for depth in range(1, min(len(parts), 6) + 1):
                suffix = "/".join(parts[-depth:])
                index.setdefault(suffix, full)
    _SOURCE_INDEX_CACHE[root] = index
    return index


def resolve_source_file(reported_path: str, src_root: str = "",
                        report_path: str = "") -> str:
    """Best local match for a defect's file. Returns '' when nothing matches."""
    if not reported_path:
        return ""
    cleaned = reported_path.strip().replace("\\", "/")

    if os.path.isabs(cleaned) and os.path.isfile(cleaned):
        return cleaned

    candidates: List[str] = []
    roots = [r for r in (src_root, os.path.dirname(report_path or ""),
                         os.path.dirname(os.path.dirname(report_path or ""))) if r]
    for root in roots:
        candidates.append(os.path.join(root, cleaned))
        candidates.append(os.path.join(root, os.path.basename(cleaned)))
    for cand in candidates:
        if os.path.isfile(cand):
            return os.path.abspath(cand)

    if not src_root or not os.path.isdir(src_root):
        return ""

    index = _build_source_index(src_root)
    parts = [p.lower() for p in cleaned.split("/") if p and p not in ('.', '..')]
    for depth in range(min(len(parts), 6), 0, -1):
        hit = index.get("/".join(parts[-depth:]))
        if hit:
            return hit
    return ""


# --------------------------------------------------------------------------- #
# Evidence dossier
# --------------------------------------------------------------------------- #
#: How much of each caller's body travels with a defect. The model needs enough
#: to judge whether a guard exists upstream, not a copy of the file.
CALLER_CODE_LIMIT = 1200
MAX_CALLERS = 3

_DECLARATION = re.compile(
    r"^\s*(?:const\s+|static\s+|unsigned\s+|signed\s+|volatile\s+)*"
    r"(?:struct\s+\w+|union\s+\w+|enum\s+\w+|[A-Za-z_]\w*)"
    r"(?:\s+|\s*[*]+\s*)([*\s]*)([A-Za-z_]\w*)\s*(\[[^\]]*\])?\s*(?:=[^;]*)?;\s*$")
_GUARD = re.compile(
    r"^\s*(if|else\s+if|while|for|switch|assert)\b|^\s*[A-Z][A-Z0-9_]{2,}\s*\(")
#: First tokens that mean "this is a statement", not a declaration. Without
#: this, `return p;` reads as a declaration of `p` of type `return`.
_STATEMENT_KEYWORDS = {
    "return", "goto", "break", "continue", "case", "default", "sizeof", "do",
    "else", "throw", "delete", "typedef", "using", "extern",
}
_FIRST_TOKEN = re.compile(r"^\s*([A-Za-z_]\w*)")


def _line_facts(function_code: str, start_line: int, focus_line: int) -> Dict[str, Any]:
    """Declarations and guards inside the function, with their absolute lines.

    This is the "nearby invariants" half of the dossier: a model judging a
    buffer or a pointer needs the declaration that fixes the capacity, and the
    guard that may already have rejected the case — both cheaper to read here
    than to re-derive by scrolling the file.
    """
    declarations: List[Dict[str, Any]] = []
    guards: List[Dict[str, Any]] = []
    if not function_code:
        return {"declarations": declarations, "guards": guards}
    for offset, text in enumerate(function_code.splitlines()):
        line_no = start_line + offset
        stripped = text.strip()
        if not stripped or stripped.startswith(("//", "/*", "*")):
            continue
        entry = {"line": line_no, "text": text.rstrip()[:200],
                 "focus": line_no == focus_line}
        guard = _GUARD.match(text)
        if guard and len(guards) < 12:
            guards.append({**entry, "kind": guard.group(1) or "macro"})
            continue
        first = _FIRST_TOKEN.match(text)
        if first and first.group(1) in _STATEMENT_KEYWORDS:
            continue
        match = _DECLARATION.match(text)
        if match and len(declarations) < 12:
            declarations.append({
                **entry,
                "name": match.group(2),
                "array": bool(match.group(3)),
                "size": (match.group(3) or "").strip("[]").strip() or "",
                "pointer": "*" in (match.group(1) or "")
                           or "*" in text.split("=")[0],
            })
    return {"declarations": declarations, "guards": guards}


def build_evidence(context: Dict[str, Any], defect: Dict[str, Any],
                   focus_line: int) -> Dict[str, Any]:
    """Everything the engine knows about the *code around* a defect, in one object.

    The point is that one tool call should be enough for a model to judge the
    defect: the enclosing function, the line the verdict hangs on, the
    declarations that fix capacities, the guards that may already rule the case
    out, and the callers/callees whose behaviour decides reachability. Anything
    not derivable from the report or the read source is left out rather than
    guessed.
    """
    function_code = context.get("function_code") or ""
    start_line = int(context.get("code_start_line") or 0) or 0
    facts = _line_facts(function_code, start_line, focus_line)

    function_name = defect.get("function") or context.get("function") or ""
    callers: List[Dict[str, Any]] = []
    for caller in (context.get("callers") or []):
        if not isinstance(caller, dict):
            continue
        # The extraction can hand back the function itself as its own caller;
        # that is noise in a dossier a model reasons over.
        if (caller.get("caller") == function_name
                and int(caller.get("line") or 0) == start_line):
            continue
        if len(callers) >= MAX_CALLERS:
            break
        code = str(caller.get("code") or "")
        callers.append({
            "caller": caller.get("caller", ""),
            "file": caller.get("file", ""),
            "line": caller.get("line", 0),
            "snippet": (caller.get("snippet") or "").strip()[:200],
            "code": code[:CALLER_CODE_LIMIT],
            "code_truncated": len(code) > CALLER_CODE_LIMIT,
        })

    callees = []
    signatures = context.get("callee_signatures") or {}
    for name in (context.get("called_functions") or [])[:12]:
        if name == function_name:
            continue
        callees.append({
            "name": name,
            "signature": str(signatures.get(name) or "").strip()[:200],
        })

    focus_text = ""
    if function_code and start_line:
        offset = focus_line - start_line
        lines = function_code.splitlines()
        if 0 <= offset < len(lines):
            focus_text = lines[offset].rstrip()[:200]

    return {
        "function": {
            "name": function_name,
            "start_line": start_line,
            "end_line": start_line + function_code.count("\n") if function_code else 0,
            "signature": (function_code.splitlines() or [""])[0].strip()[:200],
            "line_count": function_code.count("\n") + 1 if function_code else 0,
        },
        "defect_line": {"line": focus_line, "text": focus_text},
        "declarations": facts["declarations"],
        "guards": facts["guards"],
        "callers": callers,
        "callees": callees,
        "globals": list(context.get("global_vars") or [])[:12],
        "counts": {"callers": len(context.get("callers") or []),
                   "callees": len(context.get("called_functions") or []),
                   "declarations": len(facts["declarations"]),
                   "guards": len(facts["guards"])},
    }


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
def _events_for(defect: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The Coverity event trace, synthesised when the report carries none.

    Excel exports (and SOAP pulls trimmed to a sheet) often have no trace at
    all. ``local_gui`` synthesises a single event from the defect's own
    checker/file/line in that case, and ``build_defect_context`` refuses to do
    anything without events — so both the context build and the analysis use
    this list. Keeping them consistent is what makes an Excel defect analyse
    the same way the desktop app analyses it.
    """
    events = list(defect.get("events") or [])
    if events:
        return events
    return [{
        "step": 1,
        "type": defect.get("checker", ""),
        "description": defect.get("type", ""),
        "file": defect.get("file", ""),
        "line": defect.get("line", 0),
    }]


def _guess_function_name(file_path: str, line: int, language: str) -> str:
    """Best-effort enclosing-function name, mirroring ``local_gui``.

    Only used when the report has no function column (some Excel exports) and
    the checker is one that can be judged from the whole function. Returns ''
    when nothing convincing is found — never raises.
    """
    try:
        from code_extractor import extract_enclosing_function
        result = extract_enclosing_function(file_path, line or 1, language)
        code = result[0] if isinstance(result, tuple) else result
        if not code:
            return ""
        match = re.search(r"\b([A-Za-z_]\w*)\s*\([^;{]*\)\s*\{", code)
        return match.group(1) if match else ""
    except Exception:
        return ""


def analyse_defect(defect: Dict[str, Any], src_root: str = "",
                   language: str = "c", include_events: bool = False,
                   context_lines: int = 0) -> Dict[str, Any]:
    """Run the full analysis for one defect and return a flat record.

    This mirrors ``local_gui``'s per-defect worker (the primary desktop
    application) so the GUI and every headless caller produce the same
    disposition, rationale and fix for the same input. The steps that matter
    for that parity are, in order:

    1. resolve the report's file path against the local checkout,
    2. supply an event trace (synthesised when the report has none),
    3. derive a function name when the report has no function column,
    4. build context, then call ``analyze_defect`` with the same arguments the
       GUI passes (including ``sub_checker``, ``tree`` and ``line_is_various``).

    Deviating from any of these silently changes verdicts, which
    ``tests/test_desktop_parity.py`` pins down.
    """
    _need("heuristic_analyzer")
    from context_builder import build_defect_context
    from heuristic_analyzer import analyze_defect
    from checker_categories import category_for_checker

    checker = (defect.get("checker") or "").strip()
    type_val = defect.get("type", "") or ""
    file_path = defect.get("file", "") or ""
    line = int(defect.get("line") or 0)
    func = defect.get("function", "") or ""
    if func.lower() == "unclassified":
        func = ""
    line_is_various = bool(defect.get("line_is_various"))

    real_path = resolve_source_file(file_path, src_root, "")
    context_path = real_path or file_path

    # A report that never pinned a line and whose checker needs one cannot be
    # judged mechanically; say so instead of guessing an access site. Checkers
    # that are meaningful for a whole function still get analysed — with the
    # line zeroed, as the GUI does, so nothing anchors to a stale line number.
    line_agnostic = checker.upper() in LINE_AGNOSTIC_CHECKERS
    manual_line_review = bool(line_is_various or line <= 0) and not line_agnostic
    if line_is_various and line_agnostic:
        line = 0

    events = _events_for(defect)

    # Derive a function name only where it is safe and useful: anchored by a
    # real line, or needed because the checker can be judged from the whole
    # function. Guessing for a memory-safety checker on a "Various" row would
    # put an unverified function name in a message that asks for a human.
    if not func and context_path and (line > 0 or line_agnostic):
        func = _guess_function_name(context_path, line, language)

    classification = DISPOSITION_NEEDS_REVIEW
    comment = "Context extraction failed"
    fix = ""
    confidence = 0.0
    context: Dict[str, Any] = {}

    try:
        context = build_defect_context(
            {**defect, "events": events, "file": context_path,
             "line": line, "function": func},
            src_root, language,
        ) or {}
    except Exception as exc:                      # context is best-effort
        context = {}
        comment = f"Context extraction failed: {exc}"

    if manual_line_review:
        # The desktop app's rule, mirrored exactly: a checker that needs an
        # access site cannot be judged when the report never pinned one — even
        # if the enclosing function was extracted. Only line-agnostic checkers
        # fall through to the analyser.
        extracted = bool(context.get("function_code"))
        comment = (
            f"The report lists {checker or 'this finding'} in "
            f"{func or file_path or '(unknown file)'} but carries no concrete "
            f"defect line (reported as "
            f"{'Various' if line_is_various else 'missing'}), so no access site "
            f"could be anchored. "
            + ("The enclosing function was extracted and is included with this "
               "finding; supply the actual defect line to have it re-analysed."
               if extracted else
               "Supply the source tree (--src) and/or the real line number to "
               "re-analyse.")
        )
        fix = "Manual review required — provide the actual line number."
        confidence = 0.0
    elif not context.get("function_code") and not context.get("called_function_codes"):
        comment = (
            "Context extraction failed — the source file could not be located "
            f"or read (report path: {file_path or 'unknown'}). "
            "Pass --src <checkout of the analysed tree>."
        )
    else:
        try:
            classification, comment, fix, confidence = analyze_defect(
                context, checker, events,
                sub_checker=type_val,
                file=context_path or file_path,
                line=line, function=func,
                line_is_various=line_is_various,
                tree=context.get("function_tree"),
            )
        except Exception as exc:
            classification = DISPOSITION_NEEDS_REVIEW
            comment = f"Automatic analysis raised an error: {exc}"
            fix = "Manual review required."

    record: Dict[str, Any] = {
        "cid": defect.get("cid", 0),
        "checker": checker,
        "category": category_for_checker(checker),
        "type": type_val,
        "severity": defect.get("severity", ""),
        "file": file_path,
        "resolved_file": real_path,
        "line": line,
        "line_is_various": line_is_various,
        "function": func,
        "disposition": classification,
        "confidence": round(float(confidence or 0.0), 4),
        "comment": (comment or "").strip(),
        "proposed_fix": (fix or "").strip(),
    }
    if include_events:
        record["events"] = events
    if context.get("function_code") or context.get("callers"):
        # One call should be enough to judge the defect: code facts travel with it.
        record["evidence"] = build_evidence(context, defect, line)
    if context_lines:
        code = context.get("function_code") or context.get("source_code") or ""
        if code:
            start = int(context.get("code_start_line") or 1)
            snippet = _snippet(code, start, line, context_lines)
            record["source_context"] = snippet
    return record


def _snippet(code: str, code_start_line: int, defect_line: int,
             window: int) -> Dict[str, Any]:
    """Numbered source window around the defect line, clamped to the function."""
    lines = code.splitlines()
    if not lines:
        return {"start_line": code_start_line, "code": "", "focus_line": defect_line}
    focus = defect_line or code_start_line
    idx = max(0, min(len(lines) - 1, focus - code_start_line))
    lo = max(0, idx - window)
    hi = min(len(lines), idx + window + 1)
    numbered = "\n".join(f"{code_start_line + i:6d} | {lines[i]}"
                         for i in range(lo, hi))
    return {"start_line": code_start_line + lo, "code": numbered,
            "focus_line": focus}


def iter_analysis(defects: Sequence[Dict[str, Any]], src_root: str = "",
                  language: str = "c", limit: int = 0, checker: str = "",
                  cid: int = 0, include_events: bool = False,
                  context_lines: int = 0,
                  progress=None) -> Iterator[Dict[str, Any]]:
    """Yield one analysed record per selected defect (streaming friendly)."""
    selected = list(select_defects(defects, limit=limit, checker=checker, cid=cid))
    total = len(selected)
    for i, defect in enumerate(selected, start=1):
        if progress:
            progress(i, total, defect)
        record = analyse_defect(defect, src_root, language,
                                include_events=include_events,
                                context_lines=context_lines)
        record["index"] = i
        record["total"] = total
        yield record


def select_defects(defects: Sequence[Dict[str, Any]], limit: int = 0,
                   checker: str = "", cid: int = 0,
                   severity: str = "") -> Iterator[Dict[str, Any]]:
    """Apply the filters every entry point shares."""
    checker_u = (checker or "").strip().upper()
    severity_l = (severity or "").strip().lower()
    emitted = 0
    for defect in defects:
        if cid and int(defect.get("cid") or 0) != int(cid):
            continue
        if checker_u and (defect.get("checker") or "").strip().upper() != checker_u:
            continue
        if severity_l and (defect.get("severity") or "").strip().lower() != severity_l:
            continue
        if limit and emitted >= limit:
            return
        emitted += 1
        yield defect


def summarise(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Disposition/confidence roll-up — the same numbers the GUI status bar shows."""
    counts = {d: 0 for d in DISPOSITIONS}
    for r in records:
        disposition = str(r.get("disposition") or DISPOSITION_NEEDS_REVIEW)
        counts[disposition] = counts.get(disposition, 0) + 1

    confidences = [float(r.get("confidence") or 0.0) for r in records]
    return {
        "total": len(records),
        "bug": counts.get(DISPOSITION_BUG, 0),
        "false_positive": counts.get(DISPOSITION_FALSE_POSITIVE, 0),
        "intentional": counts.get(DISPOSITION_INTENTIONAL, 0),
        "needs_review": counts.get(DISPOSITION_NEEDS_REVIEW, 0),
        "mean_confidence": (round(sum(confidences) / len(confidences), 4)
                            if confidences else 0.0),
        "by_checker": _top_counts(records, "checker"),
        "by_severity": _top_counts(records, "severity"),
    }


def _top_counts(records: Sequence[Dict[str, Any]], key: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in records:
        k = str(r.get(key) or "unknown")
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


# --------------------------------------------------------------------------- #
# High-level operations used by the CLI *and* the MCP server
# --------------------------------------------------------------------------- #
def op_capabilities() -> Dict[str, Any]:
    return capabilities_payload()


def op_list(report: str, limit: int = 0, checker: str = "",
            severity: str = "") -> Dict[str, Any]:
    defects = load_defects(report)
    rows = [{
        "cid": d.get("cid", 0),
        "checker": d.get("checker", ""),
        "type": d.get("type", ""),
        "severity": d.get("severity", ""),
        "file": d.get("file", ""),
        "line": d.get("line", 0),
        "line_is_various": bool(d.get("line_is_various")),
        "function": d.get("function", ""),
    } for d in select_defects(defects, limit=limit, checker=checker,
                              severity=severity)]
    return {
        "report": resolve_report_path(report),
        "total_in_report": len(defects),
        "returned": len(rows),
        "defects": rows,
    }


DISPOSITIONS_CSV_HEADER = (
    "CID", "Checker", "Type", "Severity", "Action", "File", "Line", "Function",
    "Classification", "Comment", "Fix", "Timestamp", "Category",
)


def write_dispositions_csv(records: Sequence[Dict[str, Any]], path: str,
                           reviewer: str = "") -> Dict[str, Any]:
    """Write the desktop app's ``coverity_dispositions.csv`` format.

    The column names and order are deliberately **identical** to the header
    written by ``local_gui`` (see ``DISPOSITIONS_CSV_HEADER``, which is pinned
    against that source in ``tests/test_export_results.py``). That is what lets
    the reviewer hand this file straight to the desktop application's
    **Push to Coverity** page (its "Select Dispositions CSV" box accepts both
    the dispositions and the final-decisions layouts) instead of retyping
    dispositions into Coverity Connect by hand.

    CSV is written with ``utf-8-sig`` and ``\\r\\n`` like the desktop app, so
    existing spreadsheets open it without mojibake.
    """
    import csv
    from checker_categories import category_for_checker
    try:
        from coverity_push import default_action_for_classification, normalize_action
    except Exception:                                     # pragma: no cover
        default_action_for_classification = lambda _c: ""  # noqa: E731
        normalize_action = lambda value, *_a: (value or "")  # noqa: E731

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    target = os.path.abspath(os.path.expanduser(path))
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)

    with open(target, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(list(DISPOSITIONS_CSV_HEADER))
        for record in records:
            classification = str(record.get("disposition") or DISPOSITION_NEEDS_REVIEW)
            action = normalize_action(record.get("action", "")) or \
                default_action_for_classification(classification)
            writer.writerow([
                record.get("cid", ""),
                record.get("checker", ""),
                record.get("type", ""),
                record.get("severity", ""),
                action,
                record.get("file", ""),
                record.get("line", 0),
                record.get("function", ""),
                classification,
                (record.get("comment") or "").strip(),
                (record.get("proposed_fix") or "").strip(),
                stamp,
                record.get("category") or category_for_checker(record.get("checker", "")),
            ])

    counts: Dict[str, int] = {}
    for record in records:
        key = str(record.get("disposition") or DISPOSITION_NEEDS_REVIEW)
        counts[key] = counts.get(key, 0) + 1
    return {
        "path": target,
        "rows": len(records),
        "header": list(DISPOSITIONS_CSV_HEADER),
        "dispositions": counts,
        "reviewer": reviewer,
        "next_step": ("Open the desktop Coverity Findings Analyzer → Push page → "
                      "Select Dispositions CSV → choose this file → validate the "
                      "CIDs → Push. Credentials stay in the desktop app."),
    }


def op_analyze(report: str, src_root: str = "", language: str = "c",
               limit: int = 0, checker: str = "", cid: int = 0,
               severity: str = "", include_events: bool = False,
               context_lines: int = 0,
               progress=None) -> Dict[str, Any]:
    defects = load_defects(report)
    records = list(iter_analysis(defects, src_root=src_root, language=language,
                                 limit=limit, checker=checker, cid=cid,
                                 include_events=include_events,
                                 context_lines=context_lines, progress=progress))
    if severity:
        records = [r for r in records
                   if (r.get("severity") or "").lower() == severity.lower()]
    return {
        "report": resolve_report_path(report),
        "src_root": os.path.abspath(src_root) if src_root else "",
        "language": language,
        "total_in_report": len(defects),
        "capabilities": capabilities_payload(),
        "summary": summarise(records),
        "defects": records,
    }


def op_context(report: str, cid: int, src_root: str = "", language: str = "c",
               lines: int = 30) -> Dict[str, Any]:
    """Source-anchored view of a single defect (what a reviewer needs first)."""
    defects = load_defects(report)
    match = next((d for d in defects if int(d.get("cid") or 0) == int(cid)), None)
    if match is None:
        raise BridgeError(
            f"CID {cid} not found in {os.path.basename(resolve_report_path(report))}.",
            hint="Use the list command to see the CIDs present in this report.",
            kind="NotFound",
        )
    record = analyse_defect(match, src_root, language,
                            include_events=True, context_lines=lines)
    record.pop("index", None)
    record.pop("total", None)
    return record


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _emit(payload: Dict[str, Any], out, pretty: bool) -> None:
    json.dump(payload, out, indent=2 if pretty else None, ensure_ascii=False)
    out.write("\n")
    out.flush()


def _fail(out, pretty: bool, exc: Exception, command: str) -> int:
    payload = {
        "ok": False,
        "schema": SCHEMA_VERSION,
        "command": command,
        "error": {
            "type": getattr(exc, "kind", type(exc).__name__),
            "message": getattr(exc, "message", str(exc)),
            "hint": getattr(exc, "hint", ""),
        },
    }
    _emit(payload, out, pretty)
    return 1


def build_parser() -> argparse.ArgumentParser:
    # --pretty is accepted both before and after the subcommand; the subparser
    # copy uses SUPPRESS so an omitted flag does not clobber the global one.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--pretty", action="store_true",
                        default=argparse.SUPPRESS,
                        help="indent the JSON (for humans; the extension does not need it)")

    parser = argparse.ArgumentParser(
        prog="vscode_bridge.py",
        description="Headless JSON front end for the Coverity Tool "
                    "(used by the VS Code extension and coverity_mcp_server.py).",
    )
    parser.add_argument("--version", action="store_true",
                        help="print the bridge/schema version as JSON and exit")
    parser.add_argument("--pretty", action="store_true",
                        help="indent the JSON (for humans; the extension does not need it)")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("capabilities", help="report which analysis backends are live",
                   parents=[common])

    p_list = sub.add_parser("list", help="list defects in a report (no analysis)",
                            parents=[common])
    _add_report_arg(p_list)
    _add_filter_args(p_list)

    p_analyze = sub.add_parser("analyze", parents=[common],
                               help="analyse defects and emit dispositions")
    _add_report_arg(p_analyze)
    _add_filter_args(p_analyze)
    p_analyze.add_argument("--src", default="", help="root of the analysed C/C++ source tree")
    p_analyze.add_argument("--language", default="c", help="c or cpp (default: c)")
    p_analyze.add_argument("--events", action="store_true",
                           help="include the Coverity event trace for each defect")
    p_analyze.add_argument("--context-lines", type=int, default=0, metavar="N",
                           help="attach an N-line numbered source window per defect")
    p_analyze.add_argument("--jsonl", action="store_true",
                           help="stream one JSON object per line as each defect finishes")
    p_analyze.add_argument("--csv", default="", metavar="PATH",
                           help="also write a dispositions CSV that the desktop "
                                "app's Push page can load")
    p_analyze.add_argument("--out", default="",
                           help="also write the full annotation to this JSON file")
    p_analyze.add_argument("--quiet", action="store_true",
                           help="suppress per-defect progress on stderr")

    p_ctx = sub.add_parser("context", parents=[common],
                           help="source context for one CID")
    _add_report_arg(p_ctx)
    p_ctx.add_argument("--cid", type=int, required=True, help="defect CID")
    p_ctx.add_argument("--src", default="", help="root of the analysed C/C++ source tree")
    p_ctx.add_argument("--language", default="c")
    p_ctx.add_argument("--lines", type=int, default=30,
                       help="lines of context on each side of the defect")

    return parser


def _add_report_arg(p) -> None:
    p.add_argument("--report", required=True,
                   help="Coverity HTML report (index.html or its folder), "
                        "Excel export (.xlsx) or a triage .json")


def _add_filter_args(p) -> None:
    p.add_argument("--limit", type=int, default=0, help="analyse at most N defects")
    p.add_argument("--checker", default="", help="only this checker, e.g. BUFFER_SIZE")
    p.add_argument("--cid", type=int, default=0, help="only this defect CID")
    p.add_argument("--severity", default="", help="only this severity")


def _progress_printer(quiet: bool):
    def _progress(i: int, total: int, defect: Dict[str, Any]) -> None:
        if quiet:
            return
        print(f"[{i}/{total}] CID {defect.get('cid')} "
              f"{defect.get('checker')} ...", file=sys.stderr, flush=True)
    return _progress


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # stdout is reserved for JSON.  Anything the analysis stack prints (a
    # warning, a traceback from a caught exception) must not land in the
    # payload, so the process' own stdout is redirected to stderr for the
    # duration and the payload is written to the saved handle.
    out = sys.stdout
    sys.stdout = sys.stderr

    command = args.command or ("version" if args.version else "capabilities")
    try:
        if args.version:
            _emit({"ok": True, "schema": SCHEMA_VERSION, "version": SCHEMA_VERSION,
                   "bridge": os.path.abspath(__file__), "python": sys.version.split()[0]},
                  out, args.pretty)
            return 0
        if args.command is None:
            parser.print_help(sys.stderr)
            return 2

        if command == "capabilities":
            payload = {"ok": True, "schema": SCHEMA_VERSION, "command": command,
                       "capabilities": op_capabilities()}
            _emit(payload, out, args.pretty)
            return 0

        if command == "list":
            payload = {"ok": True, "schema": SCHEMA_VERSION, "command": command,
                       **op_list(args.report, limit=args.limit,
                                 checker=args.checker, severity=args.severity)}
            _emit(payload, out, args.pretty)
            return 0

        if command == "context":
            payload = {"ok": True, "schema": SCHEMA_VERSION, "command": command,
                       "defect": op_context(args.report, args.cid, args.src,
                                            args.language, args.lines)}
            _emit(payload, out, args.pretty)
            return 0

        if command == "analyze":
            defects = load_defects(args.report)
            selected = list(select_defects(defects, limit=args.limit,
                                           checker=args.checker, cid=args.cid,
                                           severity=args.severity))
            progress = _progress_printer(args.quiet)
            started = time.time()
            records: List[Dict[str, Any]] = []

            if args.jsonl:
                _emit({"ok": True, "schema": SCHEMA_VERSION, "command": "analyze",
                       "event": "start", "report": resolve_report_path(args.report),
                       "total": len(selected)}, out, False)
                for i, defect in enumerate(selected, start=1):
                    progress(i, len(selected), defect)
                    record = analyse_defect(defect, args.src, args.language,
                                            include_events=args.events,
                                            context_lines=args.context_lines)
                    record["index"] = i
                    record["total"] = len(selected)
                    records.append(record)
                    _emit({"ok": True, "schema": SCHEMA_VERSION, "event": "defect",
                           **record}, out, False)
                summary = summarise(records)
                if args.out:
                    write_annotation(args.out, {
                        "report": resolve_report_path(args.report),
                        "src_root": os.path.abspath(args.src) if args.src else "",
                        "language": args.language,
                        "capabilities": capabilities_payload(),
                        "summary": summary,
                        "defects": records,
                    })
                csv_info = write_dispositions_csv(records, args.csv) \
                    if getattr(args, "csv", "") else {}
                _emit({"ok": True, "schema": SCHEMA_VERSION, "event": "done",
                       "summary": summary,
                       "dispositions_csv": csv_info,
                       "written_to": os.path.abspath(args.out) if args.out else "",
                       "elapsed_seconds": round(time.time() - started, 3)}, out, False)
            else:
                for i, defect in enumerate(selected, start=1):
                    progress(i, len(selected), defect)
                    record = analyse_defect(defect, args.src, args.language,
                                            include_events=args.events,
                                            context_lines=args.context_lines)
                    record["index"] = i
                    record["total"] = len(selected)
                    records.append(record)
                payload = {
                    "ok": True, "schema": SCHEMA_VERSION, "command": "analyze",
                    "report": resolve_report_path(args.report),
                    "src_root": os.path.abspath(args.src) if args.src else "",
                    "language": args.language,
                    "total_in_report": len(defects),
                    "capabilities": capabilities_payload(),
                    "elapsed_seconds": round(time.time() - started, 3),
                    "summary": summarise(records),
                    "defects": records,
                }
                if args.out:
                    write_annotation(args.out, payload)
                    payload["written_to"] = os.path.abspath(args.out)
                if getattr(args, "csv", ""):
                    payload["dispositions_csv"] = write_dispositions_csv(
                        records, args.csv)
                _emit(payload, out, args.pretty)
            return 0

        raise BridgeError(f"Unknown command: {command}")
    except BridgeError as exc:
        return _fail(out, getattr(args, "pretty", False), exc, command)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:                       # never leak a traceback to a parser
        return _fail(out, getattr(args, "pretty", False), exc, command)
    finally:
        sys.stdout = out


def write_annotation(path: str, payload: Dict[str, Any]) -> str:
    """Persist the annotation so an editor can reload it without re-analysing."""
    target = os.path.abspath(os.path.expanduser(path))
    parent = os.path.dirname(target)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    document = {
        "schema": SCHEMA_VERSION,
        "tool": "coverity-tool",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "report": payload.get("report", ""),
        "src_root": payload.get("src_root", ""),
        "language": payload.get("language", "c"),
        "capabilities": payload.get("capabilities", {}),
        "summary": payload.get("summary", {}),
        "defects": payload.get("defects", []),
    }
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(document, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, target)
    return target


if __name__ == "__main__":
    raise SystemExit(main())
