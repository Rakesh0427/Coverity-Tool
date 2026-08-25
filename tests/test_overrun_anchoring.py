"""The analysis side of the 706-vs-710 fix.

The pulled defect has the correct main-event line (710) and events, but the
OVERRUN analyzer used to report the *nearest array subscript* elsewhere in the
function (e.g. ``buf[i]`` at 707) instead of the flagged sink line. It must
anchor on the flagged line and quote the sink call there.
"""
import pytest

from code_extractor import extract_enclosing_function
from heuristic_analyzer import analyze_defect


def _write_c_file(tmp_path):
    code = ["void process_buffer(char *src, int n) {"]
    for i in range(3):
        code.append("    char pad%d[4];" % i)
    code.append("    char buf[10];")
    code.append("    int i;")
    code.append("    for (i = 0; i < n; i++) buf[i] = src[i];")
    code.append("    char dest[8];")
    code.append("    if (n > 0) {")
    code.append("        memcpy(dest, buf, n);")   # line 710 (the sink)
    code.append("    }")
    code.append("}")
    preamble = ["/* line %d */" % i for i in range(1, 701)]
    path = tmp_path / "example.c"
    path.write_text("\n".join(preamble + code) + "\n")
    return str(path)


def _write_direct_subscript_file(tmp_path):
    """The flagged line *is* a subscript: it must still be found and quoted."""
    code = ["void process_buffer(char *src, int n) {"]
    code.append("    char buf[10];")
    code.append("    int i;")
    code.append("    for (i = 0; i < n; i++) buf[i] = src[i];")
    code.append("    char big[4];")
    code.append("    char small[4];")
    code.append("    big[n] = small[n];")   # line 707 (the sink)
    code.append("}")
    preamble = ["/* line %d */" % i for i in range(1, 701)]
    path = tmp_path / "direct.c"
    path.write_text("\n".join(preamble + code) + "\n")
    return str(path)


def _run_analysis(path, line, events):
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
        function="process_buffer", cid=1, tree=tree)


def test_overrun_anchors_on_flagged_sink_line_not_nearest_subscript(tmp_path):
    try:
        import tree_sitter  # noqa: F401
    except ImportError:
        pytest.skip("tree-sitter not installed")
    path = _write_c_file(tmp_path)
    events = [
        {"step": 1, "type": "var_decl", "tag": "var_decl",
         "description": 'Variable "buf" declared.', "file": path,
         "line": 705, "main": False},
        {"step": 2, "type": "overrun-local", "tag": "overrun-local",
         "description": 'Overrunning array "buf".', "file": path,
         "line": 710, "main": True},
    ]
    classification, comment, fix, confidence = _run_analysis(path, 710, events)
    assert "line 710" in comment
    assert "memcpy" in comment
    # The loop-body subscript (line 707) must NOT be what we report.
    assert "line 707" not in comment
    assert "buf[i]" not in comment


def test_overrun_keeps_direct_subscript_at_flagged_line(tmp_path):
    """The proximity constraint must not break the normal direct-subscript case."""
    try:
        import tree_sitter  # noqa: F401
    except ImportError:
        pytest.skip("tree-sitter not installed")
    path = _write_direct_subscript_file(tmp_path)
    events = [
        {"step": 1, "type": "var_decl", "tag": "var_decl",
         "description": 'Variable "big" declared.', "file": path,
         "line": 705, "main": False},
        {"step": 2, "type": "overrun-local", "tag": "overrun-local",
         "description": 'Overrunning array "big".', "file": path,
         "line": 707, "main": True},
    ]
    classification, comment, fix, confidence = _run_analysis(path, 707, events)
    assert classification == "Bug"
    assert "line 707" in comment
    assert "big[n]" in comment


def test_nested_subscript_does_not_receive_single_index_patch():
    """A guard on ``table[index_map[i]]`` cannot be repaired as a guard on i."""
    from heuristic_analyzer import _has_nested_subscript_at_line

    code = """if ((si_conn_prity[ui_prty_idx] != INVALID_CONN_INDEX) &&
    (si_conn_prity[ui_prty_idx] <= MAX_NUM_ADS_CONNECTIONS) &&
    (gs_ec_rpt_tbl[si_conn_prity[ui_prty_idx]].b_ec_present == TRUE)) {
}"""
    assert _has_nested_subscript_at_line(code, line=3, code_start_line=1)
    assert not _has_nested_subscript_at_line(code, line=1, code_start_line=1)


def test_fix_gate_rejects_invented_error_path():
    """A template with ARRAY_SIZE/ERROR must not be displayed as a patch."""
    from heuristic_analyzer import _gate_fix_on_source_evidence

    fix, reason = _gate_fix_on_source_evidence(
        "Suggestion: if (idx < 0 || idx >= ARRAY_SIZE) return ERROR;",
        "void check(int idx) { values[idx] = 0; }", 1, 1, "OVERRUN")
    assert fix == "Manual review required."
    assert "invented placeholder" in reason


def test_fix_gate_rejects_nested_index_patch():
    """An inner-index patch is not a fix for a nested outer-table access."""
    from heuristic_analyzer import _gate_fix_on_source_evidence

    code = "if (table[index_map[i]].present) { }"
    fix, reason = _gate_fix_on_source_evidence(
        "if (i < limit) return;", code, 1, 1, "OVERRUN")
    assert fix == "Manual review required."
    assert "nested index" in reason
