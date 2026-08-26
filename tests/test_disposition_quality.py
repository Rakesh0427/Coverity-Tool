"""Disposition-comment and proposed-fix quality tests.

These pin the senior-reviewer output contract: the comment reads as code-fact
drive triage text, and the Proposed Fix never exposes machine placeholders,
CWE/CERT code trailers, ``Suggestion:`` noise, or gate meta-notes.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from heuristic_analyzer import analyze_defect  # noqa: E402


def _analyze(checker, code, line, function="f"):
    ctx = {
        "function_code": code,
        "source_code": code,
        "code_start_line": 1,
        "called_function_codes": {},
        "callers": [],
    }
    return analyze_defect(ctx, checker, [], file="src/example.c",
                          line=line, function=function)


# ---------------------------------------------------------------------------
# Proposed Fix quality
# ---------------------------------------------------------------------------
def test_confirm_bug_fix_is_clean_and_specific():
    code = ("void copy(const char *src)\n"
            "{\n"
            "    char name[32];\n"
            "    strncpy(name, src, sizeof(name));\n"
            "    log(name);\n"
            "}\n")
    _cls, _comment, fix, _conf = _analyze("BUFFER_SIZE", code, 4, "copy")
    assert "Suggestion" not in fix
    assert "CWE-" not in fix
    assert "<<ERROR_RETURN>>" not in fix
    assert "/* report failure here */" not in fix
    assert "strncpy(name, src, sizeof(name)-1)" in fix


def test_fp_fix_is_terminal():
    code = ("void copy(char *src)\n"
            "{\n"
            "    char name[16];\n"
            "    memset(name, 0, sizeof(name));\n"
            "    strncpy(name, src, sizeof(name));\n"
            "}\n")
    _cls, _comment, fix, _conf = _analyze("BUFFER_SIZE", code, 4, "copy")
    assert fix == "No fix required."


def test_unknown_error_convention_fix_is_prose():
    """A guard that needs an error path must be described clearly for the
    reviewer instead of leaving an uncompilable placeholder branch."""
    code = ("int divide(int n, int d)\n"
            "{\n"
            "    int r = n / d;\n"
            "    return r;\n"
            "}\n")
    _cls, _comment, fix, _conf = _analyze("DIVIDE_BY_ZERO", code, 3, "divide")
    assert "<<ERROR_RETURN>>" not in fix
    assert "/* report failure here */" not in fix
    assert "guard" in fix.lower()
    assert "error convention" in fix


# ---------------------------------------------------------------------------
# Comment quality
# ---------------------------------------------------------------------------
def test_fp_comment_does_not_carry_cwe_footer_or_confidence_boilerplate():
    code = ("void copy(char *src)\n"
            "{\n"
            "    char name[16];\n"
            "    memset(name, 0, sizeof(name));\n"
            "    strncpy(name, src, sizeof(name));\n"
            "}\n")
    cls, comment, _fix, _conf = _analyze("BUFFER_SIZE", code, 4, "copy")
    assert cls == "False positive"
    assert "High confidence" not in comment
    assert "Reasonably confident" not in comment
    assert "Reference: CWE-" not in comment
    assert "False positive" in comment


def test_intentional_comment_reads_as_intentional():
    code = ("int f(int c)\n"
            "{\n"
            "    switch (c) {\n"
            "    case 1:\n"
            "        step_a();\n"
            "        /* fall through */\n"
            "    case 2:\n"
            "        step_b();\n"
            "        break;\n"
            "    }\n"
            "    return 0;\n"
            "}\n")
    cls, comment, _fix, _conf = _analyze("NO_BREAK", code, 6, "f")
    assert cls == "Intentional"
    assert "intentional" in comment.lower()


def test_comment_does_not_contain_gate_meta_notes():
    code = ("void f(int n)\n"
            "{\n"
            "    int *p = malloc(n * 4);\n"
            "    *p = 7;\n"
            "}\n")
    cls, comment, _fix, _conf = _analyze("FORWARD_NULL", code, 4, "f")
    assert cls == "Bug"
    for noise in ("Proposed fix uses this module",
                  "could not be matched to the module",
                  "Confirm it matches the surrounding code",
                  "Analyst confidence"):
        assert noise not in comment
