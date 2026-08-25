import pytest

from code_extractor import extract_enclosing_function
from cwe_mapping import format_cwe_reference
from heuristic_analyzer import (
    _expert_fix_suggestion,
    _resolve_integer_constant,
    analyze_defect,
)


def _run_analysis(path, line, events, function="check"):
    func_code, start_line, tree = extract_enclosing_function(path, line, "c")
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
        function=function, cid=1, tree=tree)


def test_manual_review_fix_is_not_decorated_as_code():
    assert _expert_fix_suggestion("OVERRUN", {}, "Manual review required.") == "Manual review required."


def test_cwe_reference_does_not_force_web_injection_label_on_native_overrun():
    ref = format_cwe_reference("OVERRUN")
    assert "Injection" not in ref
    assert "Not directly applicable" in ref


def test_resolve_integer_constant_handles_macros_enums_and_casts():
    code = """
#define MAX_CONN 8
static const unsigned LIMIT = MAX_CONN - 1;
enum Priority {
    E_LOW_PRIORITY = 0,
    E_HIGH_PRIORITY,
    E_LAST_PRIORITY = LIMIT,
};
"""
    sources = [code]
    assert _resolve_integer_constant("MAX_CONN", sources) == 8
    assert _resolve_integer_constant("LIMIT", sources) == 7
    assert _resolve_integer_constant("E_HIGH_PRIORITY", sources) == 1
    assert _resolve_integer_constant("(unsigned int)E_LAST_PRIORITY", sources) == 7


def test_nested_overrun_keeps_manual_review_when_inner_index_is_proven_safe(tmp_path):
    code = """
enum Priority {
    E_LOW_PRIORITY = 0,
    E_HIGH_PRIORITY = 1,
    E_MAX_PRIORITY_CONN = 4,
};

enum {
    INVALID_CONN_INDEX = -1,
    TRUE = 1,
    MAX_NUM_ADS_CONNECTIONS = 3,
};

struct ec_row { int b_ec_present; };

void check(void) {
    unsigned int ui_prty_idx = (unsigned int)E_HIGH_PRIORITY;
    int si_conn_prity[E_MAX_PRIORITY_CONN] = {0, 2, 3, 0};
    struct ec_row gs_ec_rpt_tbl[MAX_NUM_ADS_CONNECTIONS + 1];
    if ((si_conn_prity[ui_prty_idx] != INVALID_CONN_INDEX) &&
        (si_conn_prity[ui_prty_idx] <= MAX_NUM_ADS_CONNECTIONS) &&
        (gs_ec_rpt_tbl[si_conn_prity[ui_prty_idx]].b_ec_present == TRUE)) {
    }
}
"""
    path = tmp_path / "nested.c"
    path.write_text(code)
    flagged_line = 22
    events = [
        {"step": 1, "type": "var_decl", "tag": "var_decl",
         "description": 'Variable "si_conn_prity" declared.', "file": str(path),
         "line": 16, "main": False},
        {"step": 2, "type": "overrun-local", "tag": "overrun-local",
         "description": 'Overrunning array "gs_ec_rpt_tbl".', "file": str(path),
         "line": flagged_line, "main": True},
    ]
    classification, comment, fix, confidence = _run_analysis(str(path), flagged_line, events)
    assert classification == "Needs review"
    assert "inner access `si_conn_prity[ui_prty_idx]` resolves with `ui_prty_idx` = 1" in comment
    assert "outer-table bound/check for `gs_ec_rpt_tbl`" in comment
    assert fix == "Manual review required."
