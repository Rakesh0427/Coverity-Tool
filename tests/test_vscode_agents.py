"""Tests for the single-file custom agent in .github/agents/.

Three things are worth locking down here:

1. **The file is a valid agent.** Malformed YAML frontmatter makes VS Code
   silently drop the agent from the picker, and a tool name that no server or
   extension contributes makes it fail at invocation — both are cheap to check
   and expensive to notice.
2. **It is the analyst.** The agent's whole reason to exist is that the VS Code
   model reads the code and decides; the engine supplies facts. If those roles
   blur in an edit (verdicts presented as the engine's answer, or claims with no
   code behind them), the agent stops being what it promises.
3. **The instructions are true.** Every command the agent is told to run must
   actually work, the four dispositions and the Connect mapping must match the
   tool, and the fix-then-re-analyse loop it promises must still hold on the
   shipped sample.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

import pytest

yaml = pytest.importorskip("yaml", reason="PyYAML is a runtime dependency")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_DIR = os.path.join(REPO_ROOT, ".github", "agents")
BRIDGE = os.path.join(REPO_ROOT, "vscode_bridge.py")
SAMPLE_REPORT = os.path.join(REPO_ROOT, "docs", "sample_report")
SAMPLE_SRC = os.path.join(REPO_ROOT, "docs", "sample_src")

#: The one agent this pack ships (mirrors build_agent_bundle.AGENT_NAME).
AGENT_NAME = "coverity-finding-analyzer.agent.md"

AGENT_FILES = sorted(
    os.path.join(AGENTS_DIR, name)
    for name in os.listdir(AGENTS_DIR)
    if name.endswith(".agent.md")
)

#: Tool namespaces that exist without any extension installed (VS Code built-ins
#: and tool sets). An MCP namespace is validated against .vscode/mcp.json.
BUILTIN_TOOL_NAMES = {
    "edit", "search", "read", "web", "agent", "todos", "problems",
    "runCommands", "runTasks", "changes", "terminal", "extensions",
}
BUILTIN_NAMESPACES = {"search", "read", "web", "edit", "runCommands", "runTasks",
                      "problems", "todos", "agent", "changes"}


def frontmatter(path: str):
    """Return (frontmatter dict, body) for an .agent.md file."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert match, f"{os.path.basename(path)} has no YAML frontmatter"
    return yaml.safe_load(match.group(1)), match.group(2)


def run_bridge(*args, expect_ok=True):
    proc = subprocess.run([sys.executable, BRIDGE, *args], cwd=REPO_ROOT,
                          capture_output=True, text=True, timeout=600)
    payload = json.loads(proc.stdout)
    if expect_ok:
        assert proc.returncode == 0, proc.stderr
        assert payload["ok"] is True
    return payload


# --------------------------------------------------------------------------- #
# 1. The files are valid agents
# --------------------------------------------------------------------------- #
class TestAgentFiles:
    def test_pack_is_the_single_file(self):
        """One agent file, and nothing else in the agents folder.

        VS Code treats every .md file in .github/agents/ as an agent, so a
        README or a second partial agent would show up in the picker. The
        engine is a tool provider, not an agent, and must not live here.
        """
        assert {os.path.basename(p) for p in AGENT_FILES} == {AGENT_NAME}
        assert sorted(os.listdir(AGENTS_DIR)) == [AGENT_NAME], \
            "only the agent file may live in .github/agents/"

    def test_agent_needs_nothing_installed(self):
        """The correction: the VS Code model does the work, not a local tool.

        The agent must run in a bare project — no engine, no MCP server, no
        Python packages. If this framing erodes, users without the toolchain
        will believe the agent cannot work for them.
        """
        _, body = frontmatter(os.path.join(AGENTS_DIR, AGENT_NAME))
        assert re.search(r"You are the analyser", body), \
            "the agent no longer states that it is the one analysing"
        assert re.search(r"Nothing needs to be installed", body), \
            "the no-installation promise is gone"
        assert re.search(r"no local tool|no server|No Python package", body, re.I)
        # The engine may only ever appear as optional.
        assert re.search(r"Optional accelerator", body)
        assert re.search(r"Never required", body), \
            "the accelerator must be explicitly optional"

    def test_agent_can_read_a_report_without_any_tooling(self):
        """Reading the report is the model's job: index, detail pages, traces."""
        _, body = frontmatter(os.path.join(AGENTS_DIR, AGENT_NAME))
        for step in ("index.html", "detail page", "event trace", "code excerpt",
                     "Strategy for a small or medium report", "large report"):
            assert step.lower() in body.lower(), f"no report-reading guidance: {step}"
        # Every non-HTML format the user might hand over needs a route.
        for fmt in (".xlsx", "CSV", "HTML"):
            assert fmt in body, f"no guidance for {fmt} reports"
        assert "openpyxl" in body and "html.unescape" in body, \
            "the flattening recipes (no local tool required) are missing"

    def test_agent_writes_the_push_file_itself(self):
        """Export must work with no engine: the model writes the CSV."""
        _, body = frontmatter(os.path.join(AGENTS_DIR, AGENT_NAME))
        assert re.search(r"write the CSV yourself", body, re.I)
        header = ('"CID","Checker","Type","Severity","Action","File","Line",'
                  '"Function","Classification","Comment","Fix","Timestamp","Category"')
        assert header in body, \
            "the exact push-ready header must be in the instructions for the model to emit"
        for mapping in ("Fix Required", "False Positive", "Ignore", "Pending",
                        "Undecided"):
            assert mapping in body, f"missing Connect mapping value: {mapping}"

    def test_agent_verifies_without_an_engine_and_says_what_that_means(self):
        """Re-reading the code is the check; a re-scan is the certification."""
        _, body = frontmatter(os.path.join(AGENTS_DIR, AGENT_NAME))
        assert re.search(r"Verifying a fix \(no engine needed\)", body)
        assert re.search(r"only a fresh Coverity scan re-certifies", body, re.I), \
            "the agent must not claim a fix is certified without a re-scan"

    def test_agent_never_claims_accelerator_output_it_did_not_get(self):
        """If the optional tools were not called, their output cannot be cited."""
        _, body = frontmatter(os.path.join(AGENTS_DIR, AGENT_NAME))
        assert re.search(r"Never invent their output", body), \
            "the agent could attribute invented results to the optional tools"
        assert re.search(r"If you did not call them", body)
        assert re.search(r"do not describe their\s+verdicts", body) or \
               "do not describe their verdicts" in body

    def test_agent_takes_the_two_inputs_the_user_named(self):
        """Report + source code. Both, asked for together, before analysing."""
        _, body = frontmatter(os.path.join(AGENTS_DIR, AGENT_NAME))
        assert re.search(r"Collect the two inputs", body), "no input-collection step"
        assert "source root" in body and "report" in body
        assert re.search(r"one\*\* question|\*\*one\*\* question", body, re.I), \
            "inputs must be requested in a single question, not drip-fed"
        assert re.search(r"Paths in the report are from the build machine", body), \
            "the build-machine-vs-local path mapping is not explained"
        assert re.search(r"corrected root", body), \
            "the commonest setup failure has no recovery procedure"

    def test_agent_carries_the_checker_playbook(self):
        """Each family of checkers needs its own question, or the model guesses."""
        _, body = frontmatter(os.path.join(AGENTS_DIR, AGENT_NAME))
        for family in ("Buffer overflow", "Null pointer", "Integer handling",
                       "Resource leaks", "Error handling", "Control flow"):
            assert family in body, f"no playbook row for {family}"
        assert body.count("|") > 40, "the playbook tables look truncated"

    def test_agent_sets_a_comment_bar_and_a_fix_bar(self):
        """The user's explicit ask: *better* comment and *better* fix."""
        _, body = frontmatter(os.path.join(AGENTS_DIR, AGENT_NAME))
        for heading in ("The disposition comment — the bar", "The proposed fix — the bar"):
            assert heading in body, f"missing quality bar: {heading}"
        for rule in ("The verdict in one sentence", "The evidence",
                     "The consequence", "Banned"):
            assert rule in body, f"comment bar is missing: {rule}"
        for rule in ("Minimal", "Compilable",
                     "the file’s own style" if "the file’s own style" in body
                     else "the file's own style",
                     "With an alternative when there is a real trade-off"):
            assert rule in body, f"fix bar is missing: {rule}"
        assert re.search(r"A wrong fix is worse than a flagged defect", body), \
            "the fix bar must permit honestly declining to patch"

    def test_agent_proposes_by_default_and_edits_only_when_asked(self):
        """Propose-only: a diff in chat, not a changed working tree."""
        _, body = frontmatter(os.path.join(AGENTS_DIR, AGENT_NAME))
        assert re.search(r"Default: propose", body), "no stated default"
        assert re.search(r"opt-in", body, re.I), \
            "editing must be described as opt-in, every time"
        assert re.search(r"one CID per run", body, re.I)
        for trigger in ("apply it", "fix it", "make the change", "patch the file"):
            assert trigger in body, f"the edit trigger {trigger!r} is not spelled out"
        assert '"What\'s the fix?" is a request for the diff' in body, \
            "the commonest ambiguity (asking for the fix vs asking for an edit) is unaddressed"

    def test_agent_reads_the_code_before_judging(self):
        """No engine to lean on: the model must read functions, callers, callees."""
        _, body = frontmatter(os.path.join(AGENTS_DIR, AGENT_NAME))
        assert re.search(r"Read the code yourself", body)
        for item in ("callers", "callee", "invariants", "enclosing function"):
            assert item in body, f"the analysis loop omits {item}"
        assert re.search(r"Quote the lines you rely on", body)
        assert re.search(r"Never invent a CID", body), "no anti-hallucination rule"

    def test_agent_offers_the_improvements_it_advertises(self):
        """The analysis-improvement levers the user can ask for."""
        _, body = frontmatter(os.path.join(AGENTS_DIR, AGENT_NAME))
        for lever in ("self-audit", "exploitability", "sibling", "Clusters"):
            assert lever.lower() in body.lower(), f"missing improvement lever: {lever}"

    @pytest.mark.parametrize("path", AGENT_FILES, ids=os.path.basename)
    def test_frontmatter_is_valid(self, path):
        fm, body = frontmatter(path)
        assert isinstance(fm, dict)
        assert fm.get("description"), "description is the one required field"
        assert len(str(fm["description"])) <= 300, "keep the picker text short"
        assert fm.get("name"), "name drives the picker label"
        assert body.strip(), "an agent without a body is a no-op"
        # 30k is the cloud-agent limit for the prompt body.
        assert len(body) < 30_000

    @pytest.mark.parametrize("path", AGENT_FILES, ids=os.path.basename)
    def test_tools_resolve(self, path):
        fm, _ = frontmatter(path)
        with open(os.path.join(REPO_ROOT, ".vscode", "mcp.json"), encoding="utf-8") as fh:
            mcp_servers = set(json.load(fh)["servers"])
        with open(os.path.join(REPO_ROOT, "vscode-extension", "package.json"),
                  encoding="utf-8") as fh:
            contributed = {t["name"] for t in
                           json.load(fh)["contributes"]["languageModelTools"]}

        for tool in fm.get("tools", []):
            if "/" in tool:
                namespace = tool.split("/")[0]
                assert namespace in mcp_servers | BUILTIN_NAMESPACES, \
                    f"{os.path.basename(path)}: unknown tool namespace '{namespace}'"
            elif tool.startswith("coverityTool_"):
                assert tool in contributed, f"extension does not contribute {tool}"
            else:
                assert tool in BUILTIN_TOOL_NAMES, f"unverified tool name '{tool}'"

    @pytest.mark.parametrize("path", AGENT_FILES, ids=os.path.basename)
    def test_handoff_targets_exist(self, path):
        fm, _ = frontmatter(path)
        for handoff in fm.get("handoffs") or []:
            assert handoff.get("label") and handoff.get("prompt")
            target = os.path.join(AGENTS_DIR, f"{handoff['agent']}.agent.md")
            assert os.path.isfile(target), \
                f"handoff points at a missing agent: {handoff['agent']}"

    def test_agent_covers_every_job_without_losing_a_feature(self):
        """The single file is the product: every capability must stay in it.

        Consolidated agents rot by omission — a job disappears in an edit and the
        uploaded file quietly loses a feature. Note what is *not* required here:
        any mention of the optional engine. The jobs must stand on their own.
        """
        fm, body = frontmatter(os.path.join(AGENTS_DIR, AGENT_NAME))

        for job in ("Job 1 — Triage a report", "Job 2 — Deep dive on one defect",
                    "Job 3 — Fix and verify", "Job 4 — Connect write-back and export",
                    "Job 5 — Diagnose and improve"):
            assert job in body, f"missing {job}"

        # The closed disposition set, in the agent's own vocabulary.
        for rule in ("Needs review", "Bug", "False positive", "Intentional"):
            assert rule in body, f"missing rule/reference: {rule}"

        # The Connect mapping the push tooling uses, verbatim.
        for mapping in ("Fix Required", "False Positive", "Ignore", "Pending",
                        "Undecided"):
            assert mapping in body, f"missing Connect mapping value: {mapping}"

        # Fixing is one CID per run and verified by re-reading the code.
        assert re.search(r"one cid per run", body, re.I), \
            "no single-CID guard in the fix job"
        assert re.search(r"Verifying a fix \(no engine needed\)", body)

        # The editor is needed to apply a fix; read-only must be stated for the rest.
        assert "edit" in (fm.get("tools") or []), "the fix job cannot apply changes"
        assert re.search(r"read-only", body), "the read-only mark on triage is missing"

    def test_agent_treats_an_absent_engine_as_normal(self):
        """No engine must be an ordinary path, not an error state."""
        _, body = frontmatter(os.path.join(AGENTS_DIR, AGENT_NAME))
        assert re.search(r"If the tools are absent", body), \
            "the agent does not say what to do when the optional tools are missing"
        assert re.search(r"just do the analysis yourself", body, re.I), \
            "an absent accelerator must not block the analysis"
        assert "Never invent" in body, "no anti-hallucination rule"


# --------------------------------------------------------------------------- #
# 2. The instructions actually work
# --------------------------------------------------------------------------- #
#: Any shell command in the agent body that runs a script from this repo.
REPO_COMMAND = re.compile(
    r"^\s*python3? (\S*(?:coverity_report_text|vscode_bridge|capabilities)\.py[^\n]*)$")


def repo_commands_in(text: str) -> list[str]:
    """Commands the agent tells a user or model to run, restricted to this repo.

    The agent is model-driven, so its recipes are mostly for *reading* a report.
    Anything it names here must actually work when copied out of the markdown —
    a broken copy-paste costs the user the whole first experience.
    """
    found = []
    for line in text.splitlines():
        match = REPO_COMMAND.match(line)
        if not match:
            continue
        # A shell would treat a trailing "# …" as a comment, so do the same.
        command = re.split(r"\s+#", match.group(1))[0].strip()
        found.append(command)
    return found


class TestInstructionsAreTrue:
    def test_documented_report_commands_actually_run(self, tmp_path):
        """Every repo command in the agent must work as written.

        `<report-folder>` placeholders are substituted with the committed sample
        so the check does not depend on the reader's own Coverity export.
        """
        commands = []
        for path in AGENT_FILES:
            _, body = frontmatter(path)
            commands.extend(repo_commands_in(body))
        assert commands, \
            "the agent documents no readable way to get at a report — the LLM path is broken"

        ran = 0
        for command in commands:
            argv = command.split()
            script = argv[0]
            assert os.path.isfile(os.path.join(REPO_ROOT, script)), \
                f"the agent documents a script that does not exist: {script}"
            args = [a.replace("<report-folder>", SAMPLE_REPORT)
                     .replace("<report>", SAMPLE_REPORT)
                     .replace("<report-folder-or-index.html>", SAMPLE_REPORT)
                    for a in argv[1:]]
            if "<" in " ".join(args):
                continue                        # still a placeholder for the user's own input
            proc = subprocess.run([sys.executable, script, *args], cwd=REPO_ROOT,
                                  capture_output=True, text=True, timeout=600)
            assert proc.returncode == 0, f"{script} {' '.join(args)} failed: {proc.stderr}"
            assert "CID" in proc.stdout or "ok" in proc.stdout, \
                f"{script} {' '.join(args)} produced nothing useful"
            ran += 1
        assert ran >= 1, "no documented command was actually executed"

    def test_the_flat_reading_recipes_work_without_any_packages(self):
        """The dependency-free recipes in the agent are the LLM-only path."""
        _, body = frontmatter(os.path.join(AGENTS_DIR, AGENT_NAME))
        assert "html.unescape" in body, "the stdlib flattening recipe is gone"
        assert "coverity_report_text.py" in body, \
            "the shipped digest script is no longer offered"
        assert "openpyxl" in body, "the spreadsheet conversion recipe is gone"

    def test_triage_agent_sample_expectations_hold(self):
        """The verdicts the optional accelerator promises for the shipped sample.

        These also pin the values the agent's own tests in docs/VSCODE_AGENTS.md
        tell a user to expect, so the two cannot drift apart.
        """
        payload = run_bridge("analyze", "--report", SAMPLE_REPORT, "--src", SAMPLE_SRC)
        by_cid = {d["cid"]: d for d in payload["defects"]}
        assert set(by_cid) == {1001, 1002}
        assert by_cid[1002]["disposition"] == "Bug"
        assert "CWE-416" in by_cid[1002]["comment"]

        if payload["capabilities"]["depth"] == "full":
            # The documented expectation when the full requirements are installed.
            assert by_cid[1001]["disposition"] == "Bug"
            assert by_cid[1001]["confidence"] == pytest.approx(1.0)
            assert by_cid[1002]["confidence"] == pytest.approx(1.0)
            assert payload["summary"]["bug"] == 2

    def test_fix_agent_verification_loop_is_real(self, tmp_path):
        """Apply the engine's proposed fix, re-analyse the same CID, expect a flip.

        This is the claim the fix agent makes to the user ("re-analysis proves
        the change"), and the difference between a verified fix and a hopeful
        one. It runs against a throwaway copy of the sample.
        """
        src = tmp_path / "src"
        report = tmp_path / "report"
        shutil.copytree(SAMPLE_SRC, src)
        shutil.copytree(SAMPLE_REPORT, report)

        before = json.loads(subprocess.run(
            [sys.executable, BRIDGE, "context", "--report", str(report),
             "--cid", "1002", "--src", str(src)],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=600).stdout)["defect"]
        assert before["disposition"] == "Bug"
        fix = before["proposed_fix"]
        assert "NULL" in fix, f"sample fix changed unexpectedly: {fix!r}"

        utils = src / "utils.c"
        source = utils.read_text(encoding="utf-8")
        assert "    free(p);\n    return p;" in source
        utils.write_text(source.replace("    free(p);\n    return p;",
                                        "    free(p);\n    p = NULL;\n    return p;"),
                         encoding="utf-8")

        after = json.loads(subprocess.run(
            [sys.executable, BRIDGE, "context", "--report", str(report),
             "--cid", "1002", "--src", str(src)],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=600).stdout)["defect"]
        assert after["disposition"] != "Bug", \
            "the engine did not recognise its own suggested fix — the fix agent's " \
            "verification step would report a false failure"
        assert after["confidence"] > 0
        assert "line 10" in after["comment"] or "assigned" in after["comment"]

    def test_docs_reference_the_agent_pack(self):
        """The upload pack must be discoverable from the repo entry points."""
        for relative in ("README.md", os.path.join("docs", "VSCODE_INTEGRATION.md")):
            with open(os.path.join(REPO_ROOT, relative), encoding="utf-8") as fh:
                text = fh.read()
            assert ".github/agents" in text, f"{relative} does not mention the agents"
        with open(os.path.join(REPO_ROOT, "docs", "VSCODE_AGENTS.md"),
                  encoding="utf-8") as fh:
            guide = fh.read()
        assert AGENT_NAME in guide, "the runbook does not name the agent file"
        # The guide must actually walk the reader through VS Code testing.
        for step in ("Ctrl+Shift+P", "Agent mode", "MCP: List Servers",
                     "F5", ".vsix", "Pass criteria"):
            assert step in guide, f"the guide is missing the '{step}' step"


# --------------------------------------------------------------------------- #
# 3. The "any agent can use it" mechanisms
#
# Coverity is a capability first: the tools are published to every agent, and
# these two files are what make an arbitrary agent use them correctly. If they
# rot, agents silently stop reaching for the engine and start guessing.
# --------------------------------------------------------------------------- #
INSTRUCTIONS = os.path.join(REPO_ROOT, ".github", "instructions",
                            "coverity-findings.instructions.md")
TOOLSET_TEMPLATE = os.path.join(REPO_ROOT, "docs", "coverity.toolsets.jsonc")

#: The MCP tools. The extension exposes five of these as LM tools; the export
#: tool is MCP/CLI only (a language-model tool that writes files would be odd).
MCP_TOOLS = (
    "coverity_capabilities", "coverity_list_defects", "coverity_analyze_defect",
    "coverity_triage_report", "coverity_export_results", "coverity_source_context",
)
EXTENSION_TOOLS = (
    "coverityTool_capabilities", "coverityTool_listDefects",
    "coverityTool_analyzeDefect", "coverityTool_triageReport",
    "coverityTool_sourceContext",
)


class TestInstructionsForAnyAgent:
    def test_exists_with_path_scoped_frontmatter(self):
        assert os.path.isfile(INSTRUCTIONS), \
            "without an instructions file, arbitrary agents do not know the tools exist"
        fm, body = frontmatter(INSTRUCTIONS)
        assert fm.get("description"), "description is shown on hover in chat"
        apply_to = fm.get("applyTo") or fm.get("applyto")
        assert apply_to, "path-scoped instructions need an applyTo glob"
        for pattern in ("*.c", "*.cpp", "*.h"):
            assert pattern in apply_to, f"applyTo does not cover {pattern} sources"
        assert body.strip()

    def test_teaches_the_rules_the_tools_cannot_enforce(self):
        _, body = frontmatter(INSTRUCTIONS)
        # Normalise markdown emphasis so the check tests the rule, not its markup.
        flat = re.sub(r"\s+", " ", body.replace("`", "").replace("*", "")).lower()
        for rule in ("never invent", "src_root", "needs review is not a verdict",
                     "re-analyse", "credentials"):
            assert rule in flat, f"instruction missing: {rule}"

    def test_names_the_tools_an_agent_should_look_for(self):
        _, body = frontmatter(INSTRUCTIONS)
        for tool in MCP_TOOLS:
            assert tool in body, f"instructions never mention {tool}"
        for tool in EXTENSION_TOOLS:
            assert tool in body, f"instructions never mention {tool}"

    def test_points_at_the_analyzer_agent(self):
        _, body = frontmatter(INSTRUCTIONS)
        assert AGENT_NAME in body, \
            "the instructions should tell an agent where the deeper analysis lives"

    def test_does_not_claim_a_persona_is_required(self):
        _, body = frontmatter(INSTRUCTIONS)
        assert re.search(r"do not\s+require it|any agent", body, re.I), \
            "instructions must not imply a persona switch is needed"


class TestToolSetTemplate:
    @staticmethod
    def _payload():
        """Parse the template the way a user would paste it (strip // lines)."""
        text = open(TOOLSET_TEMPLATE, encoding="utf-8").read()
        stripped = "\n".join(line for line in text.splitlines()
                             if not line.strip().startswith("//"))
        return json.loads(stripped)

    def test_template_is_valid_and_named_coverity(self):
        data = self._payload()
        assert "coverity" in data, "the tool set must be referenceable as #coverity"
        entry = data["coverity"]
        assert entry.get("description") and entry.get("tools")

    def test_tool_names_follow_the_server_slash_tool_form(self):
        """VS Code qualifies MCP tools as <server>/<tool>."""
        mcp_servers = set(json.load(
            open(os.path.join(REPO_ROOT, ".vscode", "mcp.json"), encoding="utf-8"))["servers"])
        tools = self._payload()["coverity"]["tools"]
        mcp_entries = [t for t in tools if t.split("/")[0] in mcp_servers]
        assert len(mcp_entries) == len(MCP_TOOLS), \
            f"expected all {len(MCP_TOOLS)} Coverity MCP tools, found {mcp_entries}"
        for tool in mcp_entries:
            server, _, name = tool.partition("/")
            assert name in MCP_TOOLS, f"{tool} is not one of the server's tools"

    def test_declares_that_it_is_a_user_profile_file(self):
        """Tool sets are not workspace files — saying otherwise wastes user time."""
        text = open(TOOLSET_TEMPLATE, encoding="utf-8").read()
        assert "user profile" in text.lower()
        assert "Configure Tool Sets" in text, "no in-product path to install it"
