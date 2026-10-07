"""The extension's CSV export must be loadable by the desktop Push page.

There are two exporters in this project — the engine's
(``vscode_bridge.write_dispositions_csv``, used by the CLI, the MCP export tool
and the agent) and the extension's (``vscode-extension/src/dispositions.ts``,
used by *Coverity: Export Triage…*). A user cannot tell them apart, so they must
produce the same columns and the same action vocabulary, or a file exported from
VS Code silently fails to load on the Coverity Push page.

The TypeScript module is executed for real (via its compiled ``out/*.js``) when
the extension has been built, and its output is fed through the same replica of
the desktop parser used by ``tests/test_export_results.py``. When it has not been
built, the source-level checks still run so drift is caught either way.
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

EXT_DIR = os.path.join(REPO_ROOT, "vscode-extension")
TS_SOURCE = os.path.join(EXT_DIR, "src", "dispositions.ts")
COMPILED = os.path.join(EXT_DIR, "out", "dispositions.js")

import vscode_bridge as bridge                       # noqa: E402
import coverity_push as cpush                        # noqa: E402

NODE = shutil.which("node")


def _compiled_or_skip():
    if not os.path.isfile(COMPILED) and NODE and os.path.isdir(
            os.path.join(EXT_DIR, "node_modules")):
        subprocess.run(["npm", "run", "compile"], cwd=EXT_DIR,
                       capture_output=True, timeout=600)
    if not (NODE and os.path.isfile(COMPILED)):
        pytest.skip("extension not built (run: npm --prefix vscode-extension run compile)")


# --------------------------------------------------------------------------- #
# 1. The two exporters agree
# --------------------------------------------------------------------------- #
class TestHeaderContract:
    def test_typescript_header_matches_the_engine_header(self):
        """Source-level guard: both exporters must list the same columns, in order."""
        source = open(TS_SOURCE, encoding="utf-8").read()
        declaration = source[source.index("DISPOSITIONS_HEADER"):]
        declaration = declaration[:declaration.index("] as const")]
        columns = [part.strip().strip("'\"")
                   for part in declaration.split("[", 1)[1].split(",")]
        columns = [column for column in columns if column]
        assert columns == list(bridge.DISPOSITIONS_CSV_HEADER), (
            "the extension exports different columns from the engine — a CSV "
            "from VS Code would not load on the desktop Push page")

    def test_action_mapping_matches_the_push_module(self):
        source = open(TS_SOURCE, encoding="utf-8").read()
        for disposition, action in (("Bug", "Fix Required"),
                                    ("False positive", "Ignore"),
                                    ("Intentional", "Ignore"),
                                    ("Needs review", "Undecided")):
            assert cpush.default_action_for_classification(disposition) == action
            assert f"'{action}'" in source, f"the extension never maps to {action}"


# --------------------------------------------------------------------------- #
# 2. Executed: the compiled module's output, through the desktop parser
# --------------------------------------------------------------------------- #
RECORDS = [
    {"cid": 1001, "checker": "BUFFER_SIZE", "type": "Buffer not null terminated",
     "severity": "High", "file": "sample_src/sample.c", "resolved_file": "/repo/sample.c",
     "line": 10, "function": "vulnerable_copy", "disposition": "Bug",
     "confidence": 1.0, "category": "Buffer overflow",
     "comment": 'Line 10 copies sizeof(buf) bytes.\n\nIndependent "corroboration".',
     "proposed_fix": "strncpy(buf, input, sizeof(buf) - 1);\nbuf[sizeof(buf) - 1] = '\\0';"},
    {"cid": 1002, "checker": "USE_AFTER_FREE", "type": "Use after free",
     "severity": "High", "file": "sample_src/utils.c", "resolved_file": "/repo/utils.c",
     "line": 10, "function": "get_value", "disposition": "Needs review",
     "confidence": 0.0, "category": "Memory - illegal accesses",
     "comment": "Insufficient evidence.", "proposed_fix": ""},
]


def _run_ts_export(records, out_path):
    script = (
        "const { dispositionsCsv } = require(process.argv[1]);"
        "const fs = require('fs');"
        "const records = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));"
        "fs.writeFileSync(process.argv[3], dispositionsCsv(records,"
        "  new Date(2026, 7, 14, 9, 30, 0)), 'utf8');"
    )
    with open(out_path + ".records.json", "w", encoding="utf-8") as handle:
        json.dump(records, handle)
    proc = subprocess.run([NODE, "-e", script, COMPILED, out_path + ".records.json",
                           out_path],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return out_path


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    """The extension's real output, produced by executing its compiled module."""
    _compiled_or_skip()
    path = str(tmp_path_factory.mktemp("ext-export") / "dispositions.csv")
    return _run_ts_export(RECORDS, path)


class TestExtensionExportIsPushable:

    def test_rows_and_header_match_the_engine_format(self, exported):
        with open(exported, newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == len(RECORDS)
        assert list(rows[0].keys()) == list(bridge.DISPOSITIONS_CSV_HEADER)
        assert rows[0]["CID"] == "1001"
        assert rows[0]["Classification"] == "Bug"
        assert rows[0]["Action"] == "Fix Required"
        assert rows[1]["Action"] == "Undecided", \
            "an undecided finding must not be pushed as if it were accepted"
        assert rows[0]["Timestamp"] == "2026-08-14 09:30:00"

    def test_desktop_push_page_parser_accepts_every_row(self, exported):
        """Replicates PushPage._load_csv, as test_export_results.py does."""
        with open(exported, newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        valid = []
        for row in rows:
            cid = row.get("CID") or row.get("cid") or ""
            classification = (row.get("Classification")
                              or row.get("FinalClassification") or "")
            action = cpush.normalize_action(row.get("Action") or "") or \
                cpush.default_action_for_classification(classification)
            if cid and classification:
                valid.append({"cid": int(cid), "classification": classification,
                              "action": action, "comment": row.get("Comment") or "",
                              "checker": row.get("Checker") or "",
                              "file": row.get("File") or ""})
        assert len(valid) == len(RECORDS), "the Push page would drop rows from this file"
        push_rows = cpush.build_push_rows(valid, reviewer="extension-test")
        assert len(push_rows) == len(RECORDS)
        assert {row.action for row in push_rows} == {"Fix Required", "Undecided"}

    def test_awkward_text_survives(self, exported):
        with open(exported, newline="", encoding="utf-8-sig") as handle:
            rows = {row["CID"]: row for row in csv.DictReader(handle)}
        assert '"corroboration"' in rows["1001"]["Comment"]
        assert "\n" in rows["1001"]["Comment"]
        assert "sizeof(buf) - 1" in rows["1001"]["Fix"]

    def test_resolved_path_is_exported_not_the_report_path(self, exported):
        """The Push page and the reviewer both want the real file."""
        with open(exported, newline="", encoding="utf-8-sig") as handle:
            rows = {row["CID"]: row for row in csv.DictReader(handle)}
        assert rows["1001"]["File"] == "/repo/sample.c"
