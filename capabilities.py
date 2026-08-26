#!/usr/bin/env python3
"""
capabilities.py — runtime probe of the optional analysis backends.

Why this module exists
----------------------
Every heavy dependency in this tool (tree-sitter, libclang, z3, cppcheck) is
imported behind a bare ``try/except ImportError`` that flips a boolean and
carries on.  That is the right *behaviour* — the tool must still run when a
site has no LLVM install — but historically nothing ever told the operator
which backends were actually live.  A run with every backend missing produced
the same "Needs review" wording as a full-strength run, so the two were
indistinguishable in the output and the numbers could not be interpreted.

This module centralises the probing so that:

* a single banner can be logged at run start (``format_banner``),
* each defect can record the depth it was analysed at (``analysis_depth``),
* withheld fixes and Needs-review verdicts can say *why* in the comment
  (``depth_note``), instead of implying the analyser understood the code and
  still found nothing.

Probes are cached: the cost is paid once per process.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Dict, List, NamedTuple, Optional

__all__ = [
    "Capability", "probe", "format_banner", "analysis_depth",
    "depth_note", "missing_backends", "reset_cache",
    "find_cppcheck_bin", "cppcheck_probe_timeout",
    "CPPCHECK_PROBE_TIMEOUT_DEFAULT",
    "DEPTH_FULL", "DEPTH_PARTIAL", "DEPTH_MINIMAL",
]


class Capability(NamedTuple):
    """One optional backend and whether it is usable in this process."""
    key: str            # short id, e.g. 'z3'
    label: str          # human name for the banner
    available: bool     # import/probe succeeded
    detail: str         # version, path, or the reason it is unavailable
    critical: bool      # True when its absence materially weakens analysis

    @property
    def status(self) -> str:
        if self.available:
            return "OK"
        return "MISSING" if self.critical else "disabled"


#: Analysis-depth labels, ordered weakest → strongest.
DEPTH_MINIMAL = "minimal"    # regex only: no AST, no type info, no proofs
DEPTH_PARTIAL = "partial"    # AST available, but proof/type backends missing
DEPTH_FULL = "full"          # every critical backend live

_CACHE: Optional[Dict[str, Capability]] = None

#: Seconds to wait for ``cppcheck --version`` before declaring it unavailable.
#: cppcheck is a native binary, so startup is fast; the default is still
#: generous because slow disks / antivirus scanning on Windows can stall any
#: first process spawn.
CPPCHECK_PROBE_TIMEOUT_DEFAULT = 10.0


def cppcheck_probe_timeout() -> float:
    """Seconds to allow for ``cppcheck --version`` before giving up.

    Override with ``COVERITY_CPPCHECK_PROBE_TIMEOUT`` (seconds, float); the
    legacy ``COVERITY_SEMGREP_PROBE_TIMEOUT`` name is still honoured so old
    scripts keep working.  A non-numeric or sub-second value falls back to the
    default.  Set ``COVERITY_DISABLE_CPPCHECK=1`` (or the legacy
    ``COVERITY_DISABLE_SEMGREP=1``) to skip the probe entirely.
    """
    for var in ("COVERITY_CPPCHECK_PROBE_TIMEOUT",
                "COVERITY_SEMGREP_PROBE_TIMEOUT"):
        raw = os.environ.get(var, "").strip()
        if raw:
            try:
                return max(1.0, float(raw))
            except ValueError:
                pass
    return CPPCHECK_PROBE_TIMEOUT_DEFAULT


def semgrep_probe_timeout() -> float:
    """Deprecated alias for :func:`cppcheck_probe_timeout`.

    Kept so callers of the old semgrep-backed API do not break; new code
    should call :func:`cppcheck_probe_timeout` directly.
    """
    return cppcheck_probe_timeout()


def find_cppcheck_bin() -> Optional[str]:
    """Locate the cppcheck executable used for corroboration.

    cppcheck replaces semgrep as the corroboration backend: it runs fully
    offline (its rules ship inside the binary — no registry, no network) and
    is small enough to bundle inside the frozen Windows exe.  Resolution
    order:

    1. ``COVERITY_CPPCHECK_BIN`` — explicit path to the binary.
    2. ``cppcheck`` on PATH — the official install (package manager, official
       release archive, etc.).
    3. Frozen-app locations (PyInstaller): ``cppcheck.exe`` next to the
       executable, inside ``sys._MEIPASS``, and the ``cppcheck/Cppcheck/``
       data bundled by ``CoverityTool.spec``.
    4. The ``cppcheck`` pip wheel: ``import cppcheck`` exposes the bundled
       official binary via ``cppcheck.get_cppcheck_dir()`` — no PATH entry
       needed, which is what makes corroboration work in a plain venv and in
       the frozen exe.

    Returns an absolute path string, or ``None`` when no usable binary exists.
    """
    exe_name = "cppcheck.exe" if os.name == "nt" else "cppcheck"
    override = os.environ.get("COVERITY_CPPCHECK_BIN", "").strip()
    if override:
        # An explicit-but-broken override must not silently fall through to
        # a different binary; surface it by returning None.
        if os.path.isfile(override):
            return os.path.abspath(override)
        return None
    found = shutil.which("cppcheck")
    if found:
        return os.path.abspath(found)
    candidates: List[str] = []
    try:
        frozen = bool(getattr(sys, "frozen", False))
    except Exception:
        frozen = False
    if frozen:
        meipass = getattr(sys, "_MEIPASS", None)
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        if meipass:
            candidates.append(os.path.join(meipass, exe_name))
            candidates.append(os.path.join(meipass, "cppcheck", "Cppcheck",
                                           exe_name))
        candidates.append(os.path.join(exe_dir, exe_name))
    try:
        import cppcheck as _cc_wheel  # pip wheel bundles the official binary
        candidates.append(os.path.join(str(_cc_wheel.get_cppcheck_dir()),
                                       exe_name))
    except Exception:
        pass
    for cand in candidates:
        if cand and os.path.isfile(cand):
            return os.path.abspath(cand)
    return None


# --------------------------------------------------------------------------- #
# individual probes
# --------------------------------------------------------------------------- #
def _probe_tree_sitter() -> Capability:
    """tree-sitter drives every AST query; without it extraction is regex."""
    try:
        import tree_sitter  # noqa: F401
    except Exception as exc:
        return Capability("tree_sitter", "tree-sitter (AST)", False,
                          f"import failed: {exc}", True)
    grammars: List[str] = []
    for mod, name in (("tree_sitter_c", "c"), ("tree_sitter_cpp", "cpp")):
        try:
            __import__(mod)
            grammars.append(name)
        except Exception:
            pass
    if not grammars:
        return Capability("tree_sitter", "tree-sitter (AST)", False,
                          "no C/C++ grammar installed", True)
    ver = getattr(__import__("tree_sitter"), "__version__", "?")
    return Capability("tree_sitter", "tree-sitter (AST)", True,
                      f"v{ver}, grammars: {'+'.join(grammars)}", True)


def _probe_libclang() -> Capability:
    """libclang supplies real type/array sizes and macro expansion."""
    try:
        import clang_resolver as _cr
    except Exception as exc:
        return Capability("libclang", "libclang (types/macros)", False,
                          f"clang_resolver import failed: {exc}", True)
    try:
        if _cr._clang_available():
            hint = os.environ.get("LIBCLANG_PATH", "") or "auto-discovered"
            return Capability("libclang", "libclang (types/macros)", True,
                              hint, True)
    except Exception as exc:
        return Capability("libclang", "libclang (types/macros)", False,
                          f"probe raised: {exc}", True)
    return Capability("libclang", "libclang (types/macros)", False,
                      "libclang.dll/.so not found — set LIBCLANG_PATH", True)


def _probe_z3() -> Capability:
    """z3 proves guard safety and off-by-one bounds."""
    try:
        import z3
    except Exception as exc:
        return Capability("z3", "z3 (SMT path proofs)", False,
                          f"import failed: {exc}", True)
    try:
        ver = z3.get_version_string()
    except Exception:
        ver = "?"
    return Capability("z3", "z3 (SMT path proofs)", True, f"v{ver}", True)


def _probe_flow() -> Capability:
    """flow_analysis builds the CFG used for dominance checks."""
    try:
        import flow_analysis  # noqa: F401
    except Exception as exc:
        return Capability("flow", "flow_analysis (CFG)", False,
                          f"import failed: {exc}", True)
    return Capability("flow", "flow_analysis (CFG)", True, "builtin", True)


def _probe_cppcheck() -> Capability:
    """cppcheck is corroborating evidence only, is cached per-file, and is on
    by default.  Disable with COVERITY_DISABLE_CPPCHECK=1 (or the legacy
    COVERITY_DISABLE_SEMGREP=1 / COVERITY_ENABLE_SEMGREP=0/false/no/off
    flags, kept so old scripts keep working)."""
    truthy = ("1", "true", "yes", "on")
    if os.environ.get("COVERITY_DISABLE_CPPCHECK", "").strip().lower() in truthy:
        return Capability("cppcheck", "cppcheck (corroboration)", False,
                          "disabled by COVERITY_DISABLE_CPPCHECK", False)
    if os.environ.get("COVERITY_DISABLE_SEMGREP", "").strip().lower() in truthy:
        return Capability("cppcheck", "cppcheck (corroboration)", False,
                          "disabled by legacy COVERITY_DISABLE_SEMGREP", False)
    enable = os.environ.get("COVERITY_ENABLE_SEMGREP", "").strip().lower()
    if enable and enable not in truthy:
        return Capability("cppcheck", "cppcheck (corroboration)", False,
                          "disabled by legacy COVERITY_ENABLE_SEMGREP=0", False)
    bin_path = find_cppcheck_bin()
    if bin_path is None:
        return Capability(
            "cppcheck", "cppcheck (corroboration)", False,
            "cppcheck not found — pip install cppcheck (bundles the official "
            "binary) or add it to PATH", False)
    timeout = cppcheck_probe_timeout()
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        r = subprocess.run([bin_path, "--version"],
                           capture_output=True, text=True, timeout=timeout,
                           creationflags=creationflags)
    except subprocess.TimeoutExpired:
        # A slow start is not a failure: report it as a probe timeout (not a
        # crash) and tell the operator how to raise the window or opt out.
        return Capability(
            "cppcheck", "cppcheck (corroboration)", False,
            (f"version probe timed out after {timeout:g}s — raise "
             f"COVERITY_CPPCHECK_PROBE_TIMEOUT or set "
             f"COVERITY_DISABLE_CPPCHECK=1 to skip it"), False)
    except OSError as exc:
        return Capability("cppcheck", "cppcheck (corroboration)", False,
                          f"version probe failed to launch: {exc}", False)
    except Exception as exc:  # defensive: a probe must never break a run
        return Capability("cppcheck", "cppcheck (corroboration)", False,
                          f"probe raised: {exc}", False)
    if r.returncode == 0:
        return Capability("cppcheck", "cppcheck (corroboration)", True,
                          (r.stdout or "").strip() or "ok", False)
    return Capability("cppcheck", "cppcheck (corroboration)", False,
                      f"version probe exited with code {r.returncode}", False)


def _probe_simple(key: str, label: str, module: str,
                  critical: bool = False) -> Capability:
    try:
        mod = __import__(module)
    except Exception as exc:
        return Capability(key, label, False, f"import failed: {exc}", critical)
    ver = getattr(mod, "__version__", "") or "installed"
    return Capability(key, label, True, str(ver), critical)


_PROBES = (
    _probe_tree_sitter,
    _probe_libclang,
    _probe_z3,
    _probe_flow,
    _probe_cppcheck,
    lambda: _probe_simple("lxml", "lxml (HTML report parsing)", "lxml"),
    lambda: _probe_simple("openpyxl", "openpyxl (Excel I/O)", "openpyxl"),
    lambda: _probe_simple("zeep", "zeep (Coverity SOAP)", "zeep"),
)


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def probe(force: bool = False) -> Dict[str, Capability]:
    """Return {key: Capability}, probing once and caching the result."""
    global _CACHE
    if _CACHE is None or force:
        found: Dict[str, Capability] = {}
        for fn in _PROBES:
            try:
                cap = fn()
            except Exception as exc:              # a probe must never break a run
                cap = Capability("unknown", "unknown", False,
                                 f"probe crashed: {exc}", False)
            found[cap.key] = cap
        _CACHE = found
    return _CACHE


def reset_cache() -> None:
    """Drop cached probe results (used by tests and after env changes)."""
    global _CACHE
    _CACHE = None


def missing_backends(critical_only: bool = True) -> List[str]:
    """Names of backends that are not usable, for messages and notes."""
    caps = probe()
    return [c.label for c in caps.values()
            if not c.available and (c.critical or not critical_only)]


def analysis_depth() -> str:
    """Classify how much analytical power this process actually has.

    ``full``     every critical backend live — a Needs review verdict here
                 really means the evidence was inconclusive.
    ``partial``  the AST is available but a proof/type backend is missing.
    ``minimal``  no AST: extraction and matching are regex-only.
    """
    caps = probe()
    ts = caps.get("tree_sitter")
    if ts is None or not ts.available:
        return DEPTH_MINIMAL
    critical_missing = [c for c in caps.values() if c.critical and not c.available]
    return DEPTH_FULL if not critical_missing else DEPTH_PARTIAL


def depth_note() -> str:
    """One sentence naming the missing backends, or '' when at full strength.

    Appended to comments so a degraded verdict is never mistaken for a
    confident one.
    """
    depth = analysis_depth()
    if depth == DEPTH_FULL:
        return ""
    missing = missing_backends(critical_only=True)
    if not missing:
        return ""
    joined = ", ".join(missing)
    if depth == DEPTH_MINIMAL:
        return (f"[Reduced analysis: {joined} unavailable, so this verdict "
                f"came from regex matching without an AST. Re-run with the "
                f"full dependency set before treating it as conclusive.]")
    return (f"[Reduced analysis: {joined} unavailable, so type sizes and/or "
            f"path proofs could not be computed for this defect.]")


def format_banner() -> str:
    """Multi-line capability banner for the run log / GUI status pane."""
    caps = probe()
    depth = analysis_depth()
    width = max((len(c.label) for c in caps.values()), default=10)
    lines = ["Analysis backends:"]
    for cap in caps.values():
        lines.append(f"  {cap.label.ljust(width)}  {cap.status:<8} {cap.detail}")
    lines.append(f"  → analysis depth: {depth.upper()}")
    if depth != DEPTH_FULL:
        lines.append("    Install the full requirements.txt for maximum accuracy: "
                     "pip install -r requirements.txt")
    return "\n".join(lines)


if __name__ == "__main__":       # `python capabilities.py` prints the banner
    print(format_banner())
