"""Tests for the commit-only Coverity driver (cov_cli.py) and its CLI."""
import os
import stat
import sys

import pytest

import cov_cli as cc
import cov_commit


@pytest.fixture
def fake_bin(tmp_path, monkeypatch):
    """A directory holding a stub cov-commit-defects, wired into PATH."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    name = cc.COV_COMMIT + (".exe" if sys.platform.startswith("win") else "")
    p = bindir / name
    p.write_text("#!/bin/sh\nexit 0\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
    return str(bindir)


@pytest.fixture
def idir(tmp_path):
    """A realistic intermediate directory: emit/ + output/."""
    d = tmp_path / "cov-idir"
    (d / "emit").mkdir(parents=True)
    (d / "output").mkdir()
    return str(d)


def cfg_for(idir, **kw):
    base = dict(idir=idir, host="cov.example.com", stream="MyStream",
                username="rakesh", password="secret")
    base.update(kw)
    return cc.CommitConfig(**base)


# --------------------------------------------------------------------------- #
# tool discovery
# --------------------------------------------------------------------------- #
def test_missing_tool_raises_a_helpful_error(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(cc.CovToolsNotFound) as exc:
        cc.resolve_tool(cc.COV_COMMIT)
    assert "not found" in str(exc.value)


def test_bin_dir_is_preferred_over_path(fake_bin):
    assert cc.resolve_tool(cc.COV_COMMIT, fake_bin).startswith(fake_bin)


def test_install_root_resolves_via_bin_subfolder(fake_bin):
    root = os.path.dirname(fake_bin)
    assert cc.resolve_tool(cc.COV_COMMIT, root).startswith(fake_bin)


def test_commit_tool_path_returns_none_when_absent(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert cc.commit_tool_path() is None


# --------------------------------------------------------------------------- #
# input inspection — the HTML-vs-idir distinction
# --------------------------------------------------------------------------- #
def test_real_idir_is_committable(idir):
    info = cc.inspect_input(idir)
    assert info.kind == cc.INPUT_IDIR and info.committable


def test_html_report_folder_is_rejected_with_an_explanation(tmp_path):
    html = tmp_path / "report"
    (html / "Code").mkdir(parents=True)
    (html / "index.html").write_text("<html></html>")

    info = cc.inspect_input(str(html))
    assert info.kind == cc.INPUT_HTML
    assert not info.committable
    # The user must learn WHY, and what to pick instead.
    assert "idir" in info.hint.lower()
    assert "cov-format-errors" in info.hint


def test_html_folder_without_index_still_detected(tmp_path):
    html = tmp_path / "report"
    html.mkdir()
    (html / "1_buf.html").write_text("<html></html>")
    assert cc.inspect_input(str(html)).kind == cc.INPUT_HTML


def test_captured_but_unanalysed_idir_is_rejected(tmp_path):
    d = tmp_path / "idir"
    (d / "emit").mkdir(parents=True)          # no output/
    info = cc.inspect_input(str(d))
    assert info.kind == cc.INPUT_EMPTY_IDIR
    assert not info.committable
    assert "cov-analyze" in info.hint


def test_unrelated_folder_is_rejected(tmp_path):
    d = tmp_path / "src"
    d.mkdir()
    (d / "main.c").write_text("int main(void){return 0;}")
    info = cc.inspect_input(str(d))
    assert info.kind == cc.INPUT_UNKNOWN and not info.committable


def test_missing_path_and_empty_path(tmp_path):
    assert cc.inspect_input(str(tmp_path / "nope")).kind == cc.INPUT_MISSING
    assert cc.inspect_input("").kind == cc.INPUT_MISSING


def test_file_instead_of_folder_is_rejected(tmp_path):
    f = tmp_path / "report.html"
    f.write_text("<html></html>")
    info = cc.inspect_input(str(f))
    assert not info.committable and "folder" in info.message.lower()


def test_repo_sample_html_report_is_recognised():
    """The bundled sample report must be detected as HTML, not an idir."""
    sample = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "docs", "sample_report")
    if not os.path.isdir(sample):
        pytest.skip("sample report not present")
    assert cc.inspect_input(sample).kind == cc.INPUT_HTML


# --------------------------------------------------------------------------- #
# command construction
# --------------------------------------------------------------------------- #
def test_commit_has_dir_host_stream_and_user(fake_bin, idir):
    cmd = cc.build_commit_command(cfg_for(idir, bin_dir=fake_bin))
    assert cmd[cmd.index("--dir") + 1] == idir
    assert cmd[cmd.index("--host") + 1] == "cov.example.com"
    assert cmd[cmd.index("--stream") + 1] == "MyStream"
    assert cmd[cmd.index("--user") + 1] == "rakesh"


def test_password_never_appears_on_the_command_line(fake_bin, idir):
    cfg = cfg_for(idir, bin_dir=fake_bin)
    cmd = cc.build_commit_command(cfg)
    assert "secret" not in " ".join(cmd)
    assert "--password" not in cmd
    # ...it travels in the environment instead
    assert cc.commit_env(cfg, base_env={})["COVERITY_PASSPHRASE"] == "secret"


def test_auth_key_file_replaces_user_and_passphrase(fake_bin, idir, tmp_path):
    key = tmp_path / "auth.key"
    key.write_text("k")
    cfg = cfg_for(idir, bin_dir=fake_bin, auth_key_file=str(key))
    cmd = cc.build_commit_command(cfg)
    assert "--auth-key-file" in cmd and "--user" not in cmd
    assert "COVERITY_PASSPHRASE" not in cc.commit_env(cfg, base_env={})


def test_ssl_uses_https_port(fake_bin, idir):
    cmd = cc.build_commit_command(cfg_for(idir, bin_dir=fake_bin,
                                          port="8443", use_ssl=True))
    assert cmd[cmd.index("--https-port") + 1] == "8443"


def test_plain_http_uses_port(fake_bin, idir):
    cmd = cc.build_commit_command(cfg_for(idir, bin_dir=fake_bin,
                                          port="8080", use_ssl=False))
    assert cmd[cmd.index("--port") + 1] == "8080"


def test_ssl_without_port_passes_ssl_flag(fake_bin, idir):
    cmd = cc.build_commit_command(cfg_for(idir, bin_dir=fake_bin, port=""))
    assert "--ssl" in cmd


def test_optional_metadata_is_included(fake_bin, idir):
    cmd = cc.build_commit_command(cfg_for(
        idir, bin_dir=fake_bin, description="nightly", version="abc123",
        strip_paths=["/build"], extra_args="--ticker-mode none"))
    assert cmd[cmd.index("--description") + 1] == "nightly"
    assert cmd[cmd.index("--version") + 1] == "abc123"
    assert cmd[cmd.index("--strip-path") + 1] == "/build"
    assert "--ticker-mode" in cmd


def test_trust_cert_can_be_disabled(fake_bin, idir):
    cmd = cc.build_commit_command(cfg_for(idir, bin_dir=fake_bin,
                                          on_new_cert_trust=False))
    assert "--on-new-cert" not in cmd


def test_missing_required_fields_raise(fake_bin, idir):
    for field in ("idir", "host", "stream"):
        cfg = cfg_for(idir, bin_dir=fake_bin)
        setattr(cfg, field, "")
        with pytest.raises(ValueError):
            cc.build_commit_command(cfg)


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def test_validate_accepts_a_good_config(fake_bin, idir):
    assert cc.validate_config(cfg_for(idir, bin_dir=fake_bin)) == []


def test_validate_rejects_an_html_folder(fake_bin, tmp_path):
    html = tmp_path / "report"
    html.mkdir()
    (html / "index.html").write_text("<html></html>")
    problems = cc.validate_config(cfg_for(str(html), bin_dir=fake_bin))
    assert any("HTML report" in p for p in problems)


def test_validate_collects_every_problem_at_once(fake_bin):
    problems = cc.validate_config(cc.CommitConfig(bin_dir=fake_bin))
    joined = " ".join(problems).lower()
    assert "host" in joined and "stream" in joined and "username" in joined


def test_validate_flags_missing_password(fake_bin, idir):
    cfg = cfg_for(idir, bin_dir=fake_bin, password="")
    assert any("Password" in p for p in cc.validate_config(cfg))


def test_validate_flags_missing_auth_key_file(fake_bin, idir, tmp_path):
    cfg = cfg_for(idir, bin_dir=fake_bin,
                  auth_key_file=str(tmp_path / "nope.key"))
    assert any("Auth key file not found" in p for p in cc.validate_config(cfg))


def test_validate_reports_missing_tool(idir, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert any("not found on PATH" in p
               for p in cc.validate_config(cfg_for(idir)))


# --------------------------------------------------------------------------- #
# execution
# --------------------------------------------------------------------------- #
def _script_bin(tmp_path, body):
    """Build a stub cov-commit-defects with the given shell body."""
    bindir = tmp_path / "sbin"
    bindir.mkdir(exist_ok=True)
    p = bindir / cc.COV_COMMIT
    p.write_text("#!/bin/sh\n" + body + "\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(bindir)


@pytest.mark.skipif(sys.platform.startswith("win"), reason="sh stub")
def test_successful_commit_streams_output(tmp_path, idir):
    bindir = _script_bin(tmp_path, "echo 'Committing 42 defects'; exit 0")
    lines = []
    res = cc.run_commit(cfg_for(idir, bin_dir=bindir), log_cb=lines.append)
    assert res.ok and res.returncode == 0
    assert any("42 defects" in l for l in lines)
    assert "Commit succeeded" in res.summary()


@pytest.mark.skipif(sys.platform.startswith("win"), reason="sh stub")
def test_password_reaches_the_child_via_environment(tmp_path, idir):
    bindir = _script_bin(tmp_path, 'echo "pw=$COVERITY_PASSPHRASE"; exit 0')
    res = cc.run_commit(cfg_for(idir, bin_dir=bindir))
    assert "pw=secret" in res.output


@pytest.mark.skipif(sys.platform.startswith("win"), reason="sh stub")
def test_failed_commit_is_reported_not_raised(tmp_path, idir):
    bindir = _script_bin(
        tmp_path, "echo \"Stream 'X' does not exist\" ; exit 1")
    res = cc.run_commit(cfg_for(idir, bin_dir=bindir))
    assert not res.ok
    assert "does not exist" in res.error


def test_dry_run_executes_nothing(fake_bin, idir):
    lines = []
    res = cc.run_commit(cfg_for(idir, bin_dir=fake_bin), log_cb=lines.append,
                        dry_run=True)
    assert res.ok and res.dry_run
    assert any("dry run" in l.lower() for l in lines)
    assert "Dry run" in res.summary()


def test_bad_config_surfaces_as_an_error_not_a_crash(fake_bin, idir):
    res = cc.run_commit(cfg_for(idir, bin_dir=fake_bin, host=""))
    assert not res.ok and "host is required" in res.error.lower()


def test_missing_executable_is_reported(idir, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    res = cc.run_commit(cfg_for(idir))
    assert not res.ok and "not found" in res.error.lower()


def test_cancel_before_start_skips_the_run(fake_bin, idir):
    canceller = cc.Canceller()
    canceller.cancel()
    res = cc.run_commit(cfg_for(idir, bin_dir=fake_bin), canceller=canceller)
    assert res.cancelled and not res.ok


# --------------------------------------------------------------------------- #
# error explanations
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text,expected", [
    ("intermediate directory contains no translation units", "cov-analyze"),
    ("Authentication failed for user", "Authentication failed"),
    ("server certificate is not trusted", "certificate"),
    ("Stream 'X' does not exist", "does not exist"),
    ("connection refused", "host and port"),
    ("license check failed", "license"),
])
def test_failure_messages_are_actionable(text, expected):
    assert expected.lower() in cc.explain_failure(1, text).lower()


def test_unknown_failure_falls_back_to_exit_code():
    assert "7" in cc.explain_failure(7, "something odd")


# --------------------------------------------------------------------------- #
# headless CLI
# --------------------------------------------------------------------------- #
def test_cli_dry_run_succeeds(fake_bin, idir, capsys, monkeypatch):
    monkeypatch.setenv("COVERITY_PASSPHRASE", "pw")
    rc = cov_commit.main(["--idir", idir, "--bin-dir", fake_bin,
                          "--host", "cov.example.com", "--stream", "S",
                          "--user", "u", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "cov-commit-defects" in out and "--stream" in out


def test_cli_rejects_html_folder_with_guidance(fake_bin, tmp_path, capsys):
    html = tmp_path / "report"
    html.mkdir()
    (html / "index.html").write_text("<html></html>")
    rc = cov_commit.main(["--idir", str(html), "--bin-dir", fake_bin,
                          "--host", "h", "--stream", "s", "--user", "u",
                          "--dry-run"])
    assert rc == 2
    assert "idir" in capsys.readouterr().err.lower()


def test_cli_bad_config_exits_2(fake_bin, idir, capsys):
    rc = cov_commit.main(["--idir", idir, "--bin-dir", fake_bin, "--dry-run"])
    assert rc == 2
    assert "fix" in capsys.readouterr().err.lower()


def test_cli_takes_password_from_environment(idir, monkeypatch):
    monkeypatch.setenv("COVERITY_PASSPHRASE", "envsecret")
    args = cov_commit.build_parser().parse_args(
        ["--idir", idir, "--host", "h", "--stream", "s", "--user", "u"])
    cfg = cov_commit.config_from_args(args, os.environ["COVERITY_PASSPHRASE"])
    assert cfg.password == "envsecret"


def test_cli_has_no_password_flag():
    """argv is world-readable; the password must not be a flag."""
    help_text = cov_commit.build_parser().format_help()
    assert "--password" not in help_text
    assert "COVERITY_PASSPHRASE" in help_text


@pytest.mark.skipif(sys.platform.startswith("win"), reason="sh stub")
def test_cli_returns_1_when_the_commit_fails(tmp_path, idir, monkeypatch):
    monkeypatch.setenv("COVERITY_PASSPHRASE", "pw")
    bindir = _script_bin(tmp_path, "echo boom; exit 1")
    rc = cov_commit.main(["--idir", idir, "--bin-dir", bindir,
                          "--host", "h", "--stream", "s", "--user", "u"])
    assert rc == 1


def test_cli_inspect_reports_folder_kind(idir, capsys):
    rc = cov_commit.main(["--idir", idir, "--inspect"])
    assert rc == 0
    assert "intermediate directory" in capsys.readouterr().out.lower()
