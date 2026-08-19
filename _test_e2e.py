import heuristic_analyzer as h

def run(checker, code, line, function="f", events=None, csl=1):
    try:
        cls, comment, fix, conf = h.analyze_defect(
            {"function_code": code, "code_start_line": csl}, checker, events or [],
            file="t.c", line=line, function=function, cid=0)
        print(f"[{checker} / {cls}] conf={conf}")
        print("   comment:", comment[:400])
    except Exception as e:
        import traceback; traceback.print_exc()

# BUFFER_SIZE: full-capacity strncpy (no -1) -> bug
run("BUFFER_SIZE",
    "void copy(char *dst, char *src) {\n  strncpy(center_name, name, MAX_CENTER_NAME_SIZE);\n}",
    11, "copy")

# STRING_NULL: strncpy + explicit terminator -> FP
run("STRING_NULL",
    "void log(char *s) {\n  strncpy(m_acTraceBuffer, s, MAX_FILE_NAME_LENGTH);\n"
    "  m_acTraceBuffer[sizeof(m_acTraceBuffer)-1] = 0;\n}",
    2, "log")

# REVERSE_INULL: deref then null check
run("REVERSE_INULL",
    "int f(int *p) {\n  *p = 0;\n  if (p == NULL) return -1;\n  return *p;\n}",
    2, "f")

# FORWARD_NULL: assign NULL then deref
run("FORWARD_NULL",
    "int g(void) {\n  st_new_node_ptr = NULL;\n  for (i=0;i<10;i++){}\n  return st_new_node_ptr->data;\n}",
    4, "g")

# INTEGER_OVERFLOW
run("INTEGER_OVERFLOW",
    "void h(void) {\n  ui_curr_wpt_idx += fnnext();\n}",
    2, "h")

# ARRAY_VS_SINGLETON
run("ARRAY_VS_SINGLETON",
    "void i(void) {\n  x = &openType.data[octidx];\n}",
    2, "i")

# NEGATIVE_RETURNS
run("NEGATIVE_RETURNS",
    "void j(void) {\n  SM_Add_a_Node_To_Head(si_newIndex);\n}",
    2, "j")
