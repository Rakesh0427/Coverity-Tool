"""Tests for the two things that make the agent's opinions *informed*.

**1. The evidence dossier.** One tool call has to be enough for a model to judge
a defect for itself: the line the verdict hangs on, the declarations that fix
capacities, the guards already in the function, the callers whose behaviour
decides reachability. If those stop travelling with the defect, the agent
degrades into agreeing with a verdict it cannot check — the exact failure this
project exists to avoid.

**2. Mode detection.** "Engine said so" and "the model read the code" are
different claims with different trust levels. The payloads must say which one
applies, so the agent can label every verdict instead of blurring them.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

REPORT = os.path.join(REPO_ROOT, "docs", "sample_report")
SRC = os.path.join(REPO_ROOT, "docs")

import vscode_bridge as bridge                       # noqa: E402

pytest.importorskip("bs4", reason="report parsing needs BeautifulSoup")


@pytest.fixture(scope="module")
def dossier_1002():
    return bridge.op_context(REPORT, 1002, src_root=SRC, lines=10)["evidence"]


@pytest.fixture(scope="module")
def dossier_1001():
    return bridge.op_context(REPORT, 1001, src_root=SRC, lines=10)["evidence"]


# --------------------------------------------------------------------------- #
# 1. The dossier carries what a judgement needs
# --------------------------------------------------------------------------- #
class TestDossierContents:
    def test_defect_travels_with_its_code_facts(self, dossier_1002):
        """The five facts a model needs, on the defect it must judge."""
        assert dossier_1002["function"]["name"] == "get_value"
        assert dossier_1002["function"]["start_line"] < dossier_1002["defect_line"]["line"]
        assert "get_value" in dossier_1002["function"]["signature"]

        line = dossier_1002["defect_line"]
        assert line["line"] == 10
        assert "return p" in line["text"], \
            "the dossier must quote the line the verdict hangs on"

    def test_declarations_carry_the_capacity_facts(self, dossier_1001):
        """A buffer judgement needs the declaration, and its declared size."""
        buffer_declaration = next(d for d in dossier_1001["declarations"]
                                  if d["name"] == "buf")
        assert buffer_declaration["array"] is True
        assert buffer_declaration["size"] == "BUF_SIZE", \
            "an array without its declared size cannot be judged"
        assert buffer_declaration["line"] < dossier_1001["defect_line"]["line"]

    def test_a_pointer_declaration_is_marked_as_such(self, dossier_1002):
        pointer = next(d for d in dossier_1002["declarations"] if d["name"] == "p")
        assert pointer["pointer"] is True
        assert "malloc" in pointer["text"]

    def test_statements_are_not_reported_as_declarations(self, dossier_1002):
        """`return p;` is not a declaration of a variable called p."""
        names = [d["name"] for d in dossier_1002["declarations"]]
        assert names.count("p") == 1, (
            "the dossier reported the same name twice — a statement is being "
            f"parsed as a declaration: {dossier_1002['declarations']}")

    def test_guards_are_captured_with_their_line(self, dossier_1002):
        kinds = {g["kind"] for g in dossier_1002["guards"]}
        assert "if" in kinds
        guard = next(g for g in dossier_1002["guards"] if g["kind"] == "if")
        assert guard["line"] == 5, "the guard that decides this defect must be cited"

    def test_callers_decide_reachability(self, dossier_1001):
        """Who calls this, and where — the input-control question."""
        assert dossier_1001["callers"], "no caller information travelled with the defect"
        caller = dossier_1001["callers"][0]
        assert caller["caller"] == "main"
        assert caller["file"].endswith("sample.c")
        assert caller["line"] > 0
        assert caller["code"], "the caller's body is what makes it judgeable"

    def test_the_function_is_not_reported_as_its_own_caller(self, dossier_1002):
        """Self-references are noise in a dossier a model reasons over."""
        assert dossier_1002["callers"] == [], (
            "the enclosing function appeared as its own caller")
        assert "get_value" not in [c["name"] for c in dossier_1002["callees"]]

    def test_counts_report_the_full_picture(self, dossier_1001):
        counts = dossier_1001["counts"]
        assert counts["callers"] >= len(dossier_1001["callers"])
        assert set(counts) == {"callers", "callees", "declarations", "guards"}


class TestDossierDiscipline:
    def test_caller_bodies_are_capped_and_say_so(self, tmp_path, monkeypatch):
        """A huge caller must not blow up the agent's context window."""
        monkeypatch.setattr(bridge, "CALLER_CODE_LIMIT", 120)
        record = bridge.op_context(REPORT, 1001, src_root=SRC, lines=5)
        for caller in record["evidence"]["callers"]:
            assert len(caller["code"]) <= 120
            if len(caller["code"]) == 120:
                assert caller["code_truncated"] is True, \
                    "a truncated body must be marked, or the model trusts half a function"

    def test_dossier_stays_small_enough_for_a_prompt(self):
        payload = bridge.op_context(REPORT, 1001, src_root=SRC, lines=40)
        assert len(json.dumps(payload)) < 60_000, \
            "the dossier must fit comfortably in a prompt alongside the conversation"

    def test_text_values_are_bounded(self, dossier_1001):
        for key in ("declarations", "guards"):
            for entry in dossier_1001[key]:
                assert len(entry["text"]) <= 200
        for declaration in dossier_1001["declarations"]:
            assert declaration["name"]


# --------------------------------------------------------------------------- #
# 2. The facts reach the model as prose, not only as JSON
# --------------------------------------------------------------------------- #
class TestMcpRendering:
    @pytest.fixture(autouse=True)
    def _report(self, monkeypatch):
        monkeypatch.setenv("COVERITY_REPORT", REPORT)
        monkeypatch.setenv("COVERITY_SRC_ROOT", SRC)

    def _server(self):
        import coverity_mcp_server
        return coverity_mcp_server

    def _text(self, result):
        return result["content"][0]["text"]

    def test_analyze_renders_the_dossier_and_invites_disagreement(self):
        server = self._server()
        text = self._text(server.tool_analyze_defect({"cid": 1002, "context_lines": 10}))
        assert "Evidence dossier" in text
        for fact in ("Declaration 4", "Guard 5", "Defect line 10", "get_value"):
            assert fact in text, f"the prose dossier omits {fact}"
        assert "the engine's reading, not the last word" in text.lower() or \
               "not the last word" in text.lower(), \
            "the model must be told it may disagree — with evidence, not vibes"

    def test_source_context_renders_it_too(self):
        """The 'show me the code' tool is where a model double-checks a verdict."""
        server = self._server()
        text = self._text(server.tool_source_context({"cid": 1001, "context_lines": 12}))
        assert "Evidence dossier" in text
        assert "BUF_SIZE" in text, "the buffer's declared size is the deciding fact here"

    def test_the_json_block_still_carries_the_structured_dossier(self):
        server = self._server()
        block = json.loads(self._text_result_json(
            server.tool_analyze_defect({"cid": 1002})))
        assert block["evidence"]["defect_line"]["line"] == 10
        assert block["evidence"]["callers"] == []

    @staticmethod
    def _text_result_json(result):
        return (result["content"][1]["text"]
                .removeprefix("```json").removesuffix("```").strip())


# --------------------------------------------------------------------------- #
# 3. Mode detection — which claim is the agent allowed to make?
# --------------------------------------------------------------------------- #
class TestEngineMode:
    def test_full_install_reports_engine_mode(self):
        caps = bridge.capabilities_payload()
        assert caps["mode"] in ("engine", "degraded")
        assert caps["analyzer"] is True
        assert caps["verdicts"]
        if caps["depth"] == "full":
            assert caps["mode"] == "engine"
            assert "engine-backed" in caps["verdicts"]

    def test_missing_analyzer_reports_engine_missing(self, monkeypatch):
        """Without the analyser, no verdict may be presented as the engine's."""
        monkeypatch.setattr(bridge, "_analyzer_importable", lambda: False)
        caps = bridge.capabilities_payload()
        assert caps["mode"] == "engine_missing"
        assert caps["analyzer"] is False
        assert "model-only" in caps["verdicts"].lower()
        assert caps["verdicts"].strip()

    def test_degraded_mode_admits_the_verdicts_are_weaker(self, monkeypatch):
        """A reduced backend set must not be presented as a full analysis."""
        # Patch the module the payload actually reads.
        import capabilities as caps_module
        monkeypatch.setattr(caps_module, "analysis_depth", lambda: "minimal")
        caps = bridge.capabilities_payload()
        assert caps["mode"] == "degraded"
        assert "minimal" in caps["verdicts"]
        assert "provisional" in caps["verdicts"]

    def test_capabilities_prose_states_the_mode(self, monkeypatch):
        import coverity_mcp_server
        text = coverity_mcp_server.tool_capabilities({})["content"][0]["text"]
        assert "mode:" in text, \
            "an agent cannot label its verdicts if the capability report hides the mode"
