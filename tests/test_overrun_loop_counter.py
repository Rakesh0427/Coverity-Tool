"""Loop-counter OVERRUN triage.

Regression for a real mis-triage: an OVERRUN on ``si_conn_prity[ui_prty_idx]``
inside ``for (ui_prty_idx = (unsigned int)E_HIGH_PRIORITY;
ui_prty_idx <= (unsigned int)E_LOW_PRIORITY; ui_prty_idx++)`` was dismissed as
a false positive because the nearest assignment to the index — the loop
*initialiser* — resolved to 0, "within the declared bounds [0, 6]". The tool
ignored the loop mutation entirely, so the terminal iteration that indexes the
7-element array with 7 was never considered. The comment even repeated the
same (wrong) clause twice.

The initialiser of a mutated counter must never prove safety; the loop's
terminal bound decides.
"""
import os

import pytest

from code_extractor import extract_enclosing_function
from heuristic_analyzer import analyze_defect


def _write(tmp_path, text):
    path = tmp_path / "priority.c"
    path.write_text(text)
    return str(path)


def _run(path, line, function):
    func_code, start_line, tree = extract_enclosing_function(path, line, "c")
    events = [
        {"step": 1, "type": "var_decl", "tag": "var_decl",
         "description": 'Variable "si_conn_prity" declared.', "file": path,
         "line": start_line + 8, "main": False},
        {"step": 2, "type": "overrun-local", "tag": "overrun-local",
         "description": 'Overrunning array "si_conn_prity" at index ui_prty_idx.',
         "file": path, "line": line, "main": True},
    ]
    context = {
        "function_code": func_code,
        "source_code": func_code,
        "code_start_line": start_line,
        "function_tree": tree,
        "called_function_codes": {},
        "callers": [],
    }
    return analyze_defect(
        context, "OVERRUN", events, sub_checker="", file=path, line=line,
        function=function, cid=42, tree=tree)


BASE = """typedef enum {{
    E_HIGH_PRIORITY = 0,
    E_LOW_PRIORITY  = {low}
}} e_conn_prity_t;

#define INVALID_CONN_INDEX  (-1)
#define TRUE                1

typedef struct {{
    unsigned char b_ec_present;
}} s_ec_rpt_t;

s_ec_rpt_t gs_ec_rpt_tbl[5];

void fnadsc_rptmgr_process_ec_rpt(void)
{{
    short si_conn_prity[7];
    unsigned int ui_prty_idx;

    for (ui_prty_idx = (unsigned int)E_HIGH_PRIORITY;
         ui_prty_idx <= (unsigned int)E_LOW_PRIORITY;
         ui_prty_idx++)
    {{
        /* Check if the connection index is valid and has an active contract */
        if ((si_conn_prity[ui_prty_idx] != INVALID_CONN_INDEX) &&
            (si_conn_prity[ui_prty_idx] <= 4) &&
            (gs_ec_rpt_tbl[si_conn_prity[ui_prty_idx]].b_ec_present == TRUE))
        {{
            gs_ec_rpt_tbl[si_conn_prity[ui_prty_idx]].b_ec_present = 1;
        }}
    }}
}}
"""


def _flag_line(text):
    for i, l in enumerate(text.splitlines(), 1):
        if "si_conn_prity[ui_prty_idx] != INVALID_CONN_INDEX" in l:
            return i
    raise AssertionError("flagged access line not found in fixture")


def test_terminal_bound_reaching_array_size_is_bug(tmp_path):
    """The user's case: E_HIGH_PRIORITY = 0 is in range, but the loop runs on
    to E_LOW_PRIORITY = 7 and `si_conn_prity` only has 7 elements — the last
    iteration reads si_conn_prity[7]. Must NOT be dismissed as FP."""
    src = BASE.format(low=7)
    path = _write(tmp_path, src)
    try:
        classification, comment, fix, confidence = _run(
            path, _flag_line(src), "fnadsc_rptmgr_process_ec_rpt")
    finally:
        if os.path.exists(path):
            os.unlink(path)
    assert classification == "Bug"
    assert "reach index 7" in comment
    # The old unsound justification must be gone.
    assert "places `ui_prty_idx` at 0" not in comment


def test_terminal_bound_within_array_size_is_fp(tmp_path):
    """Same shape with E_LOW_PRIORITY = 6: the loop bound genuinely caps the
    counter inside [0, 6], so the finding is a false positive — now proven by
    the loop bound, not by the initialiser."""
    src = BASE.format(low=6)
    path = _write(tmp_path, src)
    try:
        classification, comment, fix, confidence = _run(
            path, _flag_line(src), "fnadsc_rptmgr_process_ec_rpt")
    finally:
        if os.path.exists(path):
            os.unlink(path)
    assert classification == "False positive"
    assert "caps `ui_prty_idx` at 6" in comment
    # No duplicated clause: the same fact must appear once, not twice.
    assert comment.count("within [0, 6] of `si_conn_prity`") <= 1


def test_unresolvable_terminal_bound_is_not_dismissed_as_fp(tmp_path):
    """When the loop bound cannot be resolved from the snippet, the finding
    must not be proven safe from the initialiser alone."""
    src = BASE.format(low="E_PRI_TOP")  # E_PRI_TOP defined nowhere
    path = _write(tmp_path, src)
    try:
        classification, comment, fix, confidence = _run(
            path, _flag_line(src), "fnadsc_rptmgr_process_ec_rpt")
    finally:
        if os.path.exists(path):
            os.unlink(path)
    assert classification in ("Bug", "Needs review")
    assert "places `ui_prty_idx` at 0" not in comment


def test_non_mutated_assignment_still_proves_fp(tmp_path):
    """A plain assignment with no mutation anywhere remains a legitimate
    concrete-index proof (no regression for the classic FP)."""
    src = """void f(void)
{
    short si_conn_prity[7];
    unsigned int ui_prty_idx;

    ui_prty_idx = (unsigned int)2;
    if ((si_conn_prity[ui_prty_idx] != INVALID_CONN_INDEX))
    {
        si_conn_prity[ui_prty_idx] = 1;
    }
}
"""
    path = _write(tmp_path, src)
    try:
        classification, comment, fix, confidence = _run(path, _flag_line(src), "f")
    finally:
        if os.path.exists(path):
            os.unlink(path)
    assert classification == "False positive"
    assert "places `ui_prty_idx` at 2" in comment


def test_numeric_loop_bound_proves_fp(tmp_path):
    """`for (i = 0; i < 7; i++)` over a 7-element array stays FP, proven by
    the loop bound (max reachable index 6) rather than the initialiser."""
    src = """void g(void)
{
    short si_conn_prity[7];
    unsigned int ui_prty_idx;

    for (ui_prty_idx = 0; ui_prty_idx < 7; ui_prty_idx++)
    {
        if ((si_conn_prity[ui_prty_idx] != INVALID_CONN_INDEX))
        {
            si_conn_prity[ui_prty_idx] = 1;
        }
    }
}
"""
    path = _write(tmp_path, src)
    try:
        classification, comment, fix, confidence = _run(path, _flag_line(src), "g")
    finally:
        if os.path.exists(path):
            os.unlink(path)
    assert classification == "False positive"
    assert "caps `ui_prty_idx` at 6" in comment


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
