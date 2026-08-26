"""Expert-disposition regression tests.

Regression for real mis-triages where the tool produced generic,
non-expert comments or the wrong verdict:

1. OVERRUN on a *derived outer* index — ``gs_ec_rpt_tbl[si_conn_prity[i]]``.
   The inner access is in range, but the outer table is indexed by the
   *value* of the inner element; ``<= MAX`` against a table holding exactly
   MAX elements is an off-by-one that a per-line view never sees.
2. OVERRUN whose only subscript sits a line or two below the flagged line
   (a wrapped multi-line statement).  The +/-1-line anchoring rejected the
   subscript and the comment degraded to boilerplate.
3. OVERRUN whose index is pinned by a constant ternary assignment:
   ``idx = cond ? A : B``.  Every value in range proves FP; any value at or
   past the end proves Bug with the exact offending value.
4. STRING_NULL on a function-call line with no local sink: the verdict
   text must quote the flagged statement, not "No concrete path ... may not
   be reachable" boilerplate.
5. cppcheck corroboration must actually change the output: a memory-safety
   hit near the flagged line contradicts a low-confidence false positive
   and corroborates a bug.

cppcheck is faked (subprocess.run monkeypatched) — no real install needed.
"""
import os

import pytest

import heuristic_analyzer as ha
from code_extractor import extract_enclosing_function
from heuristic_analyzer import analyze_defect


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# The user's case-1 shape: inner loop counter is capped by the loop bound;
# the *outer* table is indexed by the inner element's value with an
# inclusive ``<=`` against the table's own size.
OVERRUN_BASE = """typedef enum {{
    E_MAX_PRIORITY_CONN = 7,
    MAX_NUM_ADS_CONNECTIONS = 8
}} ATS_CORE_IFACE_TYPES;

#define INVALID_CONN_INDEX  (-1)
#define TRUE                1

typedef struct {{
    unsigned char b_ec_present;
}} s_ec_rpt_t;

s_ec_rpt_t gs_ec_rpt_tbl[{tbl}];

void fnadsc_rptmgr_process_ec_rpt(void)
{{
    short si_conn_prity[7];
    unsigned int ui_prty_idx;

    for (ui_prty_idx = 0; ui_prty_idx < (unsigned int)E_MAX_PRIORITY_CONN; ui_prty_idx++)
    {{
        if ((si_conn_prity[ui_prty_idx] != INVALID_CONN_INDEX) &&
            (si_conn_prity[ui_prty_idx] <= {chk}) &&
            (gs_ec_rpt_tbl[si_conn_prity[ui_prty_idx]].b_ec_present == TRUE))
        {{
            gs_ec_rpt_tbl[si_conn_prity[ui_prty_idx]].b_ec_present = 1;
        }}
    }}
}}
"""

# The user's case-2 shape: wrapped multi-line statement whose only
# subscript sits two lines below the flagged line; the index is pinned by
# a constant ternary assignment; the array lives in a struct declared
# outside the extracted function.
USERDATA_BASE = """typedef unsigned int DWORD;
typedef struct
{{
    unsigned char abyUserDataSegSize[4];
}} t_dendcnf_t;
typedef struct
{{
    t_dendcnf_t dEndCnf;
}} t_dpd_t;
typedef struct
{{
    t_dpd_t m_dpdData;
}} t_dsiPrimitive_t;
static DWORD fnParseUserData(void *params, t_dsiPrimitive_t *dpDsiPrimitive, DWORD segSize)
{{
    (void)params; (void)dpDsiPrimitive; (void)segSize;
    return 0;
}}
DWORD fnCM_Parse_EndCnf(t_dsiPrimitive_t *dpDsiPrimitive, void *upUserDataParams)
{{
    DWORD dwVarOffset;
    dwVarOffset = (upUserDataParams != NULL) ? 0 : {val};
    return fnParseUserData(upUserDataParams, dpDsiPrimitive,
            &dpDsiPrimitive->m_dpdData.dEndCnf.abyUserDataSegSize[dwVarOffset]);
}}
"""

# The user's case-3 shape: STRING_NULL flagged on a call line; the flagged
# argument's string is produced cross-function, no local sink exists.
STRING_NULL_SRC = """static int fnCM_proc_contact_ind(void *pReq, int port)
{
    (void)pReq; (void)port;
    return 0;
}

int fnCM_LS_Listen_State(void)
{
    int contactResult;
    t_contact_request smContactRequest;

    contactResult = fnCM_proc_contact_ind(&smContactRequest,
                  DSI_PORT_ID::byADMIN_PORT);

    return contactResult;
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_cppcheck(monkeypatch):
    """Deterministic default: cppcheck backend off, state clean."""
    ha._CPPCHECK_AVAILABLE = None
    ha._CPPCHECK_CACHE.clear()
    monkeypatch.setenv("COVERITY_DISABLE_CPPCHECK", "1")
    yield
    ha._CPPCHECK_AVAILABLE = None
    ha._CPPCHECK_CACHE.clear()


def _write(tmp_path, text, name="case.c"):
    path = tmp_path / name
    path.write_text(text)
    return str(path)


def _line_of(text, needle):
    for i, l in enumerate(text.splitlines(), 1):
        if needle in l:
            return i
    raise AssertionError(f"line not found in fixture: {needle!r}")


def _run(path, line, checker, function, events):
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
        context, checker, events, sub_checker="", file=path, line=line,
        function=function, cid=42, tree=tree)


def _overrun_events(path, line):
    return [
        {"step": 1, "type": "overrun-local", "tag": "overrun-local",
         "description": "Overrunning array at the flagged access.",
         "file": path, "line": line, "main": True},
    ]


def _enable_cppcheck(monkeypatch):
    monkeypatch.setattr(ha, "_cppcheck_binary", lambda: "/usr/bin/cppcheck")
    monkeypatch.setattr(ha, "_cppcheck_enabled", lambda: True)


def _fake_cppcheck(monkeypatch, hits):
    """hits: list of (line, rule) -> cppcheck --template output."""
    out = "\n".join(f"{ln}|{rule}|error|cppcheck hit on line {ln}"
                    for ln, rule in hits)

    def _run(cmd, **kwargs):
        class _R:
            returncode = 0
            stdout = out
            stderr = ""
        return _R()

    monkeypatch.setattr(ha.subprocess, "run", _run)


# ---------------------------------------------------------------------------
# 1. Derived outer index: the off-by-one the per-line view misses
# ---------------------------------------------------------------------------

def test_derived_outer_off_by_one_is_bug(tmp_path):
    """`gs_ec_rpt_tbl[si_conn_prity[i]]` with `<= MAX` and an 8-element
    table: the inner access is capped in range, but the outer derived
    index admits 8 — one past the end.  Must be Bug, naming the table,
    with an anchored ``<=`` to ``<`` fix."""
    src = OVERRUN_BASE.format(tbl="8", chk="ATS_CORE_IFACE_TYPES::MAX_NUM_ADS_CONNECTIONS")
    path = _write(tmp_path, src, "priority.c")
    flag = _line_of(src, "si_conn_prity[ui_prty_idx] != INVALID_CONN_INDEX")
    chk_line = _line_of(src, "MAX_NUM_ADS_CONNECTIONS) &&")
    try:
        cls, comment, fix, conf = _run(
            path, flag, "OVERRUN", "fnadsc_rptmgr_process_ec_rpt",
            _overrun_events(path, flag))
    finally:
        os.unlink(path)
    assert cls == "Bug"
    # The comment must name the outer table and its size, not just the inner.
    assert "gs_ec_rpt_tbl" in comment
    assert "8 elements" in comment
    # It must point at the inclusive check that admits the offending value.
    assert f"line {chk_line}" in comment
    # The fix must be anchored to that check: <= becomes <.
    assert fix != "Manual review required."
    assert f"Change the check at line {chk_line}" in fix
    assert "< ATS_CORE_IFACE_TYPES::MAX_NUM_ADS_CONNECTIONS" in fix
    assert ">=" not in fix  # no invented new bound


def test_derived_outer_verified_safe_stays_fp_with_fact(tmp_path):
    """Same shape, but the inclusive check caps the derived value inside
    the table: the finding is a false positive — and the FP comment must
    state the outer verification, not only the inner loop bound."""
    src = OVERRUN_BASE.format(tbl="5", chk="4")
    path = _write(tmp_path, src, "priority_safe.c")
    flag = _line_of(src, "si_conn_prity[ui_prty_idx] != INVALID_CONN_INDEX")
    try:
        cls, comment, fix, conf = _run(
            path, flag, "OVERRUN", "fnadsc_rptmgr_process_ec_rpt",
            _overrun_events(path, flag))
    finally:
        os.unlink(path)
    assert cls == "False positive"
    assert "gs_ec_rpt_tbl" in comment
    # The outer fact, not just the inner loop-bound fact.
    assert "derived index" in comment
    assert "5-element" in comment or "5 elements" in comment


def test_derived_outer_unresolvable_size_blocks_fp(tmp_path):
    """The outer table's size cannot be resolved from the available
    sources: an FP verdict is not supportable.  The comment must name the
    table and ask for its size instead of dismissing the finding."""
    src = OVERRUN_BASE.format(tbl="TBL_TOP", chk="4")  # TBL_TOP defined nowhere
    path = _write(tmp_path, src, "priority_unres.c")
    flag = _line_of(src, "si_conn_prity[ui_prty_idx] != INVALID_CONN_INDEX")
    try:
        cls, comment, fix, conf = _run(
            path, flag, "OVERRUN", "fnadsc_rptmgr_process_ec_rpt",
            _overrun_events(path, flag))
    finally:
        os.unlink(path)
    assert cls != "False positive"
    assert cls == "Needs review"
    assert "gs_ec_rpt_tbl" in comment


# ---------------------------------------------------------------------------
# 2. Multi-line statement: subscript below the flagged line
# ---------------------------------------------------------------------------

def test_multiline_statement_subscript_is_bug_with_real_names(tmp_path):
    """The flagged line is the first line of a wrapped call; the only
    subscript is two lines down.  The comment must name the real array
    (through the pointer chain) and the real index, and the fix must be
    anchored — not 'Manual review required.'"""
    src = USERDATA_BASE.format(val="4")
    path = _write(tmp_path, src, "userdata.c")
    flag = _line_of(src, "return fnParseUserData(upUserDataParams,")
    try:
        cls, comment, fix, conf = _run(
            path, flag, "OVERRUN", "fnCM_Parse_EndCnf",
            _overrun_events(path, flag))
    finally:
        os.unlink(path)
    assert cls == "Bug"
    assert "abyUserDataSegSize" in comment
    assert "dwVarOffset" in comment
    # The ternary's value set is the expert fact.
    assert "possible values: 0, 4" in comment
    assert "4" in comment and "beyond" in comment
    # Anchored, unsigned-aware fix (DWORD: no `< 0` clause).
    assert fix != "Manual review required."
    assert "dwVarOffset >= (int)(sizeof(" in fix
    assert "< 0" not in fix


def test_ternary_all_values_in_range_is_fp(tmp_path):
    """Same fixture, `? 0 : 3` against a 4-element array: every possible
    value is in range — false positive, listing the values."""
    src = USERDATA_BASE.format(val="3")
    path = _write(tmp_path, src, "userdata_safe.c")
    # Flag the subscript line itself: exercises the AST path, whose decl
    # lookup must fall back to the file-level sources for the struct size.
    flag = _line_of(src, "abyUserDataSegSize[dwVarOffset]")
    try:
        cls, comment, fix, conf = _run(
            path, flag, "OVERRUN", "fnCM_Parse_EndCnf",
            _overrun_events(path, flag))
    finally:
        os.unlink(path)
    assert cls == "False positive"
    assert "possible values: 0, 3" in comment
    assert "abyUserDataSegSize" in comment


# ---------------------------------------------------------------------------
# 3. STRING_NULL on a call line with no local sink
# ---------------------------------------------------------------------------

def test_string_null_call_line_quotes_flagged_statement(tmp_path):
    """The user's case-3: STRING_NULL on a function-call line, no local
    sink.  The disposition must quote the flagged statement — never the
    'No concrete path ... may not be reachable' boilerplate, never a
    placeholder subject like `the source data`."""
    path = _write(tmp_path, STRING_NULL_SRC, "listen.c")
    flag = _line_of(STRING_NULL_SRC, "fnCM_proc_contact_ind(&smContactRequest,")
    events = [
        {"step": 1, "type": "string_null", "tag": "string_null",
         "description": 'String "smContactRequest.szName" might not be '
                        "NUL-terminated.",
         "file": path, "line": flag, "main": True},
    ]
    try:
        cls, comment, fix, conf = _run(
            path, flag, "STRING_NULL", "fnCM_LS_Listen_State", events)
    finally:
        os.unlink(path)
    assert "No concrete path" not in comment
    assert "the source data" not in comment
    # The flagged statement (completed across its two lines) is quoted.
    assert "Flagged code:" in comment
    assert "fnCM_proc_contact_ind(&smContactRequest" in comment
    assert "DSI_PORT_ID::byADMIN_PORT" in comment


# ---------------------------------------------------------------------------
# 4. cppcheck corroboration changes the output
# ---------------------------------------------------------------------------

def test_cppcheck_hit_corroborates_bug(tmp_path, monkeypatch):
    """A memory-safety cppcheck hit at the flagged line must be cited in
    the Bug comment — the backend must be visible in the disposition."""
    monkeypatch.delenv("COVERITY_DISABLE_CPPCHECK", raising=False)
    src = OVERRUN_BASE.format(tbl="8", chk="ATS_CORE_IFACE_TYPES::MAX_NUM_ADS_CONNECTIONS")
    path = _write(tmp_path, src, "priority_cc.c")
    flag = _line_of(src, "si_conn_prity[ui_prty_idx] != INVALID_CONN_INDEX")
    _enable_cppcheck(monkeypatch)
    _fake_cppcheck(monkeypatch, [(flag, "arrayIndexOutOfBounds")])
    try:
        cls, comment, fix, conf = _run(
            path, flag, "OVERRUN", "fnadsc_rptmgr_process_ec_rpt",
            _overrun_events(path, flag))
    finally:
        os.unlink(path)
    assert cls == "Bug"
    assert "cppcheck" in comment
    assert "arrayIndexOutOfBounds" in comment
    assert f"line {flag}" in comment


def test_cppcheck_memory_rule_downgrades_low_confidence_fp(tmp_path, monkeypatch):
    """A memory-safety cppcheck hit near the flagged line contradicts a
    low-confidence false positive: the verdict is demoted to Needs review
    and the disagreement is stated in the comment."""
    monkeypatch.delenv("COVERITY_DISABLE_CPPCHECK", raising=False)
    src = OVERRUN_BASE.format(tbl="5", chk="4")
    path = _write(tmp_path, src, "priority_cc_fp.c")
    flag = _line_of(src, "si_conn_prity[ui_prty_idx] != INVALID_CONN_INDEX")
    _enable_cppcheck(monkeypatch)
    _fake_cppcheck(monkeypatch, [(flag, "bufferAccessOutOfBounds")])
    try:
        cls, comment, fix, conf = _run(
            path, flag, "OVERRUN", "fnadsc_rptmgr_process_ec_rpt",
            _overrun_events(path, flag))
    finally:
        os.unlink(path)
    assert cls == "Needs review"
    assert "cppcheck" in comment
    assert "bufferAccessOutOfBounds" in comment
    assert "contradicts" in comment
