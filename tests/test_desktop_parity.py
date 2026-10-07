"""Parity tests: the agent/MCP path vs the desktop Coverity Findings Analyzer.

The desktop app is the reference implementation, so "does the agent do the same
thing?" is a testable question rather than a matter of opinion. These tests
answer it three ways:

* **`local_gui.py`** (the primary desktop application) is replicated step by
  step and compared field-by-field with the bridge — expected to be identical.
* **`coverity_triage.py`** (the focused HTML triage GUI) is compared on the
  verdict, confidence and fix; its comments are allowed to be a subset because
  it passes the report's relative path, which can prevent the extra cppcheck
  corroboration sentence from being added.
* The **Excel route** (the desktop app's main input) is round-tripped and
  checked, including the `Various`-line rule for line-agnostic checkers.

If someone changes the bridge's argument list, the event synthesis or the
`Various` handling, these tests fail — which is the point: those details are
exactly what makes two pipelines disagree about the same defect.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

REPORT = os.path.join(REPO_ROOT, "docs", "sample_report")
SRC = os.path.join(REPO_ROOT, "docs")

openpyxl = pytest.importorskip("openpyxl", reason="Excel parity route needs openpyxl")

import vscode_bridge as bridge                                     # noqa: E402
from context_builder import build_defect_context, warm_workspace_index  # noqa: E402
from code_extractor import extract_enclosing_function, find_function_line_by_name  # noqa: E402
from heuristic_analyzer import analyze_defect                       # noqa: E402
from html_report_parser import (                                    # noqa: E402
    parse_coverity_excel, parse_coverity_html, write_pull_excel,
)

RECORD_FIELDS = ("disposition", "comment", "proposed_fix", "confidence")


@pytest.fixture(scope="module")
def sample_defects():
    warm_workspace_index(SRC, "c")
    return parse_coverity_html(REPORT)


# --------------------------------------------------------------------------- #
# The reference implementation, replicated
# --------------------------------------------------------------------------- #
def _local_gui_worker(defect, src_root=SRC):
    """Replicate ``local_gui``'s per-defect worker (the reference pipeline).

    Mirrors, in the same order:
      * source resolution + function-name lookup (``_find_source_file`` /
        ``_find_function_line``),
      * function extraction with ``extract_enclosing_function``,
      * ``build_defect_context`` called with the events and the resolved path,
      * ``analyze_defect`` with ``sub_checker``, ``tree`` and
        ``line_is_various``.
    """
    checker = defect["checker"]
    type_val = defect.get("type", "")
    filepath = defect.get("file", "")
    line = defect.get("line", 0)
    func = defect.get("function", "")

    real_path = bridge.resolve_source_file(filepath, src_root, "")
    extract_line = line
    if func and real_path:
        found = find_function_line_by_name(real_path, func, "c")
        if found > 0:
            extract_line = found

    code, start, _tree = ("", 1, None)
    if real_path:
        result = extract_enclosing_function(real_path, extract_line, "c")
        if isinstance(result, tuple) and len(result) >= 2:
            code, start = result[0], result[1]

    events = list(defect.get("events") or [])
    if not events:
        events = [{"step": 1, "type": checker, "description": type_val,
                   "file": filepath, "line": line}]

    rich = build_defect_context(
        {"events": events, "file": real_path or filepath, "line": line,
         "function": func, "function_code": code, "code_start_line": start},
        src_root, "c")
    rich.pop("function_code", None)
    context = {**rich, "function_code": code, "source_code": code,
               "code_start_line": start}

    classification, comment, fix, confidence = analyze_defect(
        context, checker, events, sub_checker=type_val,
        file=real_path or filepath, line=line, function=func,
        line_is_various=defect.get("line_is_various", False),
        tree=context.get("function_tree"))
    return {"disposition": classification, "comment": comment,
            "proposed_fix": fix, "confidence": confidence}


def _coverity_triage_worker(defect, src_root=SRC):
    """Replicate ``coverity_triage._analysis_worker`` (the simpler triage GUI)."""
    context = build_defect_context(defect, src_root, "c")
    if not context["function_code"]:
        return {"disposition": "Needs review", "comment": "Context extraction failed",
                "proposed_fix": "", "confidence": 0.0}
    classification, comment, fix, confidence = analyze_defect(
        context, defect["checker"], defect["events"],
        file=defect.get("file", ""), line=defect.get("line", 0),
        function=defect.get("function", ""))
    return {"disposition": classification, "comment": comment,
            "proposed_fix": fix, "confidence": confidence}


def _agent_record(cid, src_root=SRC, report=REPORT):
    record = bridge.op_context(report, cid, src_root=src_root, lines=5)
    return {field: record[field] for field in RECORD_FIELDS}


# --------------------------------------------------------------------------- #
# 1. Verdict parity with the desktop application
# --------------------------------------------------------------------------- #
class TestDesktopParity:
    def test_bridge_reproduces_local_gui_exactly(self, sample_defects):
        """The primary desktop app and the agent must agree on everything."""
        for defect in sample_defects:
            expected = _local_gui_worker(defect)
            actual = _agent_record(defect["cid"])
            for field in RECORD_FIELDS:
                assert actual[field] == expected[field], (
                    f"CID {defect['cid']} {field} differs from local_gui:\n"
                    f"  gui  : {str(expected[field])[:300]}\n"
                    f"  agent: {str(actual[field])[:300]}")

    def test_bridge_agrees_with_the_triage_gui_on_the_verdict(self, sample_defects):
        """Same verdict, confidence and fix; comments may add corroboration.

        ``coverity_triage.py`` passes the report's relative path, so when the
        checkout is elsewhere the extra cppcheck corroboration sentence cannot
        be produced. Dispositions must still match — that is what a user sees.
        """
        for defect in sample_defects:
            expected = _coverity_triage_worker(defect)
            actual = _agent_record(defect["cid"])
            assert actual["disposition"] == expected["disposition"]
            assert actual["confidence"] == expected["confidence"]
            assert actual["proposed_fix"] == expected["proposed_fix"]
            agent_comment, gui_comment = actual["comment"], expected["comment"]
            assert agent_comment == gui_comment or agent_comment.startswith(gui_comment), (
                f"CID {defect['cid']}: the agent rewrote the rationale rather than "
                f"extending it:\n  gui  : {gui_comment[:300]}\n"
                f"  agent: {agent_comment[:300]}")

    def test_replica_still_matches_the_gui_call_sites(self):
        """Guard the guard: if a GUI changes its call, re-derive the parity.

        These assertions are deliberately source-level. A refactor in either
        GUI should fail here and force a human to re-run the comparison above,
        rather than letting the replicated pipeline rot into fiction.
        """
        with open(os.path.join(REPO_ROOT, "local_gui.py"), encoding="utf-8") as fh:
            gui = fh.read()
        for fragment in ("sub_checker=type_val", 'tree=context.get("function_tree")',
                         "line_is_various=line_is_various",
                         'from coverity_events import apply_events_to_defect'):
            assert fragment in gui, f"local_gui no longer passes {fragment}"

        with open(os.path.join(REPO_ROOT, "coverity_triage.py"), encoding="utf-8") as fh:
            triage = fh.read()
        assert "build_defect_context(defect, src_root, language)" in triage
        assert 'context["function_code"]' in triage

    def test_bridge_uses_the_same_analysis_entry_point(self):
        """No re-implementation: the bridge must call the shared analyser."""
        with open(os.path.join(REPO_ROOT, "vscode_bridge.py"), encoding="utf-8") as fh:
            source = fh.read()
        assert "from heuristic_analyzer import analyze_defect" in source
        assert "from context_builder import build_defect_context" in source


# --------------------------------------------------------------------------- #
# 2. The desktop app's Excel route
# --------------------------------------------------------------------------- #
class TestExcelRoute:
    def test_pull_excel_round_trip_gives_the_same_verdicts(self, sample_defects, tmp_path):
        """The desktop app's pull→Excel→analyse loop must survive the detour."""
        xlsx = tmp_path / "pulled.xlsx"
        write_pull_excel(sample_defects, str(xlsx))
        parsed = parse_coverity_excel(str(xlsx))
        assert {d["cid"] for d in parsed} == {d["cid"] for d in sample_defects}
        assert all(d.get("events") for d in parsed), \
            "the EventsJSON column is what keeps the main-event line on a round trip"

        for defect in parsed:
            html_record = _agent_record(defect["cid"])
            excel_record = _agent_record(defect["cid"], report=str(xlsx))
            for field in RECORD_FIELDS[:-1]:            # confidence included below
                assert excel_record[field] == html_record[field], \
                    f"CID {defect['cid']} {field} changed through Excel"
            assert excel_record["confidence"] == html_record["confidence"]

    def test_various_line_rule_matches_the_desktop_app(self, tmp_path):
        """`Various` rows: memory-safety checkers need a human, line-agnostic
        checkers are analysed from the function (with the line zeroed)."""
        xlsx = tmp_path / "various.xlsx"
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append(["CID", "Checker", "Subtype", "Severity", "Action", "File",
                      "Line", "Function", "Events Summary", "EventsJSON"])
        sheet.append([9001, "BUFFER_SIZE", "Buffer not null terminated", "High", "",
                      "sample_src/sample.c", "Various", "vulnerable_copy", "", "[]"])
        sheet.append([9002, "CHECKED_RETURN", "Unchecked return value", "Medium", "",
                      "sample_src/utils.c", "Various", "get_value", "", "[]"])
        workbook.save(str(xlsx))

        memory = _agent_record(9001, report=str(xlsx))
        assert memory["disposition"] == "Needs review"
        assert "no concrete defect line" in memory["comment"]
        assert memory["confidence"] == 0.0
        assert "vulnerable_copy" in memory["comment"], \
            "the message should name the function the report supplied"

        line_agnostic = _agent_record(9002, report=str(xlsx))
        assert line_agnostic["disposition"] != "Needs review" or \
            "no concrete defect line" not in line_agnostic["comment"], \
            "a line-agnostic checker must be judged from the function, not deferred"
        assert line_agnostic["comment"], "a deferred row must still explain itself"

    def test_defect_without_events_is_not_treated_as_missing_source(self, tmp_path):
        """Excel exports usually carry no event trace.

        Synthesising one (as the desktop app does) must be enough to analyse —
        otherwise every Excel defect would come back as "Context extraction
        failed", which is exactly the bug this test prevents.
        """
        xlsx = tmp_path / "no-events.xlsx"
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append(["CID", "Checker", "Subtype", "File", "Line", "Function"])
        sheet.append([9100, "USE_AFTER_FREE", "Use after free",
                      "sample_src/utils.c", 10, "get_value"])
        workbook.save(str(xlsx))

        record = _agent_record(9100, report=str(xlsx))
        assert "could not be located or read" not in record["comment"]
        assert record["disposition"] == "Bug"
        assert "CWE-416" in record["comment"]
        assert record["proposed_fix"]


# --------------------------------------------------------------------------- #
# 3. The same parity through the CLI the agents actually use
# --------------------------------------------------------------------------- #
def test_cli_json_matches_the_in_process_result(sample_defects):
    """The agent's fallback path (subprocess) must not change the verdicts."""
    proc = subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "vscode_bridge.py"), "analyze",
         "--report", REPORT, "--src", SRC],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=600)
    payload = json.loads(proc.stdout)
    by_cid = {record["cid"]: record for record in payload["defects"]}
    for defect in sample_defects:
        in_process = _agent_record(defect["cid"])
        over_cli = by_cid[defect["cid"]]
        for field in RECORD_FIELDS:
            assert over_cli[field] == in_process[field], \
                f"CID {defect['cid']} {field} differs between CLI and library use"
