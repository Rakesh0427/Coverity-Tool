#!/usr/bin/env python3
"""Coverity event-trace helpers.

Coverity Connect's UI shows the *main event* line (the actual defect). SOAP
``mergedDefect.lineNumber`` / REST v1 ``lineNumber`` / ``defectInstance.lineNumber``
are frequently the *first* event in the path (the declaration / taint source).
That is the 706-vs-710 bug: 706 is ``var_decl``, 710 is ``overrun-local`` with
``main=true``.

These helpers pick the UI line from a normalised event list and round-trip
events through the pull Excel file so analysis sees the real trace.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Event tags that Coverity uses for the *sink* (the defect itself), as opposed
# to path events like var_decl / cond_true / alias. Hyphens and underscores
# both appear depending on SOAP vs HTML vs REST.
_SINK_TAGS = frozenset({
    "overrun", "overrun-local", "overrun-buffer-arg", "overrun-buffer-val",
    "overrun_static", "overrun_dynamic", "overrun-static", "overrun-dynamic",
    "buffer_size", "buffer_size_warning", "buffer-size", "buffer_not_null_terminated",
    "string_not_null_terminated", "string_null", "string-null",
    "deref", "deref_ptr", "null_deref", "var_deref_op", "var_deref_model",
    "forward_null", "reverse_inull", "reverse-inull",
    "use_after_free", "double_free", "freed_arg", "use-after-free",
    "integer_overflow", "integer_underflow", "shift_overflow", "divide_by_zero",
    "uninit_use", "uninit", "uninitialized",
    "resource_leak", "leaked_storage",
    "checked_return", "negative_returns", "sizeof_mismatch",
    "tainted_data", "tainted_string", "tainted_scalar",
})


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def is_main_event(event: Dict[str, Any]) -> bool:
    """True when Coverity marked this event as the defect's main event."""
    if not event:
        return False
    flag = event.get("main")
    if flag is True or flag == 1:
        return True
    if isinstance(flag, str) and flag.strip().lower() in ("true", "1", "yes"):
        return True
    return False


def _norm_tag(tag: Any) -> str:
    return str(tag or "").strip().lower().replace(" ", "_")


# Path-preamble event-tag heads that are never the defect sink, even when they
# share a prefix with the checker ("overrun-local" matches OVERRUN; "var_decl"
# does not).
_PATH_EVENT_HEADS = frozenset({
    "var", "cond", "alias", "identity", "assign", "to", "from",
    "path", "end", "begin", "entry", "exit", "caller",
})

# Event-tag suffixes that mark a *source*/taint sub-event rather than the sink,
# even when prefixed by the checker name. Coverity's STRING_NULL trace is
# var_decl -> string_null_source (where the string loses its NUL) -> string_null
# (the sink). ``string_null_source`` must never be treated as the sink: it sits
# at the *first* path line, and as a child event it can carry a higher
# eventNumber than the real ``string_null`` sink.
_NON_SINK_SUFFIXES = frozenset({"source", "taint", "src", "origin"})


def is_sink_event(event: Dict[str, Any], checker: str = "") -> bool:
    """True when the event tag is the checker sink (not a path preamble)."""
    tag = _norm_tag(event.get("type") or event.get("tag"))
    if not tag:
        return False
    underscored = tag.replace("-", "_")
    if tag in _SINK_TAGS or underscored in _SINK_TAGS:
        return True
    chk = _norm_tag(checker).replace("-", "_")
    if not chk:
        return False
    head = underscored.split("_")[0]
    # Path-preamble events (var_decl, cond_true, ...) are never the sink.
    if head in _PATH_EVENT_HEADS:
        return False
    if underscored == chk:
        return True
    # A checker-prefixed event is a sink only when its extra suffix is not a
    # source/taint marker: "overrun-local" matches OVERRUN, but
    # "string_null_source" is the source, not the STRING_NULL sink.
    if underscored.startswith(chk + "_"):
        suffix = underscored[len(chk) + 1:]
        return suffix.split("_")[0] not in _NON_SINK_SUFFIXES
    # Loose fallback: the checker name shares the tag's leading token.
    return chk.startswith(head)


def event_line(event: Dict[str, Any]) -> int:
    """Best line number carried on a single event dict."""
    if not event:
        return 0
    for key in ("line", "lineNumber", "eventLineNumber", "strippedLineNumber"):
        n = _as_int(event.get(key))
        if n:
            return n
    return 0


def line_from_events(events: Optional[Iterable[Dict[str, Any]]],
                     checker: str = "") -> int:
    """Return the Coverity Connect UI line for a defect event trace.

    Preference order (never the first path event when a later one exists):
      1. event with ``main=true`` and a real line
      2. sink-tagged event matching the checker (highest step)
      3. last event that carries a line (Coverity orders source → sink)
    """
    evs = [e for e in (events or []) if isinstance(e, dict)]
    if not evs:
        return 0

    mains = [e for e in evs if is_main_event(e) and event_line(e)]
    if mains:
        return event_line(max(mains, key=lambda e: _as_int(e.get("step"))))

    sinks = [e for e in evs if is_sink_event(e, checker) and event_line(e)]
    if sinks:
        return event_line(max(sinks, key=lambda e: _as_int(e.get("step"))))

    with_line = [e for e in evs if event_line(e)]
    if not with_line:
        return 0
    return event_line(max(with_line, key=lambda e: _as_int(e.get("step"))))


def line_source_from_events(events: Optional[Iterable[Dict[str, Any]]],
                            checker: str = "") -> Tuple[int, str]:
    """Like :func:`line_from_events` but also returns how the line was chosen."""
    evs = [e for e in (events or []) if isinstance(e, dict)]
    if not evs:
        return 0, ""
    mains = [e for e in evs if is_main_event(e) and event_line(e)]
    if mains:
        return event_line(max(mains, key=lambda e: _as_int(e.get("step")))), "main_event"
    sinks = [e for e in evs if is_sink_event(e, checker) and event_line(e)]
    if sinks:
        return event_line(max(sinks, key=lambda e: _as_int(e.get("step")))), "sink_event"
    with_line = [e for e in evs if event_line(e)]
    if not with_line:
        return 0, ""
    return event_line(max(with_line, key=lambda e: _as_int(e.get("step")))), "last_event"


def mark_main_events(events: List[Dict[str, Any]], checker: str = "") -> List[Dict[str, Any]]:
    """Ensure at least one event is flagged ``main`` when Coverity omitted it.

    If none is marked, the last sink-tagged event (else the last event with a
    line) is marked main. Mutates and returns ``events``.
    """
    if not events:
        return events
    if any(is_main_event(e) for e in events):
        return events
    candidates = [e for e in events if is_sink_event(e, checker) and event_line(e)]
    if not candidates:
        candidates = [e for e in events if event_line(e)]
    if not candidates:
        candidates = events[-1:]
    pick = max(candidates, key=lambda e: _as_int(e.get("step")))
    pick["main"] = True
    return events


def normalize_event(raw: Dict[str, Any], default_file: str = "") -> Dict[str, Any]:
    """Canonical event dict used everywhere downstream of a pull/parse."""
    raw = raw or {}
    step = _as_int(raw.get("step") or raw.get("eventNumber") or raw.get("stepNumber"))
    tag = str(raw.get("type") or raw.get("tag") or raw.get("eventTag")
              or raw.get("eventType") or "")
    desc = str(raw.get("description") or raw.get("eventDescription")
               or raw.get("covLStrEventDescription") or "")
    fpath = str(raw.get("file") or raw.get("filePathname") or raw.get("filePath")
                or default_file or "")
    line = event_line(raw)
    return {
        "step": step,
        "type": tag,
        "tag": tag,
        "description": desc,
        "file": fpath,
        "line": line,
        "main": is_main_event(raw),
    }


def events_to_json(events: Optional[Iterable[Dict[str, Any]]]) -> str:
    """Serialize events for the pull-Excel EventsJSON column."""
    out = []
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        out.append(normalize_event(ev))
    try:
        return json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return "[]"


def events_from_json(blob: Any) -> List[Dict[str, Any]]:
    """Parse EventsJSON (or a list already) back into event dicts."""
    if not blob:
        return []
    if isinstance(blob, list):
        return [normalize_event(e) for e in blob if isinstance(e, dict)]
    text = str(blob).strip()
    if not text or text in ("[]", "None"):
        return []
    try:
        data = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [normalize_event(e) for e in data if isinstance(e, dict)]


# Human-readable Events Summary written by write_pull_excel:
#   overrun-local@src/file.c:710 — Overrunning array "buf"...
_SUMMARY_PART = re.compile(
    r"([^@;]+?)@([^:]*):(\d+)\s*[—-]\s*(.*)$"
)


def events_from_summary(text: Any) -> List[Dict[str, Any]]:
    """Best-effort parse of the human Events Summary column (legacy workbooks)."""
    if not text:
        return []
    events = []
    for i, part in enumerate(str(text).split("; "), start=1):
        part = part.strip()
        if not part:
            continue
        m = _SUMMARY_PART.match(part)
        if not m:
            continue
        events.append(normalize_event({
            "step": i,
            "type": m.group(1).strip(),
            "file": m.group(2).strip(),
            "line": int(m.group(3)),
            "description": m.group(4).strip(),
        }))
    return events


def apply_events_to_defect(defect: Dict[str, Any],
                           events: Optional[List[Dict[str, Any]]] = None) -> int:
    """Attach ``events`` to ``defect`` and set ``line`` from the main event.

    Returns the line that was chosen (0 if none). Existing ``_merged_line`` /
    ``_inst_line_val`` / ``_rest_main_line`` values are kept as fallbacks only
    when the event trace has no usable line.
    """
    if events is None:
        events = defect.get("events") or []
    events = [normalize_event(e, default_file=str(defect.get("file") or ""))
              for e in events if isinstance(e, dict)]
    checker = str(defect.get("checker") or "")
    mark_main_events(events, checker)
    defect["events"] = events

    ev_line, ev_src = line_source_from_events(events, checker)
    if ev_line:
        if defect.get("line") and defect.get("line") != ev_line:
            defect["_line_prev"] = defect.get("line")
        defect["line"] = ev_line
        defect["_line_src"] = ev_src
        return ev_line

    for key, src in (
        ("_rest_main_line", "rest_main"),
        ("_inst_line_val", "instance"),
        ("_merged_line", "merged"),
    ):
        n = _as_int(defect.get(key))
        if n:
            defect["line"] = n
            defect["_line_src"] = src
            return n
    return _as_int(defect.get("line"))
