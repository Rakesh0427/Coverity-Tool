#!/usr/bin/env python3
"""
path_prover.py — Z3 SMT-backed path constraint verification.

Extracted from deep_analyzer._z3_verify_guard and expanded.
Proves whether guards make defect paths unreachable, off-by-one errors,
and whether fault handlers actually block continuation.
"""
import re
from typing import Optional, Tuple, Dict, List

# ---------------------------------------------------------------------------
# Z3 availability check
# ---------------------------------------------------------------------------

def _z3_available() -> bool:
    try:
        import z3
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Condition parser
# ---------------------------------------------------------------------------

def parse_condition_to_z3(condition_expr: str, use_bitvec: bool = True):
    """
    Parse a C condition string into Z3 constraints.
    Returns (solver, var_map) or (None, {}) if the condition cannot be encoded.
    use_bitvec=True uses BitVec(32) for unsigned-safe arithmetic.
    """
    if not _z3_available():
        return None, {}
    try:
        import z3
        sub_conds = re.split(r'&&', condition_expr)
        solver = z3.Solver()
        var_map: Dict[str, object] = {}
        encoded_any = False

        def _get_var(name: str):
            if name not in var_map:
                var_map[name] = z3.BitVec(name, 32) if use_bitvec else z3.Int(name)
            return var_map[name]

        for cond in sub_conds:
            cond = cond.strip().lstrip('(').rstrip(')')
            if not cond:
                continue
            # Pattern: var OP literal
            m = re.match(r'([A-Za-z_]\w*)\s*([<>!=]=?|==)\s*(-?\d+|0[xX][0-9a-fA-F]+)', cond)
            if m:
                var_name, op, lit_s = m.group(1), m.group(2), m.group(3)
                lit = int(lit_s, 0)
                bv = _get_var(var_name)
                constraint = _apply_op(bv, op, lit, use_bitvec, z3)
                if constraint is not None:
                    solver.add(constraint)
                    encoded_any = True
                continue
            # Pattern: literal OP var
            m = re.match(r'(-?\d+|0[xX][0-9a-fA-F]+)\s*([<>!=]=?|==)\s*([A-Za-z_]\w*)', cond)
            if m:
                lit_s, op, var_name = m.group(1), m.group(2), m.group(3)
                lit = int(lit_s, 0)
                bv = _get_var(var_name)
                flip = {'<': '>', '>': '<', '<=': '>=', '>=': '<=', '==': '==', '!=': '!='}
                constraint = _apply_op(bv, flip.get(op, op), lit, use_bitvec, z3)
                if constraint is not None:
                    solver.add(constraint)
                    encoded_any = True
                continue
            # Pattern: var OP var
            m = re.match(r'([A-Za-z_]\w*)\s*([<>!=]=?|==)\s*([A-Za-z_]\w*)', cond)
            if m:
                lhs_name, op, rhs_name = m.group(1), m.group(2), m.group(3)
                lhs = _get_var(lhs_name)
                rhs = _get_var(rhs_name)
                constraint = _apply_op_var(lhs, op, rhs, use_bitvec, z3)
                if constraint is not None:
                    solver.add(constraint)
                    encoded_any = True

        if not encoded_any:
            return None, {}
        return solver, var_map
    except Exception:
        return None, {}


def _apply_op(bv, op: str, lit: int, use_bitvec: bool, z3):
    if use_bitvec:
        ops = {
            '<':  z3.ULT(bv, lit), '>':  z3.UGT(bv, lit),
            '<=': z3.ULE(bv, lit), '>=': z3.UGE(bv, lit),
            '==': bv == lit,        '!=': bv != lit,
        }
    else:
        ops = {'<': bv < lit, '>': bv > lit, '<=': bv <= lit,
               '>=': bv >= lit, '==': bv == lit, '!=': bv != lit}
    return ops.get(op)


def _apply_op_var(lhs, op: str, rhs, use_bitvec: bool, z3):
    if use_bitvec:
        ops = {
            '<':  z3.ULT(lhs, rhs), '>':  z3.UGT(lhs, rhs),
            '<=': z3.ULE(lhs, rhs), '>=': z3.UGE(lhs, rhs),
            '==': lhs == rhs,        '!=': lhs != rhs,
        }
    else:
        ops = {'<': lhs < rhs, '>': lhs > rhs, '<=': lhs <= rhs,
               '>=': lhs >= rhs, '==': lhs == rhs, '!=': lhs != rhs}
    return ops.get(op)


# ---------------------------------------------------------------------------
# Off-by-one analysis
# ---------------------------------------------------------------------------

def is_off_by_one_bug(guard_op: str, guard_limit_expr: str, array_size: int) -> Tuple[bool, str]:
    """
    Prove whether guard_op applied to guard_limit_expr allows index == array_size.

    Examples:
      is_off_by_one_bug('<=', 'MAX_NUM_ADS_CONNECTIONS', 10)
        → (True, "The <= allows index == MAX_NUM_ADS_CONNECTIONS (10), which equals
                  the array size. Valid range is 0..9; index 10 is out of bounds.")

      is_off_by_one_bug('<', 'MAX_NUM_ADS_CONNECTIONS', 10)
        → (False, "The < strictly limits index to 0..9, within the array bounds of 10.")
    """
    # Resolve guard_limit_expr to an integer if possible
    limit_int: Optional[int] = None
    if re.match(r'^\d+$', guard_limit_expr):
        limit_int = int(guard_limit_expr)

    if limit_int is not None:
        if guard_op == '<=' and limit_int >= array_size:
            return (True,
                    f"The `<=` allows index == {guard_limit_expr} ({limit_int}), which is "
                    f">= the array size {array_size}. Valid range is 0..{array_size - 1}; "
                    f"index {limit_int} is out of bounds.")
        if guard_op == '<' and limit_int <= array_size:
            return (False,
                    f"The `<` strictly limits index to 0..{limit_int - 1}, "
                    f"within the array bounds of {array_size}.")
        if guard_op == '<=' and limit_int == array_size - 1:
            return (False,
                    f"The `<=` with limit {limit_int} is equivalent to `< {array_size}` — "
                    f"safe for an array of {array_size} elements.")
        if guard_op in ('<=', '<'):
            safe = limit_int < array_size if guard_op == '<' else limit_int < array_size
            explanation = (
                f"Guard `{guard_op} {limit_int}` on array of {array_size} elements: "
                + ("safe — highest index is within bounds." if safe
                   else "UNSAFE — index can reach or exceed array size.")
            )
            return (not safe, explanation)

    # Symbolic: can't resolve limit to int — use naming convention
    if guard_op == '<=':
        return (True,
                f"The `<=` comparison with `{guard_limit_expr}` may allow index == array_size "
                f"if `{guard_limit_expr}` == {array_size}. Verify `{guard_limit_expr}` < {array_size}.")
    if guard_op == '<':
        return (False,
                f"The `<` comparison with `{guard_limit_expr}` keeps index strictly below "
                f"the limit, which is the correct pattern for 0-based array indexing.")

    return (False, f"Guard operator `{guard_op}` with limit `{guard_limit_expr}` — unable to prove off-by-one.")


# ---------------------------------------------------------------------------
# Guard safety proof
# ---------------------------------------------------------------------------

def does_guard_prevent_access(guard_cond: str, index_var: str, array_size: int) -> Tuple[bool, str]:
    """
    Use Z3 to prove whether guard_cond prevents index_var from reaching array_size.

    Returns (is_safe, explanation).
    is_safe==True  → guard provably keeps index_var in [0, array_size-1].
    is_safe==False → counterexample exists or guard cannot be proven sufficient.
    """
    if not _z3_available():
        # Fallback: regex heuristic
        m = re.search(rf'\b{re.escape(index_var)}\s*([<>!=]=?)\s*(\d+)', guard_cond)
        if m:
            op, limit = m.group(1), int(m.group(2))
            safe = (op == '<' and limit <= array_size) or (op == '<=' and limit < array_size)
            return safe, f"Heuristic: guard `{index_var} {op} {limit}` vs array_size={array_size}"
        return False, "Z3 unavailable and guard pattern not recognized"

    try:
        import z3
        idx = z3.BitVec(index_var, 32)

        # Build guard constraint from condition
        solver, var_map = parse_condition_to_z3(guard_cond)
        if solver is None:
            return False, f"Could not encode guard `{guard_cond}` into Z3"

        # Check: is there a model where guard holds AND index >= array_size?
        solver.push()
        solver.add(z3.UGE(idx, array_size))
        result = solver.check()
        solver.pop()

        if result == z3.unsat:
            return True, (f"Z3 proves: under guard `{guard_cond}`, `{index_var}` cannot reach "
                          f"{array_size} — all accesses are within bounds 0..{array_size - 1}.")
        elif result == z3.sat:
            try:
                model = solver.model()
                cex_val = model.eval(idx, model_completion=True)
                cex_str = str(cex_val)
            except Exception:
                cex_str = f">= {array_size}"
            return False, (f"Z3 counterexample: guard `{guard_cond}` permits `{index_var}` = {cex_str}, "
                           f"which is >= array_size {array_size} — out-of-bounds access possible.")
        else:
            return False, "Z3 returned unknown — cannot prove safety"
    except Exception as e:
        return False, f"Z3 error: {e}"


# ---------------------------------------------------------------------------
# Fault-then-proceed path check
# ---------------------------------------------------------------------------

def does_fault_block_path(code: str, fault_line: int, access_line: int,
                           code_start_line: int = 1) -> Tuple[bool, str]:
    """
    Check whether every execution path that passes through fault_line
    contains a return/goto/exit before reaching access_line.

    Returns (blocks_access, explanation).
    blocks_access==True → the fault handler prevents reaching the access.
    """
    lines = code.splitlines()
    fault_rel = fault_line - code_start_line
    access_rel = access_line - code_start_line

    if fault_rel < 0 or access_rel <= fault_rel or access_rel >= len(lines):
        return False, "Line range out of code snippet bounds"

    # Scan the block between fault_line and access_line for exit statements
    EXIT_PAT = re.compile(r'\b(return|goto|exit|abort|longjmp|break|throw)\b')
    block_lines = lines[fault_rel:access_rel]

    # Count brace depth to stay within the fault handler block
    depth = 0
    in_block = False
    has_exit = False
    for line in block_lines:
        stripped = line.strip()
        if '{' in stripped:
            depth += stripped.count('{')
            in_block = True
        if '}' in stripped:
            depth -= stripped.count('}')
        if in_block and depth <= 0:
            # Exited the fault block without finding an exit
            break
        if EXIT_PAT.search(stripped):
            has_exit = True
            break

    if has_exit:
        return True, (f"The fault handler block at line {fault_line} contains an exit statement "
                      f"(return/goto/exit) — execution cannot reach line {access_line} on this path.")
    else:
        return False, (f"The fault handler block at line {fault_line} does NOT contain a return/goto/exit. "
                       f"Execution falls through to the access at line {access_line} — real bug.")


# ---------------------------------------------------------------------------
# Convenience: full OVERRUN check
# ---------------------------------------------------------------------------

def prove_overrun(guard_op: str, guard_limit_expr: str, array_size: int,
                  guard_cond: str, index_var: str) -> Dict:
    """
    Run both is_off_by_one_bug and does_guard_prevent_access.
    Returns a unified result dict for use by heuristic_analyzer.
    """
    obo_bug, obo_exp = is_off_by_one_bug(guard_op, guard_limit_expr, array_size)
    safe, safe_exp = does_guard_prevent_access(guard_cond, index_var, array_size)
    return {
        'is_off_by_one': obo_bug,
        'guard_is_safe': safe,
        'classification': 'Bug' if obo_bug or not safe else 'False positive',
        'off_by_one_explanation': obo_exp,
        'guard_explanation': safe_exp,
    }
