"""Tests for the model-facing report digest.

``coverity_report_text.py`` exists so a language model can read a large Coverity
HTML export cheaply, without the Coverity Tool engine and without third-party
parsing libraries. Two properties matter:

1. **It stays dependency-free.** The moment it imports BeautifulSoup, lxml or
   openpyxl it stops working on a machine that installed nothing — which is the
   whole reason it exists.
2. **It never invents or mangles a fact.** It reports what the HTML says,
   including when the report has a different column order, a missing detail page,
   or no table at all. A model that reads a wrong CID from here will cite it.
"""
from __future__ import annotations

import ast
import io
import json
import os
import subprocess
import sys
import contextlib

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import coverity_report_text as digest          # noqa: E402

SAMPLE = os.path.join(REPO_ROOT, "docs", "sample_report")
SCRIPT = os.path.join(REPO_ROOT, "coverity_report_text.py")

STDLIB_MODULES = {
    "__future__", "argparse", "html", "json", "os", "re", "sys",
}
THIRD_PARTY = {"bs4", "lxml", "openpyxl", "yaml", "requests", "zeep",
               "tree_sitter", "z3", "clang"}


# --------------------------------------------------------------------------- #
# 1. Dependency freedom
# --------------------------------------------------------------------------- #
class TestStaysDependencyFree:
    def test_imports_only_the_standard_library(self):
        tree = ast.parse(open(SCRIPT, encoding="utf-8").read())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not (imported & THIRD_PARTY), \
            f"the digest must not depend on {sorted(imported & THIRD_PARTY)}"
        assert imported <= STDLIB_MODULES, \
            f"unexpected imports: {sorted(imported - STDLIB_MODULES)}"

    def test_never_imports_the_engine(self):
        """It is a reading aid, not an analyser — it must not reach for the engine."""
        source = open(SCRIPT, encoding="utf-8").read()
        for module in ("html_report_parser", "heuristic_analyzer", "context_builder",
                       "vscode_bridge", "coverity_mcp_server", "decision_agent"):
            assert f"import {module}" not in source and f"from {module}" not in source, \
                f"the digest imports {module} — it would then need the engine installed"

    def test_runs_in_a_subprocess_with_no_site_packages(self, tmp_path):
        """Prove it: run with an empty PYTHONPATH and -S (no site-packages)."""
        proc = subprocess.run(
            [sys.executable, "-S", SCRIPT, SAMPLE],
            capture_output=True, text=True, cwd=REPO_ROOT,
            env={**os.environ, "PYTHONPATH": ""}, timeout=120)
        assert proc.returncode == 0, proc.stderr
        assert "CID 1001" in proc.stdout


# --------------------------------------------------------------------------- #
# 2. Facts from the report, unaltered
# --------------------------------------------------------------------------- #
class TestFacts:
    def test_reads_both_sample_defects(self):
        defects = digest.collect(SAMPLE)
        assert [d["cid"] for d in defects] == ["1001", "1002"]
        by_cid = {d["cid"]: d for d in defects}
        assert by_cid["1001"]["checker"] == "BUFFER_SIZE"
        assert by_cid["1001"]["file"] == "sample_src/sample.c"
        assert by_cid["1001"]["function"] == "vulnerable_copy"
        assert by_cid["1002"]["checker"] == "USE_AFTER_FREE"
        assert by_cid["1002"]["file"] == "sample_src/utils.c"

    def test_carries_the_event_trace_the_verdict_depends_on(self):
        by_cid = {d["cid"]: d for d in digest.collect(SAMPLE)}
        assert by_cid["1002"]["detail"]["events"], "no event trace extracted"
        assert "use_after_free" in by_cid["1002"]["detail"]["events"][0].lower()
        assert by_cid["1001"]["detail"]["events"], "no event trace extracted"
        assert "strncpy" in by_cid["1001"]["detail"]["events"][0]

    def test_carries_the_code_excerpt(self):
        by_cid = {d["cid"]: d for d in digest.collect(SAMPLE)}
        assert "free(p)" in by_cid["1002"]["detail"]["code"]
        assert "return p" in by_cid["1002"]["detail"]["code"]
        assert "strncpy" in by_cid["1001"]["detail"]["code"]

    def test_resolves_detail_pages_relative_to_the_index(self):
        by_cid = {d["cid"]: d for d in digest.collect(SAMPLE)}
        assert by_cid["1002"]["detail_page"].endswith("2_ptr.html")

    def test_the_rendered_digest_says_it_is_not_an_analysis(self):
        text = digest.render(digest.collect(SAMPLE), SAMPLE)
        assert "not an analysis" in text, \
            "a model must not mistake report facts for a verdict"
        assert "CID 1001" in text and "CID 1002" in text
        assert "```c" in text, "the code excerpt should be fenced for readability"

    def test_no_verdict_words_appear(self):
        """The digest reports; it never judges. Guard the vocabulary."""
        text = digest.render(digest.collect(SAMPLE), SAMPLE).lower()
        for word in ("false positive", "false-positive", "disposition:", "we recommend"):
            assert word not in text, f"the digest emitted a judgement: {word!r}"


class TestFormatTolerance:
    def _write(self, tmp_path, index_markup, detail_markup="<html><body><pre>"
                                                "10  return p;\n</pre></body></html>"):
        report = tmp_path / "report"
        (report / "Code").mkdir(parents=True)
        (report / "index.html").write_text(index_markup, encoding="utf-8")
        (report / "Code" / "d.html").write_text(detail_markup, encoding="utf-8")
        return report

    def test_column_order_comes_from_the_header_row(self, tmp_path):
        """Real exports vary; the digest must follow the header, not a guess."""
        report = self._write(tmp_path, """
            <table>
              <tr><th>File</th><th>Checker</th><th>CID</th><th>Function</th></tr>
              <tr><td>src/a.c</td><td>LEAK</td>
                  <td><a href="Code/d.html">4242</a></td><td>open_it</td></tr>
            </table>""")
        defect = digest.collect(str(report))[0]
        assert defect["cid"] == "4242"
        assert defect["checker"] == "LEAK"
        assert defect["file"] == "src/a.c"
        assert defect["function"] == "open_it"

    def test_repeated_header_rows_are_not_treated_as_defects(self, tmp_path):
        report = self._write(tmp_path, """
            <table>
              <tr><th>CID</th><th>Checker</th></tr>
              <tr><td><a href="Code/d.html">1</a></td><td>A</td></tr>
              <tr><th>CID</th><th>Checker</th></tr>
              <tr><td><a href="Code/d.html">2</a></td><td>B</td></tr>
            </table>""")
        assert [d["cid"] for d in digest.collect(str(report))] == ["1", "2"]

    def test_missing_detail_page_is_not_a_failure(self, tmp_path):
        report = self._write(tmp_path, """
            <table><tr><th>CID</th><th>Checker</th><th>File</th></tr>
            <tr><td><a href="Code/gone.html">7</a></td><td>X</td><td>a.c</td></tr>
            </table>""")
        (report / "Code" / "d.html").unlink()
        defects = digest.collect(str(report))
        assert defects[0]["cid"] == "7"
        assert defects[0]["detail"]["events"] == []

    def test_accepts_index_html_directly_and_a_lone_detail_page(self):
        assert len(digest.collect(os.path.join(SAMPLE, "index.html"))) == 2
        lone = digest.collect(os.path.join(SAMPLE, "Code", "2_ptr.html"))
        assert lone and lone[0]["detail"]["code"]

    def test_reports_a_missing_report_clearly(self):
        with pytest.raises(FileNotFoundError):
            digest.collect(os.path.join(SAMPLE, "does-not-exist"))


# --------------------------------------------------------------------------- #
# 3. CLI behaviour (what an agent actually invokes)
# --------------------------------------------------------------------------- #
class TestCli:
    def _run(self, *args):
        return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True,
                              text=True, cwd=REPO_ROOT, timeout=120)

    def test_version_is_machine_readable(self):
        proc = self._run("--version")
        assert json.loads(proc.stdout)["version"]
        assert proc.returncode == 0

    def test_cid_filter(self):
        proc = self._run(SAMPLE, "--cid", "1002")
        assert "CID 1002" in proc.stdout and "CID 1001" not in proc.stdout

    def test_limit(self):
        proc = self._run(SAMPLE, "--limit", "1")
        assert "CID 1001" in proc.stdout and "CID 1002" not in proc.stdout

    def test_json_output_is_valid(self):
        payload = json.loads(self._run(SAMPLE, "--json").stdout)
        assert payload["ok"] is True and payload["count"] == 2
        assert payload["defects"][0]["detail"]["code"]

    def test_out_writes_a_file(self, tmp_path):
        target = tmp_path / "digest.txt"
        proc = self._run(SAMPLE, "--out", str(target))
        assert proc.returncode == 0 and proc.stdout == ""
        assert "CID 1001" in target.read_text(encoding="utf-8")

    def test_missing_report_is_a_clean_error(self):
        proc = self._run(str(tmp_path) if False else "/nope/nope")
        assert proc.returncode == 2
        assert "not found" in proc.stderr.lower()

    def test_no_arguments_prints_usage(self):
        proc = self._run()
        assert proc.returncode == 2
        assert "usage" in proc.stderr.lower()

    def test_digest_is_small_enough_to_read_cheaply(self):
        """The point of the digest: fewer tokens than the raw markup."""
        raw = 0
        for root, _dirs, files in os.walk(SAMPLE):
            for name in files:
                raw += os.path.getsize(os.path.join(root, name))
        text = self._run(SAMPLE).stdout
        assert len(text) < raw, "the digest should be smaller than the HTML it summarises"
