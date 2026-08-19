import py_compile, io, sys

out = io.StringIO()

# 1) syntax check
try:
    py_compile.compile("local_gui.py", doraise=True)
    out.write("PYCOMPILE local_gui.py OK\n")
except Exception as e:
    out.write(f"PYCOMPILE FAIL: {e}\n")

# 2) import + helper
try:
    import local_gui as m
    out.write("import local_gui OK\n")
    text = m._defect_text(
        {"cid": 137, "checker": "BUFFER_SIZE", "file": "a.c", "line": 1136,
         "function": "f", "severity": "High", "classification": "Bug",
         "confidence": 0.9, "comment": "missing null", "fix": "add NUL",
         "source_code": "line1\nline2"}, "full")
    out.write("--- full blurb ---\n" + text + "\n---\n")
    out.write("cookie=" + repr(m._defect_text({"comment": "hi"}, "comment")) + "\n")
except Exception as e:
    out.write(f"IMPORT/HELPER FAIL: {e!r}\n")

with open("_copy_verify.txt", "w", encoding="utf-8") as f:
    f.write(out.getvalue())
