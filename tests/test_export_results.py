"""Tests for the push-ready export: triage results → desktop-loadable CSV.

The user-facing promise is: *analyse in VS Code, then push from the desktop app
without retyping anything*. That promise is only true if the CSV this project
writes is byte-compatible with what the desktop application expects, so these
tests do three things:

1. pin the header against the header ``local_gui`` actually writes (a
   source-level guard, so a rename on either side fails loudly);
2. replicate the desktop Push page's ``_load_csv`` logic and feed our file
   through it, then run the rows through ``coverity_push.build_push_rows`` —
   i.e. the same path the Push button uses;
3. check the CLI and MCP entry points both produce it, with the documented
   action mapping.
"""
from __future__ import annotations

import csv
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

import vscode_bridge as bridge                       # noqa: E402
import coverity_push as cpush                        # noqa: E402

ACTION_FOR = {
    "Bug": "Fix Required",
    "False positive": "Ignore",
    "Intentional": "Ignore",
    "Needs review": "Undecided",
}


def _records():
    return bridge.op_analyze(REPORT, src_root=SRC)["defects"]


# --------------------------------------------------------------------------- #
# 1. Format compatibility with the desktop application
# --------------------------------------------------------------------------- #
class TestDispositionsFormat:
    def test_header_matches_the_desktop_app_exactly(self):
        with open(os.path.join(REPO_ROOT, "local_gui.py"), encoding="utf-8") as fh:
            gui = fh.read()
        expected = re.search(
            r'writer\.writerow\(\[("CID".*?)\]\)', gui, re.S)
        assert expected, "could not find the dispositions header in local_gui.py"
        desktop_header = [part.strip().strip('"')
                          for part in expected.group(1).split(",")]
        assert list(bridge.DISPOSITIONS_CSV_HEADER) == desktop_header, (
            "the exported CSV must keep the desktop app's column names and order "
            "so its Push page can load it")

    def test_exported_file_has_that_header_and_one_row_per_defect(self, tmp_path):
        records = _records()
        target = tmp_path / "coverity_dispositions.csv"
        info = bridge.write_dispositions_csv(records, str(target))

        with open(target, newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        assert info["rows"] == len(records) == len(rows)
        assert list(rows[0].keys()) == list(bridge.DISPOSITIONS_CSV_HEADER)
        assert {row["CID"] for row in rows} == {str(r["cid"]) for r in records}

    def test_file_is_written_with_a_bom_so_excel_opens_it_cleanly(self, tmp_path):
        target = tmp_path / "bom.csv"
        bridge.write_dispositions_csv(_records(), str(target))
        with open(target, "rb") as handle:
            assert handle.read(3) == b"\xef\xbb\xbf"

    def test_awkward_rationales_survive_a_csv_round_trip(self, tmp_path):
        """Real rationales contain newlines, commas and quotes; none may break."""
        target = tmp_path / "quoted.csv"
        records = [
            {"cid": 1, "checker": "BUFFER_SIZE", "disposition": "Bug",
             "comment": ("Line 10 copies sizeof(buf) bytes, filling the buffer.\n\n"
                         "Independent corroboration: cppcheck's \"buffer\" rule "
                         "also flags it."),
             "proposed_fix": 'strncpy(buf, input, sizeof(buf) - 1);\nbuf[sizeof(buf) - 1] = \'\\0\';'},
            {"cid": 2, "checker": "USE_AFTER_FREE", "disposition": "Needs review",
             "comment": "Ünïcödé and \n newlines, plus a trailing comma,",
             "proposed_fix": ""},
        ]
        bridge.write_dispositions_csv(records, str(target))
        with open(target, newline="", encoding="utf-8-sig") as handle:
            parsed = {row["CID"]: row for row in csv.DictReader(handle)}
        for record in records:
            assert parsed[str(record["cid"])]["Comment"] == record["comment"].strip()
            assert parsed[str(record["cid"])]["Fix"] == record["proposed_fix"].strip()
        assert parsed["1"]["Action"] == "Fix Required"
        assert parsed["2"]["Action"] == "Undecided", \
            "an un-decided row must not be silently marked as accepted"

    def test_action_column_uses_the_connect_vocabulary(self, tmp_path):
        target = tmp_path / "actions.csv"
        records = [
            {"cid": 1, "checker": "BUFFER_SIZE", "disposition": "Bug"},
            {"cid": 2, "checker": "DEADCODE", "disposition": "False positive"},
            {"cid": 3, "checker": "FORWARD_NULL", "disposition": "Intentional"},
            {"cid": 4, "checker": "CHECKED_RETURN", "disposition": "Needs review"},
        ]
        bridge.write_dispositions_csv(records, str(target))
        with open(target, newline="", encoding="utf-8-sig") as handle:
            actions = {row["CID"]: row["Action"] for row in csv.DictReader(handle)}
        assert actions == {"1": "Fix Required", "2": "Ignore",
                           "3": "Ignore", "4": "Undecided"}
        for disposition, action in ACTION_FOR.items():
            assert cpush.default_action_for_classification(disposition) == action


# --------------------------------------------------------------------------- #
# 2. The desktop Push page really can consume it
# --------------------------------------------------------------------------- #
def _desktop_push_page_parse(path):
    """Replicate ``PushPage._load_csv`` (local_gui.py) exactly."""
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            rows.append(row)
    valid = []
    for row in rows:
        cid = row.get("CID") or row.get("cid") or ""
        classification = (row.get("Classification") or row.get("FinalClassification")
                          or row.get("classification") or "")
        comment = (row.get("Comment") or row.get("FinalComment")
                   or row.get("comment") or "")
        action = cpush.normalize_action(row.get("Action") or row.get("FinalAction")
                                        or row.get("action") or "") or \
            cpush.default_action_for_classification(classification)
        checker = row.get("Checker") or row.get("checker") or ""
        file_path = row.get("File") or row.get("file") or ""
        if cid and classification:
            valid.append({"cid": int(cid), "classification": classification,
                          "action": action, "comment": comment,
                          "checker": checker, "file": file_path})
    seen = {}
    for row in valid:
        seen[row["cid"]] = row
    return list(seen.values())


class TestDesktopPushPageAcceptance:
    def test_push_page_parses_every_row(self, tmp_path):
        target = tmp_path / "coverity_dispositions.csv"
        records = _records()
        bridge.write_dispositions_csv(records, str(target))
        loaded = _desktop_push_page_parse(str(target))
        assert len(loaded) == len(records), \
            "the Push page would silently drop rows it cannot parse"
        assert {row["cid"] for row in loaded} == {r["cid"] for r in records}
        assert all(row["classification"] in bridge.DISPOSITIONS for row in loaded)
        assert all(row["action"] for row in loaded)

    def test_loaded_rows_build_pushable_connect_rows(self, tmp_path):
        target = tmp_path / "coverity_dispositions.csv"
        bridge.write_dispositions_csv(_records(), str(target))
        loaded = _desktop_push_page_parse(str(target))
        push_rows = cpush.build_push_rows(loaded, reviewer="guide-check")
        assert len(push_rows) == len(loaded)
        for row in push_rows:
            assert row.cid
            assert row.action in set(ACTION_FOR.values())
            assert row.comment, "a pushed disposition without a rationale is useless"

    def test_guard_replica_still_matches_the_push_page_source(self):
        """If the Push page's parser changes, re-derive the replication above."""
        with open(os.path.join(REPO_ROOT, "local_gui.py"), encoding="utf-8") as fh:
            gui = fh.read()
        for fragment in ('row.get("CID") or row.get("cid")',
                         'row.get("FinalClassification")',
                         'row.get("FinalAction")',
                         "cpush.default_action_for_classification(cls)",
                         '_csv_rows = valid'):
            assert fragment in gui, f"PushPage._load_csv no longer contains {fragment}"


# --------------------------------------------------------------------------- #
# 3. Entry points
# --------------------------------------------------------------------------- #
class TestCliExport:
    def test_analyze_csv_flag_writes_the_file(self, tmp_path):
        target = tmp_path / "out.csv"
        proc = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "vscode_bridge.py"), "analyze",
             "--report", REPORT, "--src", SRC, "--csv", str(target), "--quiet"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=600)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["dispositions_csv"]["path"] == str(target)
        assert payload["dispositions_csv"]["rows"] == len(payload["defects"])
        assert target.is_file()

    def test_streaming_mode_also_reports_the_csv(self, tmp_path):
        target = tmp_path / "stream.csv"
        proc = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "vscode_bridge.py"), "analyze",
             "--report", REPORT, "--src", SRC, "--jsonl", "--out",
             str(tmp_path / "ann.json"), "--csv", str(target), "--quiet"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=600)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        events = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        done = [event for event in events if event.get("event") == "done"][-1]
        assert done["dispositions_csv"]["path"] == str(target)
        assert target.is_file()


class TestMcpExport:
    @pytest.fixture(autouse=True)
    def _configured(self, monkeypatch):
        monkeypatch.setenv("COVERITY_REPORT", REPORT)
        monkeypatch.setenv("COVERITY_SRC_ROOT", SRC)

    def _server(self):
        sys.path.insert(0, REPO_ROOT)
        import coverity_mcp_server
        return coverity_mcp_server

    def test_tool_is_advertised_with_a_write_annotation(self):
        server = self._server()
        tool = next(t for t in server.TOOLS
                    if t["name"] == "coverity_export_results")
        assert tool["annotations"]["readOnlyHint"] is False
        assert "output_path" in tool["inputSchema"]["properties"]
        assert tool["inputSchema"]["additionalProperties"] is False

    def test_tool_writes_the_csv_and_describes_the_next_step(self, tmp_path):
        server = self._server()
        target = tmp_path / "mcp.csv"
        result = server.tool_export_results({"output_path": str(target)})
        text = result["content"][0]["text"]
        assert str(target) in text
        block = json.loads(result["content"][1]["text"].removeprefix("```json")
                           .removesuffix("```").strip())
        assert block["dispositions_csv"]["path"] == str(target)
        assert block["dispositions_csv"]["rows"] == len(block["defects"])
        assert "Push page" in text
        assert target.is_file()

    def test_default_output_path_is_inside_the_tool_output_dir(self, monkeypatch,
                                                               tmp_path):
        monkeypatch.setenv("COVERITY_MCP_OUTPUT_DIR", str(tmp_path))
        server = self._server()
        result = server.tool_export_results({})
        path = json.loads(result["content"][1]["text"]
                          .removeprefix("```json").removesuffix("```").strip()) \
            ["dispositions_csv"]["path"]
        assert os.path.dirname(path) == str(tmp_path)
        assert path.endswith("_dispositions.csv")

    def test_export_never_asks_for_or_records_credentials(self, tmp_path):
        server = self._server()
        target = tmp_path / "no-creds.csv"
        result = server.tool_export_results({"output_path": str(target)})
        blob = json.dumps(result).lower()
        for banned in ("password", "passwd", "token", "auth_key", "secret"):
            assert banned not in blob, f"export must not mention {banned}"
        assert "coverity connect" in blob  # it may *name* Connect, just not use it
