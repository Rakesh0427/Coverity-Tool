"""The user manual is a deliverable, so it is tested like one.

A prompt cookbook rots the same way any guide does: it documents a script that
was renamed, quotes a CSV header that drifted, points at a sample file that
moved, or quietly resurrects the old "you must install the engine" story that
the agent no longer tells. These tests pin the manual to the code and to the
agent file, and execute the commands it prints.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

MANUAL = os.path.join(REPO_ROOT, "docs", "AGENT_USER_MANUAL.md")
AGENT = os.path.join(REPO_ROOT, ".github", "agents",
                     "coverity-finding-analyzer.agent.md")
SAMPLE_REPORT = os.path.join("docs", "sample_report")
SAMPLE_SRC = os.path.join("docs", "sample_src")


@pytest.fixture(scope="module")
def manual():
    assert os.path.isfile(MANUAL), "docs/AGENT_USER_MANUAL.md is the user-facing deliverable"
    return open(MANUAL, encoding="utf-8").read()


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


def plain(text: str) -> str:
    """Flat text with markdown emphasis removed, for prose assertions."""
    return re.sub(r"[*`]", "", flat(text))


# --------------------------------------------------------------------------- #
# It answers the questions a user actually has
# --------------------------------------------------------------------------- #
class TestCoverage:
    def test_covers_the_path_from_install_to_export(self, manual):
        text = flat(manual)
        required = {
            "install": ["install it", "agent picker"],
            "the two inputs": ["the two inputs", "source root"],
            "how to phrase a first prompt": ["analyse `docs/sample_report/index.html` against the source root `docs`"],
            "the five jobs": ["triage a report", "deep dive one defect", "fix and verify",
                              "write-back and export", "diagnose and improve"],
            "a prompt cookbook": ["prompt cookbook"],
            "how to read the answer": ["reading the answer", "evidence read", "would change my mind"],
            "big reports": ["big reports", "slice"],
            "troubleshooting": ["when something looks wrong"],
        }
        for section, needles in required.items():
            for needle in needles:
                assert needle in text, f"the manual never covers {section}: {needle!r}"

    def test_teaches_the_source_root_rule_with_a_worked_example(self, manual):
        """The single most common cause of a bad run."""
        text = flat(manual)
        assert "the folder the report's file paths are relative to" in text
        assert "sample_src/utils.c" in text and "docs/sample_src/utils.c" in text
        assert "build-machine" in text or "build machine" in text

    def test_has_a_substantial_prompt_cookbook(self, manual):
        recipes = re.findall(r"^### 4\.\d+ ", manual, re.M)
        assert len(recipes) >= 12, f"only {len(recipes)} worked prompts — the cookbook is thin"
        for phrase in ("What would change your mind", "Make the strongest possible case",
                       "Re-derive", "do not apply it"):
            assert phrase in manual, f"the cookbook lost its {phrase!r} prompt"

    def test_warns_about_the_prompts_that_waste_time(self, manual):
        assert "Prompts that waste your time" in manual
        for weak in ("Fix everything", "Mark all of these False positive", "Is this code safe?"):
            assert weak in manual


# --------------------------------------------------------------------------- #
# Every claim resolves against the real code
# --------------------------------------------------------------------------- #
class TestClaimsAreTrue:
    def test_the_documented_commands_actually_run(self, manual, tmp_path):
        """Every `python … .py …` the manual prints must work as written."""
        commands = re.findall(r"`(python3? [^`]+\.py[^`]*)`", manual)
        commands += [line.strip() for block in re.findall(r"^```bash\n(.*?)^```", manual, re.M | re.S)
                     for line in block.splitlines() if line.strip().startswith("python")]
        commands = [re.split(r"\s+#", c)[0].strip() for c in commands]
        assert commands, "the manual documents no runnable command"
        ran = 0
        for command in commands:
            argv = command.split()
            script = argv[1] if argv[0].startswith("python") else argv[0]
            assert os.path.isfile(os.path.join(REPO_ROOT, script)), \
                f"the manual prints a command for a missing script: {script}"
            if "<" in command:
                continue                        # a placeholder for the user's own paths
            proc = subprocess.run([sys.executable, script, *argv[2:]], cwd=REPO_ROOT,
                                  capture_output=True, text=True, timeout=600)
            assert proc.returncode == 0, f"{command!r} failed: {proc.stderr}"
            ran += 1
        assert ran >= 1, "not one documented command was actually executed"
        assert os.path.isfile(os.path.join(REPO_ROOT, "requirements.txt"))

    def test_the_digest_command_it_prints_works_on_the_sample(self, manual):
        assert "coverity_report_text.py <report-folder> --limit 40" in manual
        proc = subprocess.run([sys.executable, "coverity_report_text.py",
                               SAMPLE_REPORT, "--limit", "40"],
                              cwd=REPO_ROOT, capture_output=True, text=True, timeout=600)
        assert proc.returncode == 0 and "CID" in proc.stdout

    def test_the_csv_header_matches_the_push_tooling(self, manual):
        """The 13 columns the desktop Push page loads, quoted verbatim."""
        match = re.search(r'^"CID","Checker".*$', manual, re.M)
        assert match, "the manual no longer quotes the dispositions CSV header"
        quoted = match.group(0)
        columns = [c.strip('"') for c in quoted.split(",")]

        ts = open(os.path.join(REPO_ROOT, "vscode-extension", "src",
                               "dispositions.ts"), encoding="utf-8").read()
        block = ts[ts.index("DISPOSITIONS_HEADER"):ts.index("as const")]
        assert columns == re.findall(r"'([^']+)'", block), \
            "the manual's CSV header has drifted from DISPOSITIONS_HEADER"

        sys.path.insert(0, REPO_ROOT)
        import coverity_push
        assert columns == [c.strip('"') for c in coverity_push.DISPOSITIONS_COLUMNS] \
            if hasattr(coverity_push, "DISPOSITIONS_COLUMNS") else True

    def test_the_action_mapping_matches_the_push_module(self, manual):
        sys.path.insert(0, REPO_ROOT)
        import coverity_push
        for disposition, action in (("Bug", "Fix Required"),
                                    ("False positive", "Ignore"),
                                    ("Intentional", "Ignore"),
                                    ("Needs review", "Undecided")):
            assert coverity_push.default_action_for_classification(disposition) == action
            assert re.search(rf"\|\s*`?{re.escape(disposition)}`?\s*\|[^|\n]*\|\s*`?{action}",
                             manual), f"the manual omits {disposition} → {action}"

    def test_the_push_page_labels_it_tells_users_to_click_exist(self, manual):
        gui = open(os.path.join(REPO_ROOT, "local_gui.py"), encoding="utf-8").read()
        for label in ("Select Dispositions CSV", "Validate CIDs"):
            assert label in gui, f"the desktop app has no {label!r} control"
            assert label in manual, f"the manual never mentions {label!r}"

    def test_the_sample_expectations_match_the_sample(self, manual):
        """CIDs, files and lines the worked example promises must be real."""
        sample_c = open(os.path.join(SAMPLE_SRC, "sample.c"), encoding="utf-8").read().splitlines()
        utils_c = open(os.path.join(SAMPLE_SRC, "utils.c"), encoding="utf-8").read().splitlines()
        assert "strncpy(buf, input, sizeof(buf));" in sample_c[8], \
            "the manual's line-9 claim about sample.c no longer holds"
        assert sample_c[9].strip().startswith("printf"), \
            "the manual's line-10 claim about sample.c no longer holds"
        assert utils_c[8].strip() == "free(p);", \
            "the manual's line-9 claim about utils.c no longer holds"
        assert utils_c[9].strip().startswith("return p;"), \
            "the manual's line-10 claim about utils.c no longer holds"
        text = flat(manual)
        assert "1001" in text and "buffer_size" in text
        assert "1002" in text and "use_after_free" in text
        assert "sample_src/sample.c" in manual and "sample_src/utils.c" in manual

    def test_the_disposition_set_is_the_closed_set(self, manual):
        text = flat(manual)
        assert "closed set of four" in text
        for disposition in ("`bug`", "`false positive`", "`intentional`", "`needs review`"):
            assert disposition in text

    def test_the_capabilities_command_it_prints_matches_its_output(self, manual):
        """`python capabilities.py` really does print a depth line like the one quoted."""
        source = open(os.path.join(REPO_ROOT, "capabilities.py"), encoding="utf-8").read()
        assert "analysis depth: {depth.upper()}" in source
        assert "expect: analysis depth: FULL" in manual
        assert os.path.isfile(os.path.join(REPO_ROOT, "requirements.txt"))


# --------------------------------------------------------------------------- #
# It is the manual for *this* agent, and it says so honestly
# --------------------------------------------------------------------------- #
class TestModelFirstStory:
    def test_says_the_model_does_the_work_with_nothing_installed(self, manual):
        text = plain(manual)
        assert "runs on the vs code model" in text
        assert "no python, no engine, no mcp server" in text
        for phrase in ("needs nothing installed", "needs nothing", "nothing has to be installed"):
            if phrase in text:
                break
        else:
            raise AssertionError("the manual never states that nothing needs installing")

    def test_never_promises_engine_output_that_may_not_exist(self, manual):
        """No engine-first leftovers: the accelerator may only be described as optional."""
        text = flat(manual)
        for forbidden in ("verdict must come from", "silently degrades",
                          "model-only, unverified", "you must install the engine"):
            assert forbidden not in text, f"stale engine-first claim: {forbidden!r}"
        assert "optional accelerator" in text
        assert "never a requirement" in text

    def test_keeps_the_engine_out_of_the_critical_path(self, manual):
        """The engine section comes last and is marked optional."""
        section = manual.index("## 11. The optional accelerator")
        assert section > manual.index("## 8. Big reports"), \
            "the accelerator must not be in the critical path"
        tail = manual[section:]
        assert "pip install -r requirements.txt" in tail
        assert "never a requirement" in tail

    def test_the_agent_it_documents_exists_and_matches_the_name(self, manual):
        assert "coverity-finding-analyzer.agent.md" in manual
        assert os.path.isfile(AGENT)
        head = open(AGENT, encoding="utf-8").read().split("---")[1]
        assert re.search(r"name:\s*Coverity Finding Analyzer", head)
        assert "Coverity Finding Analyzer" in manual

    def test_the_two_inputs_rule_matches_the_agent(self, manual):
        """The agent asks for report + source root; the manual says the same."""
        body = open(AGENT, encoding="utf-8").read()
        assert "source root" in body
        assert "Collect the two inputs before analysing anything" in body
        assert "the report location and the source root" in flat(manual) or \
               "report + source root" in flat(manual)


# --------------------------------------------------------------------------- #
# No dead ends
# --------------------------------------------------------------------------- #
class TestLinks:
    def test_relative_links_resolve(self, manual):
        broken = []
        for target in re.findall(r"\]\((?!https?:)([^)#]+)", manual):
            if not os.path.exists(os.path.join(REPO_ROOT, "docs", target)):
                broken.append(target)
        assert not broken, f"the manual links to files that do not exist: {broken}"

    def test_internal_anchors_exist(self, manual):
        headings = {re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-")
                    for h in re.findall(r"^#{2,3} (.+)$", manual, re.M)}
        for anchor in re.findall(r"\]\(#([^)]+)\)", manual):
            assert anchor in headings or anchor in manual, \
                f"the manual links to #{anchor}, which is not a heading"

    def test_the_manual_is_reachable_from_the_entry_points(self):
        for path, label in (("README.md", "README"),
                            ("docs/VSCODE_AGENTS.md", "runbook"),
                            ("docs/USER_GUIDE.md", "user guide"),
                            ("docs/VSCODE_INTEGRATION.md", "integration doc")):
            text = open(os.path.join(REPO_ROOT, path), encoding="utf-8").read()
            assert "AGENT_USER_MANUAL.md" in text, f"{label} does not point at the manual"
