"""Tests for vscode_bridge.py — the headless JSON front end.

These lock down the contract the VS Code extension and the MCP server both
depend on:

* stdout is pure JSON (a stray ``print`` anywhere in the analysis stack must not
  corrupt the payload),
* failures are JSON with a message and a hint, and exit non-zero,
* the same defect gets the same disposition as the desktop GUI pipeline,
* source lookup bridges build-machine paths to a local checkout,
* the annotation file that editors reload has the documented shape.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIDGE = os.path.join(REPO_ROOT, "vscode_bridge.py")
SAMPLE_REPORT = os.path.join(REPO_ROOT, "docs", "sample_report")
SAMPLE_SRC = os.path.join(REPO_ROOT, "docs")

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def run_bridge(*args, **kwargs):
    """Run the bridge exactly the way the extension does: capture stdout."""
    proc = subprocess.run(
        [sys.executable, BRIDGE, *args],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=300, **kwargs)
    payload = None
    text = proc.stdout.strip()
    if text:
        payload = json.loads(text)          # must always be valid JSON
    return proc.returncode, payload, proc.stderr


# --------------------------------------------------------------------------- #
# CLI contract
# --------------------------------------------------------------------------- #
class TestCliContract:
    def test_version_payload(self):
        code, payload, _ = run_bridge("--version")
        assert code == 0
        assert payload["ok"] is True
        assert payload["schema"] == 1

    def test_capabilities_reports_backends_and_depth(self):
        code, payload, _ = run_bridge("capabilities")
        assert code == 0
        caps = payload["capabilities"]
        assert caps["depth"] in ("full", "partial", "minimal")
        labels = [b["label"] for b in caps["backends"]]
        assert any("tree-sitter" in label for label in labels)
        # A missing critical backend must be named, so the UI can explain
        # why verdicts are weaker.
        if caps["depth"] != "full":
            assert caps["missing"]

    def test_list_defects(self):
        code, payload, _ = run_bridge("list", "--report", SAMPLE_REPORT)
        assert code == 0
        assert payload["total_in_report"] == 2
        cids = {d["cid"] for d in payload["defects"]}
        assert cids == {1001, 1002}
        assert payload["defects"][0]["file"].endswith(".c")

    def test_list_respects_filters(self):
        code, payload, _ = run_bridge("list", "--report", SAMPLE_REPORT,
                                      "--checker", "BUFFER_SIZE")
        assert code == 0
        assert [d["checker"] for d in payload["defects"]] == ["BUFFER_SIZE"]

    def test_missing_report_is_json_error(self):
        code, payload, _ = run_bridge("list", "--report", "/no/such/report.html")
        assert code == 1
        assert payload["ok"] is False
        assert "not found" in payload["error"]["message"].lower()
        assert payload["error"]["hint"]

    def test_unknown_cid_is_json_error(self):
        code, payload, _ = run_bridge("context", "--report", SAMPLE_REPORT,
                                      "--cid", "999999")
        assert code == 1
        assert payload["error"]["type"] == "NotFound"

    def test_unsupported_report_type_is_explained(self):
        code, payload, _ = run_bridge("list", "--report", __file__)
        assert code == 1
        assert "Unsupported report type" in payload["error"]["message"]

    def test_pretty_works_before_and_after_subcommand(self):
        for args in (("--pretty", "capabilities"), ("capabilities", "--pretty")):
            code, payload, _ = run_bridge(*args)
            assert code == 0 and payload["ok"] is True


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
class TestAnalysis:
    def test_analyze_produces_records_with_source_context(self):
        code, payload, _ = run_bridge(
            "analyze", "--report", SAMPLE_REPORT, "--src", SAMPLE_SRC,
            "--context-lines", "3")
        assert code == 0
        assert payload["summary"]["total"] == 2
        for record in payload["defects"]:
            assert record["disposition"] in (
                "Bug", "False positive", "Intentional", "Needs review")
            assert 0.0 <= record["confidence"] <= 1.0
            assert record["comment"]
            # The sample source resolves, so a real verdict (not the
            # "context extraction failed" fallback) must come back.
            assert record["resolved_file"].endswith(".c")
            assert record["source_context"]["code"]

    def test_verdicts_are_code_anchored(self):
        """With the checkout supplied, both known sample defects are decided.

        The sample's USE_AFTER_FREE is a bug at every analysis depth; its
        BUFFER_SIZE is a true positive once the AST is available (the
        vulnerable_copy() function fills the buffer with strncpy and never
        terminates it — a line-window fallback can mis-attribute the fix in
        the neighbouring safe_copy(), which is exactly why the depth is
        reported alongside the verdict).
        """
        _, payload, _ = run_bridge("analyze", "--report", SAMPLE_REPORT,
                                   "--src", SAMPLE_SRC)
        by_cid = {d["cid"]: d for d in payload["defects"]}
        assert by_cid[1002]["disposition"] == "Bug"
        assert "CWE-416" in by_cid[1002]["comment"]
        assert by_cid[1002]["proposed_fix"]

        assert by_cid[1001]["disposition"] in ("Bug", "False positive")
        assert "strncpy" in by_cid[1001]["comment"]
        assert by_cid[1001]["confidence"] > 0.5
        if payload["capabilities"]["depth"] == "full":
            assert by_cid[1001]["disposition"] == "Bug", (
                "with the full analysis stack the sample BUFFER_SIZE defect "
                "must be identified as a real bug")

    def test_analyze_without_source_says_so(self):
        _, payload, _ = run_bridge("analyze", "--report", SAMPLE_REPORT)
        # No src root -> the report's own relative path cannot be resolved
        # from an unrelated cwd, so the tool must explain rather than crash.
        for record in payload["defects"]:
            assert record["disposition"] in (
                "Bug", "False positive", "Intentional", "Needs review")
            assert record["comment"]

    def test_jsonl_stream_has_start_defect_done(self):
        proc = subprocess.run(
            [sys.executable, BRIDGE, "analyze", "--report", SAMPLE_REPORT,
             "--src", SAMPLE_SRC, "--jsonl"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=300)
        assert proc.returncode == 0
        events = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        kinds = [e["event"] for e in events]
        assert kinds[0] == "start"
        assert kinds[-1] == "done"
        assert kinds.count("defect") == 2
        # Progress must never be mixed into stdout.
        assert all(e["ok"] is True for e in events)

    def test_out_writes_reloadable_annotation(self, tmp_path):
        target = tmp_path / "triage.json"
        code, payload, _ = run_bridge(
            "analyze", "--report", SAMPLE_REPORT, "--src", SAMPLE_SRC,
            "--out", str(target))
        assert code == 0
        document = json.loads(target.read_text())
        assert document["schema"] == 1
        assert document["tool"] == "coverity-tool"
        assert document["summary"]["total"] == 2
        assert len(document["defects"]) == 2
        assert payload["written_to"] == str(target)

    def test_limit_and_cid_filters(self):
        _, payload, _ = run_bridge("analyze", "--report", SAMPLE_REPORT,
                                   "--src", SAMPLE_SRC, "--limit", "1")
        assert len(payload["defects"]) == 1

        _, payload, _ = run_bridge("analyze", "--report", SAMPLE_REPORT,
                                   "--src", SAMPLE_SRC, "--cid", "1002")
        assert [d["cid"] for d in payload["defects"]] == [1002]


# --------------------------------------------------------------------------- #
# Library API used by coverity_mcp_server.py
# --------------------------------------------------------------------------- #
class TestLibraryApi:
    def setup_method(self):
        import vscode_bridge
        self.bridge = vscode_bridge

    def test_constants_are_stable(self):
        assert self.bridge.SCHEMA_VERSION == 1
        assert self.bridge.DISPOSITION_BUG == "Bug"
        assert self.bridge.DISPOSITION_NEEDS_REVIEW == "Needs review"
        assert "CHECKED_RETURN" in self.bridge.LINE_AGNOSTIC_CHECKERS

    def test_op_list_and_op_analyze(self):
        listing = self.bridge.op_list(SAMPLE_REPORT, limit=5)
        assert listing["total_in_report"] == 2

        payload = self.bridge.op_analyze(SAMPLE_REPORT, src_root=SAMPLE_SRC)
        assert payload["summary"]["total"] == 2
        assert payload["capabilities"]["depth"]

    def test_op_context_returns_events_and_source(self):
        record = self.bridge.op_context(SAMPLE_REPORT, 1002, src_root=SAMPLE_SRC,
                                        lines=5)
        assert record["checker"] == "USE_AFTER_FREE"
        assert record["events"]
        assert record["source_context"]["code"]

    def test_repeated_loads_hit_the_cache(self):
        first = self.bridge.load_defects(SAMPLE_REPORT)
        second = self.bridge.load_defects(SAMPLE_REPORT)
        assert first is second

    def test_source_resolution_matches_build_machine_paths(self):
        resolved = self.bridge.resolve_source_file(
            "/build/agent/workspace/proj/src/sample.c", SAMPLE_SRC)
        assert resolved.endswith(os.path.join("sample_src", "sample.c"))

    def test_summary_counts_every_disposition(self):
        records = [
            {"disposition": "Bug", "confidence": 0.9, "checker": "A", "severity": ""},
            {"disposition": "Bug", "confidence": 0.5, "checker": "A", "severity": ""},
            {"disposition": "False positive", "confidence": 1.0, "checker": "B", "severity": ""},
            {"disposition": "Needs review", "confidence": 0.0, "checker": "B", "severity": ""},
        ]
        summary = self.bridge.summarise(records)
        assert summary["total"] == 4
        assert summary["bug"] == 2
        assert summary["false_positive"] == 1
        assert summary["needs_review"] == 1
        assert summary["intentional"] == 0
        assert summary["by_checker"]["A"] == 2
        assert summary["mean_confidence"] == pytest.approx(0.6)


# --------------------------------------------------------------------------- #
# Regression: the headless path must survive a machine without tree-sitter
# --------------------------------------------------------------------------- #
def test_find_function_line_by_name_without_ast(monkeypatch, tmp_path):
    """A missing AST must degrade to 0, not raise AttributeError.

    The GUI caught this by accident of the display; the bridge runs the same
    extractor with no display and no try/except around it, so the extractor
    itself has to be safe.
    """
    import code_extractor

    source = tmp_path / "unit.c"
    source.write_text("int f(void) { return 0; }\n")

    monkeypatch.setattr(code_extractor, "_parse_file", lambda *a, **k: ("int f(void){}", None))
    assert code_extractor.find_function_line_by_name(str(source), "f") == 0

    # And extraction still falls back to a line window.
    result = code_extractor.extract_enclosing_function(str(source), 1, "c")
    assert isinstance(result, tuple) and len(result) == 3
    assert result[2] is None
    assert "int f(void)" in result[0]
