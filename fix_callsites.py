import py_compile
p = r"heuristic_analyzer.py"
s = open(p, encoding="utf-8").read()
old = "        guard_status, guard_explanation = _assess_guard_vs_index(\n        guard_cond, idx_var, guard_op, guard_limit, confirmed_idx,\n        arr_size, arr_size_expr, arr_name, guard_line,\n        bool(ctx.get('guard_covers_all_paths', False)))"
new = "    guard_status, guard_explanation = _assess_guard_vs_index(\n        guard_cond, idx_var, guard_op, guard_limit, confirmed_idx,\n        arr_size, arr_size_expr, arr_name, guard_line,\n        bool(ctx.get('guard_covers_all_paths', False)))"
n = s.count(old)
s = s.replace(old, new)
open(p, "w", encoding="utf-8").write(s)
print("fixed call-site indent, occurrences=", n)
py_compile.compile(p, doraise=True)
print("HA_COMPILE_OK")
