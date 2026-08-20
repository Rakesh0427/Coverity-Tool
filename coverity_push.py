#!/usr/bin/env python3
"""
coverity_push.py — push analysed dispositions back to Coverity Connect.

Why this module exists
----------------------
``PushDialog`` in ``local_gui.py`` can already push, but only by writing a CSV
and reading it back in. Everything it does that is *not* Tk lives here instead,
so the same logic can be reused straight from the results table (no CSV round
trip), unit-tested without a server, and driven headlessly.

The pipeline is four small, independently testable steps::

    select_defects(results, mode)        -> [defect dict, ...]
    build_push_rows(defects)             -> [PushRow, ...]
    validate_rows(rows, server_defects)  -> ValidationReport
    push_rows(client, rows, store, ...)  -> PushReport

``client`` is any object exposing ``update_triage(cid_list, triage_store_name,
classification, comment)`` returning ``(success_count, failed_cids, error)`` —
i.e. :class:`coverity_soap_client.CoveritySOAPClient`, or a fake in tests.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime

try:
    from coverity_soap_client import CLASSIFICATION_MAP
except Exception:  # pragma: no cover - keeps the module importable standalone
    CLASSIFICATION_MAP = {
        "Bug": "Bug",
        "False positive": "False Positive",
        "Intentional": "Intentional",
        "Needs review": "Pending",
        "Accepted": "Bug",
    }

# Server-side batch limit for updateTriageForCIDsInTriageStore.
MAX_BATCH = 100

# Selection modes accepted by :func:`select_defects`.
MODE_ALL = "all"
MODE_ACCEPTED = "accepted"
MODE_DECIDED = "decided"

MODE_LABELS = {
    MODE_ALL: "All analysed defects",
    MODE_ACCEPTED: "Accepted / overridden only",
    MODE_DECIDED: "Everything except 'Needs review'",
}


# --------------------------------------------------------------------------- #
# Step 1 — choose which defects to push
# --------------------------------------------------------------------------- #
def select_defects(results, mode=MODE_ACCEPTED):
    """Filter analysed ``results`` down to the defects that should be pushed.

    ``mode`` is one of :data:`MODE_ALL`, :data:`MODE_ACCEPTED` (defects the
    reviewer explicitly accepted or overrode) or :data:`MODE_DECIDED` (anything
    with a real classification, i.e. not left at "Needs review").

    Defects without a usable CID are always dropped — there is nothing to
    triage on the server without one.
    """
    mode = (mode or MODE_ACCEPTED).strip().lower()
    picked = []
    for r in results or []:
        if _coerce_cid(r.get("cid")) is None:
            continue
        if mode == MODE_ALL:
            picked.append(r)
        elif mode == MODE_ACCEPTED:
            if r.get("accepted") or r.get("overridden"):
                picked.append(r)
        elif mode == MODE_DECIDED:
            cls = (r.get("classification") or "").strip()
            if cls and cls.lower() != "needs review":
                picked.append(r)
        else:
            raise ValueError(f"unknown push mode: {mode!r}")
    return picked


def _coerce_cid(value):
    """Return ``value`` as an int CID, or ``None`` when it is not one."""
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Step 2 — turn defects into push rows
# --------------------------------------------------------------------------- #
@dataclass
class PushRow:
    """One triage update queued for the server."""

    cid: int
    classification: str
    comment: str
    checker: str = ""
    file: str = ""
    line: int = 0
    #: CID confirmed to exist on the server (set by :func:`validate_rows`).
    server_cid: int | None = None
    #: How the server CID was resolved: 'cid', 'signature' or '' (unvalidated).
    match: str = ""
    #: Push outcome, filled in by :func:`push_rows`.
    status: str = ""
    error: str = ""

    @property
    def target_cid(self):
        """The CID to actually send — the validated one when available."""
        return self.server_cid if self.server_cid is not None else self.cid

    @property
    def server_classification(self):
        """``classification`` translated to a Connect triage-store value."""
        return CLASSIFICATION_MAP.get(self.classification, self.classification)


def build_push_rows(defects, reviewer="", stamp_comment=True, max_comment=4000):
    """Convert analysed defect dicts into :class:`PushRow` objects.

    An accepted defect pushes its *underlying* classification (Bug / False
    positive / ...), not the literal word "Accepted" — "Accepted" is a review
    state in this tool, not a Coverity classification.

    When ``stamp_comment`` is set the comment gets a short provenance suffix so
    anyone reading the defect in Connect knows where the triage came from.
    Duplicate CIDs collapse to the last occurrence.
    """
    by_cid = {}
    for d in defects or []:
        cid = _coerce_cid(d.get("cid"))
        if cid is None:
            continue
        cls = (d.get("classification") or "").strip() or "Needs review"
        if cls.lower() == "accepted":
            cls = (d.get("base_classification") or "Bug").strip()
        comment = (d.get("comment") or "").strip()
        if stamp_comment:
            comment = _stamp(comment, reviewer)
        if max_comment and len(comment) > max_comment:
            comment = comment[: max_comment - 1].rstrip() + "…"
        by_cid[cid] = PushRow(
            cid=cid,
            classification=cls,
            comment=comment,
            checker=str(d.get("checker") or ""),
            file=str(d.get("file") or ""),
            line=_coerce_cid(d.get("line")) or 0,
        )
    return list(by_cid.values())


def _stamp(comment, reviewer=""):
    """Append a '[Coverity Tool — reviewer — date]' provenance marker."""
    who = (reviewer or "").strip()
    bits = ["Coverity Tool"]
    if who:
        bits.append(who)
    bits.append(datetime.now().strftime("%Y-%m-%d"))
    marker = "[" + " — ".join(bits) + "]"
    if not comment:
        return marker
    if "[Coverity Tool" in comment:
        return comment
    return f"{comment}\n{marker}"


# --------------------------------------------------------------------------- #
# Step 3 — validate CIDs against the server before writing anything
# --------------------------------------------------------------------------- #
@dataclass
class ValidationReport:
    matched: list = field(default_factory=list)      # exact CID hit
    remapped: list = field(default_factory=list)     # resolved by file+checker
    unmatched: list = field(default_factory=list)    # not on this server/project

    @property
    def pushable(self):
        """Rows safe to send (exact hits plus unambiguous remaps)."""
        return self.matched + self.remapped

    def summary(self):
        parts = [f"{len(self.pushable)} ready to push"]
        if self.remapped:
            parts.append(f"{len(self.remapped)} remapped by file+checker")
        if self.unmatched:
            parts.append(f"{len(self.unmatched)} not found on server")
        return "  •  ".join(parts)


def validate_rows(rows, server_defects):
    """Cross-check ``rows`` against defects pulled from the server.

    A row matches when its CID exists on the server. Otherwise the tool falls
    back to a (checker, filename) signature — CIDs shift between analysis runs,
    so a defect exported yesterday may carry a stale CID. A signature is only
    trusted when it resolves to exactly one server defect; ambiguous or missing
    signatures leave the row unmatched rather than guessing.
    """
    by_cid = {}
    by_sig = {}
    for d in server_defects or []:
        cid = _coerce_cid(d.get("cid"))
        if cid is None:
            continue
        by_cid[cid] = d
        sig = (str(d.get("checker") or ""), os.path.basename(str(d.get("file") or "")))
        by_sig.setdefault(sig, []).append(d)

    report = ValidationReport()
    for row in rows or []:
        if row.cid in by_cid:
            row.server_cid = row.cid
            row.match = "cid"
            report.matched.append(row)
            continue
        candidates = by_sig.get((row.checker, os.path.basename(row.file)), [])
        if len(candidates) == 1:
            row.server_cid = _coerce_cid(candidates[0].get("cid"))
            row.match = "signature"
            report.remapped.append(row)
        else:
            row.server_cid = None
            row.match = ""
            report.unmatched.append(row)
    return report


# --------------------------------------------------------------------------- #
# Step 4 — push
# --------------------------------------------------------------------------- #
@dataclass
class PushReport:
    succeeded: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    dry_run: bool = False

    @property
    def ok(self):
        return not self.failed and not self.errors

    def summary(self):
        head = "Dry run — nothing was written." if self.dry_run else ""
        lines = [
            f"  Succeeded : {len(self.succeeded)}",
            f"  Failed    : {len(self.failed)}",
        ]
        if self.skipped:
            lines.append(f"  Skipped   : {len(self.skipped)}")
        if self.errors:
            lines.append("")
            lines.extend(f"  ! {e}" for e in dict.fromkeys(self.errors))
        return "\n".join(([head, ""] if head else []) + lines)


def group_rows(rows):
    """Group rows into server batches keyed by (classification, comment).

    ``updateTriageForCIDsInTriageStore`` applies ONE classification+comment to a
    list of CIDs, so rows can only share a call when both fields are identical.
    Each group is further split to :data:`MAX_BATCH` CIDs (a server limit).
    """
    groups = {}
    for row in rows or []:
        groups.setdefault((row.classification, row.comment), []).append(row)
    batches = []
    for (cls, comment), group in groups.items():
        for i in range(0, len(group), MAX_BATCH):
            batches.append((cls, comment, group[i: i + MAX_BATCH]))
    return batches


def push_rows(client, rows, triage_store, progress_cb=None,
              dry_run=False, require_validated=True):
    """Send triage updates to Coverity Connect.

    ``require_validated`` (default) refuses to touch rows that were never
    confirmed against the server, so a stale CSV cannot silently re-triage an
    unrelated defect that happens to reuse the CID. Pass ``False`` to push
    exactly what was given.

    ``progress_cb(done, total, row)`` is called after each row resolves.
    Returns a :class:`PushReport`; each row's ``status`` is also set to
    ``"✓"``, ``"✗"`` or ``"–"``.
    """
    report = PushReport(dry_run=dry_run)
    rows = list(rows or [])

    queue = []
    for row in rows:
        if require_validated and row.server_cid is None:
            row.status = "–"
            row.error = "CID not found on server"
            report.skipped.append(row)
        else:
            queue.append(row)

    if not triage_store:
        for row in queue:
            row.status = "✗"
            row.error = "No triage store selected"
            report.failed.append(row)
        report.errors.append("No triage store selected")
        return report

    total = len(queue)
    done = 0
    for cls, comment, batch in group_rows(queue):
        cids = [r.target_cid for r in batch]
        if dry_run:
            ok_count, failed_cids, error = len(cids), [], None
        else:
            try:
                ok_count, failed_cids, error = client.update_triage(
                    cids, triage_store, cls, comment)
            except Exception as exc:  # network/SOAP blow-up mid-run
                ok_count, failed_cids, error = 0, list(cids), str(exc)

        failed_set = {_coerce_cid(c) for c in (failed_cids or [])}
        # A server that reports fewer successes than CIDs without naming them
        # must be treated as a whole-batch failure — never report a write we
        # cannot prove happened.
        blanket_fail = not failed_set and ok_count < len(cids)
        if error:
            report.errors.append(error)

        for row in batch:
            if row.target_cid in failed_set or blanket_fail:
                row.status = "✗"
                row.error = error or "Server rejected the update"
                report.failed.append(row)
            else:
                row.status = "✓"
                row.error = ""
                report.succeeded.append(row)
            done += 1
            if progress_cb:
                progress_cb(done, total, row)
    return report


def apply_status_to_results(results, rows):
    """Write each row's push outcome back onto the matching analysed defect.

    ``local_gui.ResultsPage._populate`` already colours rows green/red from
    ``push_status``; this is what fills that field in.
    """
    by_cid = {}
    for row in rows or []:
        by_cid[row.cid] = row
    touched = 0
    for r in results or []:
        row = by_cid.get(_coerce_cid(r.get("cid")))
        if not row or not row.status:
            continue
        r["push_status"] = row.status
        r["push_error"] = row.error
        r["pushed_cid"] = row.target_cid
        touched += 1
    return touched
