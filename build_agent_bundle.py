#!/usr/bin/env python3
"""
build_agent_bundle.py — produce the agent-store upload artifacts.

The store this is written for accepts either

    * one standalone ``.agent.md`` file, or
    * a ZIP whose *root* contains ``agents/*.agent.md`` or
      ``.github/agents/*.agent.md``   (100 MB limit)

So this script emits both, from the single canonical agent definition, so the
uploaded copy can never drift from the one VS Code actually loads:

    dist-store/coverity-finding-analyzer.agent.md          ← drag this to the store
    dist-store/coverity-finding-analyzer-v1.0.0.zip        ← or drag this (agent + README)

Usage
-----
    python build_agent_bundle.py            # (re)build dist-store/
    python build_agent_bundle.py --check    # verify it is up to date, exit 1 if not

``--check`` is what CI and tests/test_agent_bundle.py use: it compares the
contents of the committed artifacts with the canonical files instead of
regenerating them, so a stale upload is caught instead of shipped.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import zipfile
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))

#: Filename of the one agent this pack ships (kept in sync with the tests).
AGENT_NAME = "coverity-finding-analyzer.agent.md"

#: The single source of truth for the agent — the file VS Code loads.
CANONICAL_AGENT = os.path.join(HERE, ".github", "agents", AGENT_NAME)

#: Prose that ships inside the ZIP as README.md (store listing + install steps).
LISTING = os.path.join(HERE, "docs", "STORE_LISTING.md")

#: Output directory (committed, because the user must be able to download it).
DIST = os.path.join(HERE, "dist-store")

AGENT_VERSION = "1.0.0"

#: Path *inside the ZIP*. The store requires one of these two layouts at the
#: archive root; nesting it under a repo folder name would not be detected.
ZIP_AGENT_PATH = f".github/agents/{AGENT_NAME}"
ZIP_README_PATH = "README.md"

MAX_UPLOAD_BYTES = 100 * 1024 * 1024        # store limit, checked so we never surprise anyone

STANDALONE_PATH = os.path.join(DIST, AGENT_NAME)
ZIP_NAME = f"coverity-finding-analyzer-v{AGENT_VERSION}.zip"
ZIP_PATH = os.path.join(DIST, ZIP_NAME)


# --------------------------------------------------------------------------- #
# Reading the sources
# --------------------------------------------------------------------------- #
def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def validate_agent(text: str) -> List[str]:
    """Cheap sanity checks — a malformed upload is rejected by the store's UI."""
    problems: List[str] = []
    match = re.match(r"^---\n(.*?)\n---\n(.+)", text, re.S)
    if not match:
        problems.append("agent file has no YAML frontmatter")
        return problems
    frontmatter, body = match.group(1), match.group(2)
    if not re.search(r"^description:\s*\S", frontmatter, re.M):
        problems.append("frontmatter is missing the required 'description' field")
    if not re.search(r"^name:\s*\S", frontmatter, re.M):
        problems.append("frontmatter has no 'name' (the picker would show the filename)")
    if len(body) >= 30_000:
        problems.append(f"prompt body is {len(body)} chars (limit 30000)")
    return problems


def build_sources() -> Dict[str, str]:
    """name -> content for every file the artifacts are built from."""
    return {
        ZIP_AGENT_PATH: read_text(CANONICAL_AGENT),
        ZIP_README_PATH: read_text(LISTING),
    }


# --------------------------------------------------------------------------- #
# Building
# --------------------------------------------------------------------------- #
def _zip_bytes(entries: Dict[str, str], compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = compression
            info.external_attr = 0o644 << 16
            archive.writestr(info, entries[name])
    return buffer.getvalue()


def build(verbose: bool = True) -> Tuple[str, str]:
    entries = build_sources()
    payload = _zip_bytes(entries)

    if len(payload) > MAX_UPLOAD_BYTES:
        raise SystemExit(
            f"refusing to write a {len(payload) / 1e6:.1f} MB bundle — the store "
            f"accepts at most {MAX_UPLOAD_BYTES / 1e6:.0f} MB")

    os.makedirs(DIST, exist_ok=True)
    with open(STANDALONE_PATH, "w", encoding="utf-8", newline="") as fh:
        fh.write(entries[ZIP_AGENT_PATH])
    with open(ZIP_PATH, "wb") as fh:
        fh.write(payload)

    if verbose:
        digest = hashlib.sha256(payload).hexdigest()
        print("Built agent-store artifacts")
        print(f"  {os.path.relpath(STANDALONE_PATH, HERE):38} "
              f"{os.path.getsize(STANDALONE_PATH):>7,} B   (drag-and-drop)")
        print(f"  {os.path.relpath(ZIP_PATH, HERE):38} "
              f"{len(payload):>7,} B   (ZIP bundle)")
        print()
        print(f"  ZIP contents ({len(entries)} files):")
        for name in sorted(entries):
            print(f"    {name:38} {len(entries[name].encode('utf-8')):>7,} B")
        print()
        print(f"  sha256 {digest}")
        print(f"  version {AGENT_VERSION}")
    return STANDALONE_PATH, ZIP_PATH


# --------------------------------------------------------------------------- #
# Checking (CI / tests)
# --------------------------------------------------------------------------- #
def check() -> List[str]:
    """Return a list of problems; empty means the committed artifacts are current."""
    problems: List[str] = []
    entries = build_sources()

    if not os.path.isfile(STANDALONE_PATH):
        problems.append(f"missing {os.path.relpath(STANDALONE_PATH, HERE)} — run "
                        f"python build_agent_bundle.py")
    else:
        if read_text(STANDALONE_PATH) != entries[ZIP_AGENT_PATH]:
            problems.append(f"{os.path.relpath(STANDALONE_PATH, HERE)} is stale — "
                            f"the canonical agent changed")

    if not os.path.isfile(ZIP_PATH):
        problems.append(f"missing {os.path.relpath(ZIP_PATH, HERE)} — run "
                        f"python build_agent_bundle.py")
        return problems

    if os.path.getsize(ZIP_PATH) > MAX_UPLOAD_BYTES:
        problems.append("bundle exceeds the store's 100 MB limit")

    try:
        with zipfile.ZipFile(ZIP_PATH) as archive:
            names = archive.namelist()
            if ZIP_AGENT_PATH not in names:
                problems.append(f"bundle does not contain {ZIP_AGENT_PATH}")
            else:
                inside = archive.read(ZIP_AGENT_PATH).decode("utf-8")
                if inside != entries[ZIP_AGENT_PATH]:
                    problems.append("the agent inside the ZIP is stale — the "
                                    "canonical agent changed")
            if ZIP_README_PATH not in names:
                problems.append(f"bundle does not contain {ZIP_README_PATH}")
            elif archive.read(ZIP_README_PATH).decode("utf-8") != entries[ZIP_README_PATH]:
                problems.append("the README inside the ZIP is stale")
            # The store scans the archive root, so no repo-name prefix and no
            # duplicate agent under agents/ either.
            nested = [n for n in names if n.count("/") > 2]
            if nested:
                problems.append(f"unexpectedly nested entries: {nested}")
            agents = [n for n in names if n.endswith(".agent.md")]
            if agents != [ZIP_AGENT_PATH]:
                problems.append(f"expected exactly one agent at {ZIP_AGENT_PATH}, "
                                f"found {agents}")
    except zipfile.BadZipFile:
        problems.append("the bundle is not a valid ZIP")

    return problems


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build_agent_bundle.py",
        description="Build (or verify) the agent-store upload artifacts in dist-store/.")
    parser.add_argument("--check", action="store_true",
                        help="verify the committed artifacts are up to date and exit")
    args = parser.parse_args(argv)

    problems = validate_agent(read_text(CANONICAL_AGENT))
    if problems:
        print("The canonical agent is not uploadable:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2

    if args.check:
        found = check()
        if found:
            print("Agent-store artifacts are out of date:", file=sys.stderr)
            for problem in found:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        print("Agent-store artifacts are up to date.")
        print(f"  {os.path.relpath(STANDALONE_PATH, HERE)}")
        print(f"  {os.path.relpath(ZIP_PATH, HERE)}")
        return 0

    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
