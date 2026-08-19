import re
import heuristic_analyzer as h
import comment_style as m

src = open('comment_style.py', encoding='utf-8').read()
print("Remaining 'OK - ' count:", len(re.findall(r'OK - ', src)))

# Root fix: strcpy defect inside a function that also does memcpy elsewhere.
code = (
    "void send(char *buf, const char *msg, const void *blob, size_t n) {\n"
    "  strcpy(buf, msg);            /* flagged line 2 */\n"
    "  memcpy(tail, blob, n);       /* unrelated memcpy at line 3 */\n"
    "}"
)
sink = h._get_sink_function(code, target_line=2, code_start_line=1)
print("line-aware sink at flagged line 2:", sink)

cls, comment, fix, conf = h.analyze_defect(
    {"function_code": code, "code_start_line": 1}, "BUFFER_SIZE", [],
    file="t.c", line=2, function="send", cid=0)
print(f"[BUFFER_SIZE / {cls}] conf={conf}")
print("  comment:", comment[:220])

imsg, icomment, ifix, iconf = h.analyze_defect(
    {"function_code": code, "code_start_line": 1}, "BUFFER_SIZE", [],
    file="t.c", line=3, function="send", cid=0)
print(f"[BUFFER_SIZE flagged at line 3 / {imsg}]")
print("  comment:", icomment[:220])

# Confirm the FP renderer no longer starts with OK.
fp = m.render_example_comment("False positive", "REVERSE_INULL",
                              {"var": "p", "guard_line": 5},
                              "if (p) { use(p); }", 5, 6, "f")
print("FP render:", repr(fp))
