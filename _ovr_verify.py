import sys
from heuristic_analyzer import analyze_defect


def run(name, code, line, checker, func):
    ctx = {"function_code": code, "code_start_line": 1}
    cls, comment, fix, conf = analyze_defect(ctx, checker, [], "", False, "", line, func, 0, None)
    print(f"[{name}] -> {cls} (conf={conf})")
    print("   COMMENT:", " ".join(comment.split())[:360])
    print()
    return cls


cases = []

# Case 1: OVERRUN with NO guard (real bug).
c1 = "int a[3];\na[i] = 5;"
cases.append(("OVERRUN no guard", c1, 2, "OVERRUN", "ov_noguard"))

# Case 2: OVERRUN with a RELEVANT, SAFE bounds guard (true false positive).
c2 = "int a[5];\nint i = 0;\nfor (i = 0; i < 5; i++) a[i] = 0;"
cases.append(("OVERRUN safe guard", c2, 3, "OVERRUN", "ov_guard"))

# Case 3: OVERRUN with an IRRELEVANT guard (NULL check on the buffer), but i is
# unbounded -> must NOT be rescued to false positive; must be a Bug.
c3 = "int buf[8];\nint i;\nif (buf) buf[i] = 0;"
cases.append(("OVERRUN irrelevant guard", c3, 3, "OVERRUN", "ov_irrel"))

# Case 4: REVERSE_INULL with no guard (real bug).
c4 = "void *p;\n*p = 5;"
cases.append(("REVERSE_INULL no guard", c4, 2, "REVERSE_INULL", "rinull"))

expected = {
    "OVERRUN no guard": "Bug",
    "OVERRUN safe guard": "False positive",
    "OVERRUN irrelevant guard": "Bug",
    "REVERSE_INULL no guard": "Bug",
}

ok = True
for name, code, line, checker, func in cases:
    got = run(name, code, line, checker, func)
    exp = expected[name]
    if got != exp:
        ok = False
        print(f"   !! EXPECTED {exp} but got {got}")

print("ALL PASS" if ok else "FAILURES PRESENT")
sys.exit(0 if ok else 1)
