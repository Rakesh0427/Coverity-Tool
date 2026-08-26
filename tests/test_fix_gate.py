"""Regression tests for the fix gate.

The gate used to be a substring blacklist over the whole remediation text
('return ERROR', 'ARRAY_SIZE', 'the pointer', ...).  Because every null-deref
and integer-overflow template contains one of those strings, the gate rejected
the tool's own correctly-interpolated output and reported that a placeholder
would have been required -- which was usually untrue.

These tests pin the replacement contract:

* a stock error path is *substituted*, not rejected;
* only genuinely unresolvable tokens void a patch;
* anchoring to real identifiers is what actually catches generic advice.
"""
import pytest

from fix_gate import (
    ERROR_RETURN_SENTINEL,
    gate_fix,
    has_nested_subscript_at_line,
    infer_error_convention,
    unresolved_placeholders,
)


# --------------------------------------------------------------------------- #
# error-convention inference
# --------------------------------------------------------------------------- #
def test_infers_goto_cleanup_when_function_uses_it():
    code = """
int load(char *buf, int len) {
    char *tmp = malloc(len);
    if (!tmp) {
        goto cleanup;
    }
    memcpy(tmp, buf, len);
cleanup:
    free(tmp);
    return 0;
}
"""
    conv = infer_error_convention(code)
    assert conv.kind == "goto"
    assert conv.statement == "goto cleanup;"
    assert "cleanup" in conv.evidence


def test_infers_negative_return_code():
    code = """
int handle(int idx) {
    if (idx < 0) {
        return -1;
    }
    if (idx > 10) {
        return -1;
    }
    return 0;
}
"""
    conv = infer_error_convention(code)
    assert conv.kind == "return_value"
    assert conv.statement == "return -1;"


def test_infers_project_error_enum():
    code = """
STATUS send_frame(int fd) {
    if (fd < 0) {
        return E_INVALID_HANDLE;
    }
    return E_OK;
}
"""
    conv = infer_error_convention(code)
    assert conv.kind == "return_value"
    assert conv.statement == "return E_INVALID_HANDLE;"


def test_infers_void_return():
    code = "void notify(int id) { if (id < 0) { return; } log(id); }"
    conv = infer_error_convention(code)
    assert conv.kind == "return_void"
    assert conv.statement == "return;"


def test_goto_requires_a_defined_label():
    """A goto with no matching label must not become the convention."""
    code = "int f(int x) { if (x) { goto nowhere; } return -1; }"
    conv = infer_error_convention(code)
    assert conv.kind == "return_value"


def test_unknown_convention_is_not_invented():
    code = "int compute(int a, int b) { return a * b; }"
    conv = infer_error_convention(code)
    assert not conv.known
    assert conv.statement == ""


def test_convention_ignores_commented_out_code():
    """A `return -1;` inside a comment is not the function's contract."""
    code = """
void run(int x) {
    /* legacy: return -1; */
    use(x);
}
"""
    conv = infer_error_convention(code)
    assert conv.kind == "return_void"


def test_convention_falls_back_to_related_functions():
    code = "int helper(int a) { return a + 1; }"
    caller = "int outer(void) { if (bad()) { return -5; } return 0; }"
    conv = infer_error_convention(code, extra_sources=[caller])
    assert conv.statement == "return -5;"
    assert "related function" in conv.evidence


# --------------------------------------------------------------------------- #
# the stock error path is substituted, not rejected
# --------------------------------------------------------------------------- #
def test_stock_return_error_is_rewritten_to_project_convention():
    """The exact case the old blacklist got wrong."""
    code = """
int handle(int idx, char *p) {
    if (!p) {
        return -1;
    }
    values[idx] = 0;
    return 0;
}
"""
    result = gate_fix("if (!p) { return ERROR; }", code, 5, 1, "FORWARD_NULL")
    assert result.accepted
    assert result.adjusted
    assert "return -1;" in result.fix
    assert "return ERROR" not in result.fix
    assert "invented placeholder" not in result.reason


def test_error_overflow_template_is_accepted():
    """Every integer-overflow template used to be rejected outright."""
    code = """
int scale(int count, int factor) {
    if (count < 0) {
        return -1;
    }
    return count * factor;
}
"""
    result = gate_fix(
        "if (count != 0 && factor > INT_MAX / count) return ERROR_OVERFLOW;",
        code, 5, 1, "INTEGER_OVERFLOW")
    assert result.accepted
    assert "return -1;" in result.fix


def test_goto_convention_preferred_over_early_return():
    code = """
int load(char *buf, int len) {
    char *tmp = malloc(len);
    if (!tmp) {
        goto cleanup;
    }
    memcpy(tmp, buf, len);
cleanup:
    free(tmp);
    return 0;
}
"""
    result = gate_fix("if (len > 4096) { return ERROR; }", code, 6, 1, "OVERRUN")
    assert result.accepted
    assert "goto cleanup;" in result.fix


def test_unknown_convention_keeps_the_guard_and_flags_the_branch():
    """An unreadable error path must not discard a valid bounds check.

    Instead of leaving an uncompilable ``/* report failure here */`` marker,
    the proposal restates the real guard and leaves the failure action to the
    reviewer to match to the module's convention.
    """
    code = "int compute(int a, int b) { return a * b; }"
    result = gate_fix("if (a > INT_MAX / b) return ERROR;", code, 1, 1,
                      "INTEGER_OVERFLOW")
    assert result.accepted
    assert "if (a > INT_MAX / b)" in result.fix
    assert "report failure here" not in result.fix
    assert ERROR_RETURN_SENTINEL not in result.fix
    assert "error convention" in result.fix


def test_explicit_sentinel_is_resolved():
    code = "int f(int n) { if (n < 0) { return -7; } return n; }"
    result = gate_fix(f"if (n > 99) {ERROR_RETURN_SENTINEL}", code, 1, 1, "OVERRUN")
    assert result.accepted
    assert "return -7;" in result.fix
    assert ERROR_RETURN_SENTINEL not in result.fix


# --------------------------------------------------------------------------- #
# placeholder detection
# --------------------------------------------------------------------------- #
def test_unsubstituted_format_field_is_a_placeholder():
    assert "{var}" in unresolved_placeholders("if (!{var}) return -1;", "int f(void);")


def test_undefined_macro_is_a_placeholder():
    found = unresolved_placeholders("if (i >= ARRAY_SIZE) return -1;",
                                    "void f(int i) { a[i] = 0; }")
    assert "ARRAY_SIZE" in found


def test_macro_defined_in_source_is_not_a_placeholder():
    code = "#define MAX_CONN 16\nint t[MAX_CONN];"
    assert unresolved_placeholders("if (i >= MAX_CONN) return -1;", code) == []


def test_cwe_annotation_is_not_a_placeholder():
    """Trailing provenance comments are documentation, not code."""
    code = "void f(char *p) { free(p); }"
    assert unresolved_placeholders(
        "free(p); p = NULL;  // CWE-416 CERT MEM30-C", code) == []


def test_question_mark_argument_is_a_placeholder():
    code = "void f(char *dst) { copy(dst); }"
    assert "?" in unresolved_placeholders("if (? > sizeof(dst)) return -1;", code)


def test_gate_rejects_patch_with_undefined_macro():
    result = gate_fix("if (idx >= ARRAY_SIZE) return ERROR;",
                      "void check(int idx) { values[idx] = 0; }", 1, 1, "OVERRUN")
    assert not result.accepted
    assert result.fix == "Manual review required."
    assert "ARRAY_SIZE" in result.reason


# --------------------------------------------------------------------------- #
# anchoring
# --------------------------------------------------------------------------- #
def test_generic_advice_is_rejected_for_lack_of_anchoring():
    code = "void copy_it(char *dst, char *src) { strcpy(dst, src); }"
    result = gate_fix(
        "Add explicit bounds checking before all array and pointer dereferences.",
        code, 1, 1, "OVERRUN")
    assert not result.accepted
    assert "could not be anchored" in result.reason


def test_patch_naming_a_real_local_is_accepted():
    code = "void copy_it(char *dst, char *src) { strcpy(dst, src); }"
    result = gate_fix("strncpy(dst, src, sizeof(dst) - 1);", code, 1, 1,
                      "BUFFER_SIZE")
    assert result.accepted
    assert "dst" in result.fix


def test_prose_mentioning_the_pointer_is_no_longer_auto_rejected():
    """'the pointer' was a blacklist entry; it is ordinary English."""
    code = "void use(char *conn) { if (!conn) return; read(conn); }"
    result = gate_fix("if (!conn) return;  // guard the pointer before use",
                      code, 1, 1, "FORWARD_NULL")
    assert result.accepted


# --------------------------------------------------------------------------- #
# nested subscripts
# --------------------------------------------------------------------------- #
def test_true_nesting_is_detected():
    code = "if (table[index_map[i]].present) { }"
    assert has_nested_subscript_at_line(code, 1, 1)


def test_sibling_subscripts_are_not_nesting():
    """`foo(a[i], b[j])` has two independently boundable indices."""
    code = "memcpy(dst[i], src[j], n);"
    assert not has_nested_subscript_at_line(code, 1, 1)


def test_sibling_subscripts_still_receive_a_patch():
    code = "void f(int i, int n) { char dst[8]; char src[8]; dst[i] = src[i]; }"
    result = gate_fix("if (i >= 8) return;", code, 1, 1, "OVERRUN")
    assert result.accepted


def test_nested_subscript_patch_is_withheld():
    code = "if (table[index_map[i]].present) { }"
    result = gate_fix("if (i < limit) return;", code, 1, 1, "OVERRUN")
    assert not result.accepted
    assert "nested index" in result.reason


# --------------------------------------------------------------------------- #
# dispositions pass through
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text,expected", [
    ("No fix required.", "No fix required."),
    ("No fix required. Optionally silence with an assertion.", "No fix required."),
    ("Manual review required.", "Manual review required."),
])
def test_dispositions_are_not_treated_as_patches(text, expected):
    result = gate_fix(text, "int f(void) { return 0; }", 1, 1, "OVERRUN")
    assert result.fix == expected
    assert not result.accepted


def test_missing_source_reports_missing_source():
    result = gate_fix("if (!p) return -1;", "", 1, 1, "FORWARD_NULL")
    assert result.fix == "Manual review required."
    assert "source for the Coverity event path is unavailable" in result.reason


# --------------------------------------------------------------------------- #
# operand extraction feeding the gate
# --------------------------------------------------------------------------- #
def test_return_keyword_is_not_captured_as_an_operand():
    """`return val << bits` must yield `val`, not the uncompilable
    `sizeof(return val)` the fix template used to emit."""
    from heuristic_analyzer import _extract_binary_operation

    lhs, op, rhs = _extract_binary_operation("return val << bits;", ('<<', '>>'))
    assert lhs == "val"
    assert op == "<<"
    assert rhs == "bits"


def test_plain_assignment_operand_extraction_still_works():
    from heuristic_analyzer import _extract_binary_operation

    lhs, op, rhs = _extract_binary_operation("total = count * factor;", ('*',))
    assert lhs == "count"
    assert rhs == "factor"
