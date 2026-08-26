"""Tests for the runtime capability probe.

Optional backends are imported behind bare ``except ImportError`` handlers, so
a machine with no libclang/z3/tree-sitter silently produced far more
'Needs review' rows than a fully-provisioned one -- with nothing in the output
to distinguish the two.  These tests pin the reporting contract that makes a
degraded run visible.
"""
import capabilities


def setup_function(_fn):
    capabilities.reset_cache()


def teardown_function(_fn):
    capabilities.reset_cache()


def test_probe_returns_every_backend():
    caps = capabilities.probe()
    for key in ("tree_sitter", "libclang", "z3", "flow", "semgrep"):
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


def test_semgrep_absence_does_not_reduce_depth(monkeypatch):
    """semgrep is corroboration only; it must not be treated as critical."""
    fake = {
        k: c._replace(available=True, detail="ok")
        for k, c in capabilities.probe().items()
    }
    fake["semgrep"] = capabilities.Capability(
        "semgrep", "semgrep (corroboration)", False, "disabled by env", False)
    monkeypatch.setattr(capabilities, "_CACHE", fake)
    assert capabilities.analysis_depth() == capabilities.DEPTH_FULL


def _fake_semgrep_path(monkeypatch):
    """Make shutil.which find semgrep without needing it installed."""
    monkeypatch.setattr(
        capabilities.shutil, "which",
        lambda name: "/usr/bin/semgrep" if name == "semgrep" else None)


def test_semgrep_is_enabled_by_default(monkeypatch):
    """semgrep is corroboration-only and now ON by default; the per-file cache
    bounds the cost, so no env flag is required to use it."""
    monkeypatch.delenv("COVERITY_ENABLE_SEMGREP", raising=False)
    monkeypatch.delenv("COVERITY_DISABLE_SEMGREP", raising=False)
    _fake_semgrep_path(monkeypatch)

    class _R:
        returncode = 0
        stdout = "1.45.0\n"

    monkeypatch.setattr(capabilities.subprocess, "run", lambda *a, **k: _R())
    caps = capabilities.probe(force=True)
    assert caps["semgrep"].available is True


def test_semgrep_disable_flag_turns_it_off(monkeypatch):
    """COVERITY_DISABLE_SEMGREP=1 must be able to opt out."""
    monkeypatch.delenv("COVERITY_ENABLE_SEMGREP", raising=False)
    monkeypatch.setenv("COVERITY_DISABLE_SEMGREP", "1")
    _fake_semgrep_path(monkeypatch)

    class _R:
        returncode = 0
        stdout = "1.45.0\n"

    monkeypatch.setattr(capabilities.subprocess, "run", lambda *a, **k: _R())
    caps = capabilities.probe(force=True)
    assert caps["semgrep"].available is False
    assert "COVERITY_DISABLE_SEMGREP" in caps["semgrep"].detail


def test_semgrep_legacy_enable_zero_still_disables(monkeypatch):
    """COVERITY_ENABLE_SEMGREP=0 keeps working for old scripts."""
    monkeypatch.setenv("COVERITY_ENABLE_SEMGREP", "0")
    monkeypatch.delenv("COVERITY_DISABLE_SEMGREP", raising=False)
    _fake_semgrep_path(monkeypatch)

    class _R:
        returncode = 0
        stdout = "1.45.0\n"

    monkeypatch.setattr(capabilities.subprocess, "run", lambda *a, **k: _R())
    caps = capabilities.probe(force=True)
    assert caps["semgrep"].available is False


def test_a_crashing_probe_does_not_break_the_run(monkeypatch):
    def _boom():
        raise RuntimeError("backend exploded")

    monkeypatch.setattr(capabilities, "_PROBES", (_boom,))
    caps = capabilities.probe(force=True)
    assert caps  # the run continues
    assert any("probe crashed" in c.detail for c in caps.values())
