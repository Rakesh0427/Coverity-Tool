#!/usr/bin/env python3
"""
coverity_mcp_server.py — expose the Coverity Tool to AI agents over MCP.

What this is
------------
A Model Context Protocol server (stdio transport, JSON-RPC 2.0, newline
delimited) that publishes this repository's triage engine as agent tools:

    coverity_capabilities      which analysis backends are live
    coverity_list_defects      enumerate findings in a report
    coverity_analyze_defect    one CID: disposition, rationale, suggested fix
    coverity_triage_report     whole report: verdicts + roll-up statistics
    coverity_source_context    the source window a defect was judged against

Adding it to VS Code (no build step, no npm) — see docs/VSCODE_INTEGRATION.md:

    // .vscode/mcp.json
    { "servers": { "coverity": {
        "type": "stdio",
        "command": "python",
        "args": ["${workspaceFolder}/Coverity-Tool/coverity_mcp_server.py"],
        "env": { "COVERITY_REPORT": "${workspaceFolder}/coverity/index.html",
                 "COVERITY_SRC_ROOT": "${workspaceFolder}/src" } } } }

Why it is hand-rolled
---------------------
The official `mcp` Python package would add a dependency to a tool that is
deliberately installable offline from `requirements.txt` alone (and is frozen
into a Windows exe with PyInstaller). The wire format needed here — initialize,
tools/list, tools/call — is small and stable, and it is the same engine the GUI
uses: `vscode_bridge.py` does the analysing, this file only translates.

Protocol notes
--------------
* stdout is the transport. `sys.stdout` is immediately repointed at stderr so a
  stray print inside any analyzer cannot corrupt a frame.
* Unknown requests get a proper JSON-RPC error object rather than silence, and
  notifications are never answered (per spec, a notification must not get a
  response).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import vscode_bridge as bridge          # noqa: E402  (the analysis engine)

#: MCP revisions this server is known to speak. The client's requested version
#: is echoed when it is one of these, otherwise we answer with the newest we
#: implement and let the client decide whether to continue.
KNOWN_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_PROTOCOL_VERSION = "2025-06-18"

SERVER_NAME = "coverity-tool"
SERVER_VERSION = "1.0.0"

#: Hard ceiling on defects returned in one tool result, so an agent asking for a
#: 4000-finding report cannot blow up its own context window. Callers raise it
#: deliberately with the `limit` argument.
DEFAULT_MAX_RESULTS = int(os.environ.get("COVERITY_MCP_MAX_RESULTS", "25"))
HARD_MAX_RESULTS = int(os.environ.get("COVERITY_MCP_HARD_MAX_RESULTS", "500"))


# --------------------------------------------------------------------------- #
# Defaults (set COVERITY_* in .vscode/mcp.json env so an agent never has to
# guess the report location)
# --------------------------------------------------------------------------- #
def _defaults() -> Dict[str, str]:
    return {
        "report": os.environ.get("COVERITY_REPORT", "").strip(),
        "src_root": os.environ.get("COVERITY_SRC_ROOT", "").strip(),
        "language": (os.environ.get("COVERITY_LANGUAGE", "c").strip() or "c"),
        "output_dir": os.environ.get("COVERITY_MCP_OUTPUT_DIR",
                                     os.path.join(HERE, ".coverity")).strip(),
    }


class ToolError(Exception):
    """Raised for a bad tool argument; surfaced to the model as isError."""


# --------------------------------------------------------------------------- #
# Result formatting
# --------------------------------------------------------------------------- #
def _annotation_path(report: str) -> str:
    """Where the last triage run for this report was cached on disk."""
    out_dir = _defaults()["output_dir"]
    base = os.path.splitext(os.path.basename(str(report)))[0] or "report"
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in base)
    return os.path.join(out_dir, f"{safe}.triage.json")


def _format_defect(record: Dict[str, Any], with_events: bool = False) -> str:
    lines = [
        f"### CID {record.get('cid')} — {record.get('checker')} "
        f"({record.get('category') or 'uncategorised'})",
        f"- **Disposition:** {record.get('disposition')} "
        f"(confidence {int(round(float(record.get('confidence') or 0) * 100))}%)",
        f"- **Location:** {record.get('resolved_file') or record.get('file') or 'unknown'}"
        f":{record.get('line') or '?'}"
        + (f" in `{record.get('function')}()`" if record.get("function") else ""),
    ]
    if record.get("severity"):
        lines.append(f"- **Severity:** {record['severity']}")
    if record.get("type"):
        lines.append(f"- **Coverity type:** {record['type']}")
    if record.get("comment"):
        lines.append(f"- **Rationale:** {record['comment']}")
    if record.get("proposed_fix"):
        lines.append(f"- **Suggested fix:** `{record['proposed_fix']}`")
    if record.get("source_context", {}).get("code"):
        lines.append("- **Source (numbered):**")
        lines.append("```c\n" + record["source_context"]["code"] + "\n```")
    if with_events and record.get("events"):
        lines.append("- **Event trace:**")
        for event in record["events"]:
            lines.append(f"  {event.get('step')}. [{event.get('type')}] "
                         f"{event.get('description')} "
                         f"({event.get('file')}:{event.get('line')})")
    return "\n".join(lines)


def _format_summary(summary: Dict[str, Any]) -> str:
    return (f"**{summary.get('total', 0)} defects** — "
            f"Bug: {summary.get('bug', 0)}, "
            f"False positive: {summary.get('false_positive', 0)}, "
            f"Intentional: {summary.get('intentional', 0)}, "
            f"Needs review: {summary.get('needs_review', 0)} "
            f"(mean confidence {summary.get('mean_confidence', 0)})")


def _json_block(payload: Any) -> str:
    return "```json\n" + json.dumps(payload, indent=2, ensure_ascii=False) + "\n```"


def _text_result(text: str, structured: Any = None) -> Dict[str, Any]:
    """MCP tool result: prose for the model, plus machine-readable JSON."""
    content: List[Dict[str, Any]] = [{"type": "text", "text": text}]
    if structured is not None:
        content.append({"type": "text", "text": _json_block(structured)})
    return {"content": content, "isError": False}


# --------------------------------------------------------------------------- #
# Argument plumbing
# --------------------------------------------------------------------------- #
def _require(args: Dict[str, Any], *names: str) -> str:
    for key in names:
        value = (args.get(key) or "").strip()
        if value:
            return value
    return ""


def _report_arg(args: Dict[str, Any]) -> str:
    report = _require(args, "report", "report_path")
    if not report:
        report = _defaults()["report"]
    if not report:
        raise ToolError(
            "No report given. Pass `report` (path to Coverity's index.html, the "
            "folder containing it, an .xlsx export, or a .triage.json produced "
            "earlier), or set COVERITY_REPORT in the server environment."
        )
    if not os.path.exists(os.path.expanduser(report)):
        raise ToolError(f"Report not found: {report}")
    return report


def _src_arg(args: Dict[str, Any]) -> str:
    src = _require(args, "src_root", "src", "source_root") or _defaults()["src_root"]
    if src and not os.path.isdir(os.path.expanduser(src)):
        raise ToolError(f"Source root is not a directory: {src}")
    return src


def _language_arg(args: Dict[str, Any]) -> str:
    return (_require(args, "language") or _defaults()["language"]).lower()


def _limit_arg(args: Dict[str, Any]) -> int:
    raw = args.get("limit", DEFAULT_MAX_RESULTS)
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        raise ToolError(f"`limit` must be an integer, got {raw!r}")
    return max(1, min(limit, HARD_MAX_RESULTS))


def _cid_arg(args: Dict[str, Any]) -> int:
    raw = args.get("cid", args.get("id"))
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ToolError(f"`cid` must be an integer Coverity defect id, got {raw!r}")


# --------------------------------------------------------------------------- #
# Tool implementations
# --------------------------------------------------------------------------- #
def tool_capabilities(args: Dict[str, Any]) -> Dict[str, Any]:
    caps = bridge.op_capabilities()
    lines = [f"**Analysis depth: {str(caps.get('depth', '')).upper()}** "
             f"(mode: `{caps.get('mode', 'unknown')}`)", "",
             str(caps.get("verdicts") or ""), ""]
    for backend in caps.get("backends", []):
        mark = "available" if backend["available"] else "UNAVAILABLE"
        lines.append(f"- {backend['label']}: {mark} — {backend['detail']}")
    if caps.get("missing"):
        lines.append("")
        lines.append("Missing critical backends: " + ", ".join(caps["missing"]))
        lines.append("This lowers accuracy; the returned comments say so when a "
                     "verdict was reached without them.")
    lines.append("")
    lines.append("Install the full set with `pip install -r requirements.txt`.")
    return _text_result("\n".join(lines), caps)


def tool_list_defects(args: Dict[str, Any]) -> Dict[str, Any]:
    report = _report_arg(args)
    limit = _limit_arg(args)
    payload = bridge.op_list(
        report,
        limit=limit,
        checker=_require(args, "checker"),
        severity=_require(args, "severity"),
    )
    rows = payload["defects"]
    lines = [f"{payload['returned']} of {payload['total_in_report']} defects "
             f"in `{os.path.basename(payload['report'])}`.", "",
             "| CID | Checker | Severity | File | Line | Function |",
             "| --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        lines.append(
            f"| {row['cid']} | {row['checker']} | {row['severity'] or '-'} | "
            f"{row['file'] or '-'} | {row['line'] or 'Various'} | "
            f"{row['function'] or '-'} |")
    if payload["returned"] < payload["total_in_report"]:
        lines.append("")
        lines.append("Increase `limit` (or narrow with `checker`/`severity`) to see "
                     "the rest.")
    return _text_result("\n".join(lines), payload)


def _format_evidence(record: Dict[str, Any]) -> str:
    """Render the code facts a model needs to judge the defect on its own.

    The tool's verdict is the starting point; this block is what makes an
    informed second opinion possible: the line the verdict hangs on, the
    declarations that fix capacities, the guards that may already rule the case
    out, and the callers/callees that decide reachability.
    """
    evidence = record.get("evidence") or {}
    if not evidence:
        return ""
    function = evidence.get("function") or {}
    lines = ["", "**Evidence dossier** (everything the engine read around this defect)"]
    if function:
        lines.append(f"- Function `{function.get('name') or '?'}` — "
                     f"lines {function.get('start_line')}–{function.get('end_line')} "
                     f"({function.get('line_count')} lines)")
        if function.get("signature"):
            lines.append(f"  - signature: `{function['signature']}`")
    defect_line = evidence.get("defect_line") or {}
    if defect_line.get("line"):
        lines.append(f"- Defect line {defect_line['line']}: "
                     f"`{defect_line.get('text', '')}`")
    for declaration in evidence.get("declarations") or []:
        kind = (f"array[{declaration['size']}]" if declaration.get("array")
                else "pointer" if declaration.get("pointer") else "value")
        focus = "  ← the flagged line" if declaration.get("focus") else ""
        lines.append(f"- Declaration {declaration['line']}: `{declaration['text']}` "
                     f"— {declaration['name']} ({kind}){focus}")
    for guard in evidence.get("guards") or []:
        focus = "  ← the flagged line" if guard.get("focus") else ""
        lines.append(f"- Guard {guard['line']} ({guard['kind']}): "
                     f"`{guard['text']}`{focus}")
    callers = evidence.get("callers") or []
    if callers:
        lines.append(f"- Callers ({evidence.get('counts', {}).get('callers', len(callers))} found, "
                     f"{len(callers)} shown) — read these to judge reachability:")
        for caller in callers:
            suffix = " (body truncated)" if caller.get("code_truncated") else ""
            lines.append(f"  - `{caller['caller'] or '?'}` at {caller['file']}:{caller['line']}{suffix}")
    for callee in evidence.get("callees") or []:
        lines.append(f"- Callee `{callee['name']}`: {callee.get('signature') or 'signature unavailable'}")
    if evidence.get("globals"):
        lines.append(f"- File-scope globals: {', '.join(evidence['globals'])}")
    lines.append("")
    lines.append("Judge the defect against this code yourself: the verdict above is "
                 "the engine's reading, not the last word. If you disagree, quote "
                 "the line that justifies it, and say what the engine missed.")
    return "\n".join(lines)


def tool_analyze_defect(args: Dict[str, Any]) -> Dict[str, Any]:
    report = _report_arg(args)
    cid = _cid_arg(args)
    record = bridge.op_context(report, cid, src_root=_src_arg(args),
                               language=_language_arg(args),
                               lines=int(args.get("context_lines", 25) or 25))
    return _text_result(_format_defect(record, with_events=True)
                        + _format_evidence(record), record)


def tool_triage_report(args: Dict[str, Any]) -> Dict[str, Any]:
    report = _report_arg(args)
    src_root = _src_arg(args)
    limit = _limit_arg(args)
    checker = _require(args, "checker")
    severity = _require(args, "severity")

    out_path = _annotation_path(report)
    payload = bridge.op_analyze(report, src_root=src_root,
                                language=_language_arg(args), limit=limit,
                                checker=checker, severity=severity)
    try:
        bridge.write_annotation(out_path, payload)
        payload["written_to"] = out_path
    except OSError:
        payload.pop("written_to", None)

    lines = [_format_summary(payload["summary"]), ""]
    caps = payload.get("capabilities", {})
    if caps.get("depth") and caps["depth"] != "full":
        lines.append(f"Analysis depth: **{caps['depth']}** "
                     f"(missing: {', '.join(caps.get('missing', [])) or 'none'})")
        lines.append("")
    lines.append(f"| CID | Checker | Disposition | Confidence | Location |")
    lines.append("| --- | --- | --- | --- | --- |")
    for record in payload["defects"]:
        location = record.get("resolved_file") or record.get("file") or "-"
        lines.append(f"| {record['cid']} | {record['checker']} | "
                     f"{record['disposition']} | "
                     f"{int(round(record['confidence'] * 100))}% | "
                     f"{location}:{record['line'] or '?'} |")
    lines.append("")
    lines.append("Per-defect rationale and suggested fixes follow.")
    for record in payload["defects"]:
        lines.append("")
        lines.append(_format_defect(record))
    if payload["summary"]["needs_review"]:
        lines.append("")
        lines.append("Defects marked *Needs review* are the ones a human must "
                     "decide; ask for a specific CID to see its event trace.")
    if src_root == "":
        lines.append("")
        lines.append("No source root was supplied, so verdicts used the report's "
                     "own detail pages only. Pass `src_root` for code-anchored "
                     "analysis.")
    return _text_result("\n".join(lines), payload)


def tool_export_results(args: Dict[str, Any]) -> Dict[str, Any]:
    """Analyse a report and write the artefacts a human needs downstream."""
    report = _report_arg(args)
    src_root = _src_arg(args)
    output_path = str(args.get("output_path") or "").strip()
    payload = bridge.op_analyze(report, src_root=src_root,
                               language=_language_arg(args),
                               limit=_limit_arg(args),
                               checker=_require(args, "checker"),
                               severity=_require(args, "severity"))

    if not output_path:
        out_dir = _defaults()["output_dir"]
        base = os.path.splitext(os.path.basename(bridge.resolve_report_path(report)))[0]
        output_path = os.path.join(out_dir, f"{base or 'report'}_dispositions.csv")
    csv_info = bridge.write_dispositions_csv(payload["defects"], output_path)
    payload["dispositions_csv"] = csv_info

    note = ("This CSV carries the same columns the desktop Coverity Findings "
            "Analyzer writes, so it can be loaded straight into its Push page "
            "(*Select Dispositions CSV*) and pushed to Coverity Connect there — "
            "no re-typing, and no credentials in this editor.")
    lines = [
        f"Wrote **{csv_info['rows']}** disposition(s) to `{csv_info['path']}`.",
        "",
        _format_summary(payload["summary"]),
        "",
        note,
        "",
        "Columns: " + ", ".join(f"`{name}`" for name in csv_info["header"]) + ".",
    ]
    if src_root == "":
        lines += ["", "No `src_root` was supplied, so verdicts used the report's "
                      "detail pages only — pass the source root for code-anchored "
                      "analysis before pushing."]
    return _text_result("\n".join(lines), payload)


def tool_source_context(args: Dict[str, Any]) -> Dict[str, Any]:
    report = _report_arg(args)
    cid = _cid_arg(args)
    lines = int(args.get("context_lines", 40) or 40)
    record = bridge.op_context(report, cid, src_root=_src_arg(args),
                               language=_language_arg(args), lines=lines)
    context = record.get("source_context") or {}
    if not context.get("code"):
        return _text_result(
            f"No source could be shown for CID {cid}: the file "
            f"`{record.get('file')}` was not found locally. Pass `src_root` "
            "pointing at the analysed checkout.", record)
    header = (f"CID {cid} — {record['checker']} at "
              f"{record.get('resolved_file') or record.get('file')}:{record.get('line')} "
              f"({record.get('disposition')})")
    return _text_result(
        f"{header}\n\n```c\n{context['code']}\n```\n\n"
        f"**Proposed fix:** `{record.get('proposed_fix') or 'none'}`\n\n"
        f"**Rationale:** {record.get('comment') or ''}"
        + _format_evidence(record), record)


# --------------------------------------------------------------------------- #
# Tool registry
# --------------------------------------------------------------------------- #
TOOLS: List[Dict[str, Any]] = [
    {
        "name": "coverity_capabilities",
        "title": "Coverity analysis capabilities",
        "description": (
            "Report which optional analysis backends (tree-sitter AST, libclang "
            "types, z3 path proofs, cppcheck corroboration) are available in the "
            "Coverity Tool's Python environment, and the resulting analysis "
            "depth. Call this first when a verdict looks weak or when explaining "
            "why a defect was marked 'Needs review'."),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "coverity_list_defects",
        "title": "List Coverity defects",
        "description": (
            "Enumerate the defects in a Coverity HTML report (.html, or the "
            "folder containing index.html) or an Excel export (.xlsx), without "
            "running the analyser. Returns CID, checker, severity, file, line "
            "and function for each finding. Use it to pick a CID to analyse, or "
            "to count what is in a report. Fast."),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "inputSchema": {
            "type": "object",
            "properties": {
                "report": {"type": "string",
                           "description": "Path to index.html, the report folder, "
                                          "an .xlsx export, or a .triage.json."},
                "limit": {"type": "integer", "minimum": 1,
                          "description": "Maximum rows to return (default 25)."},
                "checker": {"type": "string",
                            "description": "Only this checker, e.g. BUFFER_SIZE."},
                "severity": {"type": "string",
                             "description": "Only this severity, e.g. High."},
            },
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "coverity_analyze_defect",
        "title": "Analyse one Coverity defect",
        "description": (
            "Run the Coverity Tool's evidence-based analysis on a single defect "
            "CID and return its disposition (Bug / False positive / Intentional / "
            "Needs review), confidence, a senior-engineer rationale citing "
            "CWE/CERT, a suggested minimal fix, the Coverity event trace, and the "
            "source window the verdict was based on. Use this to justify a triage "
            "decision or to decide whether a finding is worth fixing."),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "inputSchema": {
            "type": "object",
            "properties": {
                "cid": {"type": "integer", "description": "Coverity defect id."},
                "report": {"type": "string", "description": "Path to the report."},
                "src_root": {"type": "string",
                             "description": "Root of the analysed C/C++ checkout. "
                                            "Strongly recommended: without it the "
                                            "verdict cannot read the code."},
                "language": {"type": "string", "enum": ["c", "cpp"],
                             "description": "Source language (default c)."},
                "context_lines": {"type": "integer",
                                  "description": "Source lines around the defect "
                                                 "(default 25)."},
            },
            "required": ["cid"],
            "additionalProperties": False,
        },
    },
    {
        "name": "coverity_triage_report",
        "title": "Triage a whole Coverity report",
        "description": (
            "Analyse every defect in a Coverity report and return a disposition "
            "table plus per-defect rationale, suggested fixes and roll-up "
            "statistics (how many Bug / False positive / Intentional / Needs "
            "review). This is the slow, thorough tool — for large reports pass "
            "`limit`, or narrow with `checker`/`severity` first. The result is "
            "also written to a .triage.json next to the tool so later questions "
            "do not pay the analysis cost again."),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "inputSchema": {
            "type": "object",
            "properties": {
                "report": {"type": "string", "description": "Path to the report."},
                "src_root": {"type": "string",
                             "description": "Root of the analysed C/C++ checkout — "
                                            "required for code-anchored verdicts."},
                "language": {"type": "string", "enum": ["c", "cpp"]},
                "limit": {"type": "integer", "minimum": 1,
                          "description": f"Max defects to analyse (default "
                                         f"{DEFAULT_MAX_RESULTS}, hard cap "
                                         f"{HARD_MAX_RESULTS})."},
                "checker": {"type": "string", "description": "Only this checker."},
                "severity": {"type": "string", "description": "Only this severity."},
            },
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "coverity_export_results",
        "title": "Export triage results for pushing back to Coverity",
        "description": (
            "Run the whole triage and write a dispositions CSV that the desktop "
            "Coverity Findings Analyzer can load and push to Coverity Connect "
            "(Bug → Fix Required, False positive/Intentional → Ignore, "
            "Needs review → Undecided). Use this when the user wants the results "
            "out of the editor and into their triage workflow, or asks 'how do I "
            "push this back?'. Never asks for Coverity credentials — pushing "
            "stays in the desktop app or on the command line."),
        "annotations": {"readOnlyHint": False, "openWorldHint": False},
        "inputSchema": {
            "type": "object",
            "properties": {
                "report": {"type": "string", "description": "Path to the report."},
                "src_root": {"type": "string",
                             "description": "Root of the analysed C/C++ checkout."},
                "language": {"type": "string", "enum": ["c", "cpp"]},
                "output_path": {"type": "string",
                                "description": "Where to write the CSV. Defaults "
                                               "to <output dir>/<report>_dispositions.csv."},
                "limit": {"type": "integer", "minimum": 1,
                          "description": f"Max defects (default {DEFAULT_MAX_RESULTS}, "
                                         f"hard cap {HARD_MAX_RESULTS})."},
                "checker": {"type": "string", "description": "Only this checker."},
                "severity": {"type": "string", "description": "Only this severity."},
            },
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "coverity_source_context",
        "title": "Show source context for a defect",
        "description": (
            "Return the exact numbered source window (and suggested fix) that the "
            "Coverity Tool used when judging a defect CID. Use this when the user "
            "asks to see the code behind a finding, or when you want to write a "
            "patch: it gives you the real local path and line."),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "inputSchema": {
            "type": "object",
            "properties": {
                "cid": {"type": "integer", "description": "Coverity defect id."},
                "report": {"type": "string", "description": "Path to the report."},
                "src_root": {"type": "string", "description": "Root of the checkout."},
                "language": {"type": "string", "enum": ["c", "cpp"]},
                "context_lines": {"type": "integer",
                                  "description": "Lines shown each side (default 40)."},
            },
            "required": ["cid"],
            "additionalProperties": False,
        },
    },
]

TOOL_IMPL: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "coverity_capabilities": tool_capabilities,
    "coverity_list_defects": tool_list_defects,
    "coverity_analyze_defect": tool_analyze_defect,
    "coverity_triage_report": tool_triage_report,
    "coverity_export_results": tool_export_results,
    "coverity_source_context": tool_source_context,
}


# --------------------------------------------------------------------------- #
# JSON-RPC plumbing
# --------------------------------------------------------------------------- #
def _send(message: Dict[str, Any], out) -> None:
    out.write(json.dumps(message, ensure_ascii=False) + "\n")
    out.flush()


def _result(msg_id: Any, result: Dict[str, Any], out) -> None:
    _send({"jsonrpc": "2.0", "id": msg_id, "result": result}, out)


def _error(msg_id: Any, code: int, message: str, data: Any = None, out=None) -> None:
    error: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    _send({"jsonrpc": "2.0", "id": msg_id, "error": error}, out)


def _negotiate_version(params: Dict[str, Any]) -> str:
    requested = str(params.get("protocolVersion") or "")
    if requested in KNOWN_PROTOCOL_VERSIONS:
        return requested
    # Answer with what we implement; a client that cannot use it will say so.
    return DEFAULT_PROTOCOL_VERSION


def handle_request(message: Dict[str, Any], out) -> None:
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    # Notifications (no id) must never receive a response.
    if msg_id is None and str(method or "").startswith("notifications/"):
        return

    try:
        if method == "initialize":
            _result(msg_id, {
                "protocolVersion": _negotiate_version(params),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION,
                               "title": "Coverity Tool"},
                "instructions": (
                    "Analyses Coverity static-analysis findings for C/C++ with the "
                    "local Coverity Tool engine. Typical flow: coverity_list_defects "
                    "to see what is in the report, then coverity_analyze_defect (or "
                    "coverity_triage_report) for evidence-based dispositions, "
                    "rationales and suggested fixes. A disposition of 'Needs review' "
                    "means the evidence was genuinely inconclusive — say so rather "
                    "than inventing a verdict. Confirm the analysis depth with "
                    "coverity_capabilities before presenting numbers as authoritative."
                ),
            }, out)
            return

        if method == "ping":
            _result(msg_id, {}, out)
            return

        if method == "tools/list":
            _result(msg_id, {"tools": TOOLS}, out)
            return

        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                _error(msg_id, -32602, "Invalid params: 'arguments' must be an object",
                       out=out)
                return
            impl = TOOL_IMPL.get(str(name))
            if impl is None:
                _error(msg_id, -32602, f"Unknown tool: {name}",
                       data={"available": sorted(TOOL_IMPL)}, out=out)
                return
            try:
                _result(msg_id, impl(arguments), out)
            except ToolError as exc:
                # A bad argument is not a transport failure: report it in-band so
                # the model can correct itself and retry.
                _result(msg_id, {"content": [{"type": "text",
                                              "text": f"{exc}"}],
                                 "isError": True}, out)
            except bridge.BridgeError as exc:
                hint = f"\n\nHint: {exc.hint}" if exc.hint else ""
                _result(msg_id, {"content": [{"type": "text",
                                              "text": f"{exc.message}{hint}"}],
                                 "isError": True}, out)
            except Exception as exc:
                _result(msg_id, {"content": [{"type": "text", "text":
                                              f"Analysis failed: {type(exc).__name__}: {exc}"}],
                                 "isError": True}, out)
            return

        if method in ("resources/list",):
            _result(msg_id, {"resources": []}, out)
            return

        if method in ("prompts/list",):
            _result(msg_id, {"prompts": []}, out)
            return

        if method in ("completions/list", "logging/setLevel"):
            _result(msg_id, {}, out)
            return

        if msg_id is None:
            return                     # unknown notification: ignore, do not answer
        _error(msg_id, -32601, f"Method not found: {method}", out=out)

    except Exception as exc:           # never take the transport down
        traceback.print_exc(file=sys.stderr)
        if msg_id is not None:
            _error(msg_id, -32603, f"Internal error: {exc}", out=out)


def serve(stdin=None, out=None) -> int:
    stdin = stdin if stdin is not None else sys.stdin
    out = out if out is not None else _TRANSPORT_OUT
    for raw in stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            _error(None, -32700, "Parse error: message is not valid JSON", out=out)
            continue
        if isinstance(message, list):           # JSON-RPC batch
            for item in message:
                if isinstance(item, dict):
                    handle_request(item, out)
            continue
        if not isinstance(message, dict):
            _error(None, -32600, "Invalid request", out=out)
            continue
        handle_request(message, out)
    return 0


#: The real stdout, captured before anything can print to it.
_TRANSPORT_OUT = sys.stdout


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="coverity_mcp_server.py",
        description="MCP (stdio) server exposing the Coverity Tool's triage engine.")
    parser.add_argument("--report", default="", help="default report path")
    parser.add_argument("--src", default="", help="default source root")
    parser.add_argument("--language", default="", choices=["", "c", "cpp"])
    parser.add_argument("--list-tools", action="store_true",
                        help="print the tool catalogue as JSON and exit (debugging)")
    args = parser.parse_args(argv)

    if args.report:
        os.environ["COVERITY_REPORT"] = os.path.abspath(os.path.expanduser(args.report))
    if args.src:
        os.environ["COVERITY_SRC_ROOT"] = os.path.abspath(os.path.expanduser(args.src))
    if args.language:
        os.environ["COVERITY_LANGUAGE"] = args.language

    if args.list_tools:
        json.dump({"tools": TOOLS, "defaults": _defaults()}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    # Protect the transport: everything that is not a JSON-RPC frame goes to stderr.
    global _TRANSPORT_OUT
    _TRANSPORT_OUT = sys.stdout
    sys.stdout = sys.stderr

    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
