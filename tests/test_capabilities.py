"""Tests for the runtime capability probe.

Optional backends are imported behind bare ``except ImportError`` handlers, so
a machine with no libclang/z3/tree-sitter silently produced far more
'Needs review' rows than a fully-provisioned one -- with nothing in the output
to distinguish the two.  These tests pin the reporting contract that makes a
degraded run visible.
"""
import sys

import capabilities


def setup_function(_fn):
    capabilities.reset_cache()


def teardown_function(_fn):
    capabilities.reset_cache()


def test_probe_returns_every_backend():
    caps = capabilities.probe()
    for key in ("tree_sitter", "libclang", "z3", "flow", "cppcheck"):
        assert key in caps, f"{key} missing from capability probe"


def test_probe_is_cached():
    assert capabilities.probe() is capabilities.probe()


def test_reset_cache_forces_a_reprobe():
    first = capabilities.probe()
    capabilities.reset_cache()
    assert capabilities.probe() is not first


def test_every_capability_reports_a_reason():
    """An unavailable backend must say why, not just fail silently."""
    for cap in capabilities.probe().values():
        assert cap.detail, f"{cap.key} reported no detail"
        assert cap.status in ("OK", "MISSING", "disabled")


def test_depth_is_a_known_label():
    assert capabilities.analysis_depth() in (
        capabilities.DEPTH_FULL,
        capabilities.DEPTH_PARTIAL,
        capabilities.DEPTH_MINIMAL,
    )


def test_banner_lists_backends_and_depth():
    banner = capabilities.format_banner()
    assert "Analysis backends:" in banner
    assert "analysis depth:" in banner
    assert "tree-sitter" in banner


def test_depth_note_names_missing_backends(monkeypatch):
    """The note must name what was missing so the verdict can be judged."""
    fake = dict(capabilities.probe())
    fake["z3"] = capabilities.Capability(
        "z3", "z3 (SMT path proofs)", False, "import failed", True)
    monkeypatch.setattr(capabilities, "_CACHE", fake)
    note = capabilities.depth_note()
    assert "z3 (SMT path proofs)" in note
    assert "Reduced analysis" in note


def test_depth_note_is_empty_at_full_strength(monkeypatch):
    full = {
        k: c._replace(available=True, detail="ok")
        for k, c in capabilities.probe().items()
    }
    monkeypatch.setattr(capabilities, "_CACHE", full)
    assert capabilities.analysis_depth() == capabilities.DEPTH_FULL
    assert capabilities.depth_note() == ""


def test_missing_ast_backend_means_minimal_depth(monkeypatch):
    fake = dict(capabilities.probe())
    fake["tree_sitter"] = capabilities.Capability(
        "tree_sitter", "tree-sitter (AST)", False, "import failed", True)
    monkeypatch.setattr(capabilities, "_CACHE", fake)
    assert capabilities.analysis_depth() == capabilities.DEPTH_MINIMAL
    assert "regex matching without an AST" in capabilities.depth_note()


def test_cppcheck_absence_does_not_reduce_depth(monkeypatch):
    """cppcheck is corroboration only; it must not be treated as critical."""
    fake = {
        k: c._replace(available=True, detail="ok")
        for k, c in capabilities.probe().items()
    }
    fake["cppcheck"] = capabilities.Capability(
        "cppcheck", "cppcheck (corroboration)", False, "disabled by env", False)
    monkeypatch.setattr(capabilities, "_CACHE", fake)
    assert capabilities.analysis_depth() == capabilities.DEPTH_FULL


def _fake_cppcheck_bin(monkeypatch, path="/usr/bin/cppcheck"):
    """Point find_cppcheck_bin at a fake binary without needing cppcheck."""
    monkeypatch.setattr(capabilities, "find_cppcheck_bin", lambda: path)


def test_cppcheck_is_enabled_by_default(monkeypatch):
    """cppcheck is corroboration-only and ON by default; the per-file cache
    bounds the cost, so no env flag is required to use it."""
    monkeypatch.delenv("COVERITY_ENABLE_SEMGREP", raising=False)
    monkeypatch.delenv("COVERITY_DISABLE_SEMGREP", raising=False)
    monkeypatch.delenv("COVERITY_DISABLE_CPPCHECK", raising=False)
    _fake_cppcheck_bin(monkeypatch)

    class _R:
        returncode = 0
        stdout = "Cppcheck 2.17.1\n"

    monkeypatch.setattr(capabilities.subprocess, "run", lambda *a, **k: _R())
    caps = capabilities.probe(force=True)
    assert caps["cppcheck"].available is True


def test_cppcheck_disable_flag_turns_it_off(monkeypatch):
    """COVERITY_DISABLE_CPPCHECK=1 must be able to opt out."""
    monkeypatch.delenv("COVERITY_ENABLE_SEMGREP", raising=False)
    monkeypatch.delenv("COVERITY_DISABLE_SEMGREP", raising=False)
    monkeypatch.setenv("COVERITY_DISABLE_CPPCHECK", "1")
    _fake_cppcheck_bin(monkeypatch)

    class _R:
        returncode = 0
        stdout = "Cppcheck 2.17.1\n"

    monkeypatch.setattr(capabilities.subprocess, "run", lambda *a, **k: _R())
    caps = capabilities.probe(force=True)
    assert caps["cppcheck"].available is False
    assert "COVERITY_DISABLE_CPPCHECK" in caps["cppcheck"].detail


def test_cppcheck_timeout_reports_clearly_not_as_a_crash(monkeypatch):
    """A slow cppcheck start is a timeout, not a crash: the detail must read
    'timed out' (with guidance), never 'probe raised'."""
    monkeypatch.delenv("COVERITY_ENABLE_SEMGREP", raising=False)
    monkeypatch.delenv("COVERITY_DISABLE_SEMGREP", raising=False)
    monkeypatch.delenv("COVERITY_DISABLE_CPPCHECK", raising=False)
    monkeypatch.delenv("COVERITY_CPPCHECK_PROBE_TIMEOUT", raising=False)
    monkeypatch.delenv("COVERITY_SEMGREP_PROBE_TIMEOUT", raising=False)
    _fake_cppcheck_bin(monkeypatch)

    def _slow(*_a, **kw):
        raise capabilities.subprocess.TimeoutExpired(
            "cppcheck", timeout=kw.get("timeout", 10))

    monkeypatch.setattr(capabilities.subprocess, "run", _slow)
    cap = capabilities._probe_cppcheck()
    assert cap.available is False
    assert "timed out" in cap.detail
    assert "COVERITY_CPPCHECK_PROBE_TIMEOUT" in cap.detail
    assert "probe raised" not in cap.detail


def test_cppcheck_nonzero_exit_reports_returncode(monkeypatch):
    monkeypatch.delenv("COVERITY_ENABLE_SEMGREP", raising=False)
    monkeypatch.delenv("COVERITY_DISABLE_SEMGREP", raising=False)
    monkeypatch.delenv("COVERITY_DISABLE_CPPCHECK", raising=False)
    monkeypatch.delenv("COVERITY_CPPCHECK_PROBE_TIMEOUT", raising=False)
    monkeypatch.delenv("COVERITY_SEMGREP_PROBE_TIMEOUT", raising=False)
    _fake_cppcheck_bin(monkeypatch)

    class _R:
        returncode = 2
        stdout = ""

    monkeypatch.setattr(capabilities.subprocess, "run", lambda *a, **k: _R())
    cap = capabilities._probe_cppcheck()
    assert cap.available is False
    assert "exit" in cap.detail and "2" in cap.detail


def test_cppcheck_missing_binary_reports_install_hint(monkeypatch):
    """No binary anywhere must explain how to get one, not crash."""
    monkeypatch.delenv("COVERITY_ENABLE_SEMGREP", raising=False)
    monkeypatch.delenv("COVERITY_DISABLE_SEMGREP", raising=False)
    monkeypatch.delenv("COVERITY_DISABLE_CPPCHECK", raising=False)
    _fake_cppcheck_bin(monkeypatch, path=None)
    cap = capabilities._probe_cppcheck()
    assert cap.available is False
    assert "pip install cppcheck" in cap.detail or "PATH" in cap.detail


def test_cppcheck_probe_timeout_default(monkeypatch):
    monkeypatch.delenv("COVERITY_CPPCHECK_PROBE_TIMEOUT", raising=False)
    monkeypatch.delenv("COVERITY_SEMGREP_PROBE_TIMEOUT", raising=False)
    assert capabilities.cppcheck_probe_timeout() == \
        capabilities.CPPCHECK_PROBE_TIMEOUT_DEFAULT


def test_cppcheck_probe_timeout_env_override(monkeypatch):
    monkeypatch.setenv("COVERITY_CPPCHECK_PROBE_TIMEOUT", "12.5")
    assert capabilities.cppcheck_probe_timeout() == 12.5


def test_cppcheck_probe_timeout_legacy_env_still_works(monkeypatch):
    """Old COVERITY_SEMGREP_PROBE_TIMEOUT scripts keep working."""
    monkeypatch.setenv("COVERITY_SEMGREP_PROBE_TIMEOUT", "7.5")
    assert capabilities.cppcheck_probe_timeout() == 7.5


def test_cppcheck_probe_timeout_invalid_env_falls_back(monkeypatch):
    monkeypatch.setenv("COVERITY_CPPCHECK_PROBE_TIMEOUT", "not-a-number")
    assert capabilities.cppcheck_probe_timeout() == \
        capabilities.CPPCHECK_PROBE_TIMEOUT_DEFAULT


def test_cppcheck_legacy_semgrep_disable_still_disables(monkeypatch):
    """COVERITY_DISABLE_SEMGREP=1 keeps working for old scripts."""
    monkeypatch.delenv("COVERITY_ENABLE_SEMGREP", raising=False)
    monkeypatch.delenv("COVERITY_DISABLE_CPPCHECK", raising=False)
    monkeypatch.setenv("COVERITY_DISABLE_SEMGREP", "1")
    _fake_cppcheck_bin(monkeypatch)

    class _R:
        returncode = 0
        stdout = "Cppcheck 2.17.1\n"

    monkeypatch.setattr(capabilities.subprocess, "run", lambda *a, **k: _R())
    caps = capabilities.probe(force=True)
    assert caps["cppcheck"].available is False
    assert "COVERITY_DISABLE_SEMGREP" in caps["cppcheck"].detail


def test_cppcheck_legacy_enable_zero_still_disables(monkeypatch):
    """COVERITY_ENABLE_SEMGREP=0 keeps working for old scripts."""
    monkeypatch.setenv("COVERITY_ENABLE_SEMGREP", "0")
    monkeypatch.delenv("COVERITY_DISABLE_SEMGREP", raising=False)
    monkeypatch.delenv("COVERITY_DISABLE_CPPCHECK", raising=False)
    _fake_cppcheck_bin(monkeypatch)

    class _R:
        returncode = 0
        stdout = "Cppcheck 2.17.1\n"

    monkeypatch.setattr(capabilities.subprocess, "run", lambda *a, **k: _R())
    caps = capabilities.probe(force=True)
    assert caps["cppcheck"].available is False


def test_find_cppcheck_bin_env_override(monkeypatch, tmp_path):
    exe = tmp_path / "cppcheck"
    exe.write_text("#!/bin/sh\necho ok\n")
    monkeypatch.setenv("COVERITY_CPPCHECK_BIN", str(exe))
    assert capabilities.find_cppcheck_bin() == str(exe)


def test_find_cppcheck_bin_env_override_broken_returns_none(monkeypatch):
    """A broken explicit override must not silently fall back to PATH."""
    monkeypatch.setenv("COVERITY_CPPCHECK_BIN", "/nonexistent/cppcheck")
    monkeypatch.setattr(capabilities.shutil, "which",
                        lambda name: "/usr/bin/cppcheck")
    assert capabilities.find_cppcheck_bin() is None


def test_find_cppcheck_bin_path_fallback(monkeypatch):
    monkeypatch.delenv("COVERITY_CPPCHECK_BIN", raising=False)
    monkeypatch.setattr(
        capabilities.shutil, "which",
        lambda name: "/usr/bin/cppcheck" if name == "cppcheck" else None)
    assert capabilities.find_cppcheck_bin() == "/usr/bin/cppcheck"


def test_find_cppcheck_bin_wheel_fallback(monkeypatch, tmp_path):
    """When nothing else exists, the pip wheel's bundled binary is used."""
    import types
    cc_dir = tmp_path / "Cppcheck"
    cc_dir.mkdir()
    exe = cc_dir / "cppcheck"
    exe.write_text("#!/bin/sh\necho ok\n")
    fake = types.ModuleType("cppcheck")
    fake.get_cppcheck_dir = lambda: cc_dir
    monkeypatch.setitem(sys.modules, "cppcheck", fake)
    monkeypatch.delenv("COVERITY_CPPCHECK_BIN", raising=False)
    monkeypatch.setattr(capabilities.shutil, "which", lambda name: None)
    assert capabilities.find_cppcheck_bin() == str(exe)


def test_a_crashing_probe_does_not_break_the_run(monkeypatch):
    def _boom():
        raise RuntimeError("backend exploded")

    monkeypatch.setattr(capabilities, "_PROBES", (_boom,))
    caps = capabilities.probe(force=True)
    assert caps  # the run continues
    assert any("probe crashed" in c.detail for c in caps.values())
