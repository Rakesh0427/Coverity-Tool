import io, re, py_compile, sys

p = r"heuristic_analyzer.py"
s = open(p, encoding="utf-8").read()

n1 = s.count("                        if guard_explanation:")
s = s.replace("                        if guard_explanation:",
              "            if guard_explanation:")

old_reasons = "                reasons = []\n        if _has_pattern"
new_reasons = "        reasons = []\n        if _has_pattern"
n2 = s.count(old_reasons)
s = s.replace(old_reasons, new_reasons)

n3 = s.count("                        # path_prover off-by-one explanation")
s = s.replace("                        # path_prover off-by-one explanation",
              "            # path_prover off-by-one explanation")

open(p, "w", encoding="utf-8").write(s)
print("fixed_mangled_if", n1, "fixed_mangled_reasons", n2, "fixed_comment", n3)

py_compile.compile(p, doraise=True)
print("COMPILE_OK")
