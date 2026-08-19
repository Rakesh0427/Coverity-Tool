import py_compile, sys, os
# Compile both modified files.
py_compile.compile(r"heuristic_analyzer.py", doraise=True)
print("HEURISTIC_COMPILE_OK")
