"""Ensure the repository's top-level modules are importable during testing."""

import os
import sys
from pathlib import Path

# Semgrep is a corroboration-only backend that is ON by default, but it can
# fetch registry rules (network) and takes seconds per file.  Keep the unit
# suite deterministic and fast: disable it for the whole session.  The
# enable/disable contract itself is pinned in test_capabilities.py, which
# deletes/overrides this variable when it probes the real default.
os.environ["COVERITY_DISABLE_SEMGREP"] = "1"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
