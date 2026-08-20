"""Tests for the cov-build / cov-analyze / cov-commit-defects driver."""
import os
import stat
import sys

import pytest

import cov_cli as cc


@pytest.fixture
def fake_bin(tmp_path, monkeypatch):
    """A directory holding stub cov-* executables, wired into PATH."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in (cc.COV_BUILD, cc.COV_ANALYZE, cc.COV_COMMIT):
        name = tool + (".exe" if sys.platform.startswith("win") else "")
        p = bindir / name
        p.write_text("#!/bin/sh\nexit 0\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
    return str(bindir)


def cfg_for(tmp_path, **kw):
    base = dict(
        idir=str(tmp_path / "idir"),
        build_command="make -j8",
        host="cov.example.com",
        stream="MyStream",
        username="rakesh",
        password="secret",
    )
    base.update(kw)
    return cc.CommitConfig(**base)


# --------------------------------------------------------------------------- #
# tool discovery
# --------------------------------------------------------------------------- #
def test_missing_tools_raise_a_helpful_error(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(cc.CovToolsNotFound) as exc:
        cc.resolve_tool(cc.COV_BUILD)
    assert "not found" in str(exc.value)


def test_bin_dir_is_preferred_over_path(fake_bin, tmp_path):
    assert cc.resolve_tool(cc.COV_BUILD, fake_bin).startswith(fake_bin)


def test_install_root_resolves_via_bin_subfolder(fake_bin):
    root = os.path.dirname(fake_bin)
    assert cc.resolve_tool(cc.COV_ANALYZE, root).startswith(fake_bin)


def test_tools_available_reports_each_tool(fake_bin):
    status = cc.tools_available(fake_bin)
    assert set(status) == {cc.COV_BUILD, cc.COV_ANALYZE, cc.COV_COMMIT}
    assert all(status.values())


# --------------------------------------------------------------------------- #
# cov-build
# --------------------------------------------------------------------------- #
def test_capture_wraps_the_build_command(fake_bin, tmp_path):
    cmd = cc.build_capture_command(cfg_for(tmp_path, bin_dir=fake_bin))
    # the build command is appended verbatim, after --dir <idir>
    assert cmd[-2:] == ["make", "-j8"]
    assert cmd[cmd.index("--dir") + 1].endswith("idir")


def test_capture_requires_a_build_command(fake_bin, tmp_path):
    with pytest.raises(ValueError):
        cc.build_capture_command(cfg_for(tmp_path, build_command="", bin_dir=fake_bin))


def test_no_command_capture_scans_the_source_tree(fake_bin, tmp_path):
    cmd = cc.build_capture_command(cfg_for(
        tmp_path, no_command=True, build_command="",
        fs_capture_search="/src", bin_dir=fake_bin))
    assert "--no-command" in cmd
    assert cmd[cmd.index("--fs-capture-search") + 1] == "/src"


def test_capture_requires_an_idir(fake_bin, tmp_path):
    with pytest.raises(ValueError):
        cc.build_capture_command(cfg_for(tmp_path, idir="", bin_dir=fake_bin))


# --------------------------------------------------------------------------- #
# cov-analyze
# --------------------------------------------------------------------------- #
def test_analyze_defaults_to_all_checkers(fake_bin, tmp_path):
    cmd = cc.build_analyze_command(cfg_for(tmp_path, bin_dir=fake_bin))
    assert "--all" in cmd


def test_analyze_options_are_passed_through(fake_bin, tmp_path):
    cmd = cc.build_analyze_command(cfg_for(
        tmp_path, bin_dir=fake_bin, all_checkers=False,
        aggressiveness="high", strip_paths=["/a", "/b"],
        extra_analyze_args="--enable-fnptr"))
    assert "--all" not in cmd
    assert cmd[cmd.index("--aggressiveness-level") + 1] == "high"
    assert cmd.count("--strip-path") == 2
    assert "--enable-fnptr" in cmd


# --------------------------------------------------------------------------- #
# cov-commit-defects
# --------------------------------------------------------------------------- #
def test_commit_has_host_stream_and_user(fake_bin, tmp_path):
    cmd = cc.build_commit_command(cfg_for(tmp_path, bin_dir=fake_bin))
    assert cmd[cmd.index("--host") + 1] == "cov.example.com"
    assert cmd[cmd.index("--stream") + 1] == "MyStream"
    assert cmd[cmd.index("--user") + 1] == "rakesh"


def test_password_never_appears_on_the_command_line(fake_bin, tmp_path):
    cfg = cfg_for(tmp_path, bin_dir=fake_bin)
    cmd = cc.build_commit_command(cfg)
    assert "secret" not in " ".join(cmd)
    assert "--password" not in cmd
    # ...it travels in the environment instead
    assert cc.commit_env(cfg, base_env={})["COVERITY_PASSPHRASE"] == "secret"


def test_auth_key_file_replaces_user_and_passphrase(fake_bin, tmp_path):
    key = tmp_path / "auth.key"
    key.write_text("k")
    cfg = cfg_for(tmp_path, bin_dir=fake_bin, auth_key_file=str(key))
    cmd = cc.build_commit_command(cfg)
    assert "--auth-key-file" in cmd and "--user" not in cmd
    assert "COVERITY_PASSPHRASE" not in cc.commit_env(cfg, base_env={})


def test_ssl_uses_https_port(fake_bin, tmp_path):
    cmd = cc.build_commit_command(cfg_for(tmp_path, bin_dir=fake_bin,
                                          port="8443", use_ssl=True))
    assert cmd[cmd.index("--https-port") + 1] == "8443"


def test_plain_http_uses_port(fake_bin, tmp_path):
    cmd = cc.build_commit_command(cfg_for(tmp_path, bin_dir=fake_bin,
                                          port="8080", use_ssl=False))
    assert cmd[cmd.index("--port") + 1] == "8080"


def test_commit_requires_host_and_stream(fake_bin, tmp_path):
    with pytest.raises(ValueError):
        cc.build_commit_command(cfg_for(tmp_path, bin_dir=fake_bin, host=""))
    with pytest.raises(ValueError):
        cc.build_commit_command(cfg_for(tmp_path, bin_dir=fake_bin, stream=""))


def test_description_and_version_are_included(fake_bin, tmp_path):
    cmd = cc.build_commit_command(cfg_for(
        tmp_path, bin_dir=fake_bin, description="nightly", version="abc123"))
    assert cmd[cmd.index("--description") + 1] == "nightly"
    assert cmd[cmd.index("--version") + 1] == "abc123"


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def test_validate_accepts_a_good_config(fake_bin, tmp_path):
    (tmp_path / "src").mkdir()
    cfg = cfg_for(tmp_path, bin_dir=fake_bin, source_dir=str(tmp_path / "src"))
    assert cc.validate_config(cfg) == []


def test_validate_collects_every_problem_at_once(fake_bin, tmp_path):
    cfg = cc.CommitConfig(bin_dir=fake_bin)
    problems = cc.validate_config(cfg)
    joined = " ".join(problems)
    assert "Intermediate directory" in joined
    assert "Build command" in joined
    assert "host" in joined and "stream" in joined.lower()


def test_validate_flags_missing_password(fake_bin, tmp_path):
    cfg = cfg_for(tmp_path, bin_dir=fake_bin, password="")
    assert any("Password" in p for p in cc.validate_config(cfg))


def test_validate_flags_missing_auth_key_file(fake_bin, tmp_path):
    cfg = cfg_for(tmp_path, bin_dir=fake_bin, auth_key_file=str(tmp_path / "nope"))
    assert any("Auth key file not found" in p for p in cc.validate_config(cfg))


def test_commit_only_requires_an_existing_idir(fake_bin, tmp_path):
    cfg = cfg_for(tmp_path, bin_dir=fake_bin)  # idir never created
    problems = cc.validate_config(cfg, stages=[cc.STAGE_COMMIT])
    assert any("does not exist" in p for p in problems)


def test_validate_reports_missing_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    problems = cc.validate_config(cfg_for(tmp_path))
    assert any("not found on PATH" in p for p in problems)


# --------------------------------------------------------------------------- #
# execution
# --------------------------------------------------------------------------- #
def test_run_stage_streams_output_and_succeeds():
    lines = []
    res = cc.run_stage("t", [sys.executable, "-c", "print('hello')"],
                       log_cb=lines.append)
    assert res.ok and res.returncode == 0
    assert any("hello" in l for l in lines)


def test_run_stage_captures_failure_without_raising():
    res = cc.run_stage("t", [sys.executable, "-c", "import sys; sys.exit(3)"])
    assert not res.ok and res.returncode == 3


def test_run_stage_handles_a_missing_executable():
    res = cc.run_stage("t", ["definitely-not-a-real-binary-xyz"])
    assert not res.ok and "not found" in res.error.lower()


def test_dry_run_pipeline_executes_nothing(fake_bin, tmp_path):
    (tmp_path / "idir").mkdir()
    logs = []
    res = cc.run_pipeline(cfg_for(tmp_path, bin_dir=fake_bin),
                          log_cb=logs.append, dry_run=True)
    assert res.ok and len(res.stages) == 3
    assert all("dry run" in l for l in logs if "dry run" in l)
    assert any("cov-commit-defects" in s.command for s in res.stages)


def test_pipeline_stops_at_the_first_failure(tmp_path, monkeypatch):
    """A failed capture must not be analysed or committed."""
    calls = []

    def fake_run_stage(stage, cmd, **kw):
        calls.append(stage)
        return cc.StageResult(stage=stage, returncode=1, error="boom")

    monkeypatch.setattr(cc, "run_stage", fake_run_stage)
    monkeypatch.setattr(cc, "build_capture_command", lambda c: ["x"])
    monkeypatch.setattr(cc, "build_analyze_command", lambda c: ["x"])
    monkeypatch.setattr(cc, "build_commit_command", lambda c: ["x"])

    res = cc.run_pipeline(cfg_for(tmp_path))
    assert calls == [cc.STAGE_BUILD]
    assert not res.ok


def test_pipeline_can_run_commit_only(fake_bin, tmp_path):
    (tmp_path / "idir").mkdir()
    res = cc.run_pipeline(cfg_for(tmp_path, bin_dir=fake_bin),
                          stages=[cc.STAGE_COMMIT], dry_run=True)
    assert [s.stage for s in res.stages] == [cc.STAGE_COMMIT]


def test_builder_errors_surface_as_stage_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    res = cc.run_pipeline(cfg_for(tmp_path), stages=[cc.STAGE_BUILD])
    assert not res.ok and "not found" in res.stages[0].error.lower()


def test_cancel_skips_remaining_stages(fake_bin, tmp_path):
    (tmp_path / "idir").mkdir()
    canceller = cc.Canceller()
    canceller.cancel()
    res = cc.run_pipeline(cfg_for(tmp_path, bin_dir=fake_bin),
                          canceller=canceller, dry_run=True)
    assert res.cancelled and all(s.skipped for s in res.stages)


# --------------------------------------------------------------------------- #
# error explanations
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text,expected", [
    ("ERROR: No files were emitted", "captured 0 files"),
    ("Authentication failed for user", "Authentication failed"),
    ("server certificate is not trusted", "certificate"),
    ("Stream 'X' does not exist", "does not exist"),
    ("connection refused", "check host and port"),
])
def test_failure_messages_are_actionable(text, expected):
    msg = cc._explain_failure(cc.STAGE_BUILD, 1, text)
    assert expected.lower() in msg.lower()


def test_unknown_failure_falls_back_to_exit_code():
    assert "7" in cc._explain_failure(cc.STAGE_ANALYZE, 7, "weird output")


def test_summary_marks_each_stage(tmp_path, fake_bin):
    (tmp_path / "idir").mkdir()
    res = cc.run_pipeline(cfg_for(tmp_path, bin_dir=fake_bin), dry_run=True)
    summary = res.summary()
    assert summary.count("✓") == 3


# --------------------------------------------------------------------------- #
# headless CLI (cov_commit.py)
# --------------------------------------------------------------------------- #
import cov_commit


def test_stage_parsing_keeps_pipeline_order():
    assert cov_commit.parse_stages("commit,build") == [cc.STAGE_BUILD,
                                                       cc.STAGE_COMMIT]


def test_stage_parsing_rejects_nonsense():
    with pytest.raises(ValueError):
        cov_commit.parse_stages("bulid")
    with pytest.raises(ValueError):
        cov_commit.parse_stages("")


def test_cli_dry_run_succeeds(fake_bin, tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("COVERITY_PASSPHRASE", "pw")
    rc = cov_commit.main([
        "--idir", str(tmp_path / "idir"),
        "--source", str(tmp_path),
        "--build-command", "make",
        "--bin-dir", fake_bin,
        "--host", "cov.example.com",
        "--stream", "S",
        "--user", "u",
        "--dry-run",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "cov-commit-defects" in out and "--stream" in out


def test_cli_reports_bad_config_and_exits_2(fake_bin, tmp_path, capsys):
    rc = cov_commit.main(["--idir", str(tmp_path / "idir"),
                          "--bin-dir", fake_bin, "--dry-run"])
    assert rc == 2
    assert "fix" in capsys.readouterr().err.lower()


def test_cli_takes_password_from_environment(fake_bin, tmp_path, monkeypatch):
    monkeypatch.setenv("COVERITY_PASSPHRASE", "envsecret")
    args = cov_commit.build_parser().parse_args([
        "--idir", str(tmp_path), "--host", "h", "--stream", "s", "--user", "u"])
    cfg = cov_commit.config_from_args(args, os.environ["COVERITY_PASSPHRASE"])
    assert cfg.password == "envsecret"
    assert "envsecret" not in " ".join(cc.build_commit_command(
        cc.CommitConfig(**{**cfg.__dict__, "bin_dir": fake_bin})))


def test_cli_has_no_password_flag():
    """argv is world-readable; the password must not be a flag."""
    help_text = cov_commit.build_parser().format_help()
    assert "--password" not in help_text
    assert "COVERITY_PASSPHRASE" in help_text
