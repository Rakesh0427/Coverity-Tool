"""Tests for coverity_mcp_server.py — the MCP (stdio) agent interface.

The server is a protocol adapter: these tests check the wire behaviour an MCP
client depends on (handshake, tool catalogue, tool results, error handling)
and that a failed tool call comes back in-band rather than killing the session.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(REPO_ROOT, "coverity_mcp_server.py")
SAMPLE_REPORT = os.path.join(REPO_ROOT, "docs", "sample_report")
SAMPLE_SRC = os.path.join(REPO_ROOT, "docs")

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

EXPECTED_TOOLS = {
    "coverity_capabilities",
    "coverity_list_defects",
    "coverity_analyze_defect",
    "coverity_triage_report",
    "coverity_export_results",
    "coverity_source_context",
}

#: Tools that only read. ``coverity_export_results`` writes a CSV for the
#: reviewer, so it is the one tool that must not claim to be read-only.
WRITE_TOOLS = {"coverity_export_results"}


def speak(frames, env_overrides=None, timeout=300):
    """Run the server over stdio and return the parsed responses."""
    env = dict(os.environ)
    env.update({
        "COVERITY_REPORT": SAMPLE_REPORT,
        "COVERITY_SRC_ROOT": SAMPLE_SRC,
        "COVERITY_MCP_MAX_RESULTS": "10",
    })
    env.update(env_overrides or {})
    payload = "\n".join(json.dumps(frame) for frame in frames) + "\n"
    proc = subprocess.run([sys.executable, SERVER], input=payload,
                          capture_output=True, text=True, timeout=timeout,
                          cwd=REPO_ROOT, env=env)
    responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    return proc, responses


def handshake(extra=None, env_overrides=None):
    frames = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
    ]
    frames.extend(extra or [])
    proc, responses = speak(frames, env_overrides=env_overrides)
    by_id = {r.get("id"): r for r in responses}
    return proc, by_id


def call(tool, arguments, msg_id=2):
    return {"jsonrpc": "2.0", "id": msg_id, "method": "tools/call",
            "params": {"name": tool, "arguments": arguments}}


def text_of(response):
    return "\n".join(part["text"] for part in response["result"]["content"])


class TestHandshake:
    def test_initialize_echoes_supported_protocol(self):
        _, by_id = handshake()
        result = by_id[1]["result"]
        assert result["protocolVersion"] == "2025-06-18"
        assert result["serverInfo"]["name"] == "coverity-tool"
        assert "tools" in result["capabilities"]

    def test_notifications_get_no_response(self):
        proc, responses = speak([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "method": "notifications/cancelled"},
        ])
        assert proc.returncode == 0
        assert len(responses) == 1

    def test_unknown_protocol_version_still_answers(self):
        _, by_id = handshake()
        _, responses = speak([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "1999-01-01"}}])
        assert responses[0]["result"]["protocolVersion"] == "2025-06-18"

    def test_ping(self):
        _, by_id = handshake([{"jsonrpc": "2.0", "id": 9, "method": "ping"}])
        assert by_id[9]["result"] == {}


class TestToolCatalogue:
    def test_tools_list_advertises_expected_tools(self):
        _, by_id = handshake([{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}])
        tools = by_id[2]["result"]["tools"]
        assert {t["name"] for t in tools} == EXPECTED_TOOLS
        for tool in tools:
            assert tool["description"].strip()
            assert tool["inputSchema"]["type"] == "object"
            assert tool["annotations"]["readOnlyHint"] is (
                tool["name"] not in WRITE_TOOLS), (
                f"{tool['name']} advertises the wrong readOnlyHint — a tool that "
                "writes a file must not claim to be read-only")

    def test_list_tools_flag_works_without_a_client(self):
        proc = subprocess.run([sys.executable, SERVER, "--list-tools"],
                              capture_output=True, text=True, cwd=REPO_ROOT)
        payload = json.loads(proc.stdout)
        assert {t["name"] for t in payload["tools"]} == EXPECTED_TOOLS


class TestToolCalls:
    def test_capabilities(self):
        _, by_id = handshake([call("coverity_capabilities", {})])
        response = by_id[2]
        assert response["result"]["isError"] is False
        assert "Analysis depth" in text_of(response)

    def test_list_defects_uses_server_defaults(self):
        _, by_id = handshake([call("coverity_list_defects", {})])
        text = text_of(by_id[2])
        assert "1001" in text and "1002" in text
        assert "BUFFER_SIZE" in text

    def test_analyze_defect_returns_verdict_and_fix(self):
        _, by_id = handshake([call("coverity_analyze_defect", {"cid": 1002})])
        response = by_id[2]
        assert response["result"]["isError"] is False
        text = text_of(response)
        assert "USE_AFTER_FREE" in text
        assert "Disposition:** Bug" in text
        assert "Suggested fix" in text
        # The structured JSON block travels with the prose so an agent can parse.
        assert '"disposition"' in text

    def test_source_context(self):
        _, by_id = handshake([call("coverity_source_context", {"cid": 1001})])
        text = text_of(by_id[2])
        assert "strncpy" in text

    def test_triage_report_writes_cache_and_summarises(self, tmp_path):
        _, by_id = handshake(
            [call("coverity_triage_report", {"limit": 2})],
            env_overrides={"COVERITY_MCP_OUTPUT_DIR": str(tmp_path)})
        response = by_id[2]
        assert response["result"]["isError"] is False
        text = text_of(response)
        assert "2 defects" in text
        cached = list(tmp_path.glob("*.triage.json"))
        assert len(cached) == 1
        document = json.loads(cached[0].read_text())
        assert document["summary"]["total"] == 2

    def test_triage_result_carries_the_analysis_depth_structurally(self):
        """An agent must always be able to see how strong the analysis was.

        The prose only mentions the depth when it is degraded (no noise at full
        strength), so the structured payload is what agents and their
        instructions rely on — it has to be there either way.
        """
        _, by_id = handshake([call("coverity_triage_report", {"limit": 2})])
        blocks = by_id[2]["result"]["content"]
        assert len(blocks) >= 2, "the machine-readable block is missing"
        payload = json.loads(blocks[1]["text"].split("```json")[1].split("```")[0])
        assert payload["capabilities"]["depth"] in ("full", "partial", "minimal")
        assert isinstance(payload["capabilities"]["missing"], list)
        if payload["capabilities"]["depth"] != "full":
            assert payload["capabilities"]["missing"], \
                "a degraded depth must name the missing backends"

    def test_bad_arguments_are_in_band_errors(self):
        _, by_id = handshake([
            call("coverity_analyze_defect", {"cid": "not-a-number"}, msg_id=2),
            call("coverity_list_defects", {"report": "/no/such/report.html"}, msg_id=3),
        ])
        for msg_id in (2, 3):
            result = by_id[msg_id]["result"]
            assert result["isError"] is True
            assert result["content"][0]["text"]
        assert "integer" in text_of(by_id[2])

    def test_unknown_tool_is_a_jsonrpc_error_not_a_crash(self):
        _, by_id = handshake([call("coverity_nope", {})])
        assert by_id[2]["error"]["code"] == -32602
        assert "Unknown tool" in by_id[2]["error"]["message"]

    def test_unknown_method_is_jsonrpc_error(self):
        _, by_id = handshake([{"jsonrpc": "2.0", "id": 2, "method": "does/not/exist"}])
        assert by_id[2]["error"]["code"] == -32601

    def test_malformed_json_reports_parse_error_and_keeps_serving(self):
        frames = [
            "this is not json",
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}),
        ]
        proc = subprocess.run([sys.executable, SERVER], input="\n".join(frames) + "\n",
                              capture_output=True, text=True, cwd=REPO_ROOT, timeout=120)
        responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        assert responses[0]["error"]["code"] == -32700
        assert responses[1]["result"] == {}


class TestTransportHygiene:
    def test_stdout_only_ever_contains_json(self):
        """Every stdout line must parse — nothing may leak from the analysers."""
        proc, _ = handshake([
            call("coverity_triage_report", {"limit": 2}),
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        ])
        for line in proc.stdout.splitlines():
            if line.strip():
                json.loads(line)

    def test_progress_and_errors_go_to_stderr(self):
        proc, _ = handshake([
            call("coverity_analyze_defect", {"cid": 999999}, msg_id=2),
        ])
        assert proc.returncode == 0
        assert "Analysis failed" in proc.stdout or "not found" in proc.stdout
