"""Unit tests for the cppcheck corroboration backend in heuristic_analyzer.

cppcheck is the local, fully-offline corroboration backend.  These tests pin
the CLI contract (the pipe-separated ``--template`` output format), the
per-file cache and the +/-3-line proximity window without requiring a real
cppcheck install — subprocess.run is faked.
"""
import subprocess

import pytest

import heuristic_analyzer as ha


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    """Reset module-level cache/availability between tests and clear env."""
    ha._CPPCHECK_AVAILABLE = None
    ha._CPPCHECK_CACHE.clear()
    monkeypatch.delenv("COVERITY_DISABLE_CPPCHECK", raising=False)
    monkeypatch.delenv("COVERITY_CPPCHECK_TIMEOUT", raising=False)
    monkeypatch.delenv("COVERITY_CPPCHECK_ARGS", raising=False)
    yield
    ha._CPPCHECK_AVAILABLE = None
    ha._CPPCHECK_CACHE.clear()


def _enable_backend(monkeypatch):
    monkeypatch.setattr(ha, "_cppcheck_binary", lambda: "/usr/bin/cppcheck")
    monkeypatch.setattr(ha, "_cppcheck_enabled", lambda: True)


def _fake_run(monkeypatch, stdout_text, stderr_text=""):
    calls = []

    def _run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        class _R:
            returncode = 0
        _R.stdout = stdout_text
        _R.stderr = stderr_text
        return _R()

    monkeypatch.setattr(ha.subprocess, "run", _run)
    return calls


def test_returns_check_id_near_defect_line(monkeypatch, tmp_path):
    """A finding within 3 lines of the defect line corroborates it."""
    src = tmp_path / "sample.c"
    src.write_text("int x;\n" * 30)
    _enable_backend(monkeypatch)
    calls = _fake_run(monkeypatch, (
        "8|bufferAccessOutOfBounds|error|Buffer is accessed out of bounds: dst\n"
        "19|doubleFree|error|Memory pointed to by 'p' is freed twice.\n"
        "Checking sample.c ...\n"  # progress noise must be ignored
    ))
    assert ha._run_cppcheck_check(str(src), defect_line=8, checker="BUFFER_SIZE") \
        == "bufferAccessOutOfBounds"
    assert ha._run_cppcheck_check(str(src), defect_line=19, checker="BUFFER_SIZE") \
        == "doubleFree"
    # Way outside the window → no corroboration
    assert ha._run_cppcheck_check(str(src), defect_line=100, checker="BUFFER_SIZE") \
        is None
    # CLI contract: one run, offline, template-based, no registry config
    cmd, kwargs = calls[0]
    assert cmd[0] == "/usr/bin/cppcheck"
    assert cmd[1].startswith("--enable=")
    assert cmd[-2].startswith("--template=")
    assert cmd[-1] == str(src)
    assert "p/c-and-cpp" not in " ".join(cmd)
    assert kwargs["timeout"] == 15.0
    # progress-noise line must not have been parsed as a hit
    assert ha._CPPCHECK_CACHE[str(src)] == [(8, "bufferAccessOutOfBounds"),
                                            (19, "doubleFree")]


def test_cache_runs_cppcheck_once_per_file(monkeypatch, tmp_path):
    src = tmp_path / "sample.c"
    src.write_text("int x;\n" * 30)
    _enable_backend(monkeypatch)
    calls = _fake_run(monkeypatch, "8|bufferAccessOutOfBounds|error|msg\n")
    ha._run_cppcheck_check(str(src), defect_line=8, checker="BUFFER_SIZE")
    ha._run_cppcheck_check(str(src), defect_line=9, checker="BUFFER_SIZE")
    ha._run_cppcheck_check(str(src), defect_line=10, checker="BUFFER_SIZE")
    assert len(calls) == 1


def test_disable_flag_skips_subprocess(monkeypatch, tmp_path):
    """COVERITY_DISABLE_CPPCHECK=1 turns corroboration off entirely."""
    src = tmp_path / "sample.c"
    src.write_text("int x;\n")
    monkeypatch.setenv("COVERITY_DISABLE_CPPCHECK", "1")
    calls = _fake_run(monkeypatch, "1|doubleFree|error|msg\n")
    assert ha._run_cppcheck_check(str(src), defect_line=1, checker="BUFFER_SIZE") \
        is None
    assert calls == []


def test_timeout_caches_empty_and_does_not_retry(monkeypatch, tmp_path):
    """A timed-out scan must not break the run and must not be retried."""
    src = tmp_path / "sample.c"
    src.write_text("int x;\n" * 30)
    _enable_backend(monkeypatch)
    calls = []

    def _slow(*_a, **kwargs):
        calls.append(1)
        raise subprocess.TimeoutExpired("cppcheck", timeout=kwargs["timeout"])

    monkeypatch.setattr(ha.subprocess, "run", _slow)
    assert ha._run_cppcheck_check(str(src), defect_line=8, checker="BUFFER_SIZE") \
        is None
    assert ha._run_cppcheck_check(str(src), defect_line=8, checker="BUFFER_SIZE") \
        is None
    assert len(calls) == 1  # cached after the failure


def test_malformed_output_lines_are_ignored(monkeypatch, tmp_path):
    src = tmp_path / "sample.c"
    src.write_text("int x;\n" * 30)
    _enable_backend(monkeypatch)
    _fake_run(monkeypatch, (
        "not a template line\n"
        "8|bufferAccessOutOfBounds|error|message with | pipe inside\n"
        "9|onlyTwoFields\n"
        "10|bufferAccessOutOfBounds|error|\n"
    ))
    # The message field legitimately contains '|'; parsing splits only the
    # first three fields, so this hit must still be found at line 8.
    assert ha._run_cppcheck_check(str(src), defect_line=8, checker="BUFFER_SIZE") \
        == "bufferAccessOutOfBounds"
    assert ha._CPPCHECK_CACHE[str(src)] == [
        (8, "bufferAccessOutOfBounds"), (10, "bufferAccessOutOfBounds")]


def test_findings_on_stderr_are_parsed_too(monkeypatch, tmp_path):
    """Real cppcheck writes template findings to stderr; both streams parse."""
    src = tmp_path / "sample.c"
    src.write_text("int x;\n" * 30)
    _enable_backend(monkeypatch)

    def _run(cmd, **kwargs):
        class _R:
            returncode = 0
            stdout = "Checking sample.c ...\n"
            stderr = "8|bufferAccessOutOfBounds|error|Buffer is accessed out of bounds: dst\n"
        return _R()

    monkeypatch.setattr(ha.subprocess, "run", _run)
    assert ha._run_cppcheck_check(str(src), defect_line=8, checker="BUFFER_SIZE") \
        == "bufferAccessOutOfBounds"
    # progress text on stdout must not be mistaken for a finding
    assert ha._CPPCHECK_CACHE[str(src)] == [(8, "bufferAccessOutOfBounds")]


def test_custom_timeout_and_extra_args_env(monkeypatch, tmp_path):
    """COVERITY_CPPCHECK_TIMEOUT and COVERITY_CPPCHECK_ARGS are honoured."""
    src = tmp_path / "sample.c"
    src.write_text("int x;\n" * 30)
    _enable_backend(monkeypatch)
    monkeypatch.setenv("COVERITY_CPPCHECK_TIMEOUT", "3.5")
    monkeypatch.setenv("COVERITY_CPPCHECK_ARGS", "--check-level=exhaustive --std=c++17")
    calls = _fake_run(monkeypatch, "8|doubleFree|error|msg\n")
    ha._run_cppcheck_check(str(src), defect_line=8, checker="BUFFER_SIZE")
    cmd, kwargs = calls[0]
    assert kwargs["timeout"] == 3.5
    assert "--check-level=exhaustive" in cmd
    assert "--std=c++17" in cmd
