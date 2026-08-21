"""
Deep Static Analysis Engine for Coverity Triage
No LLMs — pure heuristic static analysis with path sensitivity,
taint tracking, buffer dimension inference, and guard dominance checks.
"""
import re
from typing import Dict, List, Tuple, Optional, Set
from collections import namedtuple
from cwe_mapping import get_cwe

# ---------------------------------------------------------------------------
# Optional enhanced analysis modules (graceful degradation when unavailable)
# ---------------------------------------------------------------------------
try:
    import clang_resolver as _cr
    _CLANG_RESOLVER = True
except ImportError:
    _CLANG_RESOLVER = False

try:
    import path_prover as _pp
    _PATH_PROVER = True
except ImportError:
    _PATH_PROVER = False

try:
    import flow_analysis as _fa
    _FLOW_ANALYSIS = True
except ImportError:
    _FLOW_ANALYSIS = False

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
TaintSource = namedtuple('TaintSource', ['var', 'source_type', 'line_hint', 'confidence'])
GuardInfo = namedtuple('GuardInfo', ['condition', 'guarded_var', 'line_hint', 'is_null_check', 'is_bounds_check'])
BufferInfo = namedtuple('BufferInfo', ['var', 'size_expr', 'size_bytes', 'line_hint', 'alloc_type'])
CallSite = namedtuple('CallSite', ['func', 'args', 'line_hint'])

# ---------------------------------------------------------------------------
# Taint Analysis — track user-controlled data
# ---------------------------------------------------------------------------
TAINT_SOURCES = {
    'network':  ['recv', 'recvfrom', 'recvmsg', 'read', 'getline', 'fread', 'fgets'],
    'args':     ['argv', 'argc', 'getopt', 'getopt_long'],
    'env':      ['getenv'],
    'file':     ['fopen', 'open', 'creat', 'socket', 'accept'],
    'alloc':    ['malloc', 'calloc', 'realloc', 'strdup'],
    'convert':  ['atoi', 'atol', 'strtol', 'strtoul', 'atof', 'sscanf'],
    'string':   ['strcpy', 'strcat', 'sprintf', 'vsprintf', 'memcpy'],
}

SINK_PATTERNS = {
    'buffer_write': ['strcpy', 'strcat', 'sprintf', 'memcpy', 'memmove', 'strncpy', 'strncat', 'snprintf', 'wcscpy', 'wcscat', 'gets'],
    'buffer_read':  ['strlen', 'strchr', 'strcmp', 'strstr'],
    'deref':        ['->', r'\*'],
    'index':        [r'\['],
    'div':          ['/', '%'],
    'resource':     ['return', 'exit', 'break'],
}


def _extract_all_assignments(code: str) -> List[Tuple[str, str, str]]:
    """Extract (target_var, source_expr, full_line) for assignments."""
    assignments = []
    pat = re.compile(r'(?:^|;)\s*(?:\w+\s+)?(\w+)\s*=\s*([^;]+);', re.MULTILINE)
    for m in pat.finditer(code):
        assignments.append((m.group(1).strip(), m.group(2).strip(), m.group(0)))
    for m in re.finditer(r'\b(sscanf|fscanf|sprintf|snprintf)\s*\(([^)]+)\)', code):
        args = [a.strip() for a in m.group(2).split(',')]
        if len(args) >= 3 and m.group(1) in ('sscanf', 'fscanf'):
            assignments.append((args[-1], f"{m.group(1)}_input", m.group(0)))
    return assignments




def _extract_var_from_deref(code: str) -> str:
    """Try to extract the variable name being dereferenced."""
    m = re.search(r'\b(\w+)\s*->\s*\w+', code)
    if m:
        return m.group(1)
    m = re.search(r'\*(\w+)', code)
    if m:
        return m.group(1)
    m = re.search(r'\b(\w+)\s*\[', code)
    if m:
        return m.group(1)
    return ""


def _is_function_param(code: str, var_name: str) -> bool:
    """Check if a variable is a function parameter."""
    # Match function signature: void foo(int x, char *y)
    sig = re.search(r'\b\w+\s+\w*\s*\([^)]*\b' + re.escape(var_name) + r'\b[^)]*\)', code)
    return bool(sig)

def _find_variable_origin(code: str, var_name: str, depth: int = 3) -> Optional[TaintSource]:
    """
    Trace a variable backwards through up to `depth` assignments to find
    whether it ultimately derives from a taint source.
    """
    if not var_name or not re.search(rf'\b{re.escape(var_name)}\b', code):
        return None

    # Check if it's a function parameter — treat as untrusted input source
    if _is_function_param(code, var_name):
        return TaintSource(var_name, 'args', 0, 'medium')

    assignments = _extract_all_assignments(code)
    current = var_name
    seen = set()

    for _ in range(depth):
        if current in seen:
            break
        seen.add(current)

        for source_type, funcs in TAINT_SOURCES.items():
            for func in funcs:
                if re.search(rf'\b{func}\s*\(', code) and re.search(rf'\b{re.escape(current)}\b', code):
                    lines = code.splitlines()
                    for i, line in enumerate(lines):
                        if re.search(rf'\b{re.escape(current)}\b', line) and re.search(rf'\b{func}\b', line):
                            return TaintSource(current, source_type, i+1, 'high')

        for target, source_expr, _ in reversed(assignments):
            if target == current:
                ids_found = re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)\b', source_expr)
                for ident in ids_found:
                    if ident not in ('if', 'while', 'for', 'return', 'sizeof', 'NULL', 'int', 'char', 'void', 'struct'):
                        current = ident
                        break
                else:
                    for source_type, funcs in TAINT_SOURCES.items():
                        for func in funcs:
                            if re.search(rf'\b{func}\s*\(', source_expr):
                                return TaintSource(var_name, source_type, 0, 'medium')
                break

    return None


def _find_function_calls(code: str) -> List[CallSite]:
    """Extract all function calls with arguments."""
    calls = []
    for m in re.finditer(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)', code):
        func = m.group(1)
        args = [a.strip() for a in m.group(2).split(',') if a.strip()]
        line_hint = code[:m.start()].count('\n') + 1
        calls.append(CallSite(func, args, line_hint))
    return calls


# ---------------------------------------------------------------------------
# Coverity Event Evidence Extractor
# ---------------------------------------------------------------------------
# Coverity event types that directly confirm the defect exists on the flagged path
_DEFECT_CONFIRMING_TYPES = frozenset({
    'overrun_static', 'overrun_dynamic', 'overrun', 'overrun_local',
    'overrun_buffer_arg', 'overrun_buffer_val',
    'integer_overflow', 'integer_underflow',
    'null_deref', 'var_deref_model', 'var_deref_op',
    'use_after_free', 'double_free',
    'tainted_data', 'tainted_string', 'tainted_scalar',
    'user_input',
    # Coverity BUFFER_SIZE checker uses these event types
    # buffer_not_null_terminated and string_not_null_terminated are confirmed defects;
    # buffer_size_warning / buffer_size are handled specifically in parse_coverity_events
    'buffer_not_null_terminated', 'string_not_null_terminated',
})
# Coverity event types that indicate a guarding check happened on this path
_GUARD_EVENT_TYPES = frozenset({
    'check_if_null', 'check_return',
    'range_check', 'bounds_check',
})


def parse_coverity_events(events: List[Dict]) -> Dict:
    """
    Extract structured evidence from Coverity's own event trace.
    Coverity already performed interprocedural analysis — this function
    harvests its conclusions so checkers can make accurate decisions.
    """
    ev = {
        'defect_confirmed':     False,   # Coverity has a direct overrun/null/overflow event
        'taint_confirmed':      False,   # Coverity confirmed data comes from untrusted source
        'guard_on_path':        False,   # a null or bounds check was taken on this specific path
        'guard_takes_true':     False,   # the guard's true branch was taken (pointer is valid)
        'variables':            {},      # {varname: int_value} confirmed by assignment events
        'return_values':        {},      # {funcname: int_value} from return_constant events
        'array_size':           None,    # if Coverity mentions the array size explicitly
        'index_value':          None,    # if Coverity mentions the out-of-bounds index value
        'confirmed_null_var':   '',      # variable name Coverity confirmed as NULL
        'all_descriptions':     [],      # all description strings for full-text search
    }

    for event in events:
        # Coverity mixes hyphens and underscores in event tags (overrun-local
        # vs var_decl); canonicalise to underscores so every check below works
        # regardless of the source (SOAP / REST / HTML / Excel).
        ev_type  = event.get('type', '').lower().replace(' ', '_').replace('-', '_')
        desc     = event.get('description', '').strip()
        ev['all_descriptions'].append(desc)

        if ev_type in _DEFECT_CONFIRMING_TYPES:
            ev['defect_confirmed'] = True
            if 'tainted' in ev_type or 'user_input' in ev_type:
                ev['taint_confirmed'] = True

        if ev_type in _GUARD_EVENT_TYPES:
            ev['guard_on_path'] = True

        # "condition" events: detect guards that were taken on this path
        if ev_type == 'condition':
            desc_lo = desc.lower()
            is_null_guard  = bool(re.search(r'!=\s*null|!=\s*0\b|!\s*\w+\b', desc_lo))
            is_bounds_guard = bool(re.search(r'<\s*\w+|>=\s*0|within\s+bounds', desc_lo))
            if is_null_guard or is_bounds_guard:
                if 'true branch' in desc_lo:
                    ev['guard_on_path']   = True
                    ev['guard_takes_true'] = True

        # "return_constant": "\"foo()\" may return 87"  or  "foo() returns -1"
        if ev_type in ('return_constant', 'return_value'):
            m = re.search(r'"?(\w+)\(\)"?\s+(?:may\s+)?return[s]?\s+(-?\d+)', desc, re.I)
            if m:
                ev['return_values'][m.group(1)] = int(m.group(2))

        # "assignment": "Assigning: \"index\" = foo(). The value of \"index\" is now 87."
        if ev_type in ('assignment', 'var_assign_op'):
            m = re.search(r'value of\s+["\']?(\w+)["\']?\s+is\s+now\s+(-?\d+)', desc, re.I)
            if m:
                ev['variables'][m.group(1)] = int(m.group(2))
            # also: "index = foo(). index is 87."
            m2 = re.search(r'\b(\w+)\s*=.*?[.;]\s*\1\s+is\s+(-?\d+)', desc, re.I)
            if m2:
                ev['variables'][m2.group(1)] = int(m2.group(2))

        # Overrun evidence: "index may be 87, array size is 50", or the more
        # common "Overrunning array \"buf\" of N bytes at byte offset M using
        # index \"i\" (which evaluates to M)".
        if ev_type in ('overrun_static', 'overrun_dynamic', 'overrun',
                       'overrun_local', 'overrun_buffer_arg', 'overrun_buffer_val'):
            m_sz  = re.search(r'array\s+(?:size|length)\s+(?:is\s+)?(\d+)', desc, re.I)
            m_idx = re.search(r'index\s+(?:may\s+be\s+|is\s+)(-?\d+)', desc, re.I)
            if not m_sz:
                m_sz = re.search(r'array\s+["\']?([\w.->]+)["\']?\s+of\s+(\d+)\s+bytes', desc, re.I)
                if m_sz:
                    ev['array_size'] = int(m_sz.group(2))
            else:
                ev['array_size'] = int(m_sz.group(1))
            if not m_idx:
                m_idx = re.search(r'index\s+["\']?([\w.->+ -]+)["\']?\s+\(which\s+evaluates\s+to\s+(-?\d+)\)', desc, re.I)
                if m_idx:
                    ev['index_value'] = int(m_idx.group(2))
            else:
                ev['index_value'] = int(m_idx.group(1))

        # Buffer size warning: extract dest size and copy size for BUFFER_SIZE checker
        if ev_type in ('buffer_size_warning', 'buffer_size', 'buffer_not_null_terminated', 'string_not_null_terminated'):
            m_dest_sz = re.search(r'destination\s+(?:array|buffer|string)\s+[\'\"]\S+[\'\"]\s+of\s+size\s+(\d+)\s+bytes', desc, re.I)
            m_copy_sz = re.search(r'(?:maximum\s+)?size\s+argument\s+of\s+(\d+)\s+bytes', desc, re.I)
            if m_dest_sz:
                ev['array_size'] = int(m_dest_sz.group(1))
            if m_copy_sz:
                ev['index_value'] = int(m_copy_sz.group(1))  # reuse index_value as copy_size
            # "might leave the destination string unterminated" is a confirmed defect
            if re.search(r'unterminated|null.terminat', desc, re.I):
                ev['defect_confirmed'] = True

        # Null pointer evidence: "pointer \"p\" has value NULL"
        if 'null' in ev_type or 'null' in desc.lower():
            m_null = re.search(r'pointer\s+["\']?(\w+)["\']?\s+(?:has\s+value\s+null|is\s+null)', desc, re.I)
            if m_null:
                ev['confirmed_null_var'] = m_null.group(1)

    return ev


# ---------------------------------------------------------------------------
# Buffer Dimension Inference
# ---------------------------------------------------------------------------
def _libclang_buffer_info(code: str, var_name: str) -> 'Optional[BufferInfo]':
    """Use libclang AST to resolve exact buffer size including pointer-to-malloc cases."""
    try:
        import clang.cindex as cx
        import tempfile, os
        idx = cx.Index.create()
        # write to a temp .c file so clang can parse it
        with tempfile.NamedTemporaryFile(suffix='.c', mode='w', delete=False, encoding='utf-8') as f:
            f.write(code)
            tmp = f.name
        try:
            tu = idx.parse(tmp, args=['-std=c11'])
            if not tu:
                return None

            def _walk(cursor):
                if cursor.spelling == var_name:
                    t = cursor.type
                    # stack array: char buf[N]
                    if t.kind == cx.TypeKind.CONSTANTARRAY:
                        sz = t.get_array_size()
                        elem = t.get_array_element_type().get_size()
                        total = sz * elem
                        return BufferInfo(var_name, str(total), total, cursor.location.line, 'stack')
                    # pointer var: look for malloc(N) in the same initializer token range
                    if t.kind in (cx.TypeKind.POINTER, cx.TypeKind.INCOMPLETEARRAY):
                        tokens = list(cursor.get_tokens())
                        src = ' '.join(tok.spelling for tok in tokens)
                        m = re.search(r'(?:malloc|calloc|realloc)\s*\(([^)]+)\)', src)
                        if m:
                            size_expr = m.group(1).strip()
                            size_bytes = _resolve_constant(size_expr, code)
                            alloc_type = 'calloc' if 'calloc' in m.group(0) else 'malloc'
                            return BufferInfo(var_name, size_expr, size_bytes, cursor.location.line, alloc_type)
                for child in cursor.get_children():
                    r = _walk(child)
                    if r:
                        return r
                return None

            result = _walk(tu.cursor)
            return result
        finally:
            os.unlink(tmp)
    except Exception:
        return None


def infer_buffer_info(code: str, var_name: str) -> Optional[BufferInfo]:
    """Infer buffer size from declaration or allocation."""
    if not var_name:
        return None

    # Prefer clang_resolver (handles macros, typedefs, pointer-to-malloc)
    if _CLANG_RESOLVER:
        try:
            sz_bytes, sz_expr = _cr.get_array_size(code, var_name)
            if sz_bytes > 0:
                return BufferInfo(var_name, sz_expr, sz_bytes, 0, 'stack')
            # Try macro expansion on the size expression
            if sz_expr:
                expanded = _cr.expand_macro(code, sz_expr)
                if expanded is not None and expanded > 0:
                    return BufferInfo(var_name, sz_expr, expanded, 0, 'stack')
        except Exception:
            pass

    # Fall back to inline libclang probe (existing)
    lc = _libclang_buffer_info(code, var_name)
    if lc and lc.size_bytes > 0:
        return lc

    pat = re.compile(rf'\b(?:char|int|uint8_t|uint16_t|uint32_t|uint64_t|BYTE|WORD)\s+{re.escape(var_name)}\s*\[\s*([^\]]+)\s*\]')
    m = pat.search(code)
    if m:
        size_expr = m.group(1).strip()
        size_bytes = _resolve_constant(size_expr, code)
        return BufferInfo(var_name, size_expr, size_bytes, 0, 'stack')

    malloc_pat = re.compile(rf'\b{re.escape(var_name)}\s*=\s*(?:\([^)]*\))?\s*(?:malloc|calloc|realloc)\s*\(([^)]+)\)')
    m = malloc_pat.search(code)
    if m:
        size_expr = m.group(1).strip()
        size_bytes = _resolve_constant(size_expr, code)
        alloc_type = 'calloc' if 'calloc' in m.group(0) else 'malloc'
        return BufferInfo(var_name, size_expr, size_bytes, 0, alloc_type)

    str_lit_pat = re.compile(rf'\b(?:char|const\s+char)\s*\*?\s*{re.escape(var_name)}\s*=\s*"([^"]*)"')
    m = str_lit_pat.search(code)
    if m:
        lit_len = len(m.group(1))
        return BufferInfo(var_name, f'"string"({lit_len})', lit_len, 0, 'literal')

    return None


def _resolve_constant(expr: str, code: str) -> int:
    """Try to resolve a C expression to an integer constant."""
    expr = expr.strip()
    if re.match(r'^\d+$', expr):
        return int(expr)
    m = re.search(r'sizeof\s*\(([^)]+)\)', expr)
    if m:
        inner = m.group(1).strip()
        size_map = {'char':1, 'BYTE':1, 'short':2, 'WORD':2, 'int':4, 'DWORD':4, 
                    'long':8, 'size_t':8, 'uint32_t':4, 'uint64_t':8, 'float':4, 'double':8}
        if inner in size_map:
            mult = re.search(r'\*\s*(\d+)', expr)
            if mult:
                return size_map[inner] * int(mult.group(1))
            return size_map[inner]
    m = re.search(rf'#define\s+{re.escape(expr)}\s+(\d+)', code)
    if m:
        return int(m.group(1))
    m = re.match(r'(\d+)\s*\*\s*(\d+)', expr)
    if m:
        return int(m.group(1)) * int(m.group(2))
    return 0


# ---------------------------------------------------------------------------
# Guard Dominance Analysis
# ---------------------------------------------------------------------------
def extract_guards(code: str) -> List[GuardInfo]:
    """Extract all if/while conditions that look like guards."""
    guards = []
    lines = code.splitlines()

    for i, line in enumerate(lines):
        m = re.search(r'\b(if|while)\s*\(([^)]+)\)', line)
        if not m:
            continue
        cond = m.group(2).strip()
        is_null = bool(re.search(r'!=\s*NULL|==\s*NULL|!\s*\w+|\w+\s*!=\s*0', cond))
        is_bounds = bool(re.search(r'<\s*\w+|>\s*\w+|<=\s*\w+|>=\s*\w+|\blen\b|\bsize\b|\blength\b', cond))
        var = ""
        vm = re.search(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*(?:!=|==|<|>)', cond)
        if vm:
            var = vm.group(1)
        guards.append(GuardInfo(cond, var, i+1, is_null, is_bounds))
    return guards


def _z3_verify_guard(guard_cond: str, code: str) -> 'Optional[bool]':
    """Return True if z3 proves the guard makes the defect unreachable; None if unencodable."""
    # Delegate to path_prover when available
    if _PATH_PROVER:
        try:
            solver, var_map = _pp.parse_condition_to_z3(guard_cond)
            if solver is not None:
                import z3
                return solver.check() == z3.sat
        except Exception:
            pass
    # Inline fallback (original implementation)
    try:
        import z3
        sub_conds = re.split(r'&&|\|\|', guard_cond)
        solver = z3.Solver()
        encoded_any = False
        for cond in sub_conds:
            cond = cond.strip()
            m = re.match(r'(\w+)\s*([<>!=]=?|==)\s*(\d+)', cond)
            if not m:
                m = re.match(r'(\d+)\s*([<>!=]=?|==)\s*(\w+)', cond)
                if m:
                    lhs, op, rhs = m.group(3), m.group(2), int(m.group(1))
                    flip = {'<': '>', '>': '<', '<=': '>=', '>=': '<='}
                    op = flip.get(op, op)
                else:
                    continue
            else:
                lhs, op, rhs = m.group(1), m.group(2), int(m.group(3))
            bv = z3.BitVec(lhs, 32)
            ops = {'<': bv < rhs, '>': bv > rhs, '<=': bv <= rhs,
                   '>=': bv >= rhs, '==': bv == rhs, '!=': bv != rhs}
            constraint = ops.get(op)
            if constraint is not None:
                solver.add(constraint)
                encoded_any = True
        if not encoded_any:
            return None
        return solver.check() == z3.sat
    except Exception:
        return None


def analyze_guard_dominance(code: str, target_var: str, operation_line_hint: int) -> Dict:
    """Determine if a guard on target_var dominates the operation."""
    result = {
        'has_guard': False,
        'guard_covers_all_paths': False,
        'guard_type': None,
        'guard_line': 0,
        'bypass_paths': [],
        'confidence': 'low'
    }

    guards = extract_guards(code)
    relevant = [g for g in guards if g.guarded_var == target_var or target_var in g.condition]

    if not relevant:
        return result

    result['has_guard'] = True
    best = relevant[0]
    result['guard_line'] = best.line_hint
    result['guard_type'] = 'null_check' if best.is_null_check else ('bounds_check' if best.is_bounds_check else 'other')

    lines = code.splitlines()
    guard_idx = best.line_hint - 1

    brace_depth = 0
    in_guard_block = False
    has_early_return = False
    has_else_branch = False

    for i, line in enumerate(lines):
        if i == guard_idx:
            in_guard_block = True
        if in_guard_block:
            brace_depth += line.count('{') - line.count('}')
            if 'return' in line or 'exit' in line or 'goto' in line:
                has_early_return = True
            if re.search(r'\belse\b', line):
                has_else_branch = True
            if brace_depth <= 0 and '{' in ''.join(lines[guard_idx:i+1]):
                break

    if has_early_return or guard_idx < 3:
        result['guard_covers_all_paths'] = True
        result['confidence'] = 'high'
    elif not has_else_branch:
        result['guard_covers_all_paths'] = False
        result['confidence'] = 'medium'
        result['bypass_paths'].append(f"Execution may bypass the {best.line_hint} guard if condition is false")
    else:
        result['confidence'] = 'medium'

    # CFG dominance check (flow_analysis) — more precise than regex brace-counting
    if _FLOW_ANALYSIS and result['has_guard']:
        try:
            cfg = _fa.build_cfg(code)
            dominated = _fa.is_dominated_by(cfg, operation_line_hint, best.line_hint)
            if dominated:
                result['guard_covers_all_paths'] = True
                result['confidence'] = 'high'
            else:
                blocks_all, bypass = _fa.does_guard_block_all_paths(cfg, best.line_hint, operation_line_hint)
                if blocks_all:
                    result['guard_covers_all_paths'] = True
                    result['confidence'] = 'high'
                elif bypass:
                    result['bypass_paths'] = [f'bypass via block {b}' for b in bypass[:3]]
        except Exception:
            pass

    # z3 formal verification overrides the regex-based heuristic for compound guards
    if result['has_guard'] and not result['guard_covers_all_paths']:
        z3_result = _z3_verify_guard(best.condition, code)
        if z3_result is True:
            result['guard_covers_all_paths'] = True
            result['confidence'] = 'high'

    return result


# ---------------------------------------------------------------------------
# Data Flow Trace (tree-sitter backed, regex fallback)
# ---------------------------------------------------------------------------

_TAINT_MARKER = '← taint source'
_DEFECT_MARKER = '← DEFECT'

def build_data_flow_trace(code: str, var_name: str, defect_line: int,
                          callee_codes: Optional[Dict[str, str]] = None) -> str:
    """
    Build a human-readable data-flow trace showing where var_name is declared,
    assigned, passed to callees, and used at the defect line.
    Uses tree-sitter when available; falls back to line-by-line regex.
    Also checks callee_codes for taint propagation across function boundaries.
    """
    if not var_name or not code:
        return ''

    trace_entries: List[Tuple[int, str, str]] = []  # (line_no, event_type, snippet)

    # Try tree-sitter AST walk first
    _ts_trace(code, var_name, defect_line, trace_entries)

    # Fall back to regex scan if tree-sitter produced nothing
    if not trace_entries:
        _regex_trace(code, var_name, defect_line, trace_entries)

    if not trace_entries:
        return ''

    # Cross-function: check if var_name is passed into a callee that is tainted
    callee_note = ''
    if callee_codes:
        for fn_name, fn_code in callee_codes.items():
            if fn_name in code and re.search(r'\b' + re.escape(var_name) + r'\b', fn_code):
                taint_funcs = ['recv', 'fgets', 'read', 'scanf', 'getenv', 'fread']
                for tf in taint_funcs:
                    if re.search(rf'\b{tf}\s*\(', fn_code):
                        callee_note = f"    Callee {fn_name}(): introduces external data via {tf}()  {_TAINT_MARKER}\n"
                        break
            if callee_note:
                break

    lines_out = [f"  Data flow for `{var_name}`:"]
    if callee_note:
        lines_out.append(callee_note.rstrip())
    for lineno, event, snippet in sorted(trace_entries, key=lambda x: x[0]):
        marker = f"  {_DEFECT_MARKER}" if lineno == defect_line else ''
        lines_out.append(f"    Line {lineno:>4}: {event:<10}  {snippet}{marker}")
    return '\n'.join(lines_out)


def _ts_trace(code: str, var_name: str, defect_line: int,
              out: List[Tuple[int, str, str]]) -> None:
    """Populate out with trace entries via tree-sitter AST walk."""
    try:
        from code_extractor import _get_parser
        parser = _get_parser('cpp')
        tree = parser.parse(bytes(code, 'utf-8'))
        src_lines = code.splitlines()

        def _node_line(node) -> int:
            return node.start_point[0] + 1

        def _node_text(node) -> str:
            return code[node.start_byte:node.end_byte].replace('\n', ' ').strip()[:80]

        def _contains_var(node) -> bool:
            text = code[node.start_byte:node.end_byte]
            return bool(re.search(r'\b' + re.escape(var_name) + r'\b', text))

        def _walk(node):
            if not _contains_var(node):
                return
            t = node.type
            lineno = _node_line(node)

            if t == 'declaration' and _contains_var(node):
                out.append((lineno, 'declared', _node_text(node)))
            elif t == 'assignment_expression':
                left = node.child_by_field_name('left') or (node.children[0] if node.children else None)
                if left and re.search(r'\b' + re.escape(var_name) + r'\b',
                                      code[left.start_byte:left.end_byte]):
                    out.append((lineno, 'assigned', _node_text(node)))
            elif t == 'call_expression':
                args_node = node.child_by_field_name('arguments')
                if args_node and _contains_var(args_node):
                    fn_node = node.child_by_field_name('function')
                    fn_name = _node_text(fn_node) if fn_node else '?'
                    # Mark taint sources prominently
                    taint_fns = {'recv', 'fgets', 'read', 'getenv', 'scanf', 'fread'}
                    label = 'taint-src' if fn_name in taint_fns else 'passed-to'
                    out.append((lineno, label, f"{fn_name}(...{var_name}...)"))
            elif t in ('return_statement',) and _contains_var(node):
                out.append((lineno, 'returned', _node_text(node)))

            for child in node.children:
                _walk(child)

        _walk(tree.root_node)
    except Exception:
        pass


def _regex_trace(code: str, var_name: str, defect_line: int,
                 out: List[Tuple[int, str, str]]) -> None:
    """Populate out with trace entries via simple line-by-line regex (fallback)."""
    src_lines = code.splitlines()
    decl_pat  = re.compile(
        r'(?:int|char|void|uint\w*|size_t|BYTE|struct\s+\w+)\s*\*?\s*'
        + re.escape(var_name) + r'\b')
    assign_pat = re.compile(r'\b' + re.escape(var_name) + r'\s*=')
    use_pat    = re.compile(r'\b' + re.escape(var_name) + r'\b')
    taint_fns  = re.compile(r'\b(?:recv|fgets|read|getenv|scanf|fread)\s*\(')

    for i, line in enumerate(src_lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith(('//', '/*', '*')):
            continue
        if decl_pat.search(stripped):
            out.append((i, 'declared', stripped[:80]))
        elif assign_pat.search(stripped):
            event = 'taint-src' if taint_fns.search(stripped) else 'assigned'
            out.append((i, event, stripped[:80]))
        elif i == defect_line and use_pat.search(stripped):
            out.append((i, 'used', stripped[:80]))


# ---------------------------------------------------------------------------
# Expert Comment Synthesizer
# ---------------------------------------------------------------------------
EXPERT_TEMPLATES = {
    'buffer_overflow': {
        'bug': [
            "Reviewing {function}(), {sink_func}() at line {line} copies `{src_var}` (from {origin}) into `{dest_var}` without checking the source length against the destination size. {buffer_info}An unbounded copy here is exploitable — an oversized input will overwrite adjacent memory.",
            "In {function}() at line {line}, `{src_var}` originates from {origin} and is passed directly to {sink_func}() with destination `{dest_var}`. {buffer_info}No length guard is present on this path. If `{src_var}` exceeds the buffer capacity, this overwrites stack or heap memory beyond `{dest_var}`.",
        ],
        'false_positive': [
            "After reviewing {function}(), the {checker} at line {line} appears to be a false positive. {sink_func}() is used, but {guard_reason}Additionally, {buffer_info}The buffer access looks safe.",
            "The {checker} finding at line {line} in {function}() seems benign. {guard_reason}{safe_api_note}I don't see an exploitable issue here.",
        ],
        'needs_review': [
            "The {checker} at line {line} in {function}() needs closer inspection. {sink_func}() copies into `{dest_var}` from `{src_var}`, but I cannot fully verify {uncertainty_reason} Confirm the buffer sizes and the maximum length of `{src_var}` manually.",
        ],
    },
    'null_deref': {
        'bug': [
            "In {function}() at line {line}, `{var}` is dereferenced without a null check. It is assigned from {origin}, which can return NULL on failure. There is no guard between the assignment and the use at line {line}.",
            "The dereference of `{var}` at line {line} is unsafe. `{var}` originates from {origin} and is used directly. If {origin} returns NULL, this path will fault.",
        ],
        'false_positive': [
            "The null dereference concern for `{var}` at line {line} appears to be a false positive. A null check exists at line {guard_line} ({guard_cond}), and it dominates this usage. The pointer is validated before access.",
            "In {function}(), `{var}` is checked at line {guard_line} before the dereference at line {line}. The guard `{guard_cond}` ensures `{var}` is non-null on this path. Coverity likely missed this path constraint.",
        ],
    },
    'resource_leak': {
        'bug': [
            "Resource leak in {function}() at line {line}: `{resource}` is acquired but not released on {leak_paths}. Every path that allocates `{resource}` must have a matching {release_func}().",
            "{function}() acquires `{resource}` at line {alloc_line} but the return at line {line} exits without calling {release_func}(). This path leaks the resource on every execution.",
        ],
        'false_positive': [
            "The resource leak warning at line {line} looks like a false positive. `{resource}` is properly released via {release_func}() at line {release_line}, or managed by {raii_type}. No leak here.",
            "Resource management looks correct in {function}(). {release_func}() is called, or the resource is wrapped in {raii_type}. The warning can be dismissed.",
        ]
    },
    'integer_overflow': {
        'bug': [
            "In {function}() at line {line}, `{var}` is used in a {operation} with `{operand}` without a range check. `{var}` is derived from {origin} and may reach values that overflow a signed 32-bit integer, wrapping to a large negative value and corrupting downstream logic.",
            "The {operation} on `{var}` at line {line} in {function}() has no overflow guard. If `{var}` (from {origin}) exceeds INT_MAX / `{operand}`, the result wraps around, causing undefined behavior on signed types.",
        ],
        'false_positive': [
            "The overflow concern at line {line} seems safe. `{var}` is constrained by {guard_desc} before the arithmetic, and the result fits in the destination type. This is a false positive.",
            "At line {line}, the operation on `{var}` is protected by {guard_desc}, keeping values within valid range. No overflow is possible on this path.",
        ],
    },
}


def synthesize_expert_comment(checker_family: str, classification: str, context: Dict, checker: str = "") -> str:
    """Generate expert comment with CWE/CERT perspective — senior reviewer voice."""
    import hashlib
    # Resolve CWE for taxonomy sentence
    cwe = get_cwe(checker or context.get('checker',''))
    cwe_prefix = f"[CWE-{cwe['cwe_id']} {cwe['cwe_name']}] " if cwe else ""
    templates = EXPERT_TEMPLATES.get(checker_family, {}).get(classification, [])
    if not templates:
        base = context.get('default_comment', 'Manual review required.')
    else:
        cid = context.get('cid', 0)
        idx = int(hashlib.md5(str(cid).encode()).hexdigest(), 16) % len(templates)
        template = templates[idx]
        try:
            base = template.format(**context)
        except KeyError:
            base = template
            for key, val in context.items():
                base = base.replace('{' + key + '}', str(val))
            base = re.sub(r'\{[A-Za-z_]+\}', '', base)
    if cwe_prefix and cwe_prefix not in base:
        base = cwe_prefix + base
    # CWE/CERT/OWASP footer
    if cwe and f"CWE-{cwe['cwe_id']}" not in base:
        base = base.rstrip() + f"\nReference: CWE-{cwe['cwe_id']} | CERT {cwe['cert']} | {cwe['owasp']} ({cwe['cwe_url']})"
    sg_rule = context.get('semgrep_rule', '')
    if sg_rule:
        base += f" (semgrep `{sg_rule}` confirms.)"
    return base


# ---------------------------------------------------------------------------
# Fix Generator with Context Awareness
# ---------------------------------------------------------------------------
def generate_contextual_fix(checker_family: str, classification: str, context: Dict, checker: str = "") -> str:
    """Generate a *just suggestion* fix — concise, code-anchored, CWE-tagged."""
    if classification in ('False positive', 'Intentional'):
        return "No fix required." 

    fixes = {
        'buffer_overflow': {
            'strcpy': "Replace strcpy({dest_var}, {src_var}) with:\n  strncpy({dest_var}, {src_var}, sizeof({dest_var}) - 1);\n  {dest_var}[sizeof({dest_var}) - 1] = '\\0';\nAlso consider validating {src_var} length before copy.",
            'strcat': "Replace strcat({dest_var}, {src_var}) with strncat({dest_var}, {src_var}, sizeof({dest_var}) - strlen({dest_var}) - 1);",
            'sprintf': "Replace sprintf({dest_var}, ...) with snprintf({dest_var}, sizeof({dest_var}), ...);",
            'memcpy': "Ensure size <= sizeof({dest_var}):\n  size_t copy_len = (src_len < sizeof({dest_var})) ? src_len : sizeof({dest_var});\n  memcpy({dest_var}, {src_var}, copy_len);",
            'gets': "Remove gets(). Use fgets({dest_var}, sizeof({dest_var}), stdin) instead.",
            'strncpy': "strncpy() does not guarantee null termination. Add after the call:\n  {dest_var}[sizeof({dest_var}) - 1] = '\\0';\nOr switch to strlcpy() if available.",
            'strncat': "Ensure strncat() size argument accounts for existing content:\n  strncat({dest_var}, {src_var}, sizeof({dest_var}) - strlen({dest_var}) - 1);",
            'snprintf': "snprintf() is generally safe, but verify the return value to detect truncation:\n  int n = snprintf({dest_var}, sizeof({dest_var}), ...);\n  if (n < 0 || (size_t)n >= sizeof({dest_var})) { /* handle error */ }",
            'wcscpy': "Replace wcscpy({dest_var}, {src_var}) with wcsncpy({dest_var}, {src_var}, sizeof({dest_var})/sizeof(wchar_t) - 1); and null-terminate.",
            'wcscat': "Replace wcscat({dest_var}, {src_var}) with wcsncat({dest_var}, {src_var}, remaining_size - 1);",
            'memmove': "Ensure size <= sizeof({dest_var}):\n  size_t copy_len = (src_len < sizeof({dest_var})) ? src_len : sizeof({dest_var});\n  memmove({dest_var}, {src_var}, copy_len);",
            'vsprintf': "Replace vsprintf({dest_var}, ...) with vsnprintf({dest_var}, sizeof({dest_var}), ...);",
            'default': "Validate buffer size before copy. Use bounded functions (snprintf, strncpy, strncat) with explicit size checks and ensure null termination.",
        },
        'null_deref': {
            'default': "Add null validation before use:\n  if (!{var}) {{\n      // handle error: return, goto cleanup, or allocate\n      return ERROR;\n  }}\n  // safe to use {var} here",
        },
        'resource_leak': {
            'default': "Ensure {release_func}({resource}) is called on all paths.\nRecommended pattern:\n  {resource_type} {resource} = {alloc_expr};\n  if (!{resource}) return ERROR;\n  // ... use resource ...\ncleanup:\n  {release_func}({resource});",
        },
        'integer_overflow': {
            'multiplication': "Validate before multiplying:\n  if ({var} != 0 && {operand} > INT_MAX / {var}) return ERROR_OVERFLOW;\n  result = {var} * {operand};\nOr use a wider type:\n  int64_t tmp = (int64_t){var} * {operand};\n  if (tmp > INT_MAX || tmp < INT_MIN) return ERROR_OVERFLOW;",
            'subtraction':    "Validate before subtracting:\n  if ({operand} > {var}) return ERROR_UNDERFLOW;  // prevent wrap-below-zero\n  result = {var} - {operand};\nOr use a wider type:\n  int64_t tmp = (int64_t){var} - {operand};\n  if (tmp < INT_MIN || tmp > INT_MAX) return ERROR_OVERFLOW;",
            'addition':       "Validate before adding:\n  if ({var} > INT_MAX - {operand}) return ERROR_OVERFLOW;\n  result = {var} + {operand};\nOr use a wider type:\n  int64_t tmp = (int64_t){var} + {operand};\n  if (tmp > INT_MAX) return ERROR_OVERFLOW;",
            'default':        "Validate before the {operation}:\n  // Ensure {var} and {operand} are within safe range before combining them.\n  if ({var} > INT_MAX / 2 || {operand} > INT_MAX / 2) return ERROR_OVERFLOW;\n  result = {var} {operation} {operand};",
        },
    }

    family_fixes = fixes.get(checker_family, {})
    # integer_overflow fixes are keyed by operation type, not sink function
    if checker_family == 'integer_overflow':
        op_key = context.get('operation', 'default')
        fix_template = family_fixes.get(op_key, family_fixes.get('default', 'Manual review required.'))
    else:
        sink = context.get('sink_func', 'default')
        fix_template = family_fixes.get(sink, family_fixes.get('default', 'Manual review required.'))

    try:
        fix_body = fix_template.format(**context)
    except KeyError:
        fix_body = fix_template
        for key, val in context.items():
            fix_body = fix_body.replace('{' + key + '}', str(val))
        fix_body = re.sub(r'\{[A-Za-z_]+\}', '', fix_body)
    # Make fix concise: keep first code suggestion, append CWE tag
    cwe = get_cwe(checker or context.get('checker',''))
    if cwe:
        tag = f" // CWE-{cwe['cwe_id']}"
        if tag not in fix_body and len(fix_body) < 600:
            # append tag to first line if fix contains code
            if 'if (' in fix_body or 'sizeof' in fix_body:
                fix_body = fix_body.strip() + tag
    # Trim verbose fixes to just suggestion (first 2 lines)
    if len(fix_body) > 500:
        lines = [l for l in fix_body.splitlines() if l.strip()]
        # keep up to 3 lines that look like code/suggestion
        keep = []
        for l in lines:
            keep.append(l)
            if len(keep) >= 3 and any(k in l for k in (';', 'return', '}', '{')):
                break
        fix_body = "\n".join(keep[:3])
    return fix_body.strip()


# ---------------------------------------------------------------------------
# Structured context helpers (used by heuristic_analyzer Phase 7)
# ---------------------------------------------------------------------------

def get_buffer_context(code: str, var_name: str, defect_line: int,
                       code_start_line: int = 1) -> Dict:
    """
    Return a structured dict with buffer size, guard dominance, and CFG info.
    Aggregates clang_resolver + flow_analysis + regex fallbacks.
    """
    result: Dict = {
        'var': var_name,
        'size_bytes': 0,
        'size_expr': '',
        'guard_line': 0,
        'guard_cond': '',
        'guard_covers_all_paths': False,
        'cfg_dominance_proven': False,
        'bypass_paths': [],
    }
    buf = infer_buffer_info(code, var_name)
    if buf:
        result['size_bytes'] = buf.size_bytes
        result['size_expr'] = buf.size_expr

    guard = analyze_guard_dominance(code, var_name, defect_line)
    result['guard_line'] = guard.get('guard_line', 0)
    result['guard_cond'] = guard.get('guard_type', '')
    result['guard_covers_all_paths'] = guard.get('guard_covers_all_paths', False)
    result['bypass_paths'] = guard.get('bypass_paths', [])

    if _FLOW_ANALYSIS and guard['has_guard'] and result['guard_line']:
        try:
            cfg = _fa.build_cfg(code, code_start_line)
            result['cfg_dominance_proven'] = _fa.is_dominated_by(cfg, defect_line, result['guard_line'])
        except Exception:
            pass

    return result


def get_call_context(code: str, func_name: str, call_line: int,
                     code_start_line: int = 1) -> Dict:
    """
    Return structured context for a function call: guard pattern, CFG guard dominance,
    and whether the call is inside an if-body guarded by a condition.
    """
    result: Dict = {
        'func': func_name,
        'call_line': call_line,
        'is_guarded': False,
        'guard_line': 0,
        'guard_cond': '',
        'cfg_inside_condition': False,
    }
    guard = analyze_guard_dominance(code, func_name, call_line)
    if guard['has_guard']:
        result['is_guarded'] = True
        result['guard_line'] = guard.get('guard_line', 0)
        result['guard_cond'] = guard.get('guard_type', '')

    if _FLOW_ANALYSIS and result['guard_line']:
        try:
            cfg = _fa.build_cfg(code, code_start_line)
            result['cfg_inside_condition'] = _fa.is_call_inside_condition_block(
                cfg, call_line, result['guard_line'])
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# Utility: Extract variables from expressions
# ---------------------------------------------------------------------------
def extract_vars(expr: str) -> List[str]:
    """Extract C variable identifiers from an expression."""
    if not expr:
        return []
    ids = re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)\b', expr)
    keywords = {'if', 'while', 'for', 'return', 'sizeof', 'NULL', 'int', 'char', 'void', 
                'struct', 'const', 'static', 'unsigned', 'signed', 'long', 'short', 'float', 'double'}
    return [v for v in ids if v not in keywords]