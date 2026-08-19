import comment_style as m

def show(cls, checker, ctx, code, cs, line, fn):
    out = m.render_example_comment(cls, checker, ctx, code, cs, line, fn)
    print(f"[{checker} / {cls}] -> {out!r}")

# BUFFER_SIZE / STRING_NULL
show("Bug", "BUFFER_SIZE",
     {"sink_func": "strncpy", "dest_var": "center_name", "src_var": "name"},
     "void f(){\nstrncpy(center_name, name, MAX_CENTER_NAME_SIZE);\n}", 10, 11, "f")
show("False positive", "STRING_NULL",
     {"sink_func": "strncpy", "dest_var": "m_acTraceBuffer", "src_var": "szFile"},
     "strncpy(m_acTraceBuffer, szFile, MAX_FILE_NAME_LENGTH);\nm_acTraceBuffer[sizeof(m_acTraceBuffer)-1] = 0;", 200, 200, "f")
show("Bug", "STRING_NULL",
     {"sink_func": "strncpy", "dest_var": "free_text", "src_var": "msg"},
     'strncpy(&free_text[0], "UP...", strlen("UP..."));', 10451, 10451, "proc")
# REVERSE_INULL
show("Bug", "REVERSE_INULL",
     {"var": "ui_max_wpt_count_ptr", "guard_line": 1135},
     "*ui_max_wpt_count_ptr = 0;\nif (ui_max_wpt_count_ptr == NULL) return;", 1130, 1130, "f")
show("False positive", "REVERSE_INULL",
     {"var": "upUserDataParams", "guard_line": 1679},
     "if (upUserDataParams != NULL) { upUserDataParams->x = 1; }", 1682, 1682, "f")
# FORWARD_NULL
show("Bug", "FORWARD_NULL",
     {"var": "st_new_node_ptr"},
     "st_new_node_ptr = NULL;\nfor (i=0;i<10;i++){}\nst_new_node_ptr->data = 1;", 761, 775, "f")
show("False positive", "FORWARD_NULL",
     {"var": "p", "guard_line": 5, "guard_covers_all_paths": True},
     "if (p == NULL) return;\nuse(p);", 5, 6, "f")
# ARRAY_VS_SINGLETON
show("Bug", "ARRAY_VS_SINGLETON",
     {"var": "openType.data"},
     "x = &openType.data[octidx];", 73, 73, "f")
show("False positive", "ARRAY_VS_SINGLETON",
     {"var": "d"},
     "d[0] = 1;", 73, 73, "f")
# INTEGER_OVERFLOW
show("Bug", "INTEGER_OVERFLOW",
     {"var": "ui_curr_wpt_idx"},
     "ui_curr_wpt_idx += fnnext();", 1147, 1147, "f")
show("False positive", "INTEGER_OVERFLOW",
     {"var": "value"},
     "enclen = (stat == ASN_OK) ? value : stat;", 1252, 1252, "f")
# NEGATIVE_RETURNS
show("Bug", "NEGATIVE_RETURNS",
     {"var": "si_newIndex"},
     "SM_Add_a_Node_To_Head(si_newIndex);", 458, 458, "f")
show("False positive", "NEGATIVE_RETURNS",
     {"var": "result"},
     "result = get(); if (result < 0) return; use(result);", 300, 300, "f")
# unsupported checker -> None (leaves existing comment intact)
show("Bug", "UNKNOWN_CHECKER", {}, "x;", 1, 1, "f")
