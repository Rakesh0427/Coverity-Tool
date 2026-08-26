"""Accuracy benchmark built from the human-reviewed CSV export.

`ATS_CORE_EPP_Coverity_Findings_V2.csv` carries 143 findings that a human
reviewer already dispositioned (119 False Positive / 24 True Positive).  The
real sources are not in this repo, so each row's disposition comment was read
as a *code pattern* and distilled into a self-contained C snippet with the
human verdict as ground truth.  These cases pin the analyzer to the verdicts
the review team actually gave.

Pattern coverage (CSV row counts in parentheses):

True positives (24):
  * OVERRUN off-by-one: `idx <= MAX` guard with `arr[MAX]` (≈15)
  * OVERRUN else-branch: access executed only when the bounds check failed (2)
  * OVERRUN unchecked parameter indexing a global array (4)
  * OVERRUN memcpy that proceeds after only reporting a fault (2)
  * REVERSE_INULL dereference before the NULL check (1)

False positives (119):
  * BUFFER_SIZE memset-pre-zeroed destination before strncpy (47)
  * BUFFER_SIZE fixed-width struct field copied with its exact size (9)
  * BUFFER_SIZE explicit length guard before the copy (4)
  * BUFFER_SIZE strlen(src)+1 copy count (1)
  * BUFFER_SIZE destination larger than the copied payload (≈20)
  * OVERRUN zero-initialised buffer, index resolvable in range (≈10)
  * OVERRUN strict bounds guard `< size` (several)
  * INTEGER_OVERFLOW operand validated by a range guard (5)
  * REVERSE_INULL pointer checked before use (2)
  * ARRAY_VS_SINGLETON `&obj[0]` first-element alias (1)
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from heuristic_analyzer import analyze_defect  # noqa: E402


def _analyze(checker, code, line, function):
    ctx = {
        'function_code': code,
        'source_code': code,
        'code_start_line': 1,
        'called_function_codes': {},
        'callers': [],
    }
    return analyze_defect(ctx, checker, [], file='', line=line, function=function)


CASES = [
    # ------------------------------------------------------------------
    # True positives (human-confirmed bugs)
    # ------------------------------------------------------------------
    # CSV #93/#100/#101/#122-133: `<= MAX` off-by-one on a macro-sized array.
    ("tp_overrun_leq_off_by_one", "OVERRUN",
     "#define MAX_NUM_ADS_CONNECTIONS 16\n"
     "static rpt_rec_t gs_ec_rpt_tbl[MAX_NUM_ADS_CONNECTIONS];\n"
     "void fn(unsigned int ui_conn_index) {\n"
     "    if (ui_conn_index <= MAX_NUM_ADS_CONNECTIONS) {\n"
     "        gs_ec_rpt_tbl[ui_conn_index].ui_supp_ec_bitmask = 1;\n"
     "    }\n"
     "}\n", 6, 'fn', 'Bug'),

    # CSV #94/#95: access inside the else of a failed bounds check.
    ("tp_overrun_else_branch_oob", "OVERRUN",
     "#define MAX_NUM_ADS_CONNECTIONS 16\n"
     "static unsigned char gs_byDsiStartInd[MAX_NUM_ADS_CONNECTIONS];\n"
     "void fn(unsigned int ui_conn_index) {\n"
     "    if (ui_conn_index < MAX_NUM_ADS_CONNECTIONS) {\n"
     "        ok();\n"
     "    } else {\n"
     "        memset(&gs_byDsiStartInd[ui_conn_index], 0, 1);\n"
     "    }\n"
     "}\n", 8, 'fn', 'Bug'),

    # CSV #102/#105/#109/#132: parameter indexes a global array with no
    # local guard; validity depends on callers that were not checked.
    ("tp_overrun_unguarded_parameter_index", "OVERRUN",
     "#define MAX_NUM_ADS_CONNECTIONS 16\n"
     "static rpt_rec_t gs_ec_rpt_tbl[MAX_NUM_ADS_CONNECTIONS];\n"
     "void fnadsc_rptmgr_create_fmf_nonpred_dgrps_rpt(unsigned int ui_conn_index) {\n"
     "    gs_ec_rpt_tbl[ui_conn_index].b_emrgy_urgy_sts = 1;\n"
     "}\n", 4, 'fnadsc_rptmgr_create_fmf_nonpred_dgrps_rpt', 'Bug'),

    # CSV #114/#115: size validated only to *report* a fault, then the copy
    # runs anyway with the oversized length.
    ("tp_overrun_memcpy_fault_then_proceed", "OVERRUN",
     "#define maxADSCMessageSizeInBytes 32\n"
     "static struct { unsigned char data[maxADSCMessageSizeInBytes]; } aDSMessage;\n"
     "void fn(const unsigned char *src, unsigned short data_len) {\n"
     "    if (data_len > maxADSCMessageSizeInBytes) {\n"
     "        fnReportFault(data_len);\n"
     "    }\n"
     "    memcpy(aDSMessage.data, src, data_len);\n"
     "}\n", 7, 'fn', 'Bug'),

    # CSV #137: dereference first, NULL check afterwards.
    ("tp_reverse_inull_deref_then_check", "REVERSE_INULL",
     "void fnadsc_rptmgr_get_wpt_count_by_epp_time_interval(unsigned int *ui_max_wpt_count_ptr) {\n"
     "    unsigned int count = *ui_max_wpt_count_ptr;\n"
     "    if (ui_max_wpt_count_ptr == NULL) {\n"
     "        return;\n"
     "    }\n"
     "    use(count);\n"
     "}\n", 2, 'fnadsc_rptmgr_get_wpt_count_by_epp_time_interval', 'Bug'),

    # ------------------------------------------------------------------
    # False positives (human-confirmed benign)
    # ------------------------------------------------------------------
    # CSV (47 rows): destination pre-zeroed with memset before the copy.
    ("fp_buffer_size_memset_prezeroed", "BUFFER_SIZE",
     "void fn(char *src) {\n"
     "    char name[16];\n"
     "    memset(name, 0, sizeof(name));\n"
     "    strncpy(name, src, sizeof(name));\n"
     "    send(name);\n"
     "}\n", 4, 'fn', 'False positive'),

    # CSV (9 rows): fixed-width struct field copied with its exact size.
    ("fp_buffer_size_struct_field_exact", "BUFFER_SIZE",
     "struct Rec { char center_name[8]; };\n"
     "void fn(struct Rec *r, const char *src) {\n"
     "    strncpy(r->center_name, src, 8);\n"
     "}\n", 3, 'fn', 'False positive'),

    # CSV #3 (and 3 more): explicit overrun check before the copy.
    ("fp_buffer_size_guard_before_copy", "BUFFER_SIZE",
     "void fn(char *src) {\n"
     "    char name[16];\n"
     "    if (strlen(src) >= sizeof(name)) {\n"
     "        return;\n"
     "    }\n"
     "    strncpy(name, src, sizeof(name) - 1);\n"
     "    name[sizeof(name) - 1] = '\\0';\n"
     "    send(name);\n"
     "}\n", 7, 'fn', 'False positive'),

    # CSV #5: strlen(src)+1 count includes the terminator.
    ("fp_buffer_size_strlen_plus_one", "BUFFER_SIZE",
     "void fn(const char *inhib_stat_addr) {\n"
     "    char inhbtd_statn_addr[11];\n"
     "    strncpy(inhbtd_statn_addr, inhib_stat_addr, strlen(inhib_stat_addr) + 1);\n"
     "}\n", 3, 'fn', 'False positive'),

    # CSV (≈20 rows): destination declared larger than the payload copied.
    ("fp_buffer_size_dest_larger_than_payload", "BUFFER_SIZE",
     "void fn(void) {\n"
     "    char uc_afn_msg[121];\n"
     "    strncpy(uc_afn_msg, \"ATC\", 3);\n"
     "    uc_afn_msg[3] = '\\0';\n"
     "    send(uc_afn_msg);\n"
     "}\n", 3, 'fn', 'False positive'),

    # CSV: code compiled out by a pre-processor conditional.
    ("fp_buffer_size_ifdef_disabled", "BUFFER_SIZE",
     "void fn(char *src) {\n"
     "    char name[8];\n"
     "#ifdef UNUSED_FEATURE\n"
     "    strncpy(name, src, sizeof(name));\n"
     "#endif\n"
     "}\n", 4, 'fn', 'False positive'),

    # CSV (≈10 rows): buffer zero-initialised, index resolvably in range.
    ("fp_overrun_zeroed_buffer_bounded_index", "OVERRUN",
     "static unsigned char g_st_afn_dlqm_buffer[256];\n"
     "void fn(void) {\n"
     "    unsigned int ui_index = 0;\n"
     "    memset(g_st_afn_dlqm_buffer, 0, sizeof(g_st_afn_dlqm_buffer));\n"
     "    ui_index += 4;\n"
     "    g_st_afn_dlqm_buffer[ui_index] = 0x01;\n"
     "}\n", 6, 'fn', 'False positive'),

    # CSV: strict `<` bounds guard keeps the index in range.
    ("fp_overrun_strict_guard", "OVERRUN",
     "#define MAX_CPDLC_CONNECTIONS 8\n"
     "static cpdlc_conn_t gs_cpdlc_conn_tbl[MAX_CPDLC_CONNECTIONS];\n"
     "void fnCPDLC_Usr_proc_msg_ind(unsigned int ui_conn_index) {\n"
     "    if (ui_conn_index < MAX_CPDLC_CONNECTIONS) {\n"
     "        gs_cpdlc_conn_tbl[ui_conn_index].state = 1;\n"
     "    }\n"
     "}\n", 6, 'fnCPDLC_Usr_proc_msg_ind', 'False positive'),

    # CSV #92: callee returns a provably valid index that is then used.
    ("fp_overrun_index_from_checked_helper", "OVERRUN",
     "#define MAX_TICKETS 64\n"
     "static ticket_t min_tickets[MAX_TICKETS];\n"
     "int FindFreeEntry(void); /* returns 0..MAX_TICKETS-1 */\n"
     "void LogTicketManager_Store(void) {\n"
     "    int idx = FindFreeEntry();\n"
     "    if (idx >= 0 && idx < MAX_TICKETS) {\n"
     "        min_tickets[idx].used = 1;\n"
     "    }\n"
     "}\n", 7, 'LogTicketManager_Store', 'False positive'),

    # CSV (5 rows): operand validated by an explicit range guard.
    ("fp_integer_overflow_range_guard", "INTEGER_OVERFLOW",
     "#define MAX_CONNECTIONS 64\n"
     "void fn(int si_conn_index) {\n"
     "    if (si_conn_index >= 0 && si_conn_index < MAX_CONNECTIONS) {\n"
     "        unsigned int ui_slot = si_conn_index + 1;\n"
     "        use(ui_slot);\n"
     "    }\n"
     "}\n", 4, 'fn', 'False positive'),

    # CSV (2 rows): pointer checked for NULL before use.
    ("fp_reverse_inull_checked_first", "REVERSE_INULL",
     "void fnBuildDD(struct_t *dpDsiPrimitive) {\n"
     "    if (dpDsiPrimitive == NULL) {\n"
     "        return;\n"
     "    }\n"
     "    use(dpDsiPrimitive->field);\n"
     "}\n", 5, 'fnBuildDD', 'False positive'),

    # CSV #1: `&obj[0]` designates the same address as `&obj`.
    ("fp_array_vs_singleton_first_element_alias", "ARRAY_VS_SINGLETON",
     "void pe_OpenType(obj_t *ptr) {\n"
     "    consume(&ptr[0]);\n"
     "}\n", 2, 'pe_OpenType', 'False positive'),

    # ------------------------------------------------------------------
    # Second wave - remaining clusters from the same CSV
    # ------------------------------------------------------------------
    # CSV #85: pointer assigned a valid address on the guarded path.
    ("fp_forward_null_assigned_in_guard", "FORWARD_NULL",
     "static node_t gs_slots[8];\n"
     "void fnadsc_qm_enqueue_in_session_queue(unsigned int idx) {\n"
     "    node_t *st_new_node_ptr = NULL;\n"
     "    if (queue_space_available()) {\n"
     "        st_new_node_ptr = &gs_slots[idx];\n"
     "        st_new_node_ptr->next = NULL;\n"
     "    }\n"
     "}\n", 6, 'fnadsc_qm_enqueue_in_session_queue', 'False positive'),

    # CSV #87/#89: counter bounded by `< waypoint_num` with a constant ceiling.
    ("fp_integer_overflow_counter_bounded_by_field", "INTEGER_OVERFLOW",
     "#define MAX_WAYPOINTS 128\n"
     "void fn(epp_t *st_epp_ptr) {\n"
     "    unsigned int ui_next = 0;\n"
     "    if (st_epp_ptr->waypoint_num <= MAX_WAYPOINTS) {\n"
     "        for (unsigned int start_idx = 0; start_idx < st_epp_ptr->waypoint_num; start_idx++) {\n"
     "            ui_next = start_idx + 1;\n"
     "        }\n"
     "    }\n"
     "    use(ui_next);\n"
     "}\n", 6, 'fn', 'False positive'),

    # CSV #88: value checked non-negative before the arithmetic.
    ("fp_integer_overflow_value_nonneg_checked", "INTEGER_OVERFLOW",
     "void pd_DynBitString(int nocts) {\n"
     "    if (nocts < 0) {\n"
     "        return;\n"
     "    }\n"
     "    unsigned int total = nocts + 4;\n"
     "    use(total);\n"
     "}\n", 6, 'pd_DynBitString', 'False positive'),

    # CSV #90: index range-validated before the flagged subtraction.
    ("fp_integer_overflow_validated_index_arith", "INTEGER_OVERFLOW",
     "#define MAX_CONNECTIONS 16\n"
     "#define DSI_PORT_ID_IDX_OFFSET 1\n"
     "void fnADSC_conn_mgr_process_cntrt_req(int si_conn_index) {\n"
     "    if (si_conn_index < 0 || si_conn_index >= MAX_CONNECTIONS) {\n"
     "        return;\n"
     "    }\n"
    "    fnadsc_qm_session_established(si_conn_index - DSI_PORT_ID_IDX_OFFSET);\n"
    "}\n", 7, 'fnADSC_conn_mgr_process_cntrt_req', 'False positive'),

    # CSV #138: dereference only inside the `if (ptr != NULL)` block.
    ("fp_reverse_inull_deref_inside_if_block", "REVERSE_INULL",
     "void fnBuildDDataReq(struct_t *dpDsiPrimitive) {\n"
     "    if (dpDsiPrimitive != NULL) {\n"
     "        dpDsiPrimitive->field = 1;\n"
     "    }\n"
     "}\n", 3, 'fnBuildDDataReq', 'False positive'),

    # CSV #140: strlen on a pre-zeroed buffer, guarded by a validity flag.
    ("fp_string_null_guarded_strlen_prezeroed", "STRING_NULL",
     "#define FLIGHT_ID_LEN 12\n"
     "void build_flight_id_group(int flight_id_valid) {\n"
     "    char flight_id[FLIGHT_ID_LEN + 1];\n"
     "    memset(flight_id, 0, sizeof(flight_id));\n"
     "    if (flight_id_valid) {\n"
     "        size_t len = strlen(flight_id);\n"
     "        use_len(len);\n"
     "    }\n"
     "}\n", 6, 'build_flight_id_group', 'False positive'),

    # CSV #142: bounded copy guarded by a length check with an explicit NUL.
    ("fp_string_null_guarded_copy_with_explicit_nul", "STRING_NULL",
     "void format_dl_degrees_minutes(const char *src) {\n"
     "    char uc_minutes[8];\n"
     "    char uc_temp[8];\n"
     "    substring(uc_temp, sizeof(uc_temp), src);\n"
     "    size_t len = strlen(uc_temp);\n"
     "    if (len + 1 <= sizeof(uc_minutes)) {\n"
     "        strncpy(uc_minutes, uc_temp, len);\n"
     "        uc_minutes[len] = '\\0';\n"
     "    }\n"
     "}\n", 8, 'format_dl_degrees_minutes', 'False positive'),

    # CSV #91: index found in a loop, checked non-negative before use.
    ("fp_negative_returns_index_checked_before_use", "NEGATIVE_RETURNS",
     "#define MAX_SIZE_CNTR_TRANS_TBL 32\n"
     "static tbl_t gs_trans_tbl[MAX_SIZE_CNTR_TRANS_TBL];\n"
     "void SM_Add_To_Center_Trans_Tbl(unsigned int ui_current_size) {\n"
     "    int si_newIndex = -1;\n"
     "    if (ui_current_size < MAX_SIZE_CNTR_TRANS_TBL) {\n"
     "        for (int i = 0; i < MAX_SIZE_CNTR_TRANS_TBL; i++) {\n"
     "            if (gs_trans_tbl[i].free) {\n"
     "                si_newIndex = i;\n"
     "                break;\n"
     "            }\n"
     "        }\n"
     "    }\n"
    "    if (si_newIndex >= 0) {\n"
    "        SM_Add_a_Node_To_Head(si_newIndex);\n"
    "    }\n"
    "}\n", 14, 'SM_Add_To_Center_Trans_Tbl', 'False positive'),

    # CSV #96/#111/#112: fixed-length struct fields of matching size.
    ("fp_overrun_memcpy_matching_fixed_fields", "OVERRUN",
     "typedef struct { char procedure[16]; } fans_proc_t;\n"
     "typedef struct { char procedure[16]; } atn_proc_t;\n"
     "void fn(fans_proc_t *fans, atn_proc_t *atn) {\n"
     "    memcpy(atn->procedure, fans->procedure, sizeof(atn->procedure));\n"
     "}\n", 4, 'fn', 'False positive'),
]


@pytest.mark.parametrize("name,checker,code,line,function,expected", CASES,
                         ids=[c[0] for c in CASES])
def test_csv_reviewed_pattern(name, checker, code, line, function, expected):
    cls, comment, _fix, _conf = _analyze(checker, code, line, function)
    assert cls == expected, (
        f"{name}: got {cls!r}, human-reviewed verdict is {expected!r}\ncomment: {comment[:400]}"
    )


def _case_stats():
    """Summary line for the console (not a test)."""
    total = {"Bug": 0, "False positive": 0, "Needs review": 0, "Intentional": 0}
    for name, checker, code, line, function, expected in CASES:
        cls, _c, _f, _conf = _analyze(checker, code, line, function)
        total[cls] = total.get(cls, 0) + 1
    return total


if __name__ == '__main__':
    ok = 0
    for name, checker, code, line, function, expected in CASES:
        cls, comment, fix, conf = _analyze(checker, code, line, function)
        mark = 'OK  ' if cls == expected else 'FAIL'
        ok += cls == expected
        print(f"{mark} {name:45s} -> {cls:15s} (expected {expected})")
        if cls != expected:
            print(f"     {comment[:300]}")
    print(f"\n{ok}/{len(CASES)} patterns match the human-reviewed verdicts")
