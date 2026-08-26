"""Ensure the repository's top-level modules are importable during testing."""

import os
import sys
from pathlib import Path

# cppcheck is the corroboration backend (replaces semgrep).  It is ON by
# default but runs a native subprocess per source file; keep the unit suite
# deterministic and fast: disable it for the whole session.  The
# enable/disable contract itself is pinned in test_capabilities.py, which
# deletes/overrides this variable when it probes the real default.
# COVERITY_DISABLE_SEMGREP is the legacy alias and is set too, so no old
# script or fixture regresses.
os.environ["COVERITY_DISABLE_CPPCHECK"] = "1"
os.environ["COVERITY_DISABLE_SEMGREP"] = "1"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
