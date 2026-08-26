"""Classification accuracy regression tests.

Each case is a canonical C snippet plus the ground-truth disposition a senior
reviewer would give. They guard the decision pipeline (context building →
weighted evidence → per-checker corrections) against regressions that flip
Bug/False-positive/Intentional verdicts.

These ran as ad-hoc probes while fixing systematic misclassifications:

* regexes corrupted with literal 0x08 bytes (silent no-match)
* `release_function_found` FP evidence fired from the allocator's *expected*
  releaser even when no release call existed (unchecked malloc derefs read as
  "released")
* guard operator derived from the first comparison of a compound condition
  (`i >= 0 && i < 16` assessed with `>=`) instead of the bound comparison
* resource-leak verdict credited a release call that sits on a different path
  than the leaking early return
* uninitialised-variable evidence not scoped to the flagged variable, and
  declaration initialisers (`int x = 0;`) not recognised
* CHECKED_RETURN candidate selection discarding the (void)-cast call on the
  flagged line
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from heuristic_analyzer import analyze_defect  # noqa: E402


def _analyze(checker, code, line, function, events):
    ctx = {
        'function_code': code,
        'code_start_line': 1,
        'called_function_codes': {},
        'callers': [],
    }
    return analyze_defect(ctx, checker, events, file='', line=line, function=function)


# ---------------------------------------------------------------------------
# Code-only cases (Excel mode / no event trace)
# ---------------------------------------------------------------------------
CODE_CASES = [
    # (name, checker, code, line, function, expected)
    ("string_null_strncpy_full_size", "STRING_NULL",
     "void copy_name(const char *src) {\n"
     "    char name[32];\n"
     "    strncpy(name, src, sizeof(name));\n"
     "    log_msg(name);\n"
     "}\n", 3, 'copy_name', 'Bug'),

    ("string_null_strncpy_minus_one", "STRING_NULL",
     "void copy_name(const char *src) {\n"
     "    char name[32];\n"
     "    strncpy(name, src, sizeof(name) - 1);\n"
     "    name[sizeof(name) - 1] = '\\0';\n"
     "    log_msg(name);\n"
     "}\n", 3, 'copy_name', 'False positive'),

    ("buffer_size_strncpy_full_size", "BUFFER_SIZE",
     "void copy_name(const char *src) {\n"
     "    char name[32];\n"
     "    strncpy(name, src, sizeof(name));\n"
     "    log_msg(name);\n"
     "}\n", 3, 'copy_name', 'Bug'),

    ("buffer_size_strcpy_unbounded", "BUFFER_SIZE",
     "void copy_name(const char *src) {\n"
     "    char name[32];\n"
     "    strcpy(name, src);\n"
     "    log_msg(name);\n"
     "}\n", 3, 'copy_name', 'Bug'),

    # Unsigned wrap-around is defined behaviour in C.
    ("int_overflow_unsigned_wrap", "INTEGER_OVERFLOW",
     "uint32_t wrap(uint32_t a, uint32_t b) {\n"
     "    uint32_t r;\n"
     "    r = a * b;\n"
     "    return r;\n"
     "}\n", 3, 'wrap', 'False positive'),

    ("div_zero_no_guard", "DIVIDE_BY_ZERO",
     "int split(int n, int d) {\n"
     "    int r;\n"
     "    r = n / d;\n"
     "    return r;\n"
     "}\n", 3, 'split', 'Bug'),

    ("div_zero_guarded", "DIVIDE_BY_ZERO",
     "int split(int n, int d) {\n"
     "    int r;\n"
     "    if (d != 0)\n"
     "        r = n / d;\n"
     "    else\n"
     "        r = 0;\n"
     "    return r;\n"
     "}\n", 4, 'split', 'False positive'),

    # `i >= 0 && i < 16` is a valid bounds guard — the upper-bound comparison
    # must be assessed with its own operator, not the first one in the text.
    ("overrun_guarded_in_range", "OVERRUN",
     "int table[16];\n"
     "int lookup(int i) {\n"
     "    if (i >= 0 && i < 16)\n"
     "        return table[i];\n"
     "    return -1;\n"
     "}\n", 4, 'lookup', 'False positive'),

    ("overrun_off_by_one", "OVERRUN",
     "int table[16];\n"
     "int lookup(int i) {\n"
     "    if (i >= 0 && i <= 16)\n"
     "        return table[i];\n"
     "    return -1;\n"
     "}\n", 4, 'lookup', 'Bug'),

    ("overrun_loop_terminal_oob", "OVERRUN",
     "int table[16];\n"
     "int scan(void) {\n"
     "    int i;\n"
     "    int s = 0;\n"
     "    for (i = 0; i <= 16; i++)\n"
     "        s += table[i];\n"
     "    return s;\n"
     "}\n", 6, 'scan', 'Bug'),

    ("overrun_loop_bounded", "OVERRUN",
     "int table[16];\n"
     "int scan(void) {\n"
     "    int i;\n"
     "    int s = 0;\n"
     "    for (i = 0; i < 16; i++)\n"
     "        s += table[i];\n"
     "    return s;\n"
     "}\n", 6, 'scan', 'False positive'),

    # Early return between allocation and free is a real leak even though
    # free() exists later in the function.
    ("resource_leak_early_return", "RESOURCE_LEAK",
     "int proc(int n) {\n"
     "    int *p;\n"
     "    p = malloc(n * 4);\n"
     "    if (n < 0)\n"
     "        return -1;\n"
     "    use(p);\n"
     "    free(p);\n"
     "    return 0;\n"
     "}\n", 3, 'proc', 'Bug'),

    # goto-cleanup: every exit reaches the single release point.
    ("resource_leak_goto_cleanup", "RESOURCE_LEAK",
     "int proc(int n) {\n"
     "    int *p;\n"
     "    p = malloc(n * 4);\n"
     "    if (n < 0)\n"
     "        goto done;\n"
     "    if (p == NULL)\n"
     "        goto done;\n"
     "    use(p);\ndone:\n"
     "    free(p);\n"
     "    return 0;\n"
     "}\n", 3, 'proc', 'False positive'),

    # Release on the same path, immediately before the early return.
    ("resource_leak_free_before_return", "RESOURCE_LEAK",
     "int proc(int n) {\n"
     "    int *p;\n"
     "    p = malloc(n * 4);\n"
     "    if (n < 0) {\n"
     "        free(p);\n"
     "        return -1;\n"
     "    }\n"
     "    use(p);\n"
     "    free(p);\n"
     "    return 0;\n"
     "}\n", 3, 'proc', 'False positive'),

    ("forward_null_guarded", "FORWARD_NULL",
     "int init(int n) {\n"
     "    int *p;\n"
     "    p = malloc(n * 4);\n"
     "    if (!p)\n"
     "        return -1;\n"
     "    *p = 7;\n"
     "    return 0;\n"
     "}\n", 6, 'init', 'False positive'),

    # No null check on a malloc result: the canonical FORWARD_NULL bug. The
    # allocator's *expected* releaser must not be read as a null guard or a
    # release that makes the pointer safe.
    ("forward_null_unchecked", "FORWARD_NULL",
     "int init(int n) {\n"
     "    int *p;\n"
     "    p = malloc(n * 4);\n"
     "    *p = 7;\n"
     "    return 0;\n"
     "}\n", 4, 'init', 'Bug'),

    ("reverse_inull_check_after_use", "REVERSE_INULL",
     "int handle(int *p) {\n"
     "    p->value = 1;\n"
     "    if (p == NULL)\n"
     "        return -1;\n"
     "    return 0;\n"
     "}\n", 2, 'handle', 'Bug'),

    ("use_after_free_plain", "USE_AFTER_FREE",
     "void recycle(char *p) {\n"
     "    free(p);\n"
     "    p[0] = 'x';\n"
     "    log(p);\n"
     "}\n", 3, 'recycle', 'Bug'),

    ("use_after_free_reassigned", "USE_AFTER_FREE",
     "void recycle(char *p) {\n"
     "    free(p);\n"
     "    p = malloc(64);\n"
     "    p[0] = 'x';\n"
     "    log(p);\n"
     "}\n", 4, 'recycle', 'False positive'),

    ("neg_ret_checked", "NEGATIVE_RETURNS",
     "int readall(int fd) {\n"
     "    char buf[256];\n"
     "    int n;\n"
     "    n = read(fd, buf, sizeof buf);\n"
     "    if (n < 0)\n"
     "        return -1;\n"
     "    use(buf, n);\n"
     "    return n;\n"
     "}\n", 7, 'readall', 'False positive'),

    # Conditional assignment does not prove initialisation — the flagged path
    # is the one that skips it.
    ("uninit_read_before_assign", "UNINIT",
     "int total(int a) {\n"
     "    int x;\n"
     "    if (a > 100)\n"
     "        x = a;\n"
     "    return x + 1;\n"
     "}\n", 5, 'total', 'Bug'),

    ("uninit_zero_init", "UNINIT",
     "int total(int a) {\n"
     "    int x = 0;\n"
     "    if (a > 100)\n"
     "        x = a;\n"
     "    return x + 1;\n"
     "}\n", 5, 'total', 'False positive'),

    ("uninit_straight_assign", "UNINIT",
     "int total(int a) {\n"
     "    int x;\n"
     "    x = a * 2;\n"
     "    return x + 1;\n"
     "}\n", 4, 'total', 'False positive'),

    ("deadcode_if0", "DEADCODE",
     "void legacy(void) {\n"
     "#if 0\n"
     "    old_call();\n"
     "#endif\n"
     "    new_call();\n"
     "}\n", 3, 'legacy', 'Intentional'),

    ("nobreak_fallthrough_doc", "NO_BREAK",
     "int decode(int c) {\n"
     "    switch (c) {\n"
     "    case 1:\n"
     "        step_a();\n"
     "        /* fall through */\n"
     "    case 2:\n"
     "        step_b();\n"
     "        break;\n"
     "    }\n"
     "    return 0;\n"
     "}\n", 5, 'decode', 'Intentional'),

    ("checked_return_discarded_critical", "CHECKED_RETURN",
     "int pump(int fd) {\n"
     "    char buf[256];\n"
     "    read(fd, buf, sizeof buf);\n"
     "    use(buf);\n"
     "    return 0;\n"
     "}\n", 3, 'pump', 'Bug'),

    # Explicit (void) cast on the flagged line documents intent to ignore.
    ("checked_return_void_cast", "CHECKED_RETURN",
     "int pump(int fd) {\n"
     "    char buf[256];\n"
     "    (void)fflush(stdin);\n"
     "    use(buf);\n"
     "    return 0;\n"
     "}\n", 3, 'pump', 'Intentional'),
]


@pytest.mark.parametrize("name,checker,code,line,function,expected", CODE_CASES,
                         ids=[c[0] for c in CODE_CASES])
def test_code_only_classification(name, checker, code, line, function, expected):
    cls, _comment, _fix, _conf = _analyze(checker, code, line, function, [])
    assert cls == expected, f"{name}: got {cls}, expected {expected}"


# ---------------------------------------------------------------------------
# Event-trace cases (HTML report mode)
# ---------------------------------------------------------------------------
EVENT_CASES = [
    ("ev_overrun_confirmed_oob", "OVERRUN",
     "int table[50];\n"
     "int lookup(int i) {\n"
     "    if (i >= 0)\n"
     "        return table[i];\n"
     "    return -1;\n"
     "}\n", 4, 'lookup', 'Bug',
     [{'type': 'var_decl', 'description': 'Declaring variable "i".'},
      {'type': 'overrun_local',
       'description': 'Overrunning array "table" of 50 bytes at byte offset 204 '
                      'using index "i" (which evaluates to 50).'}]),

    # A concrete trace index that contradicts a dominating textual guard is
    # only possible if the guard is not actually on the traced path — the
    # path-specific trace wins.
    ("ev_overrun_guard_contradicted_by_trace", "OVERRUN",
     "int table[50];\n"
     "int lookup(int i) {\n"
     "    if (i >= 0 && i < 50)\n"
     "        return table[i];\n"
     "    return -1;\n"
     "}\n", 4, 'lookup', 'Bug',
     [{'type': 'overrun_local',
       'description': 'Overrunning array "table" of 50 bytes at byte offset 204 '
                      'using index "i" (which evaluates to 50).'}]),

    ("ev_forward_null_confirmed", "FORWARD_NULL",
     "int init(int n) {\n"
     "    int *p;\n"
     "    p = malloc(n * 4);\n"
     "    if (n > 0)\n"
     "        *p = 7;\n"
     "    return 0;\n"
     "}\n", 5, 'init', 'Bug',
     [{'type': 'var_deref_op', 'description': 'Dereferencing pointer "p".'},
      {'type': 'null_return', 'description': '"malloc" may return NULL.'},
      {'type': 'var_deref_op', 'description': 'Pointer "p" has value NULL.'}]),

    ("ev_string_null_strncpy", "STRING_NULL",
     "void copy_name(const char *src) {\n"
     "    char name[32];\n"
     "    strncpy(name, src, sizeof(name));\n"
     "    log_msg(name);\n"
     "}\n", 3, 'copy_name', 'Bug',
     [{'type': 'string_not_null_terminated',
       'description': 'Calling "strncpy" with a maximum size argument of 32 bytes '
                      'on destination array "name" of size 32 bytes might leave the '
                      'destination string unterminated.'}]),

    ("ev_integer_overflow_unsigned", "INTEGER_OVERFLOW",
     "uint32_t wrap(uint32_t a, uint32_t b) {\n"
     "    uint32_t r;\n"
     "    r = a * b;\n"
     "    return r;\n"
     "}\n", 3, 'wrap', 'False positive',
     [{'type': 'integer_overflow',
       'description': 'Multiplication "a * b" may overflow "uint32_t".'}]),

    ("ev_resource_leak", "RESOURCE_LEAK",
     "int proc(int n) {\n"
     "    int *p;\n"
     "    p = malloc(n * 4);\n"
     "    if (n < 0)\n"
     "        return -1;\n"
     "    use(p);\n"
     "    free(p);\n"
     "    return 0;\n"
     "}\n", 3, 'proc', 'Bug',
     [{'type': 'leak', 'description': 'Leaking "p"; this is a memory leak.'}]),

    ("ev_neg_ret_checked", "NEGATIVE_RETURNS",
     "int readall(int fd) {\n"
     "    char buf[256];\n"
     "    int n;\n"
     "    n = read(fd, buf, sizeof buf);\n"
     "    if (n < 0)\n"
     "        return -1;\n"
     "    use(buf, n);\n"
     "    return n;\n"
     "}\n", 7, 'readall', 'False positive',
     [{'type': 'negative_return', 'description': '"read" may return a negative error code.'}]),
]


@pytest.mark.parametrize("name,checker,code,line,function,expected,events", EVENT_CASES,
                         ids=[c[0] for c in EVENT_CASES])
def test_event_trace_classification(name, checker, code, line, function, expected, events):
    cls, _comment, _fix, _conf = _analyze(checker, code, line, function, events)
    assert cls == expected, f"{name}: got {cls}, expected {expected}"


# ---------------------------------------------------------------------------
# Leak-path scanner unit checks
# ---------------------------------------------------------------------------
from decision_agent import analyze_leak_exits  # noqa: E402


def test_leak_scanner_early_return_leaks():
    code = ("int proc(int n) {\n"
            "    int *p;\n"
            "    p = malloc(n * 4);\n"
            "    if (n < 0)\n"
            "        return -1;\n"
            "    use(p);\n"
            "    free(p);\n"
            "    return 0;\n"
            "}\n")
    facts = analyze_leak_exits(code, 'p', 'free', 3, 1)
    assert facts['has_exit']
    assert facts['leak_exits'] == [5]


def test_leak_scanner_goto_cleanup_clean():
    code = ("int proc(int n) {\n"
            "    int *p;\n"
            "    p = malloc(n * 4);\n"
            "    if (n < 0)\n"
            "        goto done;\n"
            "    if (p == NULL)\n"
            "        goto done;\n"
            "    use(p);\ndone:\n"
            "    free(p);\n"
            "    return 0;\n"
            "}\n")
    facts = analyze_leak_exits(code, 'p', 'free', 3, 1)
    assert facts['has_exit']
    assert facts['leak_exits'] == []
    assert facts['all_exits_clear']


def test_leak_scanner_release_before_return_clean():
    code = ("int proc(int n) {\n"
            "    int *p;\n"
            "    p = malloc(n * 4);\n"
            "    if (n < 0) {\n"
            "        free(p);\n"
            "        return -1;\n"
            "    }\n"
            "    use(p);\n"
            "    free(p);\n"
            "    return 0;\n"
            "}\n")
    facts = analyze_leak_exits(code, 'p', 'free', 3, 1)
    assert facts['leak_exits'] == []
    assert facts['all_exits_clear']


def test_leak_scanner_no_alloc_returns_none():
    assert analyze_leak_exits("int f(void) { return 0; }", 'p', 'free', 0, 1) is None
    assert analyze_leak_exits("int f(void) { return 0; }", '', 'free', 1, 1) is None
