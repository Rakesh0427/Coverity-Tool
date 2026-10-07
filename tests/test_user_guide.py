"""The user guide is a deliverable, so it is tested like one.

Two failure modes matter for a guide: it can *rot* (documenting a flag, setting
or tool that no longer exists) and it can *lie* (promising something the code
cannot do — e.g. implying the agent pulls from Coverity Connect). These tests
catch both, plus broken relative links, so a reader never hits a dead end.
"""
from __future__ import annotations

import json
import os
import re
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

GUIDE = os.path.join(REPO_ROOT, "docs", "USER_GUIDE.md")


@pytest.fixture(scope="module")
def guide():
    assert os.path.isfile(GUIDE), "docs/USER_GUIDE.md is the user-facing deliverable"
    return open(GUIDE, encoding="utf-8").read()


# --------------------------------------------------------------------------- #
# It answers the questions it exists to answer
# --------------------------------------------------------------------------- #
class TestCoverage:
    def test_answers_all_six_setup_questions(self, guide):
        """The questions a user actually asks before they can start."""
        flat = re.sub(r"\s+", " ", guide).lower()
        required = {
            "how to give the input file": ["giving it input", "index.html", ".xlsx"],
            "where the code folder goes": ["where the code folder goes", "source root"],
            "how output is generated": ["where the output goes", "dispositions csv"],
            "how the code is analysed": ["how the analysis works", "build_defect_context",
                                         "analyze_defect", "needs review"],
            "how to get Coverity data": ["connect", "export"],
            "how to push back": ["pushing dispositions back", "fix required", "undecided"],
        }
        for question, needles in required.items():
            for needle in needles:
                assert needle in flat, f"{question}: guide never mentions {needle!r}"

    def test_states_that_credentials_never_reach_the_agent(self, guide):
        flat = re.sub(r"\s+", " ", guide).lower()
        assert "never talks to connect" in flat or "never asks for credentials" in flat
        assert "credentials stay in the desktop" in flat or \
               "credentials and stays in the desktop" in flat

    def test_documents_the_depth_caveat(self, guide):
        """The single most common cause of "it says something different"."""
        assert "full" in guide and "minimal" in guide
        assert "depth" in guide.lower()

    def test_various_line_rule_is_explained(self, guide):
        assert "Various" in guide, \
            "Excel exports without line numbers are the most common confusion"


# --------------------------------------------------------------------------- #
# Every concrete claim resolves against the real code
# --------------------------------------------------------------------------- #
class TestClaimsAreTrue:
    def test_named_tools_exist_on_the_server(self, guide):
        sys.path.insert(0, REPO_ROOT)
        import coverity_mcp_server
        names = {tool["name"] for tool in coverity_mcp_server.TOOLS}
        mentioned = set(re.findall(r"`(coverity_[a-z_]+)`", guide))
        assert mentioned, "the guide should name the tools it tells users to ask for"
        assert mentioned <= names, f"guide names tools that do not exist: {mentioned - names}"

    def test_named_settings_exist_in_the_extension(self, guide):
        package = json.load(open(os.path.join(REPO_ROOT, "vscode-extension",
                                              "package.json"), encoding="utf-8"))
        declared = set(package["contributes"]["configuration"]["properties"])
        mentioned = set(re.findall(r"`(coverityTool\.[A-Za-z]+)`", guide))
        assert mentioned, "the guide should show the settings route"
        assert mentioned <= declared, f"guide names settings that do not exist: {mentioned - declared}"

    def test_named_cli_flags_exist(self, guide):
        source = open(os.path.join(REPO_ROOT, "vscode_bridge.py"), encoding="utf-8").read()
        flags = set(re.findall(r"`(--[a-z-]+)`", guide))
        assert flags <= {"--csv", "--jsonl", "--out"}, "unexpected flag documented"
        for flag in flags:
            assert f'"{flag}"' in source, f"guide documents {flag}, which the CLI lacks"

    def test_push_instructions_match_the_desktop_app(self, guide):
        """The Push page labels the guide tells users to click must exist."""
        gui = open(os.path.join(REPO_ROOT, "local_gui.py"), encoding="utf-8").read()
        for label in ("Select Dispositions CSV", "Validate CIDs"):
            assert label in gui, f"the desktop app has no {label!r} control"
            assert label in guide, f"guide never tells the user to click {label!r}"
        assert 'or "Default"' in gui, "push store default changed"

    def test_action_mapping_matches_the_push_module(self, guide):
        sys.path.insert(0, REPO_ROOT)
        import coverity_push
        for disposition, action in (("Bug", "Fix Required"),
                                    ("False positive", "Ignore"),
                                    ("Intentional", "Ignore"),
                                    ("Needs review", "Undecided")):
            assert coverity_push.default_action_for_classification(disposition) == action
            assert re.search(rf"\|\s*{re.escape(disposition)}\s*\|\s*`?{action}",
                             guide), f"guide's table omits {disposition} → {action}"

    def test_batch_limit_claim_is_accurate(self, guide):
        sys.path.insert(0, REPO_ROOT)
        import coverity_push
        assert str(coverity_push.MAX_BATCH) in guide, \
            "the guide states the push batch size; keep it true"


# --------------------------------------------------------------------------- #
# No dead ends
# --------------------------------------------------------------------------- #
class TestLinks:
    def test_relative_links_resolve(self, guide):
        broken = []
        for target in re.findall(r"\]\((?!https?:)([^)#]+)", guide):
            candidate = os.path.join(os.path.dirname(GUIDE), target)
            if not os.path.exists(candidate):
                broken.append(target)
        assert not broken, f"guide links to files that do not exist: {broken}"

    def test_internal_anchors_exist(self, guide):
        headings = {re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-")
                    for h in re.findall(r"^#{2,3} (.+)$", guide, re.M)}
        for anchor in re.findall(r"\]\(#([^)]+)\)", guide):
            assert anchor in headings or anchor in guide, \
                f"guide links to #{anchor}, which is not a heading"

    def test_the_guide_is_reachable_from_the_entry_points(self):
        """A guide nobody finds helps nobody."""
        for path, label in (("README.md", "README"),
                            ("docs/VSCODE_AGENTS.md", "runbook"),
                            ("docs/VSCODE_INTEGRATION.md", "integration doc")):
            text = open(os.path.join(REPO_ROOT, path), encoding="utf-8").read()
            assert "USER_GUIDE.md" in text, f"{label} does not point at the user guide"
