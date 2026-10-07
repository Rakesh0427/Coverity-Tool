"""Tests for the agent-store upload artifacts (dist-store/).

The store will happily accept a stale bundle, and nobody notices until a
downloaded agent behaves differently from the one in the repository. These
tests pin the two things that actually break uploads:

1. **Structure** — the archive root must contain ``.github/agents/*.agent.md``
   (or ``agents/*.agent.md``); a bundle nested under a repo folder name is
   silently ignored, and a second agent would register twice.
2. **Freshness** — the uploaded copy must be byte-identical to the canonical
   ``.github/agents/coverity-finding-analyzer.agent.md`` that VS Code loads.
"""
from __future__ import annotations

import os
import zipfile

import pytest

import build_agent_bundle as bundle

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

pytestmark = pytest.mark.skipif(
    not os.path.isdir(bundle.DIST),
    reason="dist-store/ has not been built (python build_agent_bundle.py)",
)


class TestArtifactsExist:
    def test_standalone_agent_file_is_present(self):
        assert os.path.isfile(bundle.STANDALONE_PATH), \
            "the standalone .agent.md is what most users drag onto the store"

    def test_zip_bundle_is_present_and_within_limit(self):
        assert os.path.isfile(bundle.ZIP_PATH)
        size = os.path.getsize(bundle.ZIP_PATH)
        assert 0 < size < bundle.MAX_UPLOAD_BYTES


class TestZipLayout:
    """The store scans the archive *root* — this is the part that breaks."""

    def test_agent_sits_at_an_accepted_path(self):
        with zipfile.ZipFile(bundle.ZIP_PATH) as archive:
            names = archive.namelist()
        accepted = any(
            name.startswith("agents/") or name.startswith(".github/agents/")
            for name in names)
        assert accepted, f"no agents/*.agent.md or .github/agents/*.agent.md: {names}"
        assert bundle.ZIP_AGENT_PATH in names

    def test_exactly_one_agent(self):
        with zipfile.ZipFile(bundle.ZIP_PATH) as archive:
            agents = [n for n in archive.namelist() if n.endswith(".agent.md")]
        assert agents == [bundle.ZIP_AGENT_PATH], \
            "a second agent file would register twice in the picker"

    def test_nothing_is_nested_under_a_repo_folder(self):
        with zipfile.ZipFile(bundle.ZIP_PATH) as archive:
            for name in archive.namelist():
                assert name.count("/") <= 2, f"unexpectedly deep path: {name}"
                assert not name.startswith("Coverity-Tool/"), \
                    "the store would not find the agent inside a wrapper folder"

    def test_readme_travels_with_the_agent(self):
        with zipfile.ZipFile(bundle.ZIP_PATH) as archive:
            assert bundle.ZIP_README_PATH in archive.namelist()
            readme = archive.read(bundle.ZIP_README_PATH).decode("utf-8")
        # The store listing doubles as the bundle README, so it must tell a
        # downloader what to install and how to try it.
        assert "requirements.txt" in readme
        assert "MCP: List Servers" in readme
        assert bundle.AGENT_NAME in readme
        # The listing must not imply the agent *is* the capability.
        assert "capability" in readme.lower()


class TestFreshness:
    """A stale artifact is the failure mode nobody sees."""

    def test_committed_artifacts_match_the_canonical_agent(self):
        assert bundle.check() == [], (
            "dist-store/ is out of date — run `python build_agent_bundle.py` "
            "and commit the result")

    def test_standalone_copy_is_byte_identical(self):
        with open(bundle.STANDALONE_PATH, encoding="utf-8") as fh:
            standalone = fh.read()
        with open(bundle.CANONICAL_AGENT, encoding="utf-8") as fh:
            canonical = fh.read()
        assert standalone == canonical

    def test_zip_rebuilds_to_the_same_content(self):
        """Content comparison (not byte comparison): timestamps may differ."""
        entries = bundle.build_sources()
        with zipfile.ZipFile(bundle.ZIP_PATH) as archive:
            for name, expected in entries.items():
                assert archive.read(name).decode("utf-8") == expected, \
                    f"{name} inside the ZIP differs from its source"


class TestUploadable:
    def test_canonical_agent_passes_the_builders_validation(self):
        with open(bundle.CANONICAL_AGENT, encoding="utf-8") as fh:
            text = fh.read()
        assert bundle.validate_agent(text) == []

    def test_version_is_declared_and_used_in_the_filename(self):
        assert bundle.AGENT_VERSION
        assert bundle.AGENT_VERSION in os.path.basename(bundle.ZIP_PATH)

    def test_check_detects_a_stale_artifact(self, monkeypatch, tmp_path):
        """Guard the guard: a broken --check would let staleness through."""
        fake_dist = tmp_path / "dist-store"
        fake_dist.mkdir()
        monkeypatch.setattr(bundle, "DIST", str(fake_dist))
        monkeypatch.setattr(bundle, "STANDALONE_PATH",
                            str(fake_dist / bundle.AGENT_NAME))
        monkeypatch.setattr(bundle, "ZIP_PATH",
                            str(fake_dist / bundle.ZIP_NAME))

        problems = bundle.check()
        assert any("missing" in problem for problem in problems)

        # Write a *wrong* agent and confirm it is reported, not accepted.
        with open(bundle.STANDALONE_PATH, "w", encoding="utf-8") as fh:
            fh.write("stale\n")
        monkeypatch.setattr(bundle, "build_sources",
                            lambda: {bundle.ZIP_AGENT_PATH: "fresh\n",
                                     bundle.ZIP_README_PATH: "readme\n"})
        problems = bundle.check()
        assert any("stale" in problem for problem in problems)


class TestListingDocument:
    def test_store_listing_has_the_fields_the_form_asks_for(self):
        with open(os.path.join(REPO_ROOT, "docs", "STORE_LISTING.md"),
                  encoding="utf-8") as fh:
            listing = fh.read()
        for field in ("## Title", "## Short description", "## Long description",
                      "## Tags", "## Requirements", "## What is in the bundle",
                      "## Installation", "## First test"):
            assert field in listing, f"store form field missing: {field}"
        assert bundle.AGENT_NAME in listing
