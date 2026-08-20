#!/usr/bin/env python3
"""
cov_cli.py — drive the Coverity Analysis command-line tools.

This is the step BEFORE any triage happens: when a stream is empty, defects
must first be produced locally and committed to Coverity Connect.

    cov-build   --dir <idir> <build command>    capture the build
    cov-analyze --dir <idir> [checkers]         find defects
    cov-commit-defects --dir <idir> --host ...  upload them to a stream

Once committed, the normal tool flow takes over: Pull → analyse → disposition
→ Push (see ``coverity_push.py``).

Design notes
------------
* Command construction is pure (``build_*_command``) so it can be unit-tested
  without Coverity installed.
* The password is passed via the ``COVERITY_PASSPHRASE`` environment variable
  rather than argv — command lines are visible to every user on the machine via
  the process list, environment variables are not.
* ``run_stage`` streams output line-by-line so a GUI can show live progress
  instead of freezing for the several minutes a real build takes.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
from dataclasses import dataclass, field

#: Executables this module drives, in pipeline order.
COV_BUILD = "cov-build"
COV_ANALYZE = "cov-analyze"
COV_COMMIT = "cov-commit-defects"
COV_CONFIGURE = "cov-configure"

STAGE_BUILD = "build"
STAGE_ANALYZE = "analyze"
STAGE_COMMIT = "commit"

STAGE_LABELS = {
    STAGE_BUILD: "cov-build (capture)",
    STAGE_ANALYZE: "cov-analyze (find defects)",
    STAGE_COMMIT: "cov-commit-defects (upload)",
}


class CovToolsNotFound(Exception):
    """Raised when the Coverity Analysis binaries cannot be located."""


# --------------------------------------------------------------------------- #
# locating the tools
# --------------------------------------------------------------------------- #
def _exe(name):
    """Append .exe on Windows so plain names resolve."""
    if sys.platform.startswith("win") and not name.lower().endswith(".exe"):
        return name + ".exe"
    return name


def resolve_tool(name, bin_dir=""):
    """Return the full path to a Coverity executable.

    Looks in ``bin_dir`` first (the ``bin`` folder of a cov-analysis install),
    then falls back to ``PATH``. Raises :class:`CovToolsNotFound` when missing,
    because silently shelling out to a non-existent binary produces a confusing
    "file not found" much later.
    """
    exe = _exe(name)
    if bin_dir:
        candidate = os.path.join(bin_dir, exe)
        if os.path.isfile(candidate):
            return candidate
        # bin_dir may be the install root rather than its bin/ subfolder
        candidate = os.path.join(bin_dir, "bin", exe)
        if os.path.isfile(candidate):
            return candidate
    from shutil import which
    found = which(exe) or which(name)
    if found:
        return found
    raise CovToolsNotFound(
        f"'{name}' not found. Add the Coverity Analysis bin folder to PATH, "
        f"or set the 'Coverity bin folder' field (e.g. "
        f"C:\\Program Files\\Coverity\\Coverity Static Analysis\\bin)."
    )


def tools_available(bin_dir=""):
    """Return ``{tool_name: path_or_None}`` for the three pipeline tools."""
    status = {}
    for tool in (COV_BUILD, COV_ANALYZE, COV_COMMIT):
        try:
            status[tool] = resolve_tool(tool, bin_dir)
        except CovToolsNotFound:
            status[tool] = None
    return status


# --------------------------------------------------------------------------- #
# configuration
# --------------------------------------------------------------------------- #
@dataclass
class CommitConfig:
    """Everything needed to run capture → analyse → commit."""

    idir: str = ""                  # intermediate directory (--dir)
    build_command: str = ""         # e.g. "make -j8" or "msbuild app.sln"
    source_dir: str = ""            # working directory for cov-build
    bin_dir: str = ""               # Coverity Analysis bin folder (optional)

    # analysis options
    all_checkers: bool = True       # cov-analyze --all
    aggressiveness: str = ""        # low | medium | high  (--aggressiveness-level)
    strip_paths: list = field(default_factory=list)
    extra_analyze_args: str = ""

    # server / commit options
    host: str = ""
    port: str = ""
    stream: str = ""
    username: str = ""
    password: str = ""
    auth_key_file: str = ""
    use_ssl: bool = True
    on_new_cert_trust: bool = True  # accept an unseen server certificate
    description: str = ""
    version: str = ""
    extra_commit_args: str = ""

    # capture options
    no_command: bool = False        # --no-command (interpreted languages)
    fs_capture_search: str = ""     # source tree to scan when --no-command


def _split_args(text):
    """Split an extra-args string the way a shell would."""
    if not text:
        return []
    try:
        return shlex.split(text, posix=not sys.platform.startswith("win"))
    except ValueError:
        return text.split()


# --------------------------------------------------------------------------- #
# command builders (pure — safe to unit-test)
# --------------------------------------------------------------------------- #
def build_capture_command(cfg):
    """Build the ``cov-build`` argument list."""
    if not cfg.idir:
        raise ValueError("Intermediate directory (--dir) is required.")
    cmd = [resolve_tool(COV_BUILD, cfg.bin_dir), "--dir", cfg.idir]
    if cfg.no_command:
        # Interpreted/non-compiled projects: nothing to wrap, scan the tree.
        cmd.append("--no-command")
        search = cfg.fs_capture_search or cfg.source_dir
        if not search:
            raise ValueError(
                "--no-command capture needs a source folder to scan.")
        cmd += ["--fs-capture-search", search]
    else:
        if not cfg.build_command.strip():
            raise ValueError("A build command is required (e.g. 'make').")
        cmd += _split_args(cfg.build_command)
    return cmd


def build_analyze_command(cfg):
    """Build the ``cov-analyze`` argument list."""
    if not cfg.idir:
        raise ValueError("Intermediate directory (--dir) is required.")
    cmd = [resolve_tool(COV_ANALYZE, cfg.bin_dir), "--dir", cfg.idir]
    if cfg.all_checkers:
        cmd.append("--all")
    if cfg.aggressiveness:
        cmd += ["--aggressiveness-level", cfg.aggressiveness]
    for path in cfg.strip_paths:
        if path:
            cmd += ["--strip-path", path]
    cmd += _split_args(cfg.extra_analyze_args)
    return cmd


def build_commit_command(cfg):
    """Build the ``cov-commit-defects`` argument list.

    The password is deliberately NOT placed here — see :func:`commit_env`.
    """
    if not cfg.idir:
        raise ValueError("Intermediate directory (--dir) is required.")
    if not cfg.host:
        raise ValueError("Coverity Connect host is required.")
    if not cfg.stream:
        raise ValueError("A target stream is required.")

    cmd = [resolve_tool(COV_COMMIT, cfg.bin_dir), "--dir", cfg.idir,
           "--host", cfg.host]
    if cfg.port:
        # Coverity uses --port for http and --https-port when SSL is on.
        cmd += ["--https-port" if cfg.use_ssl else "--port", str(cfg.port)]
    elif cfg.use_ssl:
        cmd.append("--ssl")
    cmd += ["--stream", cfg.stream]

    if cfg.auth_key_file:
        cmd += ["--auth-key-file", cfg.auth_key_file]
    elif cfg.username:
        cmd += ["--user", cfg.username]

    if cfg.on_new_cert_trust:
        cmd += ["--on-new-cert", "trust"]
    if cfg.description:
        cmd += ["--description", cfg.description]
    if cfg.version:
        cmd += ["--version", cfg.version]
    cmd += _split_args(cfg.extra_commit_args)
    return cmd


def commit_env(cfg, base_env=None):
    """Environment for ``cov-commit-defects`` carrying the password safely.

    Coverity reads ``COVERITY_PASSPHRASE`` when ``--password`` is absent, which
    keeps the secret out of the process list.
    """
    env = dict(base_env if base_env is not None else os.environ)
    if cfg.password and not cfg.auth_key_file:
        env["COVERITY_PASSPHRASE"] = cfg.password
    return env


def describe_command(cmd):
    """Render a command list for display/logging (never includes secrets)."""
    return " ".join(shlex.quote(str(c)) for c in cmd)


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def validate_config(cfg, stages=None):
    """Return a list of human-readable problems with ``cfg``.

    Checked up-front so the user sees every issue at once instead of
    discovering them one failed 10-minute build at a time.
    """
    stages = stages or [STAGE_BUILD, STAGE_ANALYZE, STAGE_COMMIT]
    problems = []

    if not cfg.idir:
        problems.append("Intermediate directory is required.")

    if STAGE_BUILD in stages:
        if cfg.no_command:
            if not (cfg.fs_capture_search or cfg.source_dir):
                problems.append(
                    "Capture without a build command needs a source folder.")
        elif not cfg.build_command.strip():
            problems.append("Build command is required (e.g. 'make -j8').")
        if cfg.source_dir and not os.path.isdir(cfg.source_dir):
            problems.append(f"Source folder does not exist: {cfg.source_dir}")

    if STAGE_ANALYZE in stages or STAGE_COMMIT in stages:
        # Skipping capture only makes sense against an already-populated idir.
        if STAGE_BUILD not in stages and cfg.idir and not os.path.isdir(cfg.idir):
            problems.append(
                f"Intermediate directory does not exist: {cfg.idir}. "
                "Run the capture stage first.")

    if STAGE_COMMIT in stages:
        if not cfg.host:
            problems.append("Coverity Connect host is required.")
        if not cfg.stream:
            problems.append("Target stream is required.")
        if not cfg.auth_key_file and not cfg.username:
            problems.append("Username or an auth-key file is required.")
        if cfg.auth_key_file and not os.path.isfile(cfg.auth_key_file):
            problems.append(f"Auth key file not found: {cfg.auth_key_file}")
        if not cfg.auth_key_file and cfg.username and not cfg.password:
            problems.append("Password is required (or use an auth-key file).")

    try:
        missing = [t for t, p in tools_available(cfg.bin_dir).items() if not p]
    except Exception:
        missing = []
    if missing:
        problems.append("Coverity tools not found on PATH: " + ", ".join(missing))

    return problems


# --------------------------------------------------------------------------- #
# execution
# --------------------------------------------------------------------------- #
@dataclass
class StageResult:
    stage: str
    command: str = ""
    returncode: int | None = None
    output: str = ""
    skipped: bool = False
    error: str = ""

    @property
    def ok(self):
        return not self.error and not self.skipped and self.returncode == 0


@dataclass
class PipelineResult:
    stages: list = field(default_factory=list)
    cancelled: bool = False

    @property
    def ok(self):
        return (not self.cancelled
                and bool(self.stages)
                and all(s.ok or s.skipped for s in self.stages))

    def summary(self):
        lines = []
        for s in self.stages:
            if s.skipped:
                mark, detail = "–", "skipped"
            elif s.ok:
                mark, detail = "✓", "ok"
            else:
                mark = "✗"
                detail = s.error or f"exit code {s.returncode}"
            lines.append(f"  {mark} {STAGE_LABELS.get(s.stage, s.stage)} — {detail}")
        if self.cancelled:
            lines.append("\n  Cancelled by user.")
        return "\n".join(lines)


class Canceller:
    """Cooperative cancel flag shared with a running pipeline."""

    def __init__(self):
        self._event = threading.Event()
        self._proc = None
        self._lock = threading.Lock()

    def attach(self, proc):
        with self._lock:
            self._proc = proc

    def cancel(self):
        self._event.set()
        with self._lock:
            proc = self._proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

    @property
    def cancelled(self):
        return self._event.is_set()


def run_stage(stage, cmd, cwd=None, env=None, log_cb=None, canceller=None):
    """Run one command, streaming stdout/stderr to ``log_cb``.

    Returns a :class:`StageResult`. Never raises for a non-zero exit — a failed
    Coverity stage is a normal outcome the caller reports to the user.
    """
    result = StageResult(stage=stage, command=describe_command(cmd))
    if log_cb:
        log_cb(f"$ {result.command}\n")

    if canceller and canceller.cancelled:
        result.skipped = True
        return result

    chunks = []
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd or None,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        result.error = f"Executable not found: {exc}"
        if log_cb:
            log_cb(result.error + "\n")
        return result
    except Exception as exc:
        result.error = str(exc)
        if log_cb:
            log_cb(result.error + "\n")
        return result

    if canceller:
        canceller.attach(proc)
    try:
        for line in proc.stdout:
            chunks.append(line)
            if log_cb:
                log_cb(line)
    except Exception as exc:  # pragma: no cover - stream read failure
        result.error = str(exc)
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
        result.returncode = proc.wait()

    result.output = "".join(chunks)
    if canceller and canceller.cancelled:
        result.error = "Cancelled"
    elif result.returncode != 0 and not result.error:
        result.error = _explain_failure(stage, result.returncode, result.output)
    return result


def _explain_failure(stage, code, output):
    """Turn a raw exit code into something actionable where possible."""
    text = (output or "").lower()
    if stage == STAGE_BUILD and "no files were emitted" in text:
        return ("cov-build captured 0 files — the build command did not compile "
                "anything. Clean the build first so sources actually recompile.")
    if "authentication" in text or "invalid username" in text or "401" in text:
        return "Authentication failed — check username/password or auth-key file."
    if "certificate" in text:
        return ("Server certificate not trusted — tick 'Trust new certificate' "
                "or install the CA certificate.")
    if "stream" in text and "does not exist" in text:
        return ("The target stream does not exist on the server. Create it in "
                "Coverity Connect (or via cov-manage-im) first.")
    if "connection refused" in text or "unknown host" in text:
        return "Could not reach the server — check host and port."
    return f"exit code {code}"


def run_pipeline(cfg, stages=None, log_cb=None, stage_cb=None, canceller=None,
                 dry_run=False):
    """Run capture → analyse → commit (whichever stages are requested).

    Stops at the first failing stage: analysing a failed capture, or committing
    a failed analysis, would upload nothing useful.
    """
    stages = list(stages or [STAGE_BUILD, STAGE_ANALYZE, STAGE_COMMIT])
    result = PipelineResult()

    builders = {
        STAGE_BUILD: (build_capture_command, cfg.source_dir or None, None),
        STAGE_ANALYZE: (build_analyze_command, cfg.source_dir or None, None),
        STAGE_COMMIT: (build_commit_command, None, "env"),
    }

    for stage in stages:
        if canceller and canceller.cancelled:
            result.cancelled = True
            result.stages.append(StageResult(stage=stage, skipped=True))
            continue
        if stage_cb:
            stage_cb(stage)

        builder, cwd, env_kind = builders[stage]
        try:
            cmd = builder(cfg)
        except (ValueError, CovToolsNotFound) as exc:
            sr = StageResult(stage=stage, error=str(exc))
            result.stages.append(sr)
            if log_cb:
                log_cb(f"! {exc}\n")
            break

        if dry_run:
            sr = StageResult(stage=stage, command=describe_command(cmd),
                             returncode=0)
            if log_cb:
                log_cb(f"$ {sr.command}\n  (dry run — not executed)\n")
            result.stages.append(sr)
            continue

        env = commit_env(cfg) if env_kind == "env" else None
        sr = run_stage(stage, cmd, cwd=cwd, env=env, log_cb=log_cb,
                       canceller=canceller)
        result.stages.append(sr)
        if not sr.ok:
            if canceller and canceller.cancelled:
                result.cancelled = True
            break

    return result
