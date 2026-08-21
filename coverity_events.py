#!/usr/bin/env python3
"""Coverity event-trace helpers.

Coverity Connect's UI shows the *main event* line (the actual defect). SOAP
``mergedDefect.lineNumber`` / REST v1 ``lineNumber`` / ``defectInstance.lineNumber``
are frequently the *first* event in the path (the declaration / taint source).
That is the 706-vs-710 bug: 706 is ``var_decl``, 710 is ``overrun-local`` with
``main=true``.

These helpers pick the UI line from a normalised event list and round-trip
events through the pull Excel file so analysis sees the real trace.

The selection is *ranked* rather than a single tag lookup, because a single
Coverity defect can carry several sink-looking events at different lines:

* STRING_NULL  -> ``var_decl`` (174), ``string_null`` (268, sink), and a child
  ``string_null_source`` (174) that may have a *higher* eventNumber.
* BUFFER_SIZE  -> ``var_decl`` (174), ``buffer_size`` (268, sink) and a
  secondary ``buffer_size_warning`` (174) with a higher eventNumber.
* OVERRUN      -> ``var_decl`` (174), ``overrun-local`` (268, sink) plus child
  ``overrun-buffer-arg`` / ``overrun-local`` events in callees.

Naively taking the highest ``step`` among "sink" events therefore reports the
*source* line (174) instead of the sink (268).  The ranking below prefers
``main=true``, then the primary sink tag, then a checker-prefixed variant, then
a weak/secondary sink (``*_warning`` / ``*_source`` / ``*_taint``), and only
then the last non-path event.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Event tags Coverity uses for the *primary* sink (the defect itself), as
# opposed to path events like var_decl / cond_true / alias. All keys are the
# canonical underscore form (``_sink_rank`` normalises hyphens to underscores
# before comparing, so "overrun-local" and "overrun_local" both match
# "overrun_local").
_STRONG_SINK_TAGS = frozenset({
    "overrun", "overrun_local", "overrun_buffer_arg", "overrun_buffer_val",
    "overrun_static", "overrun_dynamic",
    "buffer_size", "buffer_not_null_terminated",
    "string_not_null_terminated", "string_null",
    "deref", "deref_ptr", "null_deref", "var_deref_op", "var_deref_model",
    "forward_null", "reverse_inull",
    "use_after_free", "double_free", "freed_arg",
    "integer_overflow", "integer_underflow", "shift_overflow", "divide_by_zero",
    "uninit_use", "uninit", "uninitialized",
    "resource_leak", "leaked_storage",
    "checked_return", "negative_returns", "sizeof_mismatch",
    "tainted_data", "tainted_string", "tainted_scalar",
})

# Secondary / weaker sink tags. These still mean the checker fired, but they are
# *not* the primary defect location: ``buffer_size_warning`` can sit at the
# buffer's declaration while the real ``buffer_size`` event is at the copy.
_WEAK_SINK_TAGS = frozenset({
    "buffer_size_warning",
})

# Path-preamble event-tag heads that are never the defect sink, even when they
# share a prefix with the checker ("overrun-local" matches OVERRUN; "var_decl"
# does not).
_PATH_EVENT_HEADS = frozenset({
    "var", "cond", "condition", "alias", "identity", "assign", "assignment",
    "to", "from", "via", "const", "path", "end", "begin", "entry", "exit",
    "caller", "callee", "return", "returned", "check", "range", "bounds",
    "init", "default", "fallthrough", "case", "goto", "label", "noescape",
    "escape", "alloc", "free", "pass", "param", "member", "field", "function",
})

# Event-tag suffixes that mark a *source*/taint sub-event rather than the sink,
# even when prefixed by the checker name. Coverity's STRING_NULL trace is
# var_decl -> string_null_source (where the string loses its NUL) -> string_null
# (the sink). ``string_null_source`` must never be treated as the primary sink:
# it sits at the *first* path line, and as a child event it can carry a higher
# eventNumber than the real ``string_null`` sink.
_SOURCE_SUFFIXES = frozenset({"source", "taint", "src", "origin"})

# ``buffer_size_warning`` (BUFFER_SIZE's secondary event) — kept distinct from
# the source suffixes so the BUFFER_SIZE_WARNING checker still recognises it as
# its own primary sink via the exact-tag match in :func:`_sink_rank`.
_WARNING_SUFFIXES = frozenset({"warning", "warn"})

# Internal marker distinguishing a heuristic ``main`` flag (set by
# :func:`mark_main_events`) from a genuine Coverity ``main=true``. Only the
# genuine flag is trusted blindly; a heuristic flag is re-evaluated when more
# information (the checker name) becomes available.
_MAIN_HEURISTIC = "_main_heuristic"


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


def _sink_rank(event: Dict[str, Any], checker: str = "") -> Optional[int]:
    """Rank how strongly ``event`` is the defect's primary sink.

    Lower is better: 0 = primary sink, 1 = checker-prefixed variant,
    2 = weak/secondary (warning/source/taint). Returns ``None`` when the event
    is a path preamble (or otherwise not a sink).
    """
    tag = _norm_tag(event.get("type") or event.get("tag"))
    if not tag:
        return None
    underscored = tag.replace("-", "_")
    chk = _norm_tag(checker).replace("-", "_")

    # Exact checker tag is always the primary sink for that checker
    # (e.g. ``buffer_size`` for BUFFER_SIZE, ``buffer_size_warning`` for
    # BUFFER_SIZE_WARNING).
    if chk and underscored == chk:
        return 0
    if underscored in _STRONG_SINK_TAGS:
        return 0

    head = underscored.split("_")[0]
    if head in _PATH_EVENT_HEADS:
        return None
    if underscored in _WEAK_SINK_TAGS:
        return 2
    if not chk:
        return None

    # A checker-prefixed event: "overrun-local" matches OVERRUN. A source/taint
    # or warning suffix demotes it to a secondary sink ("string_null_source" is
    # the source, not the STRING_NULL sink; "buffer_size_warning" is secondary
    # to "buffer_size").
    if underscored.startswith(chk + "_"):
        suffix_head = underscored[len(chk) + 1:].split("_")[0]
        if suffix_head in _SOURCE_SUFFIXES or suffix_head in _WARNING_SUFFIXES:
            return 2
        return 1
    # Loose fallback: the checker name shares the tag's leading token
    # (e.g. TAINTED_STRING vs ``tainted_data``).
    if chk.startswith(head):
        return 1
    return None


def is_sink_event(event: Dict[str, Any], checker: str = "") -> bool:
    """True when the event tag is the checker's *primary* sink (not a path
    preamble and not a weak warning/source/taint variant)."""
    rank = _sink_rank(event, checker)
    return rank in (0, 1)


def _is_path_event(event: Dict[str, Any]) -> bool:
    tag = _norm_tag(event.get("type") or event.get("tag"))
    return bool(tag) and tag.replace("-", "_").split("_")[0] in _PATH_EVENT_HEADS


def event_line(event: Dict[str, Any]) -> int:
    """Best line number carried on a single event dict."""
    if not event:
        return 0
    for key in ("line", "lineNumber", "eventLineNumber", "strippedLineNumber"):
        n = _as_int(event.get(key))
        if n:
            return n
    return 0


def _pick_event(events: List[Dict[str, Any]],
                checker: str = "") -> Tuple[Optional[Dict[str, Any]], str]:
    """Choose the event that locates the defect.

    Returns ``(event, reason)`` where reason is ``main_event``, ``sink_event``
    or ``last_event``. Preference order:

      1. genuine ``main=true`` event (highest step)
      2. primary sink tag (rank 0)
      3. checker-prefixed sink variant (rank 1)
      4. weak/secondary sink (rank 2 — warning/source/taint)
      5. last non-path event with a line
      6. last event with a line
    """
    best: Optional[Dict[str, Any]] = None
    best_key: Optional[Tuple[int, int]] = None
    for e in events:
        if not event_line(e):
            continue
        if is_main_event(e):
            # Coverity's own main flag is authoritative; among (rare) multiple
            # mains, the last one wins.
            key = (-1, -_as_int(e.get("step")))
        else:
            rank = _sink_rank(e, checker)
            if rank is None:
                continue
            # Within the same rank, prefer the *earlier* event: the primary
            # sink precedes its child/source elaborations (a callee's own
            # overrun-local / buffer_size_warning / string_null_source come
            # after the main event and carry higher eventNumbers).
            key = (rank, _as_int(e.get("step")))
        if best_key is None or key < best_key:
            best_key = key
            best = e
    if best is not None:
        return best, "main_event" if best_key[0] == -1 else "sink_event"

    # Fallback: last event that carries a line, preferring one that is not a
    # known path preamble (a child ``var_decl``/``assignment`` should not shadow
    # the real end of the trace).
    with_line = [e for e in events if event_line(e)]
    if not with_line:
        return None, ""
    non_path = [e for e in with_line if not _is_path_event(e)]
    candidates = non_path or with_line
    return max(candidates, key=lambda e: _as_int(e.get("step"))), "last_event"


def line_from_events(events: Optional[Iterable[Dict[str, Any]]],
                     checker: str = "") -> int:
    """Return the Coverity Connect UI line for a defect event trace.

    See :func:`_pick_event` for the preference order. Never returns the first
    path event's line when a later sink/main event exists.
    """
    evs = [e for e in (events or []) if isinstance(e, dict)]
    if not evs:
        return 0
    ev, _ = _pick_event(evs, checker)
    return event_line(ev) if ev else 0


def line_source_from_events(events: Optional[Iterable[Dict[str, Any]]],
                            checker: str = "") -> Tuple[int, str]:
    """Like :func:`line_from_events` but also returns how the line was chosen."""
    evs = [e for e in (events or []) if isinstance(e, dict)]
    if not evs:
        return 0, ""
    ev, reason = _pick_event(evs, checker)
    return (event_line(ev), reason) if ev else (0, "")


def mark_main_events(events: List[Dict[str, Any]], checker: str = "") -> List[Dict[str, Any]]:
    """Ensure at least one event is flagged ``main``.

    A genuine Coverity ``main=true`` flag is preserved as-is. Otherwise the
    primary sink event (else the last non-path event with a line) is flagged.
    A heuristic flag set by an earlier call is re-evaluated when ``checker``
    becomes available, so a checker-less marking made during HTML parsing is
    corrected once the defect's checker is known.

    Mutates and returns ``events``.
    """
    if not events:
        return events
    if any(is_main_event(e) and not e.get(_MAIN_HEURISTIC) for e in events):
        return events
    # Drop a previous heuristic marking so we can re-evaluate with the current
    # (possibly richer) checker information.
    for e in events:
        if e.get(_MAIN_HEURISTIC):
            e.pop("main", None)
            e.pop(_MAIN_HEURISTIC, None)
    pick, _ = _pick_event(events, checker)
    if pick is not None:
        pick["main"] = True
        pick[_MAIN_HEURISTIC] = True
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
    out = {
        "step": step,
        "type": tag,
        "tag": tag,
        "description": desc,
        "file": fpath,
        "line": line,
        "main": is_main_event(raw),
    }
    # Preserve the heuristic marker so a later, checker-aware marking pass can
    # re-evaluate a heuristic main flag instead of mistaking it for Coverity's.
    if raw.get(_MAIN_HEURISTIC):
        out[_MAIN_HEURISTIC] = True
    return out


def events_to_json(events: Optional[Iterable[Dict[str, Any]]]) -> str:
    """Serialize events for the pull-Excel EventsJSON column."""
    out = []
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        norm = normalize_event(ev)
        # Internal marker does not need to persist to the user-facing sheet.
        norm.pop(_MAIN_HEURISTIC, None)
        out.append(norm)
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
