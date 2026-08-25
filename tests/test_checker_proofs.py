import pytest

from code_extractor import extract_enclosing_function
from heuristic_analyzer import analyze_defect


def _run_analysis(path, checker, line, function="check", events=None):
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
        context, checker, events or [], sub_checker="", file=path, line=line,
        function=function, cid=1, tree=tree)


def test_integer_overflow_false_positive_from_concrete_operands(tmp_path):
    code = """
int check(void) {
    int count = 10;
    int total = count + 4;
    return total;
}
"""
    path = tmp_path / "overflow_fp.c"
    path.write_text(code)
    classification, comment, fix, confidence = _run_analysis(str(path), "INTEGER_OVERFLOW", 4)
    assert classification == "False positive"
    assert "resolves to `count + 4` = 14" in comment
    assert fix == "No fix required."


def test_negative_returns_bug_from_concrete_negative_value(tmp_path):
    code = """
int check(void) {
    int ret = -1;
    char buf[16] = {0};
    buf[ret] = 1;
    return 0;
}
"""
    path = tmp_path / "negative_bug.c"
    path.write_text(code)
    classification, comment, fix, confidence = _run_analysis(str(path), "NEGATIVE_RETURNS", 5)
    assert classification == "Bug"
    assert "resolves to -1" in comment
    # A proven Bug on a named local must yield a patch anchored to that local.
    # This function has no readable error convention (it only ever returns 0),
    # so the error branch is marked for the reviewer rather than invented --
    # but the guard itself is still offered.
    assert "ret" in fix
    assert "if (ret < 0)" in fix
    assert fix != "Manual review required."


def test_divide_by_zero_false_positive_from_concrete_nonzero_divisor(tmp_path):
    code = """
int check(void) {
    int divisor = 4;
    int out = 16 / divisor;
    return out;
}
"""
    path = tmp_path / "div_fp.c"
    path.write_text(code)
    classification, comment, fix, confidence = _run_analysis(str(path), "DIVIDE_BY_ZERO", 4)
    assert classification == "False positive"
    assert "resolves to 4" in comment
    assert fix == "No fix required."


def test_shift_overflow_bug_from_out_of_range_constant(tmp_path):
    code = """
unsigned int check(void) {
    unsigned int value = 1u;
    unsigned int out = value << 32;
    return out;
}
"""
    path = tmp_path / "shift_bug.c"
    path.write_text(code)
    classification, comment, fix, confidence = _run_analysis(str(path), "SHIFT_OVERFLOW", 4)
    assert classification == "Bug"
    assert "shift amount resolves to 32" in comment
    assert "value << 32" in fix


def test_use_after_free_false_positive_when_pointer_reassigned(tmp_path):
    code = """
void check(void) {
    int *p = (int *)malloc(sizeof(int));
    free(p);
    p = (int *)malloc(sizeof(int));
    *p = 1;
}
"""
    path = tmp_path / "uaf_fp.c"
    path.write_text(code)
    classification, comment, fix, confidence = _run_analysis(str(path), "USE_AFTER_FREE", 6)
    assert classification == "False positive"
    assert "assigned a new value" in comment
    assert fix == "No fix required."
