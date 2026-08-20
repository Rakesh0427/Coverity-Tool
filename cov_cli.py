#!/usr/bin/env python3
"""
cov_cli.py — commit existing Coverity analysis results to Coverity Connect.

Scope
-----
This module drives ONE Coverity command: ``cov-commit-defects``. Running the
build/analysis (``cov-build`` / ``cov-analyze``) is deliberately out of scope —
the user performs that separately and comes to this tool with results already
in hand.

    cov-commit-defects --dir <idir> --host <h> --stream <s> ...

What can actually be committed
------------------------------
``cov-commit-defects`` reads an **intermediate directory** (the ``--dir`` idir
produced by ``cov-build``/``cov-analyze``). It cannot read an HTML report:
the HTML folder is *generated from* an idir by
``cov-format-errors --dir idir --html-output <folder>`` and contains no emit or
analysis data to upload. :func:`inspect_input` recognises what a user pointed
at and explains the difference instead of letting Coverity fail cryptically.

Design notes
------------
* Command construction is pure (:func:`build_commit_command`) so it can be
  unit-tested without Coverity installed.
* The password is passed via the ``COVERITY_PASSPHRASE`` environment variable
  rather than argv — command lines are visible to every user on the machine via
  the process list, environment variables are not.
* :func:`run_commit` streams output line-by-line so a GUI can show live
  progress instead of freezing while a large snapshot uploads.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
from dataclasses import dataclass, field

#: The only Coverity executable this module drives.
COV_COMMIT = "cov-commit-defects"

#: Classifications returned by :func:`inspect_input`.
INPUT_IDIR = "idir"            # a usable intermediate directory
INPUT_HTML = "html"            # a cov-format-errors HTML report folder
INPUT_EMPTY_IDIR = "idir_no_output"  # idir captured but never analysed
INPUT_MISSING = "missing"      # path does not exist
INPUT_UNKNOWN = "unknown"      # exists but is not recognisable


class CovToolsNotFound(Exception):
    """Raised when ``cov-commit-defects`` cannot be located."""


# --------------------------------------------------------------------------- #
# locating the tool
# --------------------------------------------------------------------------- #
def _exe(name):
    """Append .exe on Windows so plain names resolve."""
    if sys.platform.startswith("win") and not name.lower().endswith(".exe"):
        return name + ".exe"
    return name


def resolve_tool(name=COV_COMMIT, bin_dir=""):
    """Return the full path to a Coverity executable.

    Looks in ``bin_dir`` first (either the ``bin`` folder of a cov-analysis
    install or the install root), then falls back to ``PATH``.
    """
    exe = _exe(name)
    if bin_dir:
        for candidate in (os.path.join(bin_dir, exe),
                          os.path.join(bin_dir, "bin", exe)):
            if os.path.isfile(candidate):
                return candidate
    from shutil import which
    found = which(exe) or which(name)
    if found:
        return found
    raise CovToolsNotFound(
        f"'{name}' not found. Add the Coverity Analysis bin folder to PATH, "
        f"or set the 'Coverity bin folder' field (for example "
        f"C:\\Program Files\\Coverity\\Coverity Static Analysis\\bin)."
    )


def commit_tool_path(bin_dir=""):
    """Return the cov-commit-defects path, or ``None`` when unavailable."""
    try:
        return resolve_tool(COV_COMMIT, bin_dir)
    except CovToolsNotFound:
        return None


# --------------------------------------------------------------------------- #
# understanding what the user selected
# --------------------------------------------------------------------------- #
@dataclass
class InputInfo:
    """What a chosen folder actually is, and whether it can be committed."""

    path: str
    kind: str
    committable: bool = False
    message: str = ""
    hint: str = ""


def _looks_like_html_report(path):
    """True when the folder is a cov-format-errors HTML report."""
    if os.path.isfile(os.path.join(path, "index.html")):
        return True
    try:
        names = os.listdir(path)
    except OSError:
        return False
    return any(n.lower().endswith((".html", ".htm")) for n in names)


def inspect_input(path):
    """Classify ``path`` and explain whether cov-commit-defects can use it.

    Returns an :class:`InputInfo`. The HTML case matters most: users naturally
    assume the report folder they already have is what gets uploaded, but
    Coverity needs the intermediate directory that produced it.
    """
    path = (path or "").strip()
    if not path:
        return InputInfo(path, INPUT_MISSING, False,
                         "No folder selected.",
                         "Choose the intermediate directory (idir) created by "
                         "cov-build / cov-analyze.")
    if not os.path.exists(path):
        return InputInfo(path, INPUT_MISSING, False,
                         f"Folder does not exist: {path}", "")
    if not os.path.isdir(path):
        return InputInfo(path, INPUT_UNKNOWN, False,
                         "That is a file, not a folder.",
                         "cov-commit-defects needs the intermediate directory "
                         "(idir) folder.")

    has_emit = os.path.isdir(os.path.join(path, "emit"))
    has_output = os.path.isdir(os.path.join(path, "output"))

    if has_emit and has_output:
        return InputInfo(path, INPUT_IDIR, True,
                         "Valid intermediate directory (analysis results found).",
                         "")
    if has_emit and not has_output:
        return InputInfo(
            path, INPUT_EMPTY_IDIR, False,
            "This intermediate directory has captured source (emit/) but no "
            "analysis results (output/).",
            "Run cov-analyze --dir <idir> before committing.")

    if _looks_like_html_report(path):
        return InputInfo(
            path, INPUT_HTML, False,
            "This is an HTML report folder, which cannot be committed.",
            "Coverity uploads the intermediate directory (idir), not the HTML "
            "report — the HTML is generated FROM the idir by cov-format-errors. "
            "Select the idir folder that was passed to cov-build --dir / "
            "cov-analyze --dir instead.")

    return InputInfo(
        path, INPUT_UNKNOWN, False,
        "This folder is not a Coverity intermediate directory.",
        "An idir contains 'emit' and 'output' subfolders. Select the folder "
        "that was passed to cov-build --dir / cov-analyze --dir.")


# --------------------------------------------------------------------------- #
# configuration
# --------------------------------------------------------------------------- #
@dataclass
class CommitConfig:
    """Everything needed to run ``cov-commit-defects``."""

    idir: str = ""                  # intermediate directory (--dir)
    bin_dir: str = ""               # Coverity Analysis bin folder (optional)

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
    strip_paths: list = field(default_factory=list)
    extra_args: str = ""


def _split_args(text):
    """Split an extra-args string the way a shell would."""
    if not text:
        return []
    try:
        return shlex.split(text, posix=not sys.platform.startswith("win"))
    except ValueError:
        return text.split()


# --------------------------------------------------------------------------- #
# command construction (pure — safe to unit-test)
# --------------------------------------------------------------------------- #
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
    for path in cfg.strip_paths:
        if path:
            cmd += ["--strip-path", path]
    cmd += _split_args(cfg.extra_args)
    return cmd


def commit_env(cfg, base_env=None):
    """Environment carrying the password safely.

    Coverity reads ``COVERITY_PASSPHRASE`` when ``--password`` is absent, which
    keeps the secret out of the process list.
    """
    env = dict(base_env if base_env is not None else os.environ)
    if cfg.password and not cfg.auth_key_file:
        env["COVERITY_PASSPHRASE"] = cfg.password
    return env


def describe_command(cmd):
    """Render a command list for display/logging (never contains secrets)."""
    return " ".join(shlex.quote(str(c)) for c in cmd)


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def validate_config(cfg):
    """Return a list of human-readable problems with ``cfg``.

    Everything is checked up-front so the user sees all issues at once rather
    than discovering them one failed upload at a time.
    """
    problems = []

    info = inspect_input(cfg.idir)
    if not info.committable:
        problems.append(info.message + (f" {info.hint}" if info.hint else ""))

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
    if not commit_tool_path(cfg.bin_dir):
        problems.append(f"'{COV_COMMIT}' not found on PATH.")

    return problems


# --------------------------------------------------------------------------- #
# execution
# --------------------------------------------------------------------------- #
@dataclass
class CommitResult:
    command: str = ""
    returncode: int | None = None
    output: str = ""
    error: str = ""
    cancelled: bool = False
    dry_run: bool = False

    @property
    def ok(self):
        return not self.error and not self.cancelled and self.returncode == 0

    def summary(self):
        if self.dry_run:
            return "Dry run — nothing was uploaded."
        if self.cancelled:
            return "Cancelled before the commit finished."
        if self.ok:
            return "Commit succeeded."
        return f"Commit failed — {self.error or f'exit code {self.returncode}'}"


class Canceller:
    """Cooperative cancel flag shared with a running commit."""

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


def run_commit(cfg, log_cb=None, canceller=None, dry_run=False):
    """Run ``cov-commit-defects``, streaming output to ``log_cb``.

    Returns a :class:`CommitResult`. A non-zero exit never raises — a rejected
    commit is a normal outcome that the caller reports to the user.
    """
    result = CommitResult(dry_run=dry_run)

    try:
        cmd = build_commit_command(cfg)
    except (ValueError, CovToolsNotFound) as exc:
        result.error = str(exc)
        if log_cb:
            log_cb(f"! {exc}\n")
        return result

    result.command = describe_command(cmd)
    if log_cb:
        log_cb(f"$ {result.command}\n")

    if dry_run:
        result.returncode = 0
        if log_cb:
            log_cb("  (dry run — not executed)\n")
        return result

    if canceller and canceller.cancelled:
        result.cancelled = True
        return result

    chunks = []
    try:
        proc = subprocess.Popen(
            cmd,
            env=commit_env(cfg),
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
        result.cancelled = True
        result.error = "Cancelled"
    elif result.returncode != 0 and not result.error:
        result.error = explain_failure(result.returncode, result.output)
    return result


def explain_failure(code, output):
    """Turn a raw exit code into something actionable where possible."""
    text = (output or "").lower()
    if "no translation units" in text or "contains no" in text:
        return ("The intermediate directory has no analysis results. Run "
                "cov-analyze --dir <idir> before committing.")
    if ("authentication" in text or "invalid username" in text
            or "401" in text or "unauthorized" in text):
        return "Authentication failed — check the username/password or auth-key file."
    if "certificate" in text:
        return ("Server certificate not trusted — tick 'Trust new certificate' "
                "or install the CA certificate.")
    if "stream" in text and ("does not exist" in text or "not found" in text):
        return ("The target stream does not exist on the server. Create it in "
                "Coverity Connect (or with cov-manage-im) first.")
    if "connection refused" in text or "unknown host" in text:
        return "Could not reach the server — check the host and port."
    if "license" in text:
        return "Coverity license problem — check your license file."
    return f"exit code {code}"
