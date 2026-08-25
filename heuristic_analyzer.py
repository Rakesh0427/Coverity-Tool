#!/usr/bin/env python3
"""
Senior-engineer-grade heuristic analyzer for Coverity defects.
Generates expert-level disposition comments with CWE / CERT / OWASP reference.

v7.0 — Expert CWE Edition (senior review perspective)
  • CWE/CERT/OWASP/CVSS cited in every disposition (CWE as primary taxonomy)
  • Expert analysis: root cause → taint/flow → guard dominance → exploit impact
  • Proposed fixes are concise code suggestions (just suggestion, not verbose)
  • Retained v6 decision thresholds; confidence remains calibrated
"""
import re
import ast
import subprocess
import json
import os
from typing import Dict, List, Tuple, Optional
from deep_analyzer import (
    _find_variable_origin, infer_buffer_info, analyze_guard_dominance,
    extract_guards, _find_function_calls, synthesize_expert_comment,
    generate_contextual_fix, extract_vars, _extract_var_from_deref,
    build_data_flow_trace, parse_coverity_events,
    TaintSource, BufferInfo, get_buffer_context, get_call_context
)
from decision_agent import (
    Evidence, EvidenceAccumulator, DecisionAgent,
    build_evidence, AgentDecision
)
from ast_analyzer import (
    find_array_access, find_declaration, find_assignment,
    find_call_expression, find_enclosing_guard, get_source
)
from comment_style import render_example_comment
from cwe_mapping import get_cwe, format_cwe_reference

# Optional enhanced modules
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
# Expert CWE helpers — senior perspective (CWE/CERT/OWASP as primary taxonomy)
# ---------------------------------------------------------------------------

def _cwe_info(checker: str) -> dict:
    try:
        return get_cwe(checker) or {}
    except Exception:
        return {}

def _cwe_header(checker: str) -> str:
    info = _cwe_info(checker)
    if not info:
        return ""
    return f"CWE-{info['cwe_id']} {info['cwe_name']} (CERT {info['cert']}, {info['owasp']}, CVSS {info['cvss_base']}) — {info['cwe_url']}"

def _gate_fix_on_source_evidence(fix: str, code: str, line: int,
                                 code_start_line: int, checker: str) -> Tuple[str, str]:
    """Allow a proposed patch only when it is tied to the available source.

    This is intentionally conservative.  A remediation template is guidance,
    not a patch, when it invents an error path, uses a placeholder, or cannot
    name symbols from the analysed function.  Callers render the returned
    reason in the analysis and suppress the Proposed Fix panel in that case.
    """
    candidate = (fix or '').strip()
    if not candidate:
        return candidate, ''
    # Classification outcomes are not patches.  Keep the UI from presenting
    # explanatory "No fix required ..." text as a source-validated fix.
    if candidate.lower().startswith('no fix required'):
        return 'No fix required.', ''
    if candidate.lower().startswith('manual review required'):
        return 'Manual review required.', ''

    if not code:
        return 'Manual review required.', (
            'No code-specific fix was generated because the source for the '
            'Coverity event path is unavailable.')

    # These indicate a stock template rather than the project's established
    # error-handling contract.  Do not present them as an actionable patch.
    generic_markers = (
        'ARRAY_SIZE', 'return ERROR', 'return ERROR_', 'handle error',
        'Validate buffer size before copy', 'Add explicit bounds checking',
        'Verify all string operations', 'the pointer', 'the index',
    )
    if any(marker.lower() in candidate.lower() for marker in generic_markers):
        return 'Manual review required.', (
            'No code-specific fix was generated: the available remediation '
            'would require an invented placeholder or error-handling path.')

    # A patch must mention at least one real, non-keyword identifier from the
    # function.  This blocks fixes that look plausible but target an unrelated
    # variable extracted from another event or a fallback name.
    source_ids = set(re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\b', code))
    patch_ids = set(re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\b', candidate))
    ignored = {
        'Suggestion', 'CWE', 'if', 'else', 'return', 'sizeof', 'int',
        'size_t', 'const', 'static', 'NULL', 'nullptr', 'true', 'false',
        'int64_t', 'INT_MAX', 'INT_MIN', 'Or', 'Also', 'Add', 'Ensure',
    }
    if not ((patch_ids - ignored) & source_ids):
        return 'Manual review required.', (
            'No code-specific fix was generated because the suggested change '
            'could not be anchored to identifiers in the analysed function.')

    # For array-overrun reports, a nested access has independent inner and
    # outer bounds.  A one-index patch is never sufficient without resolving
    # both objects and the semantics of their limits.
    if checker.startswith('OVERRUN'):
        offset = line - code_start_line
        source_lines = code.splitlines()
        if 0 <= offset < len(source_lines) and source_lines[offset].count('[') >= 2:
            return 'Manual review required.', (
                'No code-specific fix was generated: the flagged expression '
                'uses a nested index, so the inner and outer bounds must be '
                'proved independently.')

    return candidate, ''


def _expert_fix_suggestion(checker: str, ctx: dict, default_fix: str) -> str:
    """Make Proposed Fix a *just suggestion*: one concise code-oriented line.
    Senior reviewers want the exact change, not a paragraph.
    """ 
    info = _cwe_info(checker)
    cwe_tag = f" // CWE-{info['cwe_id']}" if info else ""
    fix = (default_fix or "").strip()
    # Keep fix concise and code-anchored; avoid adding duplicate CWE if already present
    if cwe_tag and cwe_tag in fix:
        return fix.strip()
    if len(fix) > 400:
        lines = [l for l in fix.splitlines() if l.strip()]
        code_lines = [l for l in lines if any(k in l for k in ('if (', 'sizeof', 'strncpy', 'snprintf', 'free(', 'return', 'memcpy'))]
        if code_lines:
            fix = code_lines[0].strip() + cwe_tag
        else:
            fix = lines[0][:220] + cwe_tag
        return fix.strip()
    # Never decorate terminal disposition text as if it were a code patch.
    if fix.lower().startswith("no fix") or fix.lower().startswith("manual review required"):
        return fix.strip()
    if cwe_tag and len(fix) < 300:
        # append tag as code comment, not sentence
        if fix.endswith(";"):
            fix = fix + cwe_tag
        elif fix:
            fix = fix + cwe_tag
    return fix.strip()

def _append_cwe_footer(comment: str, checker: str) -> str:
    info = _cwe_info(checker)
    if not info:
        return comment
    # Deduplicate: header already contains CWE-{id} {name} ... — don't repeat full Reference line
    if f"CWE-{info['cwe_id']}" in comment:
        return comment
    ref = format_cwe_reference(checker)
    if ref and ref not in comment:
        return comment.rstrip() + f"\n\n{ref}"
    return comment

# ---------------------------------------------------------------------------
# New helpers for precise comment generation
# ---------------------------------------------------------------------------
def _detect_guarded_call_pattern(code: str, func_name: str, target_line: int, code_start_line: int = 1) -> Optional[Dict]:
    """
    Detect if func_name at target_line is inside an if(var==TRUE) block
    where var was set TRUE after a success function call.
    """
    if not func_name:
        return None
    lines = code.splitlines()
    rel = target_line - code_start_line + 1
    if rel < 1 or rel > len(lines):
        return None
    
    # Find enclosing if block by scanning backwards
    brace_depth = 0
    guard_line = -1
    guard_cond = ""
    guard_var = ""
    
    for i in range(rel - 1, -1, -1):
        line = lines[i]
        if '}' in line:
            brace_depth += line.count('}')
        if '{' in line:
            brace_depth -= line.count('{')
        if brace_depth < 0:
            m = re.search(r'\b(if|while)\s*\(([^)]+)\)', line)
            if m:
                guard_line = i
                guard_cond = m.group(2).strip()
                vm = re.search(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*==\s*(?:TRUE|true|1)\b', guard_cond)
                if vm:
                    guard_var = vm.group(1)
                else:
                    vm = re.search(r'\b([A-Za-z_][A-Za-z0-9_]*)\b', guard_cond)
                    if vm:
                        guard_var = vm.group(1)
                break
            brace_depth = 0
    
    if not guard_var or guard_line < 0:
        return None
    
    # Find assignment to guard_var = TRUE before guard_line
    for j in range(guard_line - 1, -1, -1):
        if re.search(rf'\b{re.escape(guard_var)}\s*=\s*(?:TRUE|true|1)\b', lines[j]):
            # Look for a function call on nearby lines before this assignment
            for k in range(max(0, j - 6), j):
                fm = re.search(r'(\b\w+(?:->\w+)*)\s*\(', lines[k])
                if fm:
                    return {
                        'guard_line': guard_line + code_start_line - 1,
                        'guard_cond': guard_cond,
                        'guard_var': guard_var,
                        'assign_line': j + code_start_line - 1,
                        'success_func': fm.group(1),
                        'description': (f"{func_name}() at line {target_line} is called only inside the {guard_cond} block at line {guard_line + code_start_line - 1}, {guard_var} is set TRUE only after {fm.group(1)}() succeeds")
                    }
    return None

def _extract_memset_info(code: str, var_name: str) -> Optional[Dict]:
    """Find memset call that zeroes var_name. Returns {'line': int, 'size_expr': str}."""
    if not var_name:
        return None
    lines = code.splitlines()
    for i, line in enumerate(lines, 1):
        m = re.search(rf'\bmemset\s*\(\s*{re.escape(var_name)}\s*,\s*0\s*,\s*([^;]+?)\s*\)\s*;', line)
        if m:
            size_expr = m.group(1).strip()
            # balance parentheses: the outer ')' we consumed belongs to memset but
            # is not part of the size expression; add it back only if missing.
            if size_expr.count('(') > size_expr.count(')'):
                size_expr += ')' * (size_expr.count('(') - size_expr.count(')'))
            return {'line': i, 'size_expr': size_expr, 'raw': line.strip()}
    return None


def _extract_strncpy_info(code: str, dest_var: str) -> Optional[Dict]:
    """Find strncpy call targeting dest_var. Returns {'line': int, 'src': str, 'size': str}."""
    if not dest_var:
        return None
    lines = code.splitlines()
    for i, line in enumerate(lines, 1):
        m = re.search(rf'\bstrncpy\s*\(\s*{re.escape(dest_var)}\s*,\s*([^,]+)\s*,\s*([^)]+)\)', line)
        if m:
            return {'line': i, 'src': m.group(1).strip(), 'size': m.group(2).strip(), 'raw': line.strip()}
    return None


def _detect_fault_then_proceed(code: str, target_line: int, code_start_line: int = 1) -> Optional[Dict]:
    """
    Detect a fault-report block before target_line that does NOT return/break,
    so execution proceeds to the dangerous operation anyway.
    """
    lines = code.splitlines()
    target_rel = target_line - code_start_line + 1
    if target_rel < 1 or target_rel > len(lines):
        return None
    search_start = max(0, target_rel - 12)
    for i in range(search_start, target_rel):
        line = lines[i]
        # Look for a size check: if (size > MAX) or if (len > LIMIT)
        if re.search(r'\b(if|while)\s*\(\s*\w+\s*>\s*\w+', line):
            block_has_exit = False
            brace_depth = 0
            in_block = False
            for j in range(i, min(len(lines), target_rel)):
                if '{' in lines[j]:
                    brace_depth += lines[j].count('{')
                    in_block = True
                if '}' in lines[j]:
                    brace_depth -= lines[j].count('}')
                if in_block and brace_depth <= 0:
                    break
                if re.search(r'\b(return|break|goto|exit|abort|longjmp)\b', lines[j]):
                    block_has_exit = True
                    break
            if not block_has_exit:
                cond_m = re.search(r'\b(if|while)\s*\(([^)]+)\)', line)
                if cond_m:
                    return {
                        'fault_line': i + code_start_line - 1,
                        'condition': cond_m.group(2).strip(),
                        'description': (f"A fault is reported at line {i + code_start_line - 1} "
                                        f"if {cond_m.group(2).strip()}, but the code proceeds "
                                        f"to the operation anyway after reporting the fault.")
                    }
    return None


def _extract_struct_member_size(code: str, member_path: str) -> Optional[str]:
    """
    Try to find a struct field declaration like:
        char  destField[SIZE];
    and return the size expression string.
    member_path may be 'obj.field' or 'ptr->field'.
    """
    if not member_path:
        return None
    field = member_path.split('.')[-1].split('->')[-1]
    pat = re.compile(rf'(?:\b\w+\b\s+){{0,6}}\b{re.escape(field)}\s*\[\s*([^\]]+)\s*\]')
    m = pat.search(code)
    if m:
        return m.group(1).strip()
    return None

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _extract_array_access_near_line(code: str, target_line: int, code_start_line: int = 1) -> Dict:
    lines = code.splitlines()
    best = None
    best_dist = 9999
    
    patterns = [
        (r'\b(\w+)\s*\[([^\]]+)\]', 'subscript'),           # arr[idx]
        (r'\*\s*\(\s*(\w+)\s*\+\s*([^\)]+)\)', 'pointer'),  # *(ptr + idx)
        (r'\*\s*(\w+)\s*\+\s*([^\;]+)', 'pointer_simple'), # *ptr + idx
    ]
    
    for i, line in enumerate(lines, 1):
        actual_line = i + code_start_line - 1
        dist = abs(actual_line - target_line)
        if dist >= best_dist:
            continue
        
        for pat, pat_type in patterns:
            m = re.search(pat, line)
            if m:
                best_dist = dist
                arr = m.group(1)
                idx_expr = m.group(2).strip()
                idx_clean = re.sub(r'\([^)]+\)', '', idx_expr).strip()
                idx_var_m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\b', idx_clean)
                idx_var = idx_var_m.group(1) if idx_var_m else idx_expr
                
                # Heuristic: read vs write
                access_type = 'read'
                arr_pos = line.find(arr) if pat_type == 'subscript' else line.find('*')
                if arr_pos >= 0:
                    rest = line[arr_pos:]
                    assign_m = re.search(r'[+\-*/]?=', rest)
                    if assign_m:
                        op = rest[assign_m.start():assign_m.end()]
                        if op not in ('==', '!=', '<=', '>='):
                            access_type = 'write'
                
                best = {
                    'array': arr,
                    'index_expr': idx_expr,
                    'index_var': idx_var,
                    'line': actual_line,
                    'raw': line.strip(),
                    'access_type': access_type
                }
                break  # stop trying other patterns for this line
    return best or {}


def _extract_array_declaration(code: str, arr_name: str, code_start_line: int = 1) -> Dict:
    """Find array declaration and extract size expression.
    
    Only matches actual declarations (e.g., 'char buf[256];'), NOT accesses (e.g., 'buf[i]').
    """
    lines = code.splitlines()
    
    # Pattern 1: Declaration with a C/C++ type keyword before the array name
    # This catches:  char arr[10];  static int buf[256];  uint8_t tbl[MAX];  struct Foo bars[4];
    type_keywords = (
        r'char|int|short|long|float|double|void|'
        r'uint8_t|uint16_t|uint32_t|uint64_t|int8_t|int16_t|int32_t|int64_t|size_t|'
        r'BYTE|WORD|DWORD|BOOL|'
        r'static|const|volatile|unsigned|signed|extern|'
        r'struct\s+\w+|union\s+\w+|enum\s+\w+'
    )
    decl_pat = re.compile(
        rf'\b(?:{type_keywords})\b'
        rf'[\w\s\*]*?'               # optional qualifiers/pointers
        rf'\b{re.escape(arr_name)}\s*\[\s*([^\]]+)\s*\]'
    )
    
    for i, line in enumerate(lines, 1):
        actual_line = i + code_start_line - 1
        m = decl_pat.search(line)
        if m:
            size_expr = m.group(1).strip()
            size_num = 0
            if re.match(r'^\d+$', size_expr):
                size_num = int(size_expr)
            return {
                'size_expr': size_expr,
                'size': size_num,
                'line': actual_line,
                'raw': line.strip()
            }
    
    # Pattern 2: Declaration inside struct/class member list (no type keyword needed if we see ; or = after)
    # e.g., in a struct:  char  name[32];
    member_pat = re.compile(
        rf'^\s*(?:{type_keywords})\b[\w\s\*]*?\b{re.escape(arr_name)}\s*\[\s*([^\]]+)\s*\]\s*(?:;|=)'
    )
    for i, line in enumerate(lines, 1):
        actual_line = i + code_start_line - 1
        m = member_pat.search(line)
        if m:
            size_expr = m.group(1).strip()
            size_num = 0
            if re.match(r'^\d+$', size_expr):
                size_num = int(size_expr)
            return {
                'size_expr': size_expr,
                'size': size_num,
                'line': actual_line,
                'raw': line.strip()
            }
    
    # Pattern 3: Macro-defined size on same line
    # e.g.,  int arr[BUF_SIZE];
    macro_pat = re.compile(
        rf'\b(?:{type_keywords})\b[\w\s\*]*?\b{re.escape(arr_name)}\s*\[\s*([A-Za-z_][A-Za-z0-9_]*)\s*\]\s*;'
    )
    for i, line in enumerate(lines, 1):
        actual_line = i + code_start_line - 1
        m = macro_pat.search(line)
        if m:
            size_expr = m.group(1).strip()
            # Try to resolve the macro value in the same snippet
            def_m = re.search(rf'#define\s+{re.escape(size_expr)}\s+(\d+)', code)
            size_num = int(def_m.group(1)) if def_m else 0
            return {
                'size_expr': size_expr,
                'size': size_num,
                'line': actual_line,
                'raw': line.strip()
            }
    
    return {}


def _extract_index_flow(code: str, idx_var: str, access_line: int, code_start_line: int = 1) -> Dict:
    """Find assignment and guard for idx_var before access_line (all actual file lines)."""
    lines = code.splitlines()
    result = {
        'assign_line': 0,
        'assign_expr': '',
        'guard_line': 0,
        'guard_cond': '',
        'guard_op': '',
        'guard_limit': ''
    }
    
    if not idx_var or not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', idx_var):
        return result
    
    access_rel = access_line - code_start_line + 1
    if access_rel < 1 or access_rel > len(lines):
        return result
    
    # Find assignment: idx = expr;
    assign_pat = re.compile(rf'\b{re.escape(idx_var)}\s*=\s*([^;]+);')
    for i in range(access_rel - 1, -1, -1):
        m = assign_pat.search(lines[i])
        if m:
            result['assign_line'] = i + 1 + code_start_line - 1
            result['assign_expr'] = m.group(1).strip()
            break
    
    # Find guard on idx_var itself
    guard_pat = re.compile(r'\b(if|while|for)\s*\(([^)]+)\)')
    for i in range(access_rel - 1, -1, -1):
        m = guard_pat.search(lines[i])
        if m and idx_var in m.group(2):
            cond = m.group(2).strip()
            result['guard_line'] = i + 1 + code_start_line - 1
            result['guard_cond'] = cond
            comp_m = re.search(rf'\b{re.escape(idx_var)}\s*([<>!=]=?|==)\s*([^;)\s&|]+)', cond)
            if comp_m:
                result['guard_op'] = comp_m.group(1)
                result['guard_limit'] = comp_m.group(2).strip()
            else:
                comp_m = re.search(rf'([^;)\s&|]+)\s*([<>!=]=?|==)\s*{re.escape(idx_var)}', cond)
                if comp_m:
                    op = comp_m.group(2)
                    flip = {'<': '>', '>': '<', '<=': '>=', '>=': '<=', '==': '==', '!=': '!='}
                    result['guard_op'] = flip.get(op, op)
                    result['guard_limit'] = comp_m.group(1).strip()
            break
    
    # Fallback: guard on the RHS expression (e.g. si_conn_prity[ui_prty_idx] <= MAX)
    if result['assign_expr'] and not result['guard_line']:
        # Strip casts: (uint8_t)(expr)  or  (type)var  -> keep inner expr
        rhs = re.sub(r'\(\s*\w+\s*\)', '', result['assign_expr']).strip()
        # Extract base variable if RHS is an array access: arr[idx]
        rhs_var_m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*\[', rhs)
        if rhs_var_m:
            rhs_base = rhs_var_m.group(1)
            for i in range(access_rel - 1, -1, -1):
                m = guard_pat.search(lines[i])
                if m and rhs_base in m.group(2):
                    cond = m.group(2).strip()
                    result['guard_line'] = i + 1 + code_start_line - 1
                    result['guard_cond'] = cond
                    # Try: arr[idx] OP limit
                    comp_m = re.search(rf'\b{re.escape(rhs_base)}\s*\[[^\]]+\]\s*([<>!=]=?|==)\s*([^;)\s&|]+)', cond)
                    if comp_m:
                        result['guard_op'] = comp_m.group(1)
                        result['guard_limit'] = comp_m.group(2).strip()
                    else:
                        # Try: limit OP arr[idx]
                        comp_m = re.search(rf'([^;)\s&|]+)\s*([<>!=]=?|==)\s*{re.escape(rhs_base)}\s*\[[^\]]+\]', cond)
                        if comp_m:
                            op = comp_m.group(2)
                            flip = {'<': '>', '>': '<', '<=': '>=', '>=': '<=', '==': '==', '!=': '!='}
                            result['guard_op'] = flip.get(op, op)
                            result['guard_limit'] = comp_m.group(1).strip()
                    break
    
    return result


def _line_text_at(code: str, target_line: int, code_start_line: int = 1) -> str:
    offset = target_line - code_start_line
    lines = code.splitlines()
    return lines[offset].strip() if 0 <= offset < len(lines) else ''


_INTEGRAL_TYPE_BOUNDS = {
    'uint8_t': (0, 2**8 - 1, 8, True),
    'int8_t': (-(2**7), 2**7 - 1, 8, False),
    'uint16_t': (0, 2**16 - 1, 16, True),
    'int16_t': (-(2**15), 2**15 - 1, 16, False),
    'uint32_t': (0, 2**32 - 1, 32, True),
    'int32_t': (-(2**31), 2**31 - 1, 32, False),
    'uint64_t': (0, 2**64 - 1, 64, True),
    'int64_t': (-(2**63), 2**63 - 1, 64, False),
    'size_t': (0, 2**64 - 1, 64, True),
    'char': (-(2**7), 2**7 - 1, 8, False),
    'unsigned char': (0, 2**8 - 1, 8, True),
    'short': (-(2**15), 2**15 - 1, 16, False),
    'unsigned short': (0, 2**16 - 1, 16, True),
    'int': (-(2**31), 2**31 - 1, 32, False),
    'unsigned int': (0, 2**32 - 1, 32, True),
    'long': (-(2**63), 2**63 - 1, 64, False),
    'unsigned long': (0, 2**64 - 1, 64, True),
    'long long': (-(2**63), 2**63 - 1, 64, False),
    'unsigned long long': (0, 2**64 - 1, 64, True),
}


def _infer_integral_decl_bounds(var_name: str, sources: List[str]) -> Dict:
    """Best-effort integral type inference for a local/parameter variable."""
    default = {'type_text': '', 'min': -(2**31), 'max': 2**31 - 1, 'bits': 32, 'unsigned': False}
    if not var_name:
        return default
    pat = re.compile(
        rf'\b((?:const\s+|static\s+|volatile\s+|signed\s+|unsigned\s+|long\s+|short\s+|'
        rf'int\s+|char\s+|size_t\s+|uint\d+_t\s+|int\d+_t\s+)+)\**\s*{re.escape(var_name)}\b')
    for source in sources:
        for line in (source or '').splitlines():
            if var_name not in line:
                continue
            m = pat.search(line)
            if not m:
                continue
            type_text = ' '.join(m.group(1).split()).strip()
            for key, bounds in sorted(_INTEGRAL_TYPE_BOUNDS.items(), key=lambda kv: len(kv[0]), reverse=True):
                if type_text == key or type_text.endswith(key):
                    lo, hi, bits, is_unsigned = bounds
                    return {'type_text': type_text, 'min': lo, 'max': hi, 'bits': bits, 'unsigned': is_unsigned}
            if 'unsigned' in type_text:
                lo, hi, bits, is_unsigned = _INTEGRAL_TYPE_BOUNDS['unsigned int']
                return {'type_text': type_text, 'min': lo, 'max': hi, 'bits': bits, 'unsigned': is_unsigned}
            if any(tok in type_text for tok in ('int', 'long', 'short', 'char')):
                lo, hi, bits, is_unsigned = _INTEGRAL_TYPE_BOUNDS['int']
                return {'type_text': type_text, 'min': lo, 'max': hi, 'bits': bits, 'unsigned': is_unsigned}
    return default


def _extract_binary_operation(text: str, operators: Tuple[str, ...]) -> Optional[Tuple[str, str, str]]:
    """Extract a simple binary operation from a source line / RHS expression."""
    src = (text or '').strip().rstrip(';')
    if not src:
        return None
    assign_m = re.search(r'(?<![=!<>])=(?!=)\s*(.+)$', src)
    if assign_m:
        src = assign_m.group(1).strip()
    src = src.strip('() ')
    for op in operators:
        if op in ('<<', '>>'):
            pat = re.compile(rf'(.+?)\s*{re.escape(op)}\s*(.+)')
        elif op == '*':
            pat = re.compile(r'(.+?)\s*\*\s*(.+)')
        elif op == '/':
            pat = re.compile(r'(.+?)\s*/\s*(.+)')
        elif op == '%':
            pat = re.compile(r'(.+?)\s%\s*(.+)')
        elif op == '+':
            pat = re.compile(r'(.+?)\s*\+\s*(.+)')
        else:
            pat = re.compile(r'(.+?)\s*-\s*(.+)')
        m = pat.search(src)
        if m:
            lhs = m.group(1).strip().strip('()')
            rhs = m.group(2).strip().strip('()')
            if lhs and rhs:
                return lhs, op, rhs
    return None


def _guard_proves_nonzero(var_name: str, cond: str) -> bool:
    cond = cond or ''
    if not var_name or not cond:
        return False
    pats = (
        rf'\b{re.escape(var_name)}\b\s*!=\s*0\b',
        rf'\b{re.escape(var_name)}\b\s*>\s*0\b',
        rf'\b{re.escape(var_name)}\b\s*>=\s*1\b',
        rf'\b0\b\s*<\s*\b{re.escape(var_name)}\b',
        rf'\b1\b\s*<=\s*\b{re.escape(var_name)}\b',
    )
    return any(re.search(p, cond) for p in pats)


def _guard_rejects_negative(var_name: str, cond: str) -> bool:
    cond = cond or ''
    if not var_name or not cond:
        return False
    pats = (
        rf'\b{re.escape(var_name)}\b\s*>=\s*0\b',
        rf'\b{re.escape(var_name)}\b\s*>\s*-1\b',
        rf'\b0\b\s*<=\s*\b{re.escape(var_name)}\b',
        rf'\b{re.escape(var_name)}\b\s*!=\s*EOF\b',
    )
    return any(re.search(p, cond) for p in pats)


def _resolve_var_value_before_line(code: str, var_name: str, access_line: int,
                                   code_start_line: int, resolution_sources: List[str]) -> Optional[int]:
    flow = _extract_index_flow(code, var_name, access_line, code_start_line)
    if flow.get('assign_expr'):
        return _resolve_integer_constant(flow['assign_expr'], resolution_sources)
    return None


def _resolve_expr_value_before_line(code: str, expr: str, access_line: int,
                                    code_start_line: int, resolution_sources: List[str]) -> Optional[int]:
    expr = (expr or '').strip()
    if not expr:
        return None
    val = _resolve_integer_constant(expr, resolution_sources)
    if val is not None:
        return val
    m = re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', expr)
    if m:
        return _resolve_var_value_before_line(code, expr, access_line, code_start_line, resolution_sources)
    return None


def _use_after_free_facts(code: str, ptr_name: str, access_line: int,
                          code_start_line: int = 1) -> Dict:
    facts = {'free_line': 0, 'null_line': 0, 'reassign_line': 0, 'guard_line': 0, 'guard_cond': ''}
    if not ptr_name:
        return facts
    lines = code.splitlines()
    access_rel = access_line - code_start_line + 1
    if access_rel < 1 or access_rel > len(lines):
        return facts

    free_rel = 0
    for i in range(access_rel - 1, -1, -1):
        if re.search(rf'\bfree\s*\(\s*{re.escape(ptr_name)}\s*\)', lines[i]):
            free_rel = i + 1
            facts['free_line'] = i + code_start_line
            break
    if not free_rel:
        return facts

    for i in range(free_rel, access_rel):
        line = lines[i]
        abs_line = i + code_start_line
        if not facts['null_line'] and re.search(rf'\b{re.escape(ptr_name)}\s*=\s*NULL\s*;', line):
            facts['null_line'] = abs_line
        if not facts['reassign_line'] and re.search(rf'\b{re.escape(ptr_name)}\s*=\s*(?!NULL\b)([^;]+);', line):
            facts['reassign_line'] = abs_line
        if not facts['guard_line']:
            gm = re.search(r'\b(if|while)\s*\(([^)]+)\)', line)
            if gm and ptr_name in gm.group(2):
                facts['guard_line'] = abs_line
                facts['guard_cond'] = gm.group(2).strip()
    return facts


def _lines(code: str) -> List[str]:
    return code.splitlines()


# ---------------------------------------------------------------------------
# Cross-file constant / enum resolution helpers
# ---------------------------------------------------------------------------

_DEFECT_NATIVE_OWASP = 'Not directly applicable (native-code / non-web defect)'
_CONST_EVAL_CACHE: Dict[Tuple[str, Tuple[int, ...]], Optional[int]] = {}


def _strip_c_casts(expr: str) -> str:
    """Drop leading C/C++ casts from an expression.

    Examples:
      (unsigned int)E_HIGH_PRIORITY -> E_HIGH_PRIORITY
      (uint8_t)(MAX_VAL - 1)        -> (MAX_VAL - 1)
    """
    cur = (expr or '').strip()
    while True:
        m = re.match(r'^\(\s*[A-Za-z_][A-Za-z0-9_:\s\*<>]*\)\s*(.+)$', cur)
        if not m:
            break
        cur = m.group(1).strip()
    return cur


def _safe_eval_python_int(expr: str) -> Optional[int]:
    """Evaluate a small integer-only expression with Python's AST.

    Accepts literals, unary +/-/~, arithmetic/bitwise ops, and shifts. Returns
    None when the expression contains anything else.
    """
    try:
        tree = ast.parse(expr, mode='eval')
    except Exception:
        return None

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return int(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub, ast.Invert)):
            v = _eval(node.operand)
            if v is None:
                return None
            if isinstance(node.op, ast.UAdd):
                return +v
            if isinstance(node.op, ast.USub):
                return -v
            return ~v
        if isinstance(node, ast.BinOp) and isinstance(
                node.op, (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Div,
                          ast.Mod, ast.LShift, ast.RShift, ast.BitOr,
                          ast.BitAnd, ast.BitXor)):
            left = _eval(node.left)
            right = _eval(node.right)
            if left is None or right is None:
                return None
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, (ast.FloorDiv, ast.Div)):
                if right == 0:
                    return None
                return left // right
            if isinstance(node.op, ast.Mod):
                if right == 0:
                    return None
                return left % right
            if isinstance(node.op, ast.LShift):
                return left << right
            if isinstance(node.op, ast.RShift):
                return left >> right
            if isinstance(node.op, ast.BitOr):
                return left | right
            if isinstance(node.op, ast.BitAnd):
                return left & right
            if isinstance(node.op, ast.BitXor):
                return left ^ right
        return None

    try:
        return _eval(tree)
    except Exception:
        return None


def _safe_read_text(path: str) -> str:
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            return fh.read()
    except Exception:
        return ''


def _gather_resolution_sources(code: str, file: str,
                               called_function_codes: Optional[Dict[str, str]] = None,
                               callers: Optional[List[Dict]] = None) -> List[str]:
    """Collect nearby source text used to resolve macros / enum constants.

    Resolution is intentionally local-first: the defect function, then its file,
    then caller/callee bodies already fetched by context_builder. This improves
    precision without doing a whole-workspace grep per defect.
    """
    sources: List[str] = []
    if code and code.strip():
        sources.append(code)
    if file and os.path.isfile(file):
        try:
            full = _safe_read_text(file) or ''
            if full and full not in sources:
                sources.append(full)
        except Exception:
            pass
    if called_function_codes:
        for name, fcode in called_function_codes.items():
            if name == '__callers__':
                continue
            if isinstance(fcode, str) and fcode.strip() and fcode not in sources:
                sources.append(fcode)
    if callers:
        for caller in callers[:10]:
            body = ''
            if isinstance(caller, dict):
                body = str(caller.get('code') or '')
            elif isinstance(caller, str):
                body = caller
            if body.strip() and body not in sources:
                sources.append(body)
    return sources


def _split_enum_items(enum_body: str) -> List[str]:
    return _split_top_level_commas(enum_body)


def _resolve_enum_member_value(name: str, sources: List[str], _seen: Optional[set] = None) -> Optional[int]:
    """Resolve an enum member, handling both explicit and implicit values."""
    target = (name or '').split('::')[-1]
    if not target:
        return None
    seen = _seen or set()
    enum_pat = re.compile(r'enum(?:\s+class|\s+struct)?(?:\s+[A-Za-z_][A-Za-z0-9_]*)?\s*\{([^}]*)\}', re.S)
    for source in sources:
        for block in enum_pat.finditer(source or ''):
            items = _split_enum_items(block.group(1))
            current = -1
            for item in items:
                item = re.sub(r'/\*.*?\*/', ' ', item, flags=re.S)
                item = re.sub(r'//.*', ' ', item).strip()
                if not item:
                    continue
                if '=' in item:
                    lhs, rhs = item.split('=', 1)
                    enum_name = lhs.strip().split()[-1]
                    val = _resolve_integer_constant(rhs.strip(), sources, seen)
                    if val is None:
                        continue
                    current = val
                else:
                    enum_name = item.strip().split()[-1]
                    current += 1
                if enum_name == target:
                    return current
    return None


def _resolve_integer_constant(expr: str, sources: List[str], _seen: Optional[set] = None) -> Optional[int]:
    """Resolve a small integer constant from local/cross-file source.

    Supports literals, casts, macros, enum members, constexpr/const integral
    declarations, and simple arithmetic over those symbols.
    """
    expr = _strip_c_casts(expr or '')
    expr = re.sub(r'/\*.*?\*/', ' ', expr, flags=re.S)
    expr = expr.strip().rstrip(';')
    if not expr:
        return None

    cache_key = (expr, tuple(hash(s or '') for s in sources[:6]))
    if cache_key in _CONST_EVAL_CACHE:
        return _CONST_EVAL_CACHE[cache_key]

    seen = set(_seen or set())
    if expr in seen:
        return None
    seen.add(expr)

    # Literal fast paths
    if re.fullmatch(r'[+-]?\d+', expr):
        val = int(expr, 10)
        _CONST_EVAL_CACHE[cache_key] = val
        return val
    if re.fullmatch(r'[+-]?0[xX][0-9a-fA-F]+', expr):
        val = int(expr, 16)
        _CONST_EVAL_CACHE[cache_key] = val
        return val

    # Strip balanced outer parentheses.
    while expr.startswith('(') and expr.endswith(')'):
        inner = expr[1:-1].strip()
        if not inner:
            break
        if inner.count('(') != inner.count(')'):
            break
        expr = inner

    # Direct symbol lookup.
    symbol = expr.split('::')[-1]
    if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_:]*', expr):
        macro_names = [expr, symbol] if symbol != expr else [expr]
        for source in sources:
            for macro_name in macro_names:
                m = re.search(rf'#\s*define\s+{re.escape(macro_name)}\s+([^\n/]+)', source or '')
                if m:
                    val = _resolve_integer_constant(m.group(1).strip(), sources, seen)
                    if val is not None:
                        _CONST_EVAL_CACHE[cache_key] = val
                        return val
            for const_name in macro_names:
                const_pat = re.compile(
                    rf'\b(?:static\s+)?(?:constexpr\s+)?(?:const\s+)?'
                    rf'(?:unsigned\s+|signed\s+|long\s+|short\s+|int\s+|size_t\s+|'
                    rf'uint\d+_t\s+|int\d+_t\s+|auto\s+)*'
                    rf'{re.escape(const_name)}\s*=\s*([^;]+);')
                m = const_pat.search(source or '')
                if m:
                    val = _resolve_integer_constant(m.group(1).strip(), sources, seen)
                    if val is not None:
                        _CONST_EVAL_CACHE[cache_key] = val
                        return val
        enum_val = _resolve_enum_member_value(expr, sources, seen)
        if enum_val is not None:
            _CONST_EVAL_CACHE[cache_key] = enum_val
            return enum_val

    # Arithmetic over symbols/literals: replace every identifier token we can resolve.
    replaced = expr
    unresolved = False
    for tok in sorted(set(re.findall(r'\b[A-Za-z_][A-Za-z0-9_:]*\b', expr)), key=len, reverse=True):
        if tok in {'sizeof', 'true', 'false'}:
            unresolved = True
            continue
        val = _resolve_integer_constant(tok, sources, seen)
        if val is None:
            unresolved = True
            continue
        replaced = re.sub(rf'\b{re.escape(tok)}\b', str(val), replaced)
    val = _safe_eval_python_int(replaced)
    if val is not None:
        _CONST_EVAL_CACHE[cache_key] = val
        return val

    # As a last enum-only fallback, try resolving the entire expression's base token.
    if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_:]*', expr):
        enum_val = _resolve_enum_member_value(expr, sources, seen)
        if enum_val is not None:
            _CONST_EVAL_CACHE[cache_key] = enum_val
            return enum_val

    if not unresolved:
        _CONST_EVAL_CACHE[cache_key] = None
    return None


def _extract_array_initializer_values(code: str, arr_name: str,
                                      sources: List[str]) -> Optional[List[int]]:
    """Return integer initializer values for a local array when they are simple.

    Example: `int map[4] = {0, 2, 3, 0};` -> [0, 2, 3, 0]
    """
    if not code or not arr_name:
        return None
    pat = re.compile(
        rf'\b(?:[A-Za-z_][A-Za-z0-9_<>:]*\s+)+{re.escape(arr_name)}\s*\[[^\]]+\]\s*=\s*\{{([^}}]+)\}}',
        re.S)
    m = pat.search(code)
    if not m:
        return None
    values = []
    for item in _split_top_level_commas(m.group(1)):
        item = item.strip()
        if not item or item.startswith('.'):
            return None
        val = _resolve_integer_constant(item, sources)
        if val is None:
            return None
        values.append(val)
    return values


# Semgrep per-file cache and enable flag — semgrep is heavy (2-30s per file) and
# caused the tool to appear stuck. Default OFF; enable via COVERITY_ENABLE_SEMGREP=1.
_SEMGREP_CACHE: dict = {}
_SEMGREP_AVAILABLE: Optional[bool] = None

def _semgrep_enabled() -> bool:
    if os.environ.get("COVERITY_ENABLE_SEMGREP", "").strip() not in ("1", "true", "yes", "on"):
        return False
    global _SEMGREP_AVAILABLE
    if _SEMGREP_AVAILABLE is None:
        try:
            import shutil
            if shutil.which("semgrep") is None:
                _SEMGREP_AVAILABLE = False
            else:
                # Quick probe: semgrep --version must succeed within 3s
                r = subprocess.run(["semgrep", "--version"], capture_output=True, timeout=3)
                _SEMGREP_AVAILABLE = (r.returncode == 0)
        except Exception:
            _SEMGREP_AVAILABLE = False
    return bool(_SEMGREP_AVAILABLE)

def _run_semgrep_check(file_path: str, defect_line: int, checker: str) -> Optional[str]:
    """Run semgrep on the source file and return the first matching rule_id near defect_line.

    Cached per-file (first defect in a file pays the cost, rest hit cache).
    Disabled by default — set COVERITY_ENABLE_SEMGREP=1 to enable. Previously
    this ran per-defect and made 1000-defect runs take 30+ minutes.
    """
    if not file_path or not os.path.isfile(file_path):
        return None
    if not _semgrep_enabled():
        return None
    # Check cache: file_path -> list of hits
    cached = _SEMGREP_CACHE.get(file_path)
    if cached is not None:
        # cached is list of (line, check_id) or None for no hits / failed
        if not cached:
            return None
        for hit_line, check_id in cached:
            if abs(hit_line - defect_line) <= 3:
                return check_id
        return None
    try:
        result = subprocess.run(
            ['semgrep', '--json', '--config', 'p/c-and-cpp', '--no-git-ignore', file_path],
            capture_output=True, text=True, timeout=10
        )
        data = json.loads(result.stdout or '{}')
        hits = []
        for hit in data.get('results', []):
            hl = hit.get('start', {}).get('line', 0)
            cid = hit.get('check_id', '')
            if hl and cid:
                hits.append((hl, cid))
        _SEMGREP_CACHE[file_path] = hits
        for hit_line, check_id in hits:
            if abs(hit_line - defect_line) <= 3:
                return check_id
    except Exception:
        _SEMGREP_CACHE[file_path] = []
        pass
    return None

def _has_pattern(code: str, *patterns) -> bool:
    for pat in patterns:
        if re.search(pat, code, re.IGNORECASE):
            return True
    return False

def _event_descriptions(events: List[Dict]) -> str:
    return ' | '.join(e.get('description', '') for e in events)

def _event_types(events: List[Dict]) -> List[str]:
    return [e.get('type', '') for e in events]


# Unsafe-first ordering: always-unsafe sinks checked before bounded variants
_SINK_PRIORITY = ['strcpy', 'strcat', 'sprintf', 'gets', 'vsprintf', 'wcscpy', 'wcscat',
                  'memcpy', 'memmove', 'strncpy', 'strncat', 'snprintf']


def _get_sink_function(code: str, target_line: int = 0, code_start_line: int = 1) -> str:
    """Extract the primary buffer sink from code, preferring always-unsafe sinks
    first.  When a flagged `target_line` is known, the sink appearing on or near
    that line wins over unrelated sinks elsewhere in the function body — this
    prevents e.g. a strcpy defect being labelled as memcpy just because the
    function also performs a memcpy somewhere else."""
    if target_line and code_start_line and target_line >= code_start_line:
        lines = code.splitlines()
        rel = target_line - code_start_line
        if 0 <= rel < len(lines):
            # Prefer the sink on the flagged line, then the nearest line outward
            # (dist 1, then 2), using sink priority only as a tiebreaker.  This
            # keeps a strcpy defect from being labelled memcpy (and vice-versa)
            # when the function touches many buffers.
            for dist in range(0, 3):
                offsets = [0] if dist == 0 else [-dist, dist]
                for off in offsets:
                    idx = rel + off
                    if 0 <= idx < len(lines):
                        for func in _SINK_PRIORITY:
                            if re.search(rf'\b{func}\s*\(', lines[idx]):
                                return func
    for func in _SINK_PRIORITY:
        if re.search(rf'\b{func}\s*\(', code):
            return func
    return ""


def _get_sink_from_events(events: List[Dict]) -> str:
    """Extract the defect sink function from Coverity event descriptions.

    Prefers the precise overflow/buffer-size event that names the exact sink
    ("Calling 'strcpy' with a maximum size argument of N bytes on destination
    array 'x'"), then falls back to the *last* generic 'calling X' event.  The
    last-event preference stops a sibling sprintf/strcpy earlier in the trace
    from being reported as the defect when the actual flagged sink is strcpy.
    """
    # 1) Authoritative sink named in the BUFFER_SIZE/STRING_NULL overflow event.
    #    Coverity orders events source->sink, so the flagged copy is the *last*
    #    precise overflow event (a safe sprintf into a temp can precede it).
    for ev in reversed(events):
        desc = ev.get('description', '') or ''
        m = re.search(
            r"[Cc]alling\s+['\"](\w+)['\"]\s+with\s+a\s+(?:maximum\s+)?size\s+argument"
            r"\s+of\s+\d+\s+bytes\s+on\s+destination\s+(?:array|buffer|string)", desc)
        if m and m.group(1).lower() in _SINK_PRIORITY:
            return m.group(1).lower()
    # 2) Generic 'calling X' — the last event is nearest the flagged failure.
    for ev in reversed(events):
        desc = ev.get('description', '') or ''
        if m := re.search(r"[Cc]alling\s+['\"](\w+)['\"]|[Cc]alling\s+(\w+)\b", desc):
            fn = (m.group(1) or m.group(2) or '').lower()
            if fn in _SINK_PRIORITY:
                return fn
    return ""


def _extract_call_args_from(code: str, func_name: str, match_start: int) -> List[str]:
    """Parse the arguments of a `func_name(` call whose name begins at
    match_start, reading through the matching close paren and handling nested
    brackets and struct members."""
    paren = code.find('(', match_start)
    if paren < 0:
        return []
    start = paren + 1
    depth = 1
    i = start
    while i < len(code) and depth > 0:
        if code[i] == '(':
            depth += 1
        elif code[i] == ')':
            depth -= 1
        i += 1
    arg_str = code[start:i - 1]
    args, current, depth = [], [], 0
    for ch in arg_str:
        if ch in '([{':
            depth += 1
            current.append(ch)
        elif ch in ')]}':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            args.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        args.append(''.join(current).strip())
    return [a for a in args if a]


def _extract_call_args(code: str, func_name: str) -> List[str]:
    """Extract arguments to the first `func_name(` call in code."""
    m = re.search(rf'\b{re.escape(func_name)}\s*\(', code)
    if not m:
        return []
    return _extract_call_args_from(code, func_name, m.start())


def _extract_call_args_near(code: str, func_name: str, target_line: int,
                            code_start_line: int = 1) -> List[str]:
    """Extract the arguments of the `func_name(` call closest to the flagged
    absolute `target_line`, so a finding quotes the call actually at the flagged
    line instead of the first such call elsewhere in the function (which can be
    a different string literal / size). Falls back to the first call when no
    target line is known."""
    if not func_name:
        return []
    if not target_line or target_line <= 0:
        return _extract_call_args(code, func_name)
    best_idx, best_dist = None, None
    pos = 0
    while True:
        m = re.search(rf'\b{re.escape(func_name)}\s*\(', code[pos:])
        if not m:
            break
        idx = pos + m.start()
        line_of_call = code.count('\n', 0, idx) + 1            # snippet-relative
        abs_line = line_of_call + (code_start_line or 1) - 1   # absolute file line
        dist = abs(abs_line - target_line)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_idx = idx
        pos = pos + m.end()
    if best_idx is None:
        return []
    return _extract_call_args_from(code, func_name, best_idx)



def _bounded_api_note(api: str, code: str, target_line: int = 0,
                      code_start_line: int = 1) -> str:
    """Expert-level justification for dismissing a false positive on a bounded
    string/memory API.

    Rather than the generic 'the bounded API is used, which is good practice', it
    cites the concrete call (real destination / size argument) and explains *why*
    the copy cannot overrun the destination — the exact reasoning a C reviewer
    would accept when closing a Coverity OVERRUN/BUFFER_SIZE finding.  The call
    closest to the flagged line is quoted so a function with several bounded
    copies reports the one actually under review, not the first in the snippet.
    """
    call_desc = f"{api}()"
    args = []
    m = re.search(rf'\b{re.escape(api)}\s*\(', code)
    if m:
        args = _extract_call_args_near(code, api, target_line, code_start_line)
        if args:
            call_desc = f"{api}(" + ', '.join(args) + ")"

    if api == 'strncpy' and len(args) >= 3:
        # strncpy(dst, src, n): writes at most n bytes to dst — never more.
        dst, n = args[0], args[2]
        return (f"{call_desc} is a bounded copy: it writes no more than its size "
                f"argument ({n}) into `{dst}`. Because {n} is capped at the "
                f"destination's declared capacity (a sizeof/size constant), the write is "
                f"confined to the buffer's extent and cannot overrun past `{dst}`")

    if api == 'strncat' and len(args) >= 3:
        # strncat(dst, src, n): appends at most n bytes to dst — the total can never
        # exceed the pre-existing length plus n, and n is the caller's bound.
        dst, n = args[0], args[2]
        return (f"{call_desc} appends at most {n} bytes to `{dst}` and the size argument "
                f"is derived from the destination's capacity, so the result cannot be "
                f"written past the end of `{dst}`")

    if api == 'snprintf' and len(args) >= 2:
        # snprintf(dst, sz, ...): writes at most sz-1 chars, then always NUL-terminates.
        dst, sz = args[0], args[1]
        return (f"{call_desc} writes at most sizeof-1 characters to `{dst}` and always "
                f"appends the null terminator, so `{dst}` is both bounded and "
                f"null-terminated")

    return (f"{call_desc} bounds the operation by an explicit size argument, so it can "
            f"never write past the destination buffer's declared capacity")


def _extract_vars_from_events(events: List[Dict]) -> Dict[str, str]:
    """Parse Coverity event descriptions to extract dest_var, src_var, buffer_info."""
    result = {'dest_var': '', 'src_var': '', 'buffer_info': '', 'size_bytes': 0}
    for ev in events:
        desc = ev.get('description', '')
        m = re.search(
            r'[Cc]alling\s+[\'"][\w]+[\'"]\s+with\s+a\s+(?:maximum\s+)?size\s+argument\s+of\s+(\d+)\s+bytes\s+on\s+destination\s+(?:array|buffer|string)\s+[\'"]([^\'"]+)[\'"]',
            desc)
        if m:
            result['size_bytes'] = int(m.group(1))
            result['dest_var'] = m.group(2).strip()
            m2 = re.search(r'of\s+size\s+(\d+)\s+bytes', desc)
            if m2:
                sz = int(m2.group(1))
                result['buffer_info'] = f"`{result['dest_var']}` is a buffer of {sz} bytes (from Coverity event). "
            continue
        md = re.search(r"""destination\s+(?:array|buffer|string)?\s*['\"]([^'\"]+)['\"]""", desc)
        if md and not result['dest_var']:
            result['dest_var'] = md.group(1).strip()
        ms = re.search(r"""source\s+(?:array|buffer|string)?\s*['\"]([^'\"]+)['\"]""", desc)
        if ms and not result['src_var']:
            result['src_var'] = ms.group(1).strip()
    return result


def _fmt_location(file: str, line, function: str) -> str:
    parts = []
    if file:
        loc = file
        if line and str(line).isdigit() and int(line) > 0:
            loc += f":{line}"
        parts.append(loc)
    if function:
        parts.append(f"in function {function}()")
    if not parts:
        return ""
    return " ".join(parts)

def _build_comment_from_evidence(decision: AgentDecision, ctx: Dict) -> str:
    """
    Security-advocate-grade triage comment: root cause, attack vector,
    impact, proof evidence, and reviewer action items (all in paragraph form).
    """
    import os

    func        = ctx.get('function', 'this function')
    line        = ctx.get('line', 0)
    file        = ctx.get('file', '')
    fname       = os.path.basename(file) if file else 'the source file'
    checker     = ctx.get('checker', '')
    sink        = ctx.get('sink_func', '')
    var         = ctx.get('var', '')
    src_var     = ctx.get('src_var', '')
    dest_var    = ctx.get('dest_var', '')
    origin      = ctx.get('origin', '')
    guard_line  = ctx.get('guard_line', 0)
    guard_cond  = ctx.get('guard_cond', '')
    guard_reason  = ctx.get('guard_reason', '')
    guard_covers  = ctx.get('guard_covers_all_paths', False)
    safe_api    = ctx.get('safe_api_note', '')
    buffer_info = ctx.get('buffer_info', '')
    taint       = ctx.get('taint_desc', '')
    confidence  = decision.confidence
    code        = ctx.get('code', '')
    called_codes  = ctx.get('called_function_codes', {}) or {}
    callers     = ctx.get('callers', [])
    callee_names  = ctx.get('called_functions', [])
    data_flow   = ctx.get('data_flow_trace', '')
    ev_array_size = ctx.get('ev_array_size')
    ev_index    = ctx.get('ev_index_value')

    loc = f"{func}() [{fname} line {line}]" if line else f"{func}() [{fname}]"
    cwe = _cwe_header(checker)
    cwe_sentence = f" {cwe}." if cwe else ""

    # ------------------------------------------------------------------
    # BUG — security-advocate writeup (CWE/CERT/OWASP perspective)
    # ------------------------------------------------------------------
    if decision.classification == "Bug":
        _CHECKER_LABELS = {
            'OVERRUN':                    'Out-of-bounds memory access (OVERRUN)',
            'BUFFER_SIZE':                'Buffer overflow / missing null terminator (BUFFER_SIZE)',
            'FORWARD_NULL':               'Null-pointer dereference (FORWARD_NULL)',
            'REVERSE_INULL':              'Null-pointer dereference — check after use (REVERSE_INULL)',
            'INTEGER_OVERFLOW':           'Integer overflow / wraparound (INTEGER_OVERFLOW)',
            'RESOURCE_LEAK':              'Resource leak (RESOURCE_LEAK)',
            'USE_AFTER_FREE':             'Use-after-free memory corruption (USE_AFTER_FREE)',
            'DEADCODE':                   'Unreachable dead code (DEADCODE)',
            'UNINIT':                     'Use of uninitialized variable (UNINIT)',
            'DIVIDE_BY_ZERO':             'Division by zero (DIVIDE_BY_ZERO)',
            'NEGATIVE_RETURNS':           'Signed error-code used as unsigned size/index (NEGATIVE_RETURNS)',
            'SIZEOF_MISMATCH':            'sizeof() type mismatch (SIZEOF_MISMATCH)',
            'ARRAY_VS_SINGLETON':         'Array/singleton confusion (ARRAY_VS_SINGLETON)',
            'STRING_NULL':                'Missing null terminator (STRING_NULL)',
            'UNUSED_VALUE':               'Computed value never consumed (UNUSED_VALUE)',
            'CONSTANT_EXPRESSION_RESULT': 'Constant-expression result always true/false',
            'SHIFT_OVERFLOW':             'Bit-shift overflow (SHIFT_OVERFLOW)',
            'NO_BREAK':                   'Missing break in switch (NO_BREAK)',
        }
        label = _CHECKER_LABELS.get(checker, f'Defect ({checker})')
        parts = [f"[CONFIRMED BUG] {label} in {loc}.{cwe_sentence}\n\n"]

        # Root cause
        parts.append("Root cause: ")
        if sink and src_var and dest_var:
            parts.append(f"`{sink}({dest_var}, {src_var}, ...)` copies data into `{dest_var}` "
                         f"without adequate length validation. ")
        elif sink and dest_var:
            parts.append(f"`{sink}()` writes to `{dest_var}` without bounds verification. ")
        elif sink:
            parts.append(f"`{sink}()` is invoked without bounds checking. ")
        elif var and var not in ('the variable', 'the pointer', 'the operand'):
            parts.append(f"`{var}` is used unsafely on this execution path. ")
        else:
            parts.append("The defect path is reachable with no effective safety guard. ")

        # Buffer / size evidence
        if buffer_info:
            parts.append(buffer_info.strip().rstrip('.') + ". ")
        if ev_array_size is not None and ev_index is not None:
            verdict = 'confirmed out-of-bounds' if ev_index >= ev_array_size else 'borderline — verify'
            parts.append(f"Coverity trace: array size = {ev_array_size}, accessed index = {ev_index} ({verdict}). ")

        # Data origin / taint
        parts.append("\nData origin: ")
        if taint and 'user-controlled' in taint:
            parts.append(f"`{src_var or var}` originates from {origin}. "
                         f"This is attacker-controlled input that reaches the sink without sanitization — "
                         f"a textbook taint-to-sink flow. ")
        elif origin and origin not in ('an unknown source', ''):
            parts.append(f"`{src_var or var or 'the operand'}` is sourced from {origin}. "
                         f"This source can supply unexpected lengths or error-code values that propagate unchecked. ")
        else:
            parts.append("Data origin is unresolved; treat as potentially untrusted. ")

        # Guard failure
        if guard_reason and not guard_covers:
            parts.append(f"\nGuard analysis: {guard_reason.strip()} "
                         f"This guard does NOT cover all paths to the vulnerable operation. ")
        elif not guard_line:
            parts.append("\nGuard analysis: No bounds or null check was found before the vulnerable operation "
                         "in the extracted code. ")

        # Cross-function taint
        callee_bugs = []
        for name, ccode in called_codes.items():
            if name.startswith('__') or not isinstance(ccode, str):
                continue
            if re.search(r'(?:recv|fgets|read|scanf|getenv|fread|accept|recvfrom)\s*\(', ccode):
                callee_bugs.append(f"`{name}()` ingests external data (taint source)")
            elif re.search(r'(?:malloc|calloc|realloc)\s*\(', ccode):
                callee_bugs.append(f"`{name}()` allocates memory and may return NULL")
        if callee_bugs:
            parts.append("\nCross-function analysis: " + "; ".join(callee_bugs) + ". ")

        # Data flow trace
        if data_flow:
            df_lines = [l.strip() for l in data_flow.splitlines()
                        if l.strip() and 'Data flow' not in l][:4]
            if df_lines:
                parts.append("\nData flow trace: " + " → ".join(df_lines) + ". ")

        # Call sites
        if callers:
            clist = list(dict.fromkeys([c.get('caller', '') for c in callers if c.get('caller')]))[:3]
            if clist:
                parts.append(f"\nReachable from: {', '.join(clist)}. ")

        # Impact
        _IMPACT = {
            'OVERRUN':        ("Memory corruption" +
                               (" via attacker-controlled input — potential heap/stack overwrite "
                                "enabling code execution or control-flow hijacking."
                                if taint and 'user-controlled' in taint else
                                " — adjacent memory corrupted; may crash or enable code execution "
                                "depending on allocation layout.")),
            'BUFFER_SIZE':    ("Buffer overflow — destination can be overwritten beyond its declared size. "
                               "If the destination is on the stack, this can overwrite the return address."),
            'FORWARD_NULL':   ("Null-pointer dereference — process crash (denial of service). "
                               "On platforms permitting null-page mapping this can be elevated to code execution."),
            'REVERSE_INULL':  ("Null-pointer dereference — same impact as FORWARD_NULL; the check order "
                               "means the dereference precedes or bypasses the guard."),
            'INTEGER_OVERFLOW': ("Integer overflow — if the wrapped value is used as an allocation size "
                                 "or array index, downstream operations act on an undersized buffer, "
                                 "leading to heap corruption."),
            'RESOURCE_LEAK':  ("Resource exhaustion — repeated invocations leak the resource, "
                               "eventually exhausting file descriptors, memory, or OS handles (denial of service)."),
            'USE_AFTER_FREE': ("Use-after-free — if an attacker controls heap layout they can place "
                               "crafted data in the freed region and have it interpreted as a pointer or vtable entry "
                               "(code execution primitive)."),
            'UNINIT':         ("Uninitialized data — sensitive residual bytes from a prior stack frame may leak "
                               "(information disclosure), or unpredictable control flow if used in a branch."),
            'DIVIDE_BY_ZERO': ("Process crash via SIGFPE — denial of service; non-recoverable in kernel/embedded contexts."),
            'NEGATIVE_RETURNS': ("Signed-to-unsigned conversion — a -1 error code becomes ~0 (UINT_MAX), "
                                 "causing catastrophic over-allocation or a massive out-of-bounds index."),
            'SIZEOF_MISMATCH': ("Wrong copy/compare size — may read/write beyond the intended memory region, "
                                "causing heap corruption or information disclosure."),
        }
        impact = _IMPACT.get(checker, "Unpredictable behavior, process termination, or data corruption.")
        parts.append(f"\nSecurity impact: {impact} ")

        # Remediation
        _FIXES = {
            'OVERRUN':        f"Change the guard to use strict `<` (not `<=`) against the array size, "
                              f"or add: `if ({var or 'index'} >= array_size) return ERROR;` before the access.",
            'BUFFER_SIZE':    f"Replace `{sink or 'the copy function'}` with a bounded variant "
                              f"(snprintf/strlcpy/memcpy_s) and ensure the size argument is strictly less than "
                              f"the destination capacity.",
            'FORWARD_NULL':   f"Add `if (!{var or 'ptr'}) {{ /* handle */ return ERROR; }}` "
                              f"immediately before the first dereference at line {line}.",
            'REVERSE_INULL':  f"Move the null check for `{var or 'ptr'}` to before the first dereference, "
                              f"not after. Pattern: `if (!ptr) return; use(ptr);`",
            'INTEGER_OVERFLOW': "Widen to int64_t before arithmetic, or add: "
                                "`if (a > INT_MAX / b) return ERROR_OVERFLOW; result = a * b;`",
            'RESOURCE_LEAK':  "Ensure every allocation path has a matching release on all exit paths. "
                              "Use goto-cleanup or RAII.",
            'USE_AFTER_FREE': f"Set `{var or 'ptr'} = NULL` immediately after `free()` and validate "
                              f"with `if (!ptr) return;` before reuse.",
            'UNINIT':         f"Initialize at declaration: `{var or 'var'} = 0;` "
                              f"or for structs: `struct T x = {{0}};`",
            'DIVIDE_BY_ZERO': "Add `if (divisor == 0) return ERROR;` before the division.",
            'NEGATIVE_RETURNS': "Check `if (result < 0) {{ /* handle error */ return; }}` "
                                "before using the value as a size or index.",
            'SIZEOF_MISMATCH': "Use `sizeof(*ptr)` instead of `sizeof(ptr)` to capture the pointed-to type.",
        }
        fix_text = _FIXES.get(checker, "Add input validation and explicit bounds/null checks before the flagged operation.")
        parts.append(f"\nAnalyst confidence: {int(confidence * 100)}%. This finding needs review before release.")
        return "".join(parts)

    # ------------------------------------------------------------------
    # FALSE POSITIVE / INTENTIONAL — detailed proof chain
    # ------------------------------------------------------------------
    if decision.classification in ("False positive", "Intentional"):
        # Natural review-trials style paragraph (img-2 format).
        disp_word = "a false positive" if decision.classification == "False positive" else "intentional"
        parts = [f"After reviewing {func}(), the {checker} at line {line} is {disp_word}.{cwe_sentence} "]

        evidence_items = []

        # Checker-local aliases for readable code.
        _guard_line   = guard_line
        _guard_cond   = guard_cond
        _guard_reason = guard_reason
        _buffer_info  = buffer_info
        _safe_api     = safe_api

        # ── Generic evidence filter ───────────────────────────────────────
        # Drop safe_api notes for non-buffer checkers (strncpy is irrelevant
        # for INTEGER_OVERFLOW / USE_AFTER_FREE, etc.) so comments stay
        # checker-relevant. buffer_info and guard info stay for all checkers —
        # a null/bounds guard is meaningful everywhere.
        # Only string/memory checkers should surface a safe-API dismissal reason.
        if checker not in ('BUFFER_SIZE', 'OVERRUN', 'MISSING_BREAK', 'USE_AFTER_FREE',
                           'RESOURCE_LEAK', 'STRING_NULL', 'BUFFER_SIZE_WARNING'):
            _safe_api = ''  # clear it so the block below is skipped

        if guard_covers and _guard_line:
            evidence_items.append(
                f"Guard at line {guard_line} ({guard_cond or 'condition'}) provably dominates every "
                f"execution path to the flagged operation — the dangerous state cannot be reached without "
                f"first passing the check."
            )
        elif guard_line:
            gr = guard_reason.strip().rstrip('.') if guard_reason else f"guard at line {guard_line}"
            gr = gr[:1].upper() + gr[1:]
            evidence_items.append(
                f"{gr}. No concrete bypass route was identified, though full CFG dominance could not be proven."
            )

        if _buffer_info:
            evidence_items.append(f"Buffer bounds: {_buffer_info.strip().rstrip('.')}.")

        if _safe_api:
            evidence_items.append(f"{_safe_api.strip().rstrip('.')}.")

        if origin and any(k in origin for k in ('safe', 'literal', 'local', 'bounded',
                                                  'stack', 'constant', 'trusted', 'sizeof')):
            evidence_items.append(f"Data is bounded/trusted at its origin: {origin}.")

        for name, ccode in called_codes.items():
            if name.startswith('__') or not isinstance(ccode, str):
                continue
            if re.search(r'(?:strncpy|strncat|snprintf|strlcpy|strlcat|memcpy_s|strcpy_s)\s*\(', ccode):
                evidence_items.append(f"`{name}()` uses bounded string APIs internally — safe by implementation.")
            if re.search(r'std::unique_ptr|std::shared_ptr|QScopedPointer', ccode):
                evidence_items.append(f"`{name}()` uses RAII smart pointers — resource lifetime managed automatically.")
            if re.search(r'\bfree\s*\(|fclose\s*\(|close\s*\(', ccode):
                evidence_items.append(f"`{name}()` contains the matching resource release — no leak on this path.")

        if checker == 'DEADCODE':
            if '#if 0' in code or '#ifdef NEVER' in code:
                evidence_items.append("Block is inside `#if 0` / `#ifdef NEVER` — intentionally compiled out.")
            if re.search(r'assert\s*\(\s*0\s*\)|assert\s*\(\s*false\s*\)', code):
                evidence_items.append("Follows `assert(0)` — intentional unreachable panic handler; not an active code path.")
            if re.search(r'TODO|FIXME|DEAD', code):
                evidence_items.append("Annotated TODO/FIXME — acknowledged placeholder, not a latent defect.")

        if checker == 'NO_BREAK':
            if re.search(r'//\s*fallthrough|/\*\s*fall.?through|FALLTHRU|FALLTHROUGH|\[\[fallthrough\]\]', code, re.I):
                evidence_items.append("Fall-through annotated with FALLTHROUGH / FALLTHRU — intentional control flow documented in source.")

        if checker == 'CONSTANT_EXPRESSION_RESULT':
            if re.search(r'assert\s*\(|static_assert\s*\(', code):
                evidence_items.append("Constant expression is inside a compile-time assertion — by-design invariant check.")
            if '#if' in code:
                evidence_items.append("Expression is within a preprocessor conditional — evaluated at compile time, not a runtime defect.")

        if checker == 'RESOURCE_LEAK':
            if re.search(r'std::unique_ptr|std::shared_ptr|auto_ptr|QScopedPointer|g_auto', code):
                evidence_items.append("RAII smart pointer or scope guard — automatic release on all paths including exceptions.")
            if re.search(r'goto\s+(cleanup|done|error|exit)', code):
                evidence_items.append("goto-cleanup idiom — all exit paths converge to a single release point.")

        if checker in ('FORWARD_NULL', 'REVERSE_INULL') and re.search(r'std::unique_ptr|std::shared_ptr', code):
            evidence_items.append("Smart pointer wrapper — null dereference prevented by the wrapper's invariants.")

        if not evidence_items:
            # Be specific about what was checked rather than a vague "no path found"
            _checked = []
            if ctx.get('guard_line'):
                _checked.append(f"guard at line {ctx['guard_line']} (`{ctx.get('guard_cond','check')}`) dominates the access")
            if ctx.get('buffer_info'):
                _checked.append(ctx['buffer_info'].strip().rstrip('.'))
            if ctx.get('safe_api_note'):
                _checked.append(ctx['safe_api_note'].strip().rstrip('.'))
            if _checked:
                _joined = "; ".join(_checked)
                evidence_items.append(_joined[:1].upper() + _joined[1:] +
                                      ". No counterexample was found in the extracted snippet (full inter-procedural analysis was not performed).")
            else:
                evidence_items.append("No concrete path to the defect was found in the extracted snippet; "
                                      "the finding may not be reachable at this call site.")

        if evidence_items:
            # Weave evidence behind "This is because ..." so the paragraph
            # reads like a reviewer wrote it (img-2 style) rather than a list.
            first = evidence_items[0]
            first = first[:1].lower() + first[1:] if first else first
            rest = evidence_items[1:]
            parts.append(f"This is because {first}")
            for item in rest:
                parts.append(f" {item}")

        # Confidence and caveats — natural sentence (img-2 style).
        if confidence >= 0.85:
            parts.append(" High confidence; no code changes are needed.")
        elif confidence >= 0.65:
            parts.append(" Moderate-high confidence; confirm the guard is not bypassed "
                         "by a macro or an unanalyzed call path before closing.")
        else:
            parts.append(f" Moderate confidence; a manual walkthrough of {func}() is recommended before closing.")
        return "".join(parts)

    # ------------------------------------------------------------------
    # NEEDS REVIEW — natural reviewer paragraph (img-2 style), not a
    # rigid template. Same voice as the False positive branch above.
    # ------------------------------------------------------------------
    parts = [f"After reviewing {func}(), the {checker} at line {line} needs a manual look.{cwe_sentence} "]

    _RISK = {
        'OVERRUN':                  'high — out-of-bounds writes are a primary memory-corruption vector',
        'BUFFER_SIZE':              'high — buffer overflows can enable stack/heap corruption',
        'FORWARD_NULL':             'medium — a null dereference causes denial of service',
        'REVERSE_INULL':            'medium — same as FORWARD_NULL, with the check order compounding the risk',
        'INTEGER_OVERFLOW':         'medium-high — overflows feeding sizes or indices can corrupt the heap',
        'USE_AFTER_FREE':           'high — use-after-free is a proven code-execution primitive',
        'RESOURCE_LEAK':            'low-medium — repeated leaks cause denial of service',
        'UNINIT':                   'medium — uninitialized variables can expose residual data',
        'DIVIDE_BY_ZERO':           'medium — a crash, non-recoverable in embedded contexts',
        'NEGATIVE_RETURNS':         'medium — signed/unsigned mismatch can cause a large out-of-bounds access',
        'SIZEOF_MISMATCH':          'medium — an incorrect size can corrupt adjacent memory',
        'DEADCODE':                 'low — no runtime vulnerability, but adds maintenance risk',
        'UNUSED_VALUE':             'low — may indicate an unchecked return code',
        'ARRAY_VS_SINGLETON':       'medium — if the callee iterates the argument this is an out-of-bounds write',
        'SHIFT_OVERFLOW':           'medium — undefined behavior in C',
        'NO_BREAK':                 'low-medium — unintended fall-through can run unrelated case logic',
        'CONSTANT_EXPRESSION_RESULT': 'low — likely a design artifact',
    }
    risk = _RISK.get(checker, 'unclear — treat it as medium risk until reviewed')
    parts.append(f"The preliminary risk is {risk}. ")

    # Reasons the automated pass could not decide — woven into prose below.
    gaps = []

    if not code or len(code.splitlines()) < 5:
        gaps.append("the snippet is too small to trace the data flow")

    if guard_line and not guard_covers:
        gaps.append(f"a guard at line {guard_line} could not be confirmed to cover all paths to line {line}")
    elif not guard_line and checker in ('FORWARD_NULL', 'REVERSE_INULL', 'BUFFER_SIZE', 'OVERRUN', 'INTEGER_OVERFLOW'):
        _subj = f" for `{var or src_var}`" if (var or src_var) else ""
        gaps.append(f"no bounds/null guard{_subj} was found before line {line} (it may be in a caller or macro)")

    if not origin or origin in ('an unknown source',):
        _osubj = (f"`{var or src_var}`" if (var or src_var) else "the flagged value")
        gaps.append(f"the origin of {_osubj} is unresolved — if caller-controlled this may be a real bug")
    elif any(k in origin for k in ('args', 'network', 'env', 'file', 'external', 'caller-controlled')):
        gaps.append(f"the input comes from {origin} (untrusted) and must be validated before line {line}")

    if callee_names and not called_codes:
        gaps.append(f"source for callee(s) {', '.join(callee_names[:2])} was unavailable, so cross-function safety could not be assessed")

    _CHECKER_GAPS = {
        'ARRAY_VS_SINGLETON':       "whether the callee iterates the argument is unknown — if so, this is an OOB write",
        'RESOURCE_LEAK':            "not every allocation path could be matched with a release",
        'DEADCODE':                 "whether the block is truly unreachable or build-disabled is unclear",
        'SIZEOF_MISMATCH':          "whether `sizeof()` applies to the pointer or the pointee could not be resolved",
        'INTEGER_OVERFLOW':         "operand bounds could not be determined statically",
        'SHIFT_OVERFLOW':           "the shift amount could not be determined statically",
        'NO_BREAK':                 "intent behind the fall-through is not documented in the snippet",
    }
    if checker in _CHECKER_GAPS:
        gaps.append(_CHECKER_GAPS[checker])

    if not gaps:
        gaps.append("the available signals are conflicting")

    # Keep it short: state only the main blocker, then hand over to the
    # reviewer. The Proposed Fix panel carries the detailed guidance.
    parts.append(f"I could not fully verify this because {gaps[0]}. ")
    parts.append(f"Analyst confidence: {int(confidence * 100)}%.")
    return "".join(parts)

def _build_analysis_context(code: str, checker: str, events: List[Dict],
                            file: str, line: int, function: str, cid: int = 0,
                            called_function_codes: Optional[Dict[str, str]] = None,
                            code_start_line: int = 1) -> Dict:
    """
    Build a rich analysis context by running deep static analysis.
    Returns a dictionary with all findings needed for expert comment generation.
    """
    ctx = {
        'cid': cid,
        'checker': checker,
        'file': file,
        'line': line,
        'function': function or 'this function',
        'code': code,
        'code_start_line': code_start_line,
        'events': events,
        'sink_func': '',
        'src_var': '',
        'dest_var': '',
        'var': '',
        'origin': 'an unknown source',
        'taint_desc': '',
        'buffer_info': '',
        'guard_reason': '',
        'guard_line': 0,
        'guard_cond': '',
        'impact_sentence': '',
        'resource': '',
        'resource_type': '',
        'release_func': '',
        'alloc_expr': '',
        'raii_type': '',
        'leak_paths': 'some error paths',
        'alloc_line': 0,
        'release_line': 0,
        'operation': 'arithmetic',
        'operand': 'value',
        'safe_api_note': '',
        'uncertainty_reason': 'the data flow.',
        'default_comment': 'Manual review required.',
        'callers_list': [],
        'semgrep_rule': '',
    }

    if called_function_codes:
        raw_callers = called_function_codes.get('__callers__', [])
        ctx['callers_list'] = raw_callers if isinstance(raw_callers, list) else []

    calls = _find_function_calls(code)

    # Prefer the Coverity event trace, which names the exact API it flagged, over
    # the code-level guess. This keeps a strcpy finding from being reported as
    # memcpy merely because the function also performs a memcpy. Fall back to the
    # code scan when the events don't name a buffer sink.
    sink = _get_sink_from_events(events) or _get_sink_function(code, line, code_start_line)
    args = []
    if sink:
        ctx['sink_func'] = sink
        args = _extract_call_args_near(code, sink, line, code_start_line)
        if len(args) >= 2:
            ctx['dest_var'] = args[0]
            ctx['src_var'] = args[1] if len(args) > 1 else args[0]
            ctx['var'] = ctx['src_var']

    if sink == 'memcpy' and len(args) >= 3:
        ctx['copy_size'] = args[2]

    if ctx['var']:
        taint = _find_variable_origin(code, ctx['var'], depth=4)
        if taint:
            origin_map = {
                'network': 'a network receive buffer',
                'args': 'function arguments (caller-controlled)',
                'env': 'an environment variable',
                'file': 'a file read operation',
                'alloc': 'a heap allocation (may return NULL)',
                'convert': 'a string-to-integer conversion',
                'string': 'a string copy operation',
            }
            ctx['origin'] = origin_map.get(taint.source_type, taint.source_type)
            if taint.source_type in ('network', 'args', 'env', 'file'):
                ctx['taint_desc'] = "user-controlled data from " + ctx['origin'] + " "
            elif taint.source_type == 'alloc':
                ctx['taint_desc'] = "potentially NULL data from " + ctx['origin'] + " "
            else:
                ctx['taint_desc'] = "data from " + ctx['origin'] + " "

    if ctx['dest_var']:
        buf = infer_buffer_info(code, ctx['dest_var'])
        if buf:
            if buf.alloc_type == 'stack':
                ctx['buffer_info'] = f"`{buf.var}` is a stack buffer of {buf.size_bytes} bytes ({buf.size_expr}). "
            elif buf.alloc_type in ('malloc', 'calloc'):
                ctx['buffer_info'] = f"`{buf.var}` is heap-allocated with size {buf.size_expr} ({buf.size_bytes} bytes). "
            elif buf.alloc_type == 'literal':
                ctx['buffer_info'] = f"`{buf.var}` points to a string literal of {buf.size_bytes} chars. "

    guard_var = ctx['var'] or ctx['dest_var']
    if guard_var:
        guard_result = analyze_guard_dominance(code, guard_var, line)
        if guard_result['has_guard']:
            abs_guard = guard_result['guard_line']
            if code_start_line > 1:
                abs_guard = guard_result['guard_line'] + code_start_line - 1
            ctx['guard_line'] = abs_guard
            ctx['guard_cond'] = guard_result.get('guard_type', 'unknown')
            ctx['guard_covers_all_paths'] = guard_result.get('guard_covers_all_paths', False)
            ctx['guard_bypass_paths'] = guard_result.get('bypass_paths', [])
            if guard_result['guard_covers_all_paths']:
                ctx['guard_reason'] = f"a {guard_result['guard_type'].replace('_', ' ')} on `{guard_var}` exists at line {guard_result['guard_line']} and covers all paths. "
            else:
                ctx['guard_reason'] = f"a guard exists at line {guard_result['guard_line']}, but it may not cover all execution paths. "

    if ctx['taint_desc'] and 'user-controlled' in ctx['taint_desc']:
        ctx['impact_sentence'] = "An attacker could exploit this to achieve remote code execution or a denial of service."
    elif ctx['origin'] == 'a heap allocation (may return NULL)':
        ctx['impact_sentence'] = "If allocation fails, this will dereference NULL and crash the process."
    else:
        ctx['impact_sentence'] = "This could lead to memory corruption or unexpected behavior."

    alloc_funcs = ['malloc', 'calloc', 'realloc', 'fopen', 'open', 'socket', 'strdup']
    release_map = {'malloc': 'free', 'calloc': 'free', 'realloc': 'free', 'fopen': 'fclose',
                   'open': 'close', 'socket': 'close', 'strdup': 'free'}
    for call in calls:
        if call.func in alloc_funcs:
            ctx['resource'] = call.args[0] if call.args else call.func + "_result"
            ctx['resource_type'] = 'FILE*' if call.func == 'fopen' else 'void*'
            ctx['release_func'] = release_map.get(call.func, 'release')
            ctx['alloc_expr'] = f"{call.func}({', '.join(call.args)})"
            ctx['alloc_line'] = call.line_hint + code_start_line - 1
            break

    for call in calls:
        if call.func in release_map.values():
            ctx['release_line'] = call.line_hint + code_start_line - 1
            break

    safe_apis = ['strncpy', 'strncat', 'snprintf', 'strlcpy', 'strlcat', 'memcpy_s', 'strcpy_s']
    for api in safe_apis:
        if re.search(rf'\b{api}\s*\(', code):
            ctx['safe_api_note'] = _bounded_api_note(api, code, line, code_start_line)
            break

    if called_function_codes:
        taint_funcs = ['recv', 'fgets', 'read', 'scanf', 'getenv', 'fread', 'accept', 'recvfrom']
        for fn_name, fn_code in called_function_codes.items():
            if fn_name.startswith('__') or not isinstance(fn_code, str):
                continue
            for tf in taint_funcs:
                if re.search(rf'\b{tf}\s*\(', fn_code):
                    if not ctx['taint_desc']:
                        ctx['taint_desc'] = f"data passed through {fn_name}() which reads from external input via {tf}() "
                        ctx['origin'] = f"{fn_name}() (calls {tf}() internally)"
                    break

    ev_vars = _extract_vars_from_events(events)
    if not ctx['dest_var'] and ev_vars['dest_var']:
        ctx['dest_var'] = ev_vars['dest_var']
    if not ctx['src_var'] and ev_vars['src_var']:
        ctx['src_var'] = ev_vars['src_var']
    if not ctx['buffer_info'] and ev_vars['buffer_info']:
        ctx['buffer_info'] = ev_vars['buffer_info']
    if ev_vars['size_bytes'] and not ctx.get('ev_dest_size'):
        ctx['ev_dest_size'] = ev_vars['size_bytes']
    if not ctx['var']:
        ctx['var'] = ctx['src_var'] or ctx['dest_var'] or 'the variable'
    # Normalize generic figure-of-speech placeholders so downstream text builders
    # use their own neutral wording instead of printing e.g. `the variable` in backticks.
    for _vk in ('var', 'src_var', 'dest_var'):
        _vv = ctx.get(_vk, '')
        if isinstance(_vv, str) and _vv.lower() in (
                'the variable', 'the pointer', 'the operand', 'the data',
                'the flagged variable', 'the destination buffer', 'the source data'):
            ctx[_vk] = ''
    if not ctx['var']:
        ctx['var'] = ctx['src_var'] or ctx['dest_var'] or ''
    if not ctx['dest_var']:
        ctx['dest_var'] = ''
    if not ctx['src_var']:
        ctx['src_var'] = ''
    if not ctx['src_var']:
        ctx['src_var'] = 'the source data'

    ctx['source_origin'] = ctx['origin']
    ctx['guard_desc']    = ctx['guard_reason'] or 'no bounds/null guard found in extracted context'

    event_text = ' | '.join(
        e.get('description', '').strip() for e in events if e.get('description', '').strip()
    )
    ctx['event_context'] = f"Coverity trace: {event_text}" if event_text else ''

    ev = parse_coverity_events(events)
    ctx['ev'] = ev

    if ev['taint_confirmed'] and not ctx['taint_desc']:
        ctx['taint_desc'] = 'user-controlled data (confirmed by static trace analysis) '
        ctx['origin']     = 'a tainted external source'

    if ev['guard_on_path'] and ev['guard_takes_true'] and not ctx['guard_reason']:
        ctx['guard_reason'] = 'a guard condition was verified (true branch) before this operation on the flagged path. '

    ctx['ev_variables']    = ev['variables']
    ctx['ev_return_vals']  = ev['return_values']
    ctx['ev_array_size']   = ev['array_size']
    ctx['ev_index_value']  = ev['index_value']
    ctx['ev_null_var']     = ev['confirmed_null_var']

    confidence = 0.5
    if ev['defect_confirmed']:
        confidence += 0.35
    if ev['taint_confirmed']:
        confidence += 0.15
    if ev['guard_on_path'] and ev['guard_takes_true']:
        confidence -= 0.3
    if not code or len(code.splitlines()) < 5:
        confidence -= 0.2
    ctx['confidence'] = max(0.0, min(1.0, confidence))

    ctx['semgrep_rule'] = ''
    if file:
        sg_rule = _run_semgrep_check(file, line, checker)
        if sg_rule:
            ctx['semgrep_rule'] = sg_rule
            ctx['confidence'] = min(1.0, ctx['confidence'] + 0.15)

    primary_var = (ctx['src_var'] if ctx['src_var'] not in ('the source data',) else '') \
                   or (ctx['var'] if ctx['var'] not in ('the variable',) else '') \
                   or ''
    ctx['data_flow_trace'] = build_data_flow_trace(
        code, primary_var, line, called_function_codes
    ) if primary_var else ''

    return ctx


# ---------------------------------------------------------------------------
# Per-checker deep analysis functions — evidence-based with improved accuracy
# ---------------------------------------------------------------------------

def _apply_example_style(classification, checker, ctx, code, code_start_line,
                         line, function, comment):
    """Restyled the comment into the concise example disposition format
    (facts-driven narrative ending in 'False positive.' / 'Bug' wording) when
    the dedicated renderer can extract concrete code facts.  Otherwise the
    analyzer's existing comment is kept unchanged."""
    try:
        styled = render_example_comment(classification, checker, ctx, code,
                                        code_start_line, line, function)
    except Exception:
        styled = None
    return styled if styled else comment


def _analyze_buffer_size(code: str, sub_checker: str, events: List[Dict],
                         file: str = "", line: int = 0, function: str = "", cid: int = 0,
                         called_function_codes: Optional[Dict[str, str]] = None,
                         code_start_line: int = 1, tree=None) -> Tuple[str, str, str, float]:
    ctx = _build_analysis_context(code, 'BUFFER_SIZE', events, file, line, function, cid, called_function_codes, code_start_line)
    sink = ctx['sink_func']
    ev = ctx['ev']

    acc = build_evidence(ctx, ev, 'BUFFER_SIZE')

    dest_sz = ctx.get('ev_dest_size', 0)
    copy_sz = ev.get('index_value', 0)
    is_strncpy_sink = sink in ('strncpy', 'strncat')
    _size_eq_event = any(
        re.search(r'unterminated|null.terminat|size.*equals|equals.*size|no.*null|buffer.size', e.get('description', ''), re.I)
        for e in events
    )
    # Also detect: strncpy(dest, src, sizeof(dest)) — third arg equals sizeof first arg
    _size_eq_code = False
    if is_strncpy_sink:
        _args3 = _extract_call_args(code, sink)
        if len(_args3) >= 3:
            _d3 = _args3[0].strip()
            _s3 = _args3[2].strip()
            # size arg is sizeof(dest) or a matching constant/macro (same token as dest or dest field)
            _base_dest = re.split(r'[.\->\[\s]', _d3)[0]
            if re.search(rf'sizeof\s*\(\s*{re.escape(_base_dest)}', _s3) or (
                    _s3 and _s3 == _base_dest):
                _size_eq_code = True
            # If third arg doesn't end with -1 or -sizeof, it's likely full-size (no room for NUL)
            if not re.search(r'-\s*1\s*$|-\s*sizeof\s*\(', _s3):
                if re.search(r'\bsizeof\b', _s3) and not re.search(r'-\s*1\s*$', _s3):
                    _size_eq_code = True  # sizeof(dest) without -1 means no room for NUL
    if is_strncpy_sink and (_size_eq_event or _size_eq_code or (dest_sz and copy_sz and copy_sz >= dest_sz)):
        if dest_sz and copy_sz:
            ctx['buffer_info'] = ctx['buffer_info'] or (
                f"`{ctx['dest_var']}` has {dest_sz} bytes and {sink}() copies up to {copy_sz} bytes — "
                f"no room for the null terminator. "
            )
        acc.add(Evidence(
            label="strncpy_no_null_terminator",
            polarity="bug",
            weight=0.85,
            description=f"{sink}() size equals destination size — leaves string unterminated."
        ))

    if _has_pattern(code, r'\bstrncpy\b|\bstrncat\b|\bsnprintf\b|\bstrlcpy\b') and \
       (_has_pattern(code, r'sizeof\s*\([^)]*\)\s*-\s*1') or ctx['guard_line'] > 0):
        ctx['guard_reason'] = ctx.get('guard_reason') or "bounded string functions with size = sizeof(dest)-1 are used, preserving the null terminator slot. "
        acc.add(Evidence(
            label="safe_bounded_api_with_sizeof",
            polarity="fp",
            weight=0.70,
            description="Bounded string function with sizeof(dest)-1 size argument."
        ))

    if _has_pattern(code, r'\[\s*(?:sizeof.*-\s*1|\w+\s*-\s*1)\s*\]\s*=\s*["\']\\0["\']') and \
       _has_pattern(code, r'\bstrncpy\b|\bmemcpy\b'):
        acc.add(Evidence(
            label="explicit_null_termination_after_copy",
            polarity="fp",
            weight=0.75,
            description="Buffer explicitly null-terminated after bounded copy."
        ))

    if sink in ('strcpy', 'strcat', 'wcscpy', 'wcscat', 'gets'):
        src = ctx['src_var']
        if src and src != 'the source data' and re.search(rf'\b{re.escape(src)}\b.*sizeof|sizeof.*\b{re.escape(src)}\b', code):
            acc.add(Evidence(
                label="unsafe_sink_but_bounded_source",
                polarity="fp",
                weight=0.55,
                description=f"{sink}() used but source appears bounded by sizeof."
            ))
        else:
            acc.add(Evidence(
                label="always_unsafe_sink",
                polarity="bug",
                weight=0.75,
                description=f"Always-unsafe sink {sink}() with no visible bounds."
            ))

    if sink == 'sprintf':
        acc.add(Evidence(
            label="sprintf_unbounded",
            polarity="bug",
            weight=0.60,
            description="sprintf() is unbounded and can overflow destination."
        ))

    if sink == 'memcpy':
        # Use flow_analysis to check if memset precedes memcpy on all paths
        if _FLOW_ANALYSIS and ctx.get('dest_var'):
            try:
                preceding_memsets = _fa.find_preceding_calls(code, 'memset', line, code_start_line)
                dest_var = ctx.get('dest_var', '')
                memset_for_dest = [m for m in preceding_memsets if dest_var in m.get('args', '')]
                if memset_for_dest:
                    acc.add(Evidence(
                        label="memset_before_memcpy_cfg",
                        polarity="fp",
                        weight=0.65,
                        description=f"CFG confirms memset({dest_var}) at line {memset_for_dest[-1]['line']} precedes memcpy — destination pre-zeroed."
                    ))
            except Exception:
                pass
        if not ctx['guard_line'] and not _has_pattern(code, r'sizeof\s*\('):
            acc.add(Evidence(
                label="memcpy_without_size_guard",
                polarity="bug",
                weight=0.55,
                description="memcpy() without visible size guard or sizeof."
            ))
        else:
            acc.add(Evidence(
                label="memcpy_with_size_guard",
                polarity="fp",
                weight=0.50,
                description="memcpy() size appears bounded."
            ))

    decision = DecisionAgent.evaluate(acc, 'BUFFER_SIZE')

    func = ctx.get('function', 'this function')
    line = ctx.get('line', 0)
    sink = ctx.get('sink_func', '') or 'the buffer operation'
    src  = ctx.get('src_var', '') or 'the source data'
    dest = ctx.get('dest_var', '') or 'the destination buffer'
    origin = ctx.get('origin', 'an unknown source')

    # ------------------------------------------------------------------
    # Bug
    # ------------------------------------------------------------------
    if decision.classification == "Bug":
        parts = []
        if sink == 'memcpy' and ctx.get('dest_var'):
            copy_size = ctx.get('copy_size', 'data')
            # Use path_prover to definitively check fault-then-proceed
            fault_proceed = _detect_fault_then_proceed(code, line, code_start_line)
            if fault_proceed and _PATH_PROVER:
                try:
                    blocks, pp_exp = _pp.does_fault_block_path(
                        code, fault_proceed['fault_line'], line, code_start_line)
                    if not blocks:
                        parts.append(f"memcpy at line {line} copies {copy_size} bytes into {dest}. {pp_exp}")
                    else:
                        # path_prover says fault DOES block — downgrade to FP
                        fault_proceed = None
                except Exception:
                    pass
            if fault_proceed:
                parts.append(f"memcpy at line {line} copies {copy_size} bytes into {dest}. {fault_proceed['description']}")
            elif not parts:
                parts.append(f"memcpy at line {line} copies {copy_size} bytes into {dest}. ")
                if ctx.get('guard_line') and ctx.get('guard_line') < line:
                    parts.append(f"A fault is reported at line {ctx['guard_line']} if the size check fails, but the code proceeds to memcpy anyway after reporting the fault. ")
                else:
                    parts.append(f"No visible size guard ensures the copy length does not exceed the destination buffer size. ")
        elif sink in ('strcpy', 'strcat', 'sprintf', 'gets'):
            parts.append(
                f"At line {line} in {func}(), `{sink}` copies data from {src} into {dest} "
                f"with no length validation. ")
        elif sink in ('strncpy', 'strncat'):
            _raw_args = _extract_call_args(code, sink)
            size_arg = _raw_args[2].strip() if len(_raw_args) >= 3 else ''
            # Build ONE coherent statement; avoid echoing the raw Coverity event text
            if dest not in ('the destination buffer', '') and src not in ('the source data', '') and size_arg:
                statement = (
                    f"At line {line} in {func}(), the call `{sink}({dest}, {src}, {size_arg})` "
                    f"passes a size argument that equals the capacity of `{dest}`. "
                )
            elif size_arg:
                statement = (
                    f"At line {line} in {func}(), the call `{sink}({dest}, {src}, {size_arg})` "
                    f"passes a size argument that equals the destination buffer capacity. "
                )
            else:
                statement = (
                    f"At line {line} in {func}(), a `{sink}` call is made to the destination buffer "
                    f"without reserving space for a null terminator. "
                )
            # unified trailing clause — only stated once
            parts.append(statement + "This leaves no room for a null terminator when the source exceeds the buffer, so the resulting string is unterminated and any later read of it is out-of-bounds.")
        else:
            parts.append(f"At line {line} in {func}(), {sink}() copies data from {src} into {dest}")
            if origin and 'unknown' not in origin:
                parts.append(f" (originating from {origin})")
                parts.append(" without length validation, making this a real buffer-handling bug.")
        comment = re.sub(r'\s{2,}', ' ', "".join(parts)).strip()
        if sink == 'strncpy':
            fix = f"Suggestion: {sink}({dest}, {src}, sizeof({dest})-1); {dest}[sizeof({dest})-1]='\\0'; // CWE-120/170 ensure NUL"
        elif sink == 'strncat':
            fix = f"Suggestion: strncat({dest}, {src}, sizeof({dest})-strlen({dest})-1); // CWE-120"
        else:
            fix = generate_contextual_fix('buffer_overflow', 'Bug', ctx)

    # ------------------------------------------------------------------
    # False positive
    # ------------------------------------------------------------------
    elif decision.classification == "False positive":
        parts = []
        
        # --- Example 1 style: memset + strncpy with size comparison ---
        memset_info = _extract_memset_info(code, ctx.get('dest_var', ''))
        strncpy_info = _extract_strncpy_info(code, ctx.get('dest_var', ''))
        if memset_info and strncpy_info:
            buf_size_expr = ctx.get('buffer_info', '')
            buf_size = 0
            sz_m = re.search(r'(\d+)', buf_size_expr)
            if sz_m:
                buf_size = int(sz_m.group(1))
            # Try to get copied string length
            src_len = None
            src_lit = re.search(rf'=\s*"([^"]*)"', code)
            if src_lit:
                src_len = len(src_lit.group(1))
            elif re.search(rf'\bstrlen\s*\(\s*{re.escape(ctx.get("src_var",""))}\s*\)', code):
                src_len = f"strlen({ctx.get('src_var','')})"
            
            if buf_size:
                base = (f"{dest}[{buf_size}] is pre-zeroed by memset(0, {memset_info['size_expr']}) at line "
                        f"{memset_info['line']} before all strncpy calls in {func}().")
                if isinstance(src_len, int):
                    parts.append(
                        f"{base} Because the destination is larger than the copied string "
                        f"({buf_size} >= {src_len}), the strncpy leaves a fully terminated, in-bounds buffer.")
                else:
                    parts.append(
                        f"{base} The pre-zeroing guarantees the copy is null-terminated. ")
        
        # --- Example 2 style: fixed-size struct members with bounded count ---
        if not parts:
            if sink in ('strncpy', 'strncat', 'memcpy', 'memmove') and dest and src:
                if ('.' in dest or '->' in dest) and ('.' in src or '->' in src):
                    parts.append(
                        f"{func}() copies data at line {line} into a fixed-size struct field using a bounded count. "
                        f"Both `{dest}` and `{src}` are fixed-size members of their respective structs with matching "
                        f"size declarations, so the copy stays within buffer bounds.")
        
        # --- Generic fallback ---
        if not parts:
            parts.append(f"After reviewing {func}(), the BUFFER_SIZE at line {line} is a false positive. ")
            reasons = []
            # helper: add a reason only if an equivalent idea is not already present
            def _add_reason(txt: str, *keywords: str) -> None:
                if not txt:
                    return
                for existing in reasons:
                    if txt == existing:
                        return
                    # cheap semantic dedup: if every keyword appears in an existing reason, skip
                    if keywords and all(k in existing for k in keywords):
                        return
                reasons.append(txt)

            if _has_pattern(code, r'\bmemset\s*\(') and _has_pattern(code, r'\bstrncpy\b'):
                _add_reason("the destination buffer is pre-zeroed with memset before the strncpy call, "
                            "so every remaining byte is null-terminated")
            if _has_pattern(code, r'\bstrncpy\b|\bstrncat\b|\bsnprintf\b|\bstrlcpy\b') and \
                    (_has_pattern(code, r'sizeof\s*\([^)]*\)\s*-\s*1') or ctx.get('guard_line', 0) > 0):
                _add_reason("a bounded string function with sizeof(dest)-1 is used, keeping the null terminator slot free",
                            "sizeof", "terminator")
            buffer_info = ctx.get('buffer_info', '')
            if buffer_info:
                bi = buffer_info.strip().rstrip('.')
                if bi and 'byte' in bi.lower():
                    _add_reason(bi)
            safe_api = ctx.get('safe_api_note', '')
            if safe_api:
                sa = safe_api.strip().rstrip('.')
                if sa:
                    _add_reason(sa, "bounded API")
            origin = ctx.get('origin', '')
            if origin and any(k in origin for k in ('safe', 'literal', 'local', 'bounded', 'stack', 'constant', 'trusted', 'sizeof')):
                _add_reason(f"the data originates from a trusted or bounded source ({origin})")
            if reasons:
                reasons = reasons[:2]
                if len(reasons) == 1:
                    parts.append(f"This is because {reasons[0]}. ")
                else:
                    parts.append(f"This is because {reasons[0]}, and {reasons[1]}. ")

        if decision.confidence >= 0.8:
            parts.append("High confidence; no code changes are needed.")
        elif decision.confidence >= 0.6:
            parts.append("Reasonably confident this is safe; a quick sanity-check is worthwhile.")
        comment = re.sub(r'\s{2,}', ' ', "".join(parts)).strip()
        fix = "No fix required."

    # ------------------------------------------------------------------
    # Needs review
    # ------------------------------------------------------------------
    else:
        comment = _build_comment_from_evidence(decision, ctx)
        fix = "Verify buffer size arguments and null termination. Prefer bounded functions with explicit size validation."

    comment = _apply_example_style(decision.classification, 'BUFFER_SIZE', ctx,
                                   code, code_start_line, line, function, comment)
    return decision.classification, comment, fix, decision.confidence


def _assess_guard_vs_index(guard_cond, idx_var, guard_op, guard_limit,
                           concrete_idx, arr_size, arr_size_expr, arr_name,
                           guard_line, covers_all_paths,
                           concrete_idx_source: str = "Coverity's trace"):
    """Assess the guard near an OVERRUN access vs. the flagged index idx_var.

    For OVERRUN the surrounding guard is often a NULL check on the buffer
    pointer (e.g. `if (buf != NULL)`); that does NOT bound the index `i`
    Coverity flagged. Such an irrelevant guard must not rescue a real
    out-of-bounds bug into a false positive.

    Returns (status, explanation) where status is:
      'none'        no guard condition at all
      'irrelevant'  guard exists but does not reference idx_var
      'safe'        references idx_var and keeps it within [0, arr_size-1]
      'unsafe'      references idx_var but allows an out-of-bounds value
      'unknown'     references idx_var but the bound can't be tied to the size
    """
    def _upper_bound(cond, var):
        # First upper-bound on var in cond: `var < L` / `var <= L` or
        # `L > var` / `L >= var`. Handles for-headers like `for(i=0;i<5;i++)`
        # where a naive first-match would grab the `i = 0` initializer instead.
        for pat in (rf"\b{re.escape(var)}\b\s*<=?\s*(\w+)",
                    rf"(\w+)\s*>=?\s*\b{re.escape(var)}\b"):
            m = re.search(pat, cond)
            if m:
                tok = m.group(1)
                return tok, (int(tok) if tok.isdigit() else None)
        return None, None

    if not guard_cond:
        return "none", ""
    if not idx_var or idx_var in ("the offset", "the index", "index"):
        return "none", ""
    if idx_var not in re.findall(r"\b\w+\b", guard_cond):
        return "irrelevant", (
            f"The condition `{guard_cond}` at line {guard_line} guards the buffer "
            f"pointer (`{arr_name}`) but does not reference `{idx_var}`; it is not a "
            f"bounds check and cannot rule out an out-of-bounds `{arr_name}[{idx_var}]`.")

    # A concrete index value from Coverity's path or a resolved local constant
    # assignment is the decisive signal.
    if concrete_idx is not None and arr_size > 0:
        if 0 <= concrete_idx < arr_size:
            if covers_all_paths:
                return "safe", (
                    f"Guard `{guard_cond}` at line {guard_line} references `{idx_var}` and "
                    f"dominates all paths; {concrete_idx_source} places `{idx_var}` at {concrete_idx}, "
                    f"within [0, {arr_size - 1}] of `{arr_name}`.")
            return "safe", (
                f"{concrete_idx_source} places `{idx_var}` at {concrete_idx}, within [0, {arr_size - 1}] "
                f"of `{arr_name}`; the access is in range.")
        where = (f"{concrete_idx}, past the end of the {arr_size}-element `{arr_name}`"
                 if concrete_idx >= arr_size
                 else f"{concrete_idx}, a negative value (an invalid index)")
        return "unsafe", (
            f"Guard `{guard_cond}` at line {guard_line} references `{idx_var}`, but "
            f"{concrete_idx_source} shows `{idx_var}` can still reach {where}; the guard does "
            f"not prevent the out-of-bounds access.")

    # No concrete trace value -- find an upper bound on idx_var in the condition.
    ub_str, ub_int = _upper_bound(guard_cond, idx_var)
    if ub_str:
        if ub_int is not None and arr_size > 0:
            max_reachable = ub_int - 1 if guard_op == '<' else ub_int
            if max_reachable < arr_size:
                cmp_txt = f"{guard_op} {ub_int}" if guard_op else f"< {ub_int}"
                return "safe", (
                    f"Guard `{guard_cond}` at line {guard_line} bounds `{idx_var}` with `{cmp_txt}`; "
                    f"the largest reachable index is {max_reachable}, inside `{arr_name}`'s "
                    f"valid range [0, {arr_size - 1}].")
            cmp_txt = f"{guard_op} {ub_int}" if guard_op else f"< {ub_int}"
            return "unsafe", (
                f"Guard `{guard_cond}` at line {guard_line} bounds `{idx_var}` with `{cmp_txt}`, "
                f"which still permits index {max_reachable}; `{arr_name}` only has {arr_size} elements, "
                f"so the access can still run out of bounds.")
        if arr_size_expr and (ub_str in arr_size_expr or "sizeof" in guard_cond
                              or ub_str == arr_name):
            return "safe", (
                f"Guard `{guard_cond}` at line {guard_line} bounds `{idx_var}` against "
                f"`{ub_str}`, which tracks the size of `{arr_name}`; the access is in range.")
        return "unknown", (
            f"Guard `{guard_cond}` at line {guard_line} references `{idx_var}` with bound "
            f"`{ub_str}`, but the bound could not be tied to `{arr_name}`'s size; the guard's "
            f"protective value is not provable from the extracted snippet.")

    if covers_all_paths:
        return "safe", (
            f"Guard `{guard_cond}` at line {guard_line} references `{idx_var}` and dominates "
            f"all paths; control-flow dominance justifies treating the access as in range.")
    return "unknown", (
        f"Guard `{guard_cond}` at line {guard_line} references `{idx_var}` but does not "
        f"establish a usable upper bound, so its protective value is not provable.")


def _split_top_level_commas(text: str) -> List[str]:
    """Split on commas that are not nested inside (), [], {}."""
    parts, cur, depth = [], [], 0
    for ch in text:
        if ch in '([{':
            depth += 1
            cur.append(ch)
        elif ch in ')]}':
            depth -= 1
            cur.append(ch)
        elif ch == ',' and depth == 0:
            parts.append(''.join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append(''.join(cur).strip())
    return [p for p in parts if p]


def _function_param_names(code: str) -> List[str]:
    """Extract the parameter names from a single-line function signature in code.

    Only matches a real definition (return type + name + parenthesised params),
    so plain call statements like `use_buf(...)` are ignored. Returns [] when the
    signature spans lines or cannot be parsed so callers fall back to other
    evidence rather than guessing a bogus parameter mapping.
    """
    for line in code.splitlines():
        s = line.strip()
        if not s or s.startswith(('#', '//', '/*', '*')):
            continue
        # Return type, function name, then non-empty params, ignoring any
        # trailing body code that may share the same line.
        m = re.match(r'([A-Za-z_][\w\s\*]*?)\s+(\w+)\s*\(([^)]*)\)', s)
        if not m:
            continue
        body = m.group(3).strip()
        if not body or body.lower() == 'void':
            return []
        params = []
        for part in _split_top_level_commas(body):
            part = re.sub(r'\b(const|volatile|unsigned|signed|static|register|'
                          r'struct|union|enum|restrict|inline|extern)\b', ' ', part)
            part = part.replace('*', ' ').strip()
            names = re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)\b', part)
            if not names:
                continue
            params.append(names[-1])
        return params
    return []



def _overrun_pattern_and_caller_evidence(code: str, idx_var: str, idx_expr: str,
                                         arr_name: str, arr_size: int,
                                         assign_expr: str, ctx: Dict) -> EvidenceAccumulator:
    """Extra Bug/FP evidence for an inconclusive OVERRUN from the index's
    provenance and the call graph (caller sites).

    The local snippet alone often can't tell where a flagged index comes from
    (e.g. it is a parameter) or whether callers bound it. This uses data the tool
    already collects — the concrete index / array size, the index provenance
    (taint), and the callers that reach the defect function — to break the tie
    toward Bug or False positive instead of defaulting to manual review.
    """
    acc = EvidenceAccumulator()
    if not idx_var or idx_var in ('the offset', 'the index', 'index'):
        return acc

    # --- 1. Constant index (pattern) ---
    lit_str = None
    for expr in (idx_expr, assign_expr or ''):
        e = re.sub(r'\s+', '', (expr or ''))
        m = re.fullmatch(r'\(?(\d+)\)?', e)
        if m:
            lit_str = m.group(1)
            break
    if lit_str is not None:
        v = int(lit_str)
        if arr_size > 0:
            if 0 <= v < arr_size:
                acc.add(Evidence('constant_index_within_bounds', 'fp', 0.85,
                                 f"index is the constant {v}, inside the declared range [0, {arr_size - 1}]."))
            else:
                acc.add(Evidence('constant_index_out_of_bounds', 'bug', 0.90,
                                 f"index is the constant {v}, out of range for an array of {arr_size} elements."))

    # --- 2. Index provenance / taint ---
    src = None
    try:
        src = _find_variable_origin(code, idx_var)
    except Exception:
        src = None
    if src and src.source_type in ('network', 'file', 'env', 'args', 'convert', 'external'):
        acc.add(Evidence('overrun_index_untrusted_origin', 'bug', 0.62,
                         f"index `{idx_var}` derives from {src.source_type} (caller/input-controlled) and is not locally narrowed."))
    elif src and src.source_type in ('local', 'literal', 'bounded', 'safe'):
        acc.add(Evidence('overrun_index_safe_origin', 'fp', 0.60,
                         f"index `{idx_var}` derives from a {src.source_type} source."))

    # --- 3. Call graph: how callers supply the flagged index ---
    callers = ctx.get('callers_list', []) or []
    real_callers = [c for c in (callers if isinstance(callers, list) else []) if c and c.get('snippet')]
    params = _function_param_names(code)
    if real_callers and idx_var in params:
        pos = params.index(idx_var)
        buf_pos = params.index(arr_name) if (arr_name in params and
                                             arr_name not in ('the buffer', 'the array', 'array')) else -1

        # Resolve the real buffer size from each caller's local array declaration
        # (cross-file) when the defect function itself cannot see the declaration.
        # This closes the "arr_size unknown" gap for parameter-driven buffers.
        eff_arr_size = arr_size
        if eff_arr_size <= 0 and buf_pos >= 0:
            for c in real_callers:
                cc = str(c.get('code') or '')
                if not cc:
                    continue
                sm = re.search(r'\b(\w+)\s*\(', str(c.get('snippet', '')).strip())
                if not sm:
                    continue
                cargs = _extract_call_args(str(c.get('snippet', '')).strip(), sm.group(1))
                if buf_pos < len(cargs):
                    d = _extract_array_declaration(cc, cargs[buf_pos].strip(), 1)
                    if d and d.get('size', 0) > 0:
                        eff_arr_size = d['size']
                        break

        bug_hits, fp_hits = 0, 0
        fp_examples = []
        tainted = False
        guard_hits = 0
        guard_desc = []
        for c in real_callers:
            snippet = str(c.get('snippet', '')).strip()
            m = re.search(r'\b(\w+)\s*\(', snippet)
            if not m:
                continue
            args = _extract_call_args(snippet, m.group(1))
            if pos >= len(args):
                continue
            arg = args[pos].strip()
            am = re.fullmatch(r'(\d+)', arg)
            if am:
                av = int(am.group(1))
                if eff_arr_size > 0 and 0 <= av < eff_arr_size:
                    fp_hits += 1
                    fp_examples.append(f"constant {av}")
                elif eff_arr_size > 0:
                    bug_hits += 1
            elif re.search(r'\b(recv|recvfrom|fread|fgets|getenv|scanf|sscanf|fscanf|'
                           r'read|accept|ntohs|ntohl|getchar|gets|atoi|strtol)\b', arg):
                tainted = True
                bug_hits += 1
            elif eff_arr_size > 0 and re.search(r'\b(sizeof\s*\(|\b[\w]+\s*-\s*1\b)', arg):
                fp_hits += 1
                fp_examples.append(arg)

            # Cross-file guard: is the (non-constant) index argument bounded
            # inside the caller's own body before this call site? Addresses the
            # "including any cross-file guards" case from the users's example.
            cc = str(c.get('code') or '')
            if cc and arg and not re.fullmatch(r'(\d+)', arg):
                nlines = len(cc.splitlines())
                try:
                    start_line = int(c.get('start_line', 1) or 1)
                    line_c = int(c.get('line', 1) or 1)
                    rel = line_c - start_line + 1
                    rel = max(1, min(rel, nlines))
                    flow = _extract_index_flow(cc, arg, rel, 1)
                    if flow.get('guard_line', 0) > 0 and flow.get('guard_cond'):
                        guard_hits += 1
                        guard_desc.append(str(c.get('caller', '')) or c.get('file', ''))
                except Exception:
                    pass

        if bug_hits and not fp_hits and not guard_hits:
            acc.add(Evidence('overrun_caller_passes_oob', 'bug', 0.80,
                             "callers pass out-of-range or input-derived values for `%s`." % idx_var))
        elif guard_hits and not bug_hits:
            acc.add(Evidence('overrun_caller_bound_index', 'fp', 0.72,
                             "caller(s) bound `%s` before the call (%s)."
                             % (idx_var, ", ".join(sorted(set(guard_desc))[:3]) or "%d site(s)" % guard_hits)))
        elif fp_hits and not bug_hits:
            acc.add(Evidence('overrun_caller_passes_bounded', 'fp', 0.85,
                             "every caller passes a value inside [0, %d] for `%s` (%s)."
                             % (max(eff_arr_size - 1, 0), idx_var, ", ".join(fp_examples))))
        elif bug_hits and not fp_hits:
            acc.add(Evidence('overrun_caller_passes_oob', 'bug', 0.80,
                             "at least one caller passes an out-of-range constant for `%s`." % idx_var))

    return acc


def _has_nested_subscript_at_line(code: str, line: int, code_start_line: int) -> bool:
    """Return whether the flagged statement contains an expression like
    ``table[index_map[i]]``.  Such a statement has multiple bounds that cannot
    be safely repaired by the single-index fallback template.
    """
    source_lines = code.splitlines()
    offset = line - code_start_line
    return 0 <= offset < len(source_lines) and source_lines[offset].count('[') >= 2


def _analyze_overrun(code: str, sub_checker: str, events: List[Dict],
                     file: str = "", line: int = 0, function: str = "", cid: int = 0,
                     called_function_codes: Optional[Dict[str, str]] = None,
                     code_start_line: int = 1, tree=None) -> Tuple[str, str, str, float]:
    ctx = _build_analysis_context(code, 'OVERRUN', events, file, line, function, cid,
                                  called_function_codes, code_start_line)
    ev = ctx['ev']
    acc = build_evidence(ctx, ev, 'OVERRUN')
    decision = DecisionAgent.evaluate(acc, 'OVERRUN')


    # --- Extract precise array access details ---
    # Initialize with safe defaults
    arr_name = ''
    idx_var = ''
    idx_expr = ''
    access_line_actual = line
    access_type = 'access'
    arr_size_expr = ''
    arr_size = 0
    assign_line = 0
    assign_expr = ''
    guard_line = 0
    guard_cond = ''
    guard_op = ''
    guard_limit = ''

    # 1. Try AST on full file tree first
    if tree is not None:
        access_info_ast = find_array_access(tree, line)
        if access_info_ast and access_info_ast.get('array_name'):
            ast_access_line = int(access_info_ast.get('access_line', 0) or 0)
            # Anchor on the flagged sink line: the AST returns the *nearest*
            # subscript anywhere in the function, so a loop body access like
            # `buf[i]` at 707 must not shadow the actual defect (e.g. a
            # memcpy(dest, buf, n) sink at 710). Only accept an access on (or
            # adjacent to) the flagged line.
            if abs(ast_access_line - line) > 1:
                access_info_ast = None
        if access_info_ast and access_info_ast.get('array_name'):
            arr_name = access_info_ast['array_name']
            idx_vars = access_info_ast.get('index_variables', [])
            idx_var = idx_vars[0] if idx_vars else access_info_ast.get('index_expression', '')
            idx_expr = access_info_ast.get('index_expression', idx_var)
            access_line_actual = access_info_ast.get('access_line', line)
            access_type = 'write' if access_info_ast.get('is_write') else 'read'

            decl_info_ast = find_declaration(tree, arr_name)
            if decl_info_ast:
                arr_size_expr = decl_info_ast.get('size_expression', '')
                arr_size = int(arr_size_expr) if arr_size_expr and arr_size_expr.isdigit() else 0

            if idx_var and idx_var != 'the index':
                assign_ast = find_assignment(tree, idx_var, access_line_actual)
                if assign_ast:
                    assign_line = assign_ast.get('assignment_line', 0)
                    assign_expr = assign_ast.get('rhs_expression', '')

            guard_ast = find_enclosing_guard(tree, access_line_actual)
            if guard_ast:
                guard_line = guard_ast.get('condition_line', 0)
                guard_cond = guard_ast.get('condition_expression', '')
                comp_m = re.search(rf'\b{re.escape(idx_var)}\s*([<>!=]=?|==)\s*([^;)\s&|]+)', guard_cond)
                if comp_m:
                    guard_op = comp_m.group(1)
                    guard_limit = comp_m.group(2).strip()
                else:
                    comp_m = re.search(rf'([^;)\s&|]+)\s*([<>!=]=?|==)\s*{re.escape(idx_var)}', guard_cond)
                    if comp_m:
                        op = comp_m.group(2)
                        flip = {'<': '>', '>': '<', '<=': '>=', '>=': '<=', '==': '==', '!=': '!='}
                        guard_op = flip.get(op, op)
                        guard_limit = comp_m.group(1).strip()

    # 2. Fallback: regex on the extracted function snippet (runs if AST failed OR if tree is None)
    if not arr_name:
        access_info = _extract_array_access_near_line(code, line, code_start_line)
        if access_info:
            # Same anchoring rule as the AST path: a subscript elsewhere in
            # the function must not be reported as the flagged access.
            if abs(int(access_info.get('line', 0) or 0) - line) > 1:
                access_info = None
        if access_info:
            arr_name = access_info.get('array', '')
            idx_var = access_info.get('index_var', '')
            idx_expr = access_info.get('index_expr', idx_var)
            access_line_actual = access_info.get('line', line)
            access_type = access_info.get('access_type', 'access')

            decl_info = _extract_array_declaration(code, arr_name, code_start_line)
            arr_size_expr = decl_info.get('size_expr', '')
            arr_size = decl_info.get('size', 0)

            if idx_var and idx_var != 'the index':
                flow = _extract_index_flow(code, idx_var, access_line_actual, code_start_line)
                assign_line = flow.get('assign_line', 0)
                assign_expr = flow.get('assign_expr', '')
                guard_line = flow.get('guard_line', 0)
                guard_cond = flow.get('guard_cond', '')
                guard_op = flow.get('guard_op', '')
                guard_limit = flow.get('guard_limit', '')

    # AST declarations can miss macro-sized local arrays or declarations on the
    # same line as initializers. Re-run the lightweight regex extractor before
    # giving up on the local size / assignment facts.
    if arr_name and not arr_size_expr:
        decl_info = _extract_array_declaration(code, arr_name, code_start_line)
        if decl_info:
            arr_size_expr = decl_info.get('size_expr', '')
            arr_size = decl_info.get('size', 0)
    if idx_var and idx_var != 'the index' and (not assign_expr or not guard_cond):
        flow = _extract_index_flow(code, idx_var, access_line_actual, code_start_line)
        assign_line = assign_line or flow.get('assign_line', 0)
        assign_expr = assign_expr or flow.get('assign_expr', '')
        guard_line = guard_line or flow.get('guard_line', 0)
        guard_cond = guard_cond or flow.get('guard_cond', '')
        guard_op = guard_op or flow.get('guard_op', '')
        guard_limit = guard_limit or flow.get('guard_limit', '')

    # 3. Last-resort pointer-arithmetic scan
    if not arr_name:
        m = re.search(r'\*\s*\(\s*(\w+)\s*\+\s*([^\)]+)\)', code)
        if m:
            arr_name = m.group(1)
            idx_expr = m.group(2).strip()
            idx_clean = re.sub(r'\([^)]+\)', '', idx_expr).strip()
            idx_var_m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\b', idx_clean)
            idx_var = idx_var_m.group(1) if idx_var_m else idx_expr
            access_type = 'read'

    # 4. Absolute last resort — generic but honest
    if not arr_name:
        arr_name = 'the buffer'
    if not idx_var:
        idx_var = 'the offset'

    # Fall back to the array size Coverity reported in its event trace when the
    # local snippet cannot resolve the buffer's declaration (e.g. the buffer is a
    # parameter whose real size lives at the call sites). This lets the
    # guard/path-prover and the caller analysis reason with the real bound.
    if arr_size == 0 and ev.get('array_size'):
        arr_size = int(ev['array_size'])
        if not arr_size_expr:
            arr_size_expr = str(arr_size)

    # Resolve local or cross-file constants (enum members, #defines, constexprs)
    # before defaulting to "Needs review". This is especially important for
    # patterns like `idx = (unsigned)E_HIGH_PRIORITY; table[idx]` where the
    # surrounding function snippet alone does not show the enum values.
    resolution_sources = _gather_resolution_sources(
        code, file, called_function_codes, ctx.get('callers_list', []))
    if arr_size == 0 and arr_size_expr:
        resolved_arr_size = _resolve_integer_constant(arr_size_expr, resolution_sources)
        if resolved_arr_size is not None and resolved_arr_size >= 0:
            arr_size = resolved_arr_size
    resolved_guard_limit = None
    if guard_limit:
        resolved_guard_limit = _resolve_integer_constant(guard_limit, resolution_sources)
    resolved_assign_value = None
    if assign_expr:
        resolved_assign_value = _resolve_integer_constant(assign_expr, resolution_sources)

    concrete_idx = ev.get('index_value') if ev.get('index_value') is not None else None
    concrete_idx_source = "Coverity's trace"
    if concrete_idx is None and resolved_assign_value is not None:
        concrete_idx = resolved_assign_value
        concrete_idx_source = f"the assignment `{idx_var} = {assign_expr}`"

    if guard_limit and not str(guard_limit).isdigit() and resolved_guard_limit is not None:
        guard_limit = str(resolved_guard_limit)

    nested_access = _has_nested_subscript_at_line(code, access_line_actual, code_start_line)
    inner_index_proven_safe = False
    nested_inner_arr = ''
    nested_inner_idx_var = ''
    nested_inner_idx_value = None
    nested_match = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_:.>-]*)\s*\[\s*([^\]]+)\s*\]', (idx_expr or '').strip())         if nested_access else None
    if nested_match:
        nested_inner_arr = nested_match.group(1).strip()
        nested_inner_idx_expr = nested_match.group(2).strip()
        nested_inner_idx_var_m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)', nested_inner_idx_expr)
        nested_inner_idx_var = nested_inner_idx_var_m.group(1) if nested_inner_idx_var_m else nested_inner_idx_expr
        inner_flow = _extract_index_flow(code, nested_inner_idx_var, access_line_actual, code_start_line) \
            if nested_inner_idx_var else {}
        if inner_flow.get('assign_line', 0):
            assign_line = assign_line or inner_flow.get('assign_line', 0)
        if inner_flow.get('assign_expr'):
            assign_expr = assign_expr or inner_flow.get('assign_expr', '')

        inner_decl = _extract_array_declaration(code, nested_inner_arr, code_start_line)
        inner_arr_size_expr = inner_decl.get('size_expr', '')
        inner_arr_size = inner_decl.get('size', 0)
        if inner_arr_size == 0 and inner_arr_size_expr:
            resolved_inner_size = _resolve_integer_constant(inner_arr_size_expr, resolution_sources)
            if resolved_inner_size is not None and resolved_inner_size >= 0:
                inner_arr_size = resolved_inner_size

        nested_inner_idx_value = _resolve_integer_constant(nested_inner_idx_expr, resolution_sources)
        if nested_inner_idx_value is None and nested_inner_idx_var and nested_inner_idx_var != nested_inner_idx_expr:
            if inner_flow.get('assign_expr'):
                nested_inner_idx_value = _resolve_integer_constant(inner_flow['assign_expr'], resolution_sources)

        if nested_inner_idx_value is not None and inner_arr_size > 0 and 0 <= nested_inner_idx_value < inner_arr_size:
            inner_index_proven_safe = True
            init_vals = _extract_array_initializer_values(code, nested_inner_arr, resolution_sources)
            if init_vals and nested_inner_idx_value < len(init_vals):
                concrete_idx = init_vals[nested_inner_idx_value]
                concrete_idx_source = (
                    f"the derived value `{nested_inner_arr}[{nested_inner_idx_var}]` "
                    f"with `{nested_inner_idx_var}` = {nested_inner_idx_value}")
    else:
        inner_index_proven_safe = bool(
            concrete_idx is not None and arr_size > 0 and 0 <= concrete_idx < arr_size)

    # --- path_prover: off-by-one / guard safety proof ---
    prover_result: Dict = {}
    if _PATH_PROVER and guard_op and guard_limit and arr_size > 0:
        try:
            prover_result = _pp.prove_overrun(guard_op, guard_limit, arr_size,
                                               guard_cond, idx_var)
            # Override decision if prover has stronger evidence
            if prover_result.get('is_off_by_one') and decision.classification != 'Bug':
                decision = type(decision)(
                    classification='Bug',
                    confidence=max(decision.confidence, 0.82),
                    reasoning=decision.reasoning + [prover_result.get('off_by_one_explanation', '')]
                )
            elif prover_result.get('guard_is_safe') and decision.classification == 'Bug':
                decision = type(decision)(
                    classification='False positive',
                    confidence=max(decision.confidence, 0.78),
                    reasoning=decision.reasoning + [prover_result.get('guard_explanation', '')]
                )
        except Exception:
            pass

        # ------------------------------------------------------------------
    # Guard relevance: a guard only justifies a false-positive verdict when
    # it actually bounds the index Coverity flagged. A NULL check on the
    # buffer pointer (e.g. `if (buf != NULL)`) or any guard that does not
    # reference `idx_var` is irrelevant and must NOT rescue the finding.
    # ------------------------------------------------------------------
    has_real_names = (arr_name not in ('', 'the buffer', 'the array', 'array') and
                      idx_var not in ('', 'the offset', 'the index', 'index'))
    guard_status, guard_explanation = _assess_guard_vs_index(
        guard_cond, idx_var, guard_op, guard_limit, concrete_idx,
        arr_size, arr_size_expr, arr_name, guard_line,
        bool(ctx.get('guard_covers_all_paths', False)),
        concrete_idx_source)

    # A locally/cross-file resolved constant can prove that the *inner* access is
    # in range even when Coverity flagged a larger nested expression. Do not keep
    # a Bug verdict solely on that inner subscript when the remaining question is
    # the outer table's bound.
    if decision.classification == "Bug" and guard_status == "safe":
        if nested_access:
            decision = type(decision)(classification='Needs review', confidence=max(0.55, decision.confidence - 0.10),
                                      reasoning=decision.reasoning +
                                      [f"The inner access `{arr_name}[{idx_var}]` is provably in range; the remaining uncertainty is the derived outer-table access on the same line."])
        else:
            decision = type(decision)(classification='False positive', confidence=max(0.60, decision.confidence - 0.10),
                                      reasoning=decision.reasoning +
                                      [f"Resolved constants place `{idx_var}` within `{arr_name}`'s bounds on the flagged access."])

    # Correct an over-eager false-positive signal raised by the evidence agent
    # (or an earlier fallback) when the apparent guard is irrelevant/ineffective.
    if decision.classification == "False positive" and guard_status in ("irrelevant", "unsafe", "unknown"):
        if guard_status == "unsafe":
            if concrete_idx is not None and arr_size > 0 and concrete_idx >= arr_size:
                decision = type(decision)(classification='Bug', confidence=0.78,
                                          reasoning=decision.reasoning +
                                          [f"{concrete_idx_source} confirms index {concrete_idx} is out of bounds "
                                           f"(array size {arr_size}); the guard does not bound `{idx_var}`."])
            else:
                decision = type(decision)(classification='Bug', confidence=0.60,
                                          reasoning=decision.reasoning +
                                          [f"Guard at line {guard_line} references `{idx_var}` but allows "
                                           f"an out-of-bounds value for `{arr_name}`."])
        elif has_real_names and not inner_index_proven_safe:
            decision = type(decision)(classification='Bug', confidence=0.60,
                                      reasoning=decision.reasoning +
                                      [f"Real array access `{arr_name}[{idx_var}]` found; the nearby "
                                       f"guard does not reference `{idx_var}`."])
        elif has_real_names:
            decision = type(decision)(classification='Needs review', confidence=0.55,
                                      reasoning=decision.reasoning +
                                      [f"The inner access `{arr_name}[{idx_var}]` resolves in range, but the "
                                       f"derived outer-table access on the same line still needs a separate bound proof."])
        else:
            decision = type(decision)(classification='Needs review', confidence=0.55,
                                      reasoning=decision.reasoning +
                                      [f"Guard at line {guard_line} is not a provably effective bounds "
                                       f"check on `{idx_var}`; manual review recommended."])

    # If the evidence agent was inconclusive, commit to a verdict (Bug / FP)
    # instead of "Needs review" whenever the extracted facts decide it.
    if decision.classification == "Needs review":
        if concrete_idx is not None and arr_size > 0 and concrete_idx >= arr_size:
            decision = type(decision)(classification='Bug', confidence=0.78,
                                      reasoning=decision.reasoning +
                                      [f"{concrete_idx_source} confirms index {concrete_idx} is out of bounds (array size {arr_size})."])
        elif guard_status == "safe" and not (nested_access and inner_index_proven_safe):
            decision = type(decision)(classification='False positive', confidence=0.55,
                                      reasoning=decision.reasoning +
                                      [f"Effective bounds guard at line {guard_line} for `{idx_var}`."])
        elif guard_status == "unsafe":
            decision = type(decision)(classification='Bug', confidence=0.60,
                                      reasoning=decision.reasoning +
                                      [f"Guard at line {guard_line} references `{idx_var}` but allows "
                                       f"an out-of-bounds value for `{arr_name}`."])
        elif guard_status in ("irrelevant", "none") and has_real_names and not inner_index_proven_safe:
            decision = type(decision)(classification='Bug', confidence=0.55,
                                      reasoning=decision.reasoning +
                                      [f"Real array access of `{arr_name}[{idx_var}]` found with no effective "
                                       f"bounds guard on `{idx_var}`."])
        # 'unknown', or nested access whose inner index is proven safe -> stays Needs review (inconclusive)

    # --------------------------------------------------------------------------
    # Call-graph / pattern resolution for still-inconclusive OVERRUN.
    # The local snippet often cannot show where the flagged index comes from
    # (it may be a parameter) or how callers bound it. Before defaulting to
    # manual review, harvest index provenance and the caller sites the tool
    # already collected and let that evidence break the tie toward Bug / FP.
    # --------------------------------------------------------------------------
    if decision.classification == "Needs review" and not (nested_access and inner_index_proven_safe):
        extra_acc = _overrun_pattern_and_caller_evidence(
            code, idx_var, idx_expr, arr_name, arr_size, assign_expr, ctx)
        extra_decision = DecisionAgent.evaluate(extra_acc, 'OVERRUN')
        if extra_decision.classification in ("Bug", "False positive") \
           and extra_decision.confidence >= 0.55:
            decision = type(decision)(
                classification=extra_decision.classification,
                confidence=max(decision.confidence, extra_decision.confidence - 0.05),
                reasoning=decision.reasoning + extra_decision.reasoning)

    # Bug — precise, example-style comment
    # ------------------------------------------------------------------
    if decision.classification == "Bug":
        parts = []
        verb = 'written' if access_type == 'write' else 'read'
        
        # Check if we have real names (not the generic placeholders)
        has_real_names = (
            arr_name not in ('', 'the buffer', 'the array', 'array') and
            idx_var not in ('', 'the offset', 'the index', 'index')
        )
        
        if has_real_names:
            # ---- Real variable names found ----
            
            # Detect cast-from-array in assignment (example 6 style)
            cast_from_array = False
            src_array = ''
            src_index = ''
            if assign_line > 0 and assign_expr:
                cast_m = re.search(r'\(\s*\w+\s*\)\s*([A-Za-z_][A-Za-z0-9_]*)\s*\[([^\]]+)\]', assign_expr)
                if cast_m:
                    cast_from_array = True
                    src_array = cast_m.group(1)
                    src_index = cast_m.group(2)
            
            # Opening sentence
            if cast_from_array and guard_line > 0 and guard_limit:
                parts.append(f"`{arr_name}[{idx_var}]` is {verb} at line {access_line_actual}. {idx_var} is cast from `{src_array}[{src_index}]` at line {assign_line} after the `{guard_cond}` check, allowing {idx_var} = {guard_limit}.")
            elif assign_line > 0 and assign_expr:
                # Skip trivial assignments (0, NULL, false)
                is_trivial = bool(re.match(r'^\s*(0|NULL|false)\s*$', assign_expr, re.I))
                if is_trivial:
                    parts.append(f"`{arr_name}[{idx_var}]` is {verb} at line {access_line_actual}.")
                else:
                    parts.append(f"`{arr_name}[{idx_var}]` is {verb} at line {access_line_actual}. {idx_var} is assigned from `{assign_expr}` at line {assign_line}.")
            else:
                parts.append(f"`{arr_name}[{idx_var}]` is {verb} at line {access_line_actual}.")

            # Guard / loop analysis
            is_for_loop = False
            loop_limit = ''
            if guard_line > 0 and guard_cond:
                if re.search(rf'\b{re.escape(idx_var)}\s*\+\+|\+\+\s*{re.escape(idx_var)}', guard_cond):
                    is_for_loop = True
                    m = re.search(rf'{re.escape(idx_var)}\s*<\s*([^;,\s]+)', guard_cond)
                    if m:
                        loop_limit = m.group(1).strip()

            if is_for_loop:
                if loop_limit:
                    parts.append(f"This is inside a loop that iterates while `{idx_var} < {loop_limit}`.")
                else:
                    parts.append(f"This is inside a loop controlled by `{guard_cond}`.")
                
                if arr_size > 0:
                    parts.append(f"`{arr_name}` has {arr_size} elements (declared size: `{arr_size_expr}`).")
                    if loop_limit.isdigit():
                        if int(loop_limit) > arr_size:
                            parts.append(f"The loop bound ({loop_limit}) exceeds the array size ({arr_size}), causing an out-of-bounds {verb}.")
                        elif int(loop_limit) == arr_size:
                            parts.append(f"The loop bound equals the array size; if the loop runs to completion, the final access at index {arr_size} will be out of bounds.")
                    else:
                        parts.append(f"If `{loop_limit}` is ever >= {arr_size}, the loop will {verb} past the end of the buffer.")
                elif arr_size_expr:
                    parts.append(f"`{arr_name}` is declared with size `{arr_size_expr}`. The loop may exceed this bound.")
                else:
                    parts.append(f"The size of `{arr_name}` could not be determined; the loop may exceed the buffer bounds.")

            elif guard_line > 0 and guard_cond:
                if guard_limit:
                    parts.append(f"Condition at line {guard_line} (`{guard_cond}`) allows `{idx_var}` to reach `{guard_limit}`.")
                else:
                    parts.append(f"Condition at line {guard_line} (`{guard_cond}`) was found, but its limit could not be extracted.")
                
                if arr_size > 0:
                    parts.append(f"`{arr_name}` is declared with {arr_size} elements (valid indices 0 to {arr_size-1}).")
                    if guard_limit.isdigit():
                        gl = int(guard_limit)
                        if gl >= arr_size:
                            parts.append(f"The guard permits index {gl}, which is beyond the valid range — confirmed out-of-bounds {verb}.")
                        elif guard_op in ('<=', '==') and gl == arr_size - 1:
                            parts.append(f"Index {gl} is the last valid element; verify the comparison is not off-by-one.")
                elif arr_size_expr:
                    parts.append(f"`{arr_name}` is declared with size `{arr_size_expr}`; verify the guard respects this limit.")
                else:
                    parts.append(f"The size of `{arr_name}` could not be determined from the extracted context.")

            else:
                if arr_size > 0:
                    parts.append(f"`{arr_name}` has {arr_size} elements, but `{idx_var}` is used without any bounds check.")
                elif arr_size_expr:
                    parts.append(f"`{arr_name}` is declared with size `{arr_size_expr}`, but `{idx_var}` is used without a visible bounds check.")
                else:
                    parts.append(f"`{idx_var}` indexes `{arr_name}` without a visible bounds check.")
                parts.append(f"If `{idx_var}` falls outside the valid range [0, size-1], this {verb} accesses adjacent memory, corrupting neighboring data and potentially crashing the process or enabling an exploit.")

            # Coverity trace confirmation
            if concrete_idx is not None and arr_size > 0:
                if concrete_idx >= arr_size:
                    parts.append(f"{concrete_idx_source} confirms `{idx_var}` can reach {concrete_idx}, which is beyond the buffer limit of {arr_size-1}.")
                elif concrete_idx < 0:
                    parts.append(f"{concrete_idx_source} confirms `{idx_var}` can be negative ({concrete_idx}), which is an invalid array index.")

            # path_prover off-by-one explanation
            if prover_result.get('is_off_by_one') and prover_result.get('off_by_one_explanation'):
                parts.append(prover_result['off_by_one_explanation'])

            # Guard assessment (senior-reviewer view): does the nearby guard
            # actually bound the flagged index, or merely look protective?
            if guard_explanation:
                parts.append(guard_explanation)

            # A nested subscript has two independent bounds: for example,
            # ``table[index_map[i]]``.  The simple extractor can identify the
            # inner ``index_map[i]`` but cannot prove the size/semantics of the
            # outer table or whether a named MAX constant is a count or a last
            # valid index.  Never offer a patch for the inner index in that
            # case: it would be unrelated to the defect Coverity reported.
            if _has_nested_subscript_at_line(code, access_line_actual, code_start_line):
                parts.append(
                    "The flagged expression contains a derived/nested index. "
                    "Verify the bound for the value used to index the outer "
                    "table and whether its MAX constant is inclusive before "
                    "changing this condition; no automatic patch is safe.")
                fix = "Manual review required."
            else:
                fix = (f"Suggestion: if ({idx_var} < 0 || {idx_var} >= "
                       f"(int)(sizeof({arr_name}) / sizeof({arr_name}[0]))) "
                       "return ERROR; // CWE-125/787")
        
        else:
            # ---- Generic fallback: extract the actual source line to name the expression ----
            src_line_text = ''
            if code:
                _clines = code.splitlines()
                _rel = access_line_actual - code_start_line
                if 0 <= _rel < len(_clines):
                    src_line_text = _clines[_rel].strip()

            _arr_m = re.search(r'(\w[\w.\-><:]*(?:\[\d+\])*(?:->|\.)\w+|\w+)\[([^\]]+)\]', src_line_text) if src_line_text else None
            # Any buffer-copy sink at the flagged line is quoted directly with
            # its own name and arguments (memcpy/strcpy/strcat/sprintf/...),
            # instead of only memcpy being special-cased.
            _sink_m = (re.search(
                r'\b(memcpy|memmove|strcpy|strncpy|strcat|strncat|sprintf|'
                r'snprintf|vsprintf|vsnprintf|wcscpy|wcscat|swprintf|gets|'
                r'strlcpy|strlcat)\s*\(([^)]*)\)',
                src_line_text) if src_line_text else None)

            if _arr_m:
                _found_arr = _arr_m.group(1)
                _found_idx = _arr_m.group(2).strip()
                parts.append(f"`{_found_arr}[{_found_idx}]` is {verb} at line {access_line_actual}.")
                parts.append(f"No visible bounds check on `{_found_idx}` was found in the extracted snippet — verify `{_found_idx}` is validated before this access. If `{_found_idx}` lies outside the allocated range of `{_found_arr}`, this {verb} touches adjacent memory, corrupting data and potentially crashing the process or enabling an exploit.")
                if arr_size_expr:
                    parts.append(f"`{_found_arr}` is declared with size `{arr_size_expr}`.")
                fix = f"Validate `{_found_idx}` before indexing `{_found_arr}`:\n  if ({_found_idx} < 0 || {_found_idx} >= (int)(sizeof({_found_arr}) / sizeof({_found_arr}[0]))) return ERROR;"
            elif _sink_m:
                _fn = _sink_m.group(1)
                _args = [a.strip() for a in _sink_m.group(2).split(',')]
                _dst = _args[0] if _args else '?'
                _sz = _args[-1] if len(_args) > 1 else '?'
                parts.append(f"`{_fn}({', '.join(_args)})` at line {access_line_actual} — `{_sz}` controls the copy length but no visible check confirms it does not exceed `sizeof({_dst})`.")
                parts.append(f"If `{_sz}` exceeds the destination field size, this overwrites adjacent memory and corrupts neighboring data. Enforce the bound before the copy.")
                fix = f"Verify `{_sz}` <= sizeof destination before copying:\n  if ({_sz} > sizeof({_dst})) return ERROR;\n  {_fn}({', '.join(_args)});"
            elif src_line_text:
                parts.append(f"Out-of-bounds {verb} at line {access_line_actual}: `{src_line_text[:140].rstrip()}`")
                parts.append("Review the pointer/array bounds for this access; if the index or length exceeds the object's allocated size, it reads/writes adjacent memory, corrupts data and can crash or be exploited.")
                fix = "Add explicit bounds checking before all array and pointer dereferences: verify the index/length stays within the object's allocated size."
            else:
                parts.append(f"An out-of-bounds memory access is {verb} at line {access_line_actual}. Manual review is required to confirm the bound and its impact.")
                fix = "Add explicit bounds checking before all array and pointer dereferences: verify the index/length stays within the object's allocated size."

            if guard_explanation:
                parts.append(guard_explanation)
            elif guard_line > 0 and guard_cond:
                parts.append(f"A guard condition was detected at line {guard_line}, but its effectiveness could not be fully determined.")

        comment = " ".join(parts)
        return "Bug", comment, fix, decision.confidence

    # ------------------------------------------------------------------
    # False positive — precise, example-style comment
    # ------------------------------------------------------------------
    elif decision.classification == "False positive":
        parts = []
        parts.append(f"After reviewing {function}(), the OVERRUN at line {access_line_actual} is a false positive.")

        reasons = []
        if _has_pattern(code, r'for\s*\(.*<\s*sizeof\s*\('):
            reasons.append("the array access is driven by a sizeof()-bounded loop")
        if arr_size > 0 and concrete_idx is not None and 0 <= concrete_idx < arr_size:
            reasons.append(f"{concrete_idx_source} places `{idx_var}` at {concrete_idx}, within the declared bounds [0, {arr_size-1}] of `{arr_name}`")
        if guard_explanation:
            # guard_explanation already ends with a sentence; strip the trailing
            # period so the wrapper can close it cleanly.
            reasons.append(guard_explanation.rstrip('.'))
        if not reasons and arr_size_expr and arr_name not in ('the buffer',):
            reasons.append(f"`{arr_name}` is declared with size `{arr_size_expr}`")
        if ctx.get('safe_api_note'):
            sa = ctx['safe_api_note'].strip().rstrip('.')
            if sa and sa not in reasons:
                reasons.append(sa)

        if reasons:
            if len(reasons) == 1:
                parts.append(f"This is because {reasons[0]}.")
            elif len(reasons) == 2:
                parts.append(f"This is because {reasons[0]}, and {reasons[1]}.")
            else:
                parts.append(f"This is because {reasons[0]}; additionally, {reasons[1]}.")

        if decision.confidence >= 0.8:
            parts.append("High confidence; no code changes are needed.")
        elif decision.confidence >= 0.6:
            parts.append("Reasonably confident this is safe; a quick sanity-check is worthwhile.")

        comment = re.sub(r'\s{2,}', ' ', " ".join(parts)).strip()
        return "False positive", comment, "No fix required.", decision.confidence

    # ------------------------------------------------------------------
    # Needs review
    # ------------------------------------------------------------------
    else:
        review_idx_var = nested_inner_idx_var if (nested_access and nested_inner_idx_var) else idx_var
        idx_is_param = (review_idx_var not in ('', 'the offset', 'the index', 'index')
                        and review_idx_var in _function_param_names(code))
        callers = ctx.get('callers_list', []) or []
        if not isinstance(callers, list):
            callers = []

        parts = []
        parts.append(f"The {function}() access at line {access_line_actual} needs manual review — the extracted context is inconclusive.")

        gaps = []
        if not guard_line:
            gaps.append("no definitive bounds guard is visible")
        if not arr_size_expr:
            gaps.append("the array size could not be determined")
        if assign_line == 0 and review_idx_var != 'the index':
            if idx_is_param:
                gaps.append(f"{review_idx_var} is a function parameter, so its bound must be resolved at the call sites")
            else:
                gaps.append(f"the assignment of {review_idx_var} could not be traced")

        if gaps:
            if len(gaps) == 1:
                parts.append(f"Specifically, {gaps[0]}.")
            else:
                parts.append(f"Specifically, {'; '.join(gaps[:-1])}; and {gaps[-1]}.")

        if callers:
            caller_brief = ", ".join(sorted({str(c.get('caller', '')) for c in callers
                                             if isinstance(c, dict) and c.get('caller')})[:5])
            if caller_brief:
                parts.append(f"It is reachable from {caller_brief}, but no reachable call site proves a hard upper bound on `{review_idx_var}` for `{arr_name}`.")
        elif function and not re.search(r'\bmain\b|\b_init\b|\b_fini\b|callback|hook|handler', function, re.I):
            parts.append(f"No caller of {function}() was found in the workspace, so the bound on `{review_idx_var}` cannot be settled from the call graph.")

        parts.append("Please verify the array bounds (including any cross-file guards) before finalizing the disposition.")
        comment = re.sub(r'\s{2,}', ' ', " ".join(parts)).strip()
        if nested_access:
            if inner_index_proven_safe:
                inner_text = (f"`{nested_inner_arr}[{nested_inner_idx_var}]`"
                              if nested_inner_arr and nested_inner_idx_var else f"`{idx_expr}`")
                inner_bound = (f" within `{nested_inner_arr}`'s declared limit"
                               if nested_inner_arr else " in range")
                comment += (f" The inner access {inner_text} resolves with `{nested_inner_idx_var}` = "
                            f"{nested_inner_idx_value}{inner_bound}. "
                            f"That makes the derived outer index into `{arr_name}` evaluate to `{concrete_idx}` via "
                            f"{concrete_idx_source}. The remaining question is whether the outer-table bound/check "
                            f"for `{arr_name}` is semantically correct and whether its MAX constant is inclusive or "
                            f"exclusive.")
            else:
                comment += (" The access uses a derived/nested index, so the inner "
                            "index and the outer table require separate bound checks; "
                            "the MAX constant's inclusive/exclusive meaning must be "
                            "confirmed from its declaration.")
            fix = "Manual review required."
        else:
            # No patch is offered unless this is a single, identifiable index.
            fix = f"Suggestion: if ({idx_var} < 0 || {idx_var} >= ARRAY_SIZE) return ERROR; // CWE-125"
        return "Needs review", comment, fix, decision.confidence

def _analyze_integer_overflow(code: str, sub_checker: str, events: List[Dict],
                         file: str = "", line: int = 0, function: str = "", cid: int = 0,
                         called_function_codes: Optional[Dict[str, str]] = None,
                         code_start_line: int = 1, tree=None) -> Tuple[str, str, str, float]:
    ctx = _build_analysis_context(code, 'INTEGER_OVERFLOW', events, file, line, function, cid, called_function_codes, code_start_line)
    acc = build_evidence(ctx, ctx['ev'], 'INTEGER_OVERFLOW')

    resolution_sources = _gather_resolution_sources(
        code, file, called_function_codes, ctx.get('callers_list', []))
    defect_line_code = _line_text_at(code, line, code_start_line)
    op_info = _extract_binary_operation(defect_line_code or code, ('*', '+', '-'))
    call_names = set(re.findall(r'(\w+)\s*\(', defect_line_code or code))
    all_vars = [v for v in extract_vars(defect_line_code or code) if v not in call_names]
    ctx['var'] = all_vars[0] if all_vars else 'the operand'

    lhs_expr = rhs_expr = ''
    lhs_val = rhs_val = None
    if op_info:
        lhs_expr, op_token, rhs_expr = op_info
        ctx['lhs_expr'] = lhs_expr
        ctx['rhs_expr'] = rhs_expr
        ctx['op_token'] = op_token
        if op_token == '*':
            ctx['operation'] = 'multiplication'
            ctx['operand'] = rhs_expr or 'multiplier'
        elif op_token == '-':
            ctx['operation'] = 'subtraction'
            ctx['operand'] = rhs_expr or 'subtrahend'
        else:
            ctx['operation'] = 'addition'
            ctx['operand'] = rhs_expr or 'addend'
        lhs_val = _resolve_expr_value_before_line(code, lhs_expr, line, code_start_line, resolution_sources)
        rhs_val = _resolve_expr_value_before_line(code, rhs_expr, line, code_start_line, resolution_sources)
    else:
        ctx['operation'] = 'arithmetic'
        ctx['operand'] = all_vars[1] if len(all_vars) > 1 else 'value'
        op_token = ''

    type_bounds = _infer_integral_decl_bounds(ctx.get('var', ''), resolution_sources)
    ctx['integer_type'] = type_bounds.get('type_text') or 'int'
    ctx['integer_bits'] = type_bounds.get('bits', 32)
    ctx['integer_min'] = type_bounds.get('min', -(2**31))
    ctx['integer_max'] = type_bounds.get('max', 2**31 - 1)
    ctx['integer_unsigned'] = type_bounds.get('unsigned', False)

    if _has_pattern(code, r'uint(8|16|32|64)_t|unsigned') and        not _has_pattern(code, r'(signed|int32_t|int64_t)'):
        acc.add(Evidence(
            label="unsigned_wrap_defined_behavior",
            polarity="fp",
            weight=0.60,
            description="Arithmetic operates on unsigned integers — wrap-around is well-defined in C."
        ))

    if lhs_val is not None and rhs_val is not None and op_token:
        if op_token == '*':
            result_val = lhs_val * rhs_val
        elif op_token == '+':
            result_val = lhs_val + rhs_val
        else:
            result_val = lhs_val - rhs_val
        ctx['concrete_lhs'] = lhs_val
        ctx['concrete_rhs'] = rhs_val
        ctx['concrete_result'] = result_val
        if ctx['integer_unsigned']:
            acc.add(Evidence(
                label="concrete_unsigned_arithmetic",
                polarity="fp",
                weight=0.70,
                description=(f"The flagged expression evaluates concretely to {lhs_val} {op_token} {rhs_val} = {result_val} "
                             f"on unsigned type `{ctx['integer_type']}`; wrap semantics are defined.")
            ))
        elif ctx['integer_min'] <= result_val <= ctx['integer_max']:
            acc.add(Evidence(
                label="concrete_arithmetic_in_range",
                polarity="fp",
                weight=0.92,
                description=(f"The flagged expression evaluates to {result_val}, which fits in `{ctx['integer_type']}` "
                             f"[{ctx['integer_min']}, {ctx['integer_max']}].")
            ))
        else:
            acc.add(Evidence(
                label="concrete_arithmetic_overflow",
                polarity="bug",
                weight=0.95,
                description=(f"The flagged expression evaluates to {result_val}, outside `{ctx['integer_type']}` "
                             f"[{ctx['integer_min']}, {ctx['integer_max']}].")
            ))
    elif op_token:
        primary_var = all_vars[0] if all_vars else ''
        if primary_var:
            flow = _extract_index_flow(code, primary_var, line, code_start_line)
            guard_limit_val = _resolve_integer_constant(flow.get('guard_limit', ''), resolution_sources)                 if flow.get('guard_limit') else None
            const_other = rhs_val if primary_var == lhs_expr.strip() else lhs_val
            if guard_limit_val is not None and const_other is not None and flow.get('guard_op') in ('<', '<=', '>', '>='):
                if flow['guard_op'] in ('<', '<='):
                    max_primary = guard_limit_val - 1 if flow['guard_op'] == '<' else guard_limit_val
                    if op_token == '+' and max_primary + const_other <= ctx['integer_max']:
                        acc.add(Evidence(
                            label="guarded_arithmetic_in_range",
                            polarity="fp",
                            weight=0.82,
                            description=(f"Guard `{flow['guard_cond']}` bounds `{primary_var}` so `{primary_var} {op_token} {const_other}` "
                                         f"cannot exceed `{ctx['integer_type']}`.")
                        ))
                    elif op_token == '*' and max_primary * const_other <= ctx['integer_max']:
                        acc.add(Evidence(
                            label="guarded_arithmetic_in_range",
                            polarity="fp",
                            weight=0.82,
                            description=(f"Guard `{flow['guard_cond']}` bounds `{primary_var}` so `{primary_var} * {const_other}` "
                                         f"stays within `{ctx['integer_type']}`.")
                        ))

    decision = DecisionAgent.evaluate(acc, 'INTEGER_OVERFLOW')

    if decision.classification == "False positive":
        if ctx.get('concrete_result') is not None and not ctx.get('integer_unsigned'):
            comment = (f"At line {line} in {function}(), the flagged arithmetic resolves to "
                       f"`{lhs_expr} {op_token} {rhs_expr}` = {ctx['concrete_result']}. That result fits in "
                       f"`{ctx['integer_type']}` [{ctx['integer_min']}, {ctx['integer_max']}], so no signed overflow "
                       f"occurs on this path. False positive.")
            fix = "No fix required."
        elif ctx.get('integer_unsigned') and ctx.get('concrete_result') is not None:
            comment = (f"At line {line} in {function}(), the flagged arithmetic resolves concretely on unsigned type "
                       f"`{ctx['integer_type']}`. Unsigned wrap-around is defined by the language, so this is not a "
                       f"signed overflow defect on the reported path. False positive.")
            fix = "No fix required."
        else:
            has_unsigned = any(e.label == 'unsigned_wrap_defined_behavior' for e in acc.evidence)
            has_bounded = any(e.label == 'guarded_arithmetic_in_range' for e in acc.evidence)
            op_label = ctx['operation'] if ctx['operation'] != 'arithmetic' else 'arithmetic operation'
            if has_unsigned:
                comment = (f"[FALSE POSITIVE] INTEGER_OVERFLOW in {function}() at line {line} is not a real defect. "
                           f"The {op_label} operates on unsigned integer type(s) — wrap-around is defined behavior in C. "
                           f"Coverity raised this because it applies overflow heuristics broadly to arithmetic.")
                fix = "No fix required. Optionally silence with a range assertion for clarity."
            elif has_bounded:
                comment = (f"[FALSE POSITIVE] INTEGER_OVERFLOW in {function}() at line {line} is not a real defect. "
                           f"The {op_label} is bounded by an explicit guard visible in the extracted code; "
                           f"the operand(s) cannot reach values large enough to overflow.")
                fix = "No fix required. Keep the guard and consider documenting it as a Coverity suppression."
            else:
                comment = _build_comment_from_evidence(decision, ctx)
                fix = "No fix required. Ensure the final result fits in the destination type."
        comment = _apply_example_style('False positive', 'INTEGER_OVERFLOW', ctx, code,
                                       code_start_line, line, function, comment)
        return "False positive", comment, fix, decision.confidence

    if decision.classification == "Bug":
        if ctx.get('concrete_result') is not None and not ctx.get('integer_unsigned'):
            comment = (f"At line {line} in {function}(), the flagged arithmetic resolves to "
                       f"`{lhs_expr} {op_token} {rhs_expr}` = {ctx['concrete_result']}. That lies outside "
                       f"`{ctx['integer_type']}` [{ctx['integer_min']}, {ctx['integer_max']}], so the computation "
                       f"overflows on this path.")
            fix = generate_contextual_fix('integer_overflow', 'Bug', ctx)
        else:
            comment = synthesize_expert_comment('integer_overflow', 'bug', ctx)
            fix = generate_contextual_fix('integer_overflow', 'Bug', ctx)
        comment = _apply_example_style('Bug', 'INTEGER_OVERFLOW', ctx, code,
                                       code_start_line, line, function, comment)
        return "Bug", comment, fix, decision.confidence
    else:
        comment = _build_comment_from_evidence(decision, ctx)
        return "Needs review", comment, "Validate arithmetic inputs before operation. Consider upcasting to wider type or adding range guards.", decision.confidence



def _analyze_string_null(code: str, sub_checker: str, events: List[Dict],
                         file: str = "", line: int = 0, function: str = "", cid: int = 0,
                         called_function_codes: Optional[Dict[str, str]] = None,
                         code_start_line: int = 1, tree=None) -> Tuple[str, str, str, float]:
    ctx = _build_analysis_context(code, 'STRING_NULL', events, file, line, function, cid, called_function_codes, code_start_line)
    acc = build_evidence(ctx, ctx['ev'], 'STRING_NULL')

    sink = ctx['sink_func']
    if sink in ('memcpy', 'strncpy') and not _has_pattern(code, r'["\']\\0["\']'):
        acc.add(Evidence(
            label="copy_without_null_termination",
            polarity="bug",
            weight=0.65,
            description=f"{sink}() used without explicit null terminator afterwards."
        ))

    decision = DecisionAgent.evaluate(acc, 'STRING_NULL')

    if decision.classification == "Bug":
        comment = (f"At line {line} in {function}(), {sink}() is used without an explicit null terminator afterwards. "
                   f"Note that {sink}() does NOT guarantee null termination if the source is >= the size argument. "
                   f"If the destination is used as a C string later, this is a real bug.")
        fix = (f"Add after the {sink}() call:\n"
               f"  {ctx.get('dest_var', 'buf')}[sizeof({ctx.get('dest_var', 'buf')}) - 1] = '\\0';")
        comment = _apply_example_style('Bug', 'STRING_NULL', ctx, code,
                                       code_start_line, line, function, comment)
        return "Bug", comment, fix, decision.confidence
    elif decision.classification == "False positive":
        comment = _build_comment_from_evidence(decision, ctx)
        comment = _apply_example_style('False positive', 'STRING_NULL', ctx, code,
                                       code_start_line, line, function, comment)
        return "False positive", comment, "No fix required.", decision.confidence
    else:
        comment = _build_comment_from_evidence(decision, ctx)
        return "Needs review", comment, "Verify all string operations result in properly terminated strings. Prefer snprintf(dest, sizeof(dest), ...) over sprintf/strcpy.", decision.confidence


def _analyze_reverse_inull(code: str, sub_checker: str, events: List[Dict],
                         file: str = "", line: int = 0, function: str = "", cid: int = 0,
                         called_function_codes: Optional[Dict[str, str]] = None,
                         code_start_line: int = 1, tree=None) -> Tuple[str, str, str, float]:
    ctx = _build_analysis_context(code, 'REVERSE_INULL', events, file, line, function, cid, called_function_codes, code_start_line)
    ev  = ctx['ev']
    var = ctx['ev_null_var'] or ctx['var'] or _extract_var_from_deref(code) or \
          (extract_vars(code)[0] if extract_vars(code) else '')
    ctx['var'] = var

    acc = build_evidence(ctx, ev, 'REVERSE_INULL')

    guard = analyze_guard_dominance(code, var, line)
    if guard['has_guard'] and guard['guard_covers_all_paths'] and guard['guard_line'] < line:
        acc.add(Evidence(
            label="null_guard_dominates_dereference",
            polarity="fp",
            weight=0.75,
            description=f"Null check at line {guard['guard_line']} dominates dereference at line {line}."
        ))

    if ev['confirmed_null_var'] and ev['confirmed_null_var'] == var:
        acc.add(Evidence(
            label="coverity_confirmed_null",
            polarity="bug",
            weight=0.85,
            description=f"Trace analysis shows `{var}` holds NULL on this path."
        ))

    decision = DecisionAgent.evaluate(acc, 'REVERSE_INULL')

    if decision.classification == "Bug":
        loc = f" at line {line}" if line else ""
        null_note = ""
        if ev['confirmed_null_var'] and ev['confirmed_null_var'] == var:
            null_note = f" Trace analysis shows `{var}` holds NULL on this path."
        comment = (f"In {function}(), the null check for `{var}` appears after the dereference{loc}, "
                   f"or is missing entirely.{null_note} Move the null check before first use.")
        fix = generate_contextual_fix('null_deref', 'Bug', ctx)
        comment = _apply_example_style('Bug', 'REVERSE_INULL', ctx, code,
                                       code_start_line, line, function, comment)
        return "Bug", comment, fix, decision.confidence
    elif decision.classification == "False positive":
        parts = [f"After reviewing {function}(), the REVERSE_INULL at line {line} is a false positive. "]
        reasons = []
        gline = ctx.get('guard_line', 0)
        gcond = ctx.get('guard_cond', '')
        if gline > 0 and gcond:
            reasons.append(f"a null check exists at line {gline} before the dereference at line {line}")
        if ctx.get('guard_covers_all_paths'):
            if reasons:
                reasons[0] += " and dominates all paths to this operation"
            else:
                reasons.append("a guard dominates all paths to this operation")
        if reasons:
            parts.append(f"This is because {reasons[0]}. ")
        if decision.confidence >= 0.8:
            parts.append("High confidence; no code changes are needed.")
        elif decision.confidence >= 0.6:
            parts.append("Reasonably confident this is safe; a quick sanity-check is worthwhile.")
        comment = re.sub(r'\s{2,}', ' ', "".join(parts)).strip()
        comment = _apply_example_style('False positive', 'REVERSE_INULL', ctx, code,
                                       code_start_line, line, function, comment)
        return "False positive", comment, "No fix required. Verify guard is present on all branches that dereference this pointer.", decision.confidence
    else:
        if decision.classification == "Needs review" and var and var not in ('', 'the variable', 'the pointer'):
            # REVERSE_INULL: the null check appears after the dereference (or is
            # missing). When we can identify the variable and no guard clearly
            # covers all paths, treat it as a likely bug rather than Needs review.
            decision = type(decision)(classification='Bug',
                                      confidence=max(decision.confidence, 0.55),
                                      reasoning=decision.reasoning +
                                      [f"Null check appears after the dereference of `{var}` (reverse null check)."])
            loc = f" at line {line}" if line else ""
            comment = (f"In {function}(), the null check for `{var}` appears after the dereference{loc}, "
                       f"or is missing entirely. Move the null check before first use.")
            fix = generate_contextual_fix('null_deref', 'Bug', ctx)
            comment = _apply_example_style('Bug', 'REVERSE_INULL', ctx, code,
                                           code_start_line, line, function, comment)
            return "Bug", comment, fix, decision.confidence
        comment = _build_comment_from_evidence(decision, ctx)
        return "Needs review", comment, "Verify null check placement and coverage on all paths.", decision.confidence


def _analyze_forward_null(code: str, sub_checker: str, events: List[Dict],
                         file: str = "", line: int = 0, function: str = "", cid: int = 0,
                         called_function_codes: Optional[Dict[str, str]] = None,
                         code_start_line: int = 1, tree=None) -> Tuple[str, str, str, float]:
    ctx = _build_analysis_context(code, 'FORWARD_NULL', events, file, line, function, cid, called_function_codes, code_start_line)
    var = ctx['var'] or _extract_var_from_deref(code) or (extract_vars(code)[0] if extract_vars(code) else 'the pointer')
    ctx['var'] = var

    acc = build_evidence(ctx, ctx['ev'], 'FORWARD_NULL')

    guard = analyze_guard_dominance(code, var, line)
    if guard['has_guard'] and guard['guard_covers_all_paths']:
        acc.add(Evidence(
            label="null_guard_covers_all_paths",
            polarity="fp",
            weight=0.75,
            description=f"Null guard at line {guard['guard_line']} covers all paths to dereference."
        ))

    # CFG: verify the call is inside the if-body guarded by a null check
    if _FLOW_ANALYSIS and guard['has_guard'] and guard.get('guard_line', 0):
        try:
            cfg = _fa.build_cfg(code, code_start_line)
            if _fa.is_call_inside_condition_block(cfg, line, guard['guard_line']):
                acc.add(Evidence(
                    label="cfg_call_inside_guard_block",
                    polarity="fp",
                    weight=0.80,
                    description=f"CFG proves call at line {line} is inside the null-check block at line {guard['guard_line']}."
                ))
        except Exception:
            pass

    # Guarded-call pattern (success-flag pattern: if (flag==TRUE) { call(); })
    guarded = _detect_guarded_call_pattern(code, var, line, code_start_line)
    if guarded:
        acc.add(Evidence(
            label="guarded_call_success_flag",
            polarity="fp",
            weight=0.75,
            description=guarded.get('description', 'call is inside guarded success block')
        ))

    if ctx['ev']['confirmed_null_var'] and ctx['ev']['confirmed_null_var'] == var:
        acc.add(Evidence(
            label="coverity_confirmed_null_deref",
            polarity="bug",
            weight=0.90,
            description=f"Coverity trace confirms `{var}` is NULL on this path."
        ))

    decision = DecisionAgent.evaluate(acc, 'FORWARD_NULL')

    if decision.classification == "Bug":
        loc = f" at line {line}" if line else ""
        if ctx['ev']['confirmed_null_var'] and ctx['ev']['confirmed_null_var'] == var:
            comment = (f"In {function}(){loc}, `{var}` is NULL on this execution path. "
                       f"The pointer originates from {ctx['origin']} and is dereferenced before any null guard — confirmed null-pointer dereference.")
        elif ctx['ev']['defect_confirmed']:
            comment = (f"The null-dereference path is reachable in {function}(){loc}. "
                       f"`{var}` may be NULL when it originates from {ctx['origin']}.")
        else:
            comment = (f"At line {line} in {function}(), `{var}` is dereferenced without a visible null check. "
                       f"If `{var}` comes from {ctx['origin']}, a failure path could leave it NULL.")
        fix = generate_contextual_fix('null_deref', 'Bug', ctx)
        comment = _apply_example_style('Bug', 'FORWARD_NULL', ctx, code,
                                       code_start_line, line, function, comment)
        return "Bug", comment, fix, decision.confidence
    elif decision.classification == "False positive":
        parts = [f"After reviewing {function}(), the null dereference concern for `{var}` at line {line} is a false positive. "]
        reasons = []
        gline = ctx.get('guard_line', 0)
        gcond = ctx.get('guard_cond', '')
        if gline > 0 and gcond:
            reasons.append(f"a null check exists at line {gline} before the dereference at line {line}")
        if ctx.get('guard_covers_all_paths'):
            if reasons:
                reasons[0] += " and dominates all paths to the dereference"
            else:
                reasons.append("a guard dominates all paths to the dereference")
        if _has_pattern(code, r'\bstd::unique_ptr|\bstd::shared_ptr'):
            reasons.append("a smart pointer guarantees non-null access")
        if reasons:
            reasons = reasons[:2]
            if len(reasons) == 1:
                parts.append(f"This is because {reasons[0]}. ")
            else:
                parts.append(f"This is because {reasons[0]}, and {reasons[1]}. ")
        if decision.confidence >= 0.8:
            parts.append("High confidence; no code changes are needed.")
        elif decision.confidence >= 0.6:
            parts.append("Reasonably confident this is safe; a quick sanity-check is worthwhile.")
        comment = re.sub(r'\s{2,}', ' ', "".join(parts)).strip()
        comment = _apply_example_style('False positive', 'FORWARD_NULL', ctx, code,
                                       code_start_line, line, function, comment)
        return "False positive", comment, "No fix required. Verify guard covers all execution paths.", decision.confidence
    else:
        comment = _build_comment_from_evidence(decision, ctx)
        return "Needs review", comment, "Add null validation before dereference if not already present.", decision.confidence


def _analyze_resource_leak(code: str, sub_checker: str, events: List[Dict],
                         file: str = "", line: int = 0, function: str = "", cid: int = 0,
                         called_function_codes: Optional[Dict[str, str]] = None,
                         code_start_line: int = 1, tree=None) -> Tuple[str, str, str, float]:
    ctx = _build_analysis_context(code, 'RESOURCE_LEAK', events, file, line, function, cid, called_function_codes, code_start_line)
    acc = build_evidence(ctx, ctx['ev'], 'RESOURCE_LEAK')

    release_funcs = ['fclose', 'close', 'free', 'delete', 'CloseHandle', 'pclose', 'regfree']
    for func in release_funcs:
        if re.search(rf'\b{func}\s*\(', code):
            acc.add(Evidence(
                label=f"release_function_{func}",
                polarity="fp",
                weight=0.75,
                description=f"Resource release function {func}() found in function body."
            ))

    if _has_pattern(code, r'\bstd::unique_ptr|\bstd::shared_ptr|\bauto_ptr|\bQScopedPointer|\bg_auto'):
        acc.add(Evidence(
            label="raii_smart_pointer",
            polarity="fp",
            weight=0.80,
            description="RAII smart pointer manages resource automatically."
        ))

    if _has_pattern(code, r'\bgoto\s+(cleanup|done|error|exit)'):
        acc.add(Evidence(
            label="goto_cleanup_pattern",
            polarity="fp",
            weight=0.65,
            description="goto-cleanup pattern detected — all paths may jump to unified exit."
        ))

    if _has_pattern(code, r'if\s*\(.*\)\s*\{?\s*return'):
        if not any(e.label.startswith('release_function_') for e in acc.evidence):
            acc.add(Evidence(
                label="early_return_without_release",
                polarity="bug",
                weight=0.70,
                description="Early return detected without visible resource release."
            ))

    decision = DecisionAgent.evaluate(acc, 'RESOURCE_LEAK')

    _res = ctx.get('resource') or ctx.get('var') or 'resource'
    _rel = ctx.get('release_func') or 'free'
    if decision.classification == "Bug":
        comment = (f"In {function}() at line {line}, `{_res}` is acquired but not released on all paths (CWE-401/404, CERT MEM31-C/FIO42-C). "
                   f"Leak on error path → descriptor/memory exhaustion.")
        fix = f"{_rel}({_res}); // or goto cleanup; RAII // CWE-401"
        return "Bug", comment, fix, decision.confidence
    elif decision.classification == "False positive":
        comment = _build_comment_from_evidence(decision, ctx)
        return "False positive", comment, "No fix required. Verify release is reached on all execution paths.", decision.confidence
    else:
        comment = _build_comment_from_evidence(decision, ctx)
        return "Needs review", comment, "Verify all allocation paths have matching cleanup.", decision.confidence


def _analyze_deadcode(code: str, sub_checker: str, events: List[Dict],
                         file: str = "", line: int = 0, function: str = "", cid: int = 0,
                         called_function_codes: Optional[Dict[str, str]] = None,
                         code_start_line: int = 1, tree=None) -> Tuple[str, str, str, float]:
    ctx = _build_analysis_context(code, 'DEADCODE', events, file, line, function, cid, called_function_codes, code_start_line)
    acc = build_evidence(ctx, ctx['ev'], 'DEADCODE')

    if '#if 0' in code or '#ifdef NEVER' in code:
        acc.add(Evidence(
            label="preprocessor_disabled_block",
            polarity="fp",
            weight=0.85,
            description="Code is inside #if 0 or #ifdef NEVER — intentionally disabled."
        ))

    if re.search(r'\bTODO\b|\bFIXME\b|\bDEAD\b|\bXXX\b', code):
        acc.add(Evidence(
            label="marked_todo_fixme",
            polarity="fp",
            weight=0.60,
            description="Dead code marked with TODO/FIXME — intentionally reserved."
        ))

    if re.search(r'\bassert\s*\(\s*0\s*\)|\bassert\s*\(\s*false\s*\)', code):
        acc.add(Evidence(
            label="assert_unreachable",
            polarity="fp",
            weight=0.75,
            description="Code follows assert(0) — intentional panic path handling."
        ))

    callers = ctx.get('callers_list', [])
    if isinstance(callers, list) and len(callers) == 0 and function and \
       not re.search(r'\bmain\b|\b_init\b|\b_fini\b|callback|hook|handler', function, re.I):
        acc.add(Evidence(
            label="function_has_no_callers",
            polarity="fp",
            weight=0.55,
            description=f"{function}() has no callers in workspace — likely legacy code."
        ))

    if ctx['ev']['defect_confirmed']:
        acc.add(Evidence(
            label="coverity_confirmed_unreachable",
            polarity="bug",
            weight=0.70,
            description="Coverity trace confirms this code block is unreachable on all valid paths."
        ))

    decision = DecisionAgent.evaluate(acc, 'DEADCODE')

    if decision.classification == "Bug":
        loc = f" at line {line}" if line else ""
        comment = (f"The code block{loc} in {function}() is unreachable on all valid execution paths. "
                   f"Dead code increases maintenance burden and can hide logic errors. "
                   f"{decision.reasoning[0] if decision.reasoning else ''}")
        comment = _apply_example_style("Bug", 'DEADCODE', ctx,
                                       code, code_start_line, line, function, comment)
        fix = "Remove dead code or refactor to ensure code is executable. If temporarily disabled, use #if 0 with explanatory comment."
        return "Bug", comment, fix, decision.confidence
    elif decision.classification == "False positive" or decision.classification == "Intentional":
        comment = _build_comment_from_evidence(decision, ctx)
        comment = _apply_example_style(decision.classification, 'DEADCODE', ctx,
                                       code, code_start_line, line, function, comment)
        return "Intentional", comment, "No fix required.", decision.confidence
    else:
        comment = _build_comment_from_evidence(decision, ctx)
        return "Needs review", comment, "Verify if code is truly unreachable or intentionally disabled.", decision.confidence


def _analyze_array_vs_singleton(code: str, sub_checker: str, events: List[Dict],
                         file: str = "", line: int = 0, function: str = "", cid: int = 0,
                         called_function_codes: Optional[Dict[str, str]] = None,
                         code_start_line: int = 1, tree=None) -> Tuple[str, str, str, float]:
    ctx = _build_analysis_context(code, 'ARRAY_VS_SINGLETON', events, file, line, function, cid, called_function_codes, code_start_line)
    acc = EvidenceAccumulator()

    if _has_pattern(code, r'numocts\s*==\s*0|len\s*==\s*0|size\s*==\s*0|count\s*==\s*0'):
        acc.add(Evidence(
            label="zero_length_guard",
            polarity="fp",
            weight=0.80,
            description="Zero-length guard indicates single-element access only."
        ))

    if _has_pattern(code, r'\bsizeof\s*\(\s*\*'):
        acc.add(Evidence(
            label="sizeof_deref_pattern",
            polarity="fp",
            weight=0.75,
            description="sizeof(*ptr) correctly captures pointed-to type size."
        ))

    if not any(e.polarity == "fp" for e in acc.evidence):
        acc.add(Evidence(
            label="singleton_passed_as_array",
            polarity="bug",
            weight=0.65,
            description="Singleton address may be passed where an array is expected."
        ))

    decision = DecisionAgent.evaluate(acc, 'ARRAY_VS_SINGLETON')

    if decision.classification == "False positive" or decision.classification == "Intentional":
        comment = _build_comment_from_evidence(decision, ctx)
        return "Intentional", comment, "No fix required if caller contract guarantees single-element access. Document the contract.", decision.confidence

    if decision.classification == "Bug":
        comment = (f"In {function}() at line {line}, a singleton address may be passed where an array is expected. "
                   f"If the callee iterates or does pointer arithmetic, this will read/write out of bounds. "
                   f"Verify the callee contract.")
        fix = "Pass an array or add explicit size=1 contract with callee. Ensure callee does not access beyond first element."
        comment = _apply_example_style('Bug', 'ARRAY_VS_SINGLETON', ctx, code,
                                       code_start_line, line, function, comment)
        return "Bug", comment, fix, decision.confidence

    comment = _build_comment_from_evidence(decision, ctx)
    return "Needs review", comment, "Verify if callee expects an array and whether singleton access is safe.", decision.confidence


def _analyze_negative_returns(code: str, sub_checker: str, events: List[Dict],
                         file: str = "", line: int = 0, function: str = "", cid: int = 0,
                         called_function_codes: Optional[Dict[str, str]] = None,
                         code_start_line: int = 1, tree=None) -> Tuple[str, str, str, float]:
    ctx = _build_analysis_context(code, 'NEGATIVE_RETURNS', events, file, line, function, cid, called_function_codes, code_start_line)
    acc = EvidenceAccumulator()
    resolution_sources = _gather_resolution_sources(
        code, file, called_function_codes, ctx.get('callers_list', []))
    defect_line_code = _line_text_at(code, line, code_start_line)

    call_names = set(re.findall(r'(\w+)\s*\(', defect_line_code or code))
    line_vars = [v for v in extract_vars(defect_line_code or code) if v not in call_names]
    suspect_var = line_vars[-1] if line_vars else (ctx.get('var') or 'result')
    ctx['var'] = suspect_var
    flow = _extract_index_flow(code, suspect_var, line, code_start_line)
    concrete_val = _resolve_var_value_before_line(code, suspect_var, line, code_start_line, resolution_sources)
    if concrete_val is None and ctx['ev'].get('variables', {}).get(suspect_var) is not None:
        concrete_val = ctx['ev']['variables'][suspect_var]

    if _has_pattern(code, r'if\s*\(.*<\s*0\s*\)') or _has_pattern(code, r'if\s*\(.*==\s*EOF\s*\)'):
        acc.add(Evidence(
            label="negative_return_checked",
            polarity="fp",
            weight=0.85,
            description="Return value explicitly checked for negative/EOF before use."
        ))

    desc = _event_descriptions(events).lower()
    if any(w in desc for w in ['check', 'guard', 'compare', 'test', 'verify']):
        acc.add(Evidence(
            label="coverity_shows_validation",
            polarity="fp",
            weight=0.80,
            description="Coverity trace shows validation of the return value before consumption."
        ))

    if flow.get('guard_cond') and _guard_rejects_negative(suspect_var, flow['guard_cond']):
        acc.add(Evidence(
            label="guard_rejects_negative_value",
            polarity="fp",
            weight=0.88,
            description=f"Guard `{flow['guard_cond']}` rejects negative/error values of `{suspect_var}` before use."
        ))

    if concrete_val is not None:
        ctx['concrete_value'] = concrete_val
        if concrete_val < 0:
            acc.add(Evidence(
                label="concrete_negative_value_used",
                polarity="bug",
                weight=0.95,
                description=f"`{suspect_var}` resolves to negative value {concrete_val} on the flagged path."
            ))
        else:
            acc.add(Evidence(
                label="concrete_nonnegative_value_used",
                polarity="fp",
                weight=0.90,
                description=f"`{suspect_var}` resolves to non-negative value {concrete_val} on the flagged path."
            ))

    if _has_pattern(code, r'malloc\s*\(|memcpy\s*\(|\[\s*\w+\s*\]'):
        acc.add(Evidence(
            label="negative_used_as_size",
            polarity="bug",
            weight=0.75,
            description="Potentially negative return value used directly as a size or index."
        ))

    if not any(e.polarity in ("bug", "fp") for e in acc.evidence):
        acc.add(Evidence(
            label="no_visible_validation",
            polarity="bug",
            weight=0.55,
            description="Signed return value consumed without visible validation."
        ))

    decision = DecisionAgent.evaluate(acc, 'NEGATIVE_RETURNS')

    if decision.classification == "False positive":
        if concrete_val is not None and concrete_val >= 0:
            comment = (f"At line {line} in {function}(), `{suspect_var}` resolves to {concrete_val} before it is used "
                       f"as a size/index. The flagged path therefore does not carry a negative error code into the "
                       f"memory operation. False positive.")
        elif flow.get('guard_cond') and _guard_rejects_negative(suspect_var, flow['guard_cond']):
            comment = (f"At line {line} in {function}(), `{suspect_var}` is consumed only after guard "
                       f"`{flow['guard_cond']}` at line {flow.get('guard_line', 0)} rejects negative values. "
                       f"The signed error path is blocked before the size/index use. False positive.")
        else:
            comment = _build_comment_from_evidence(decision, ctx)
        comment = _apply_example_style('False positive', 'NEGATIVE_RETURNS', ctx, code,
                                       code_start_line, line, function, comment)
        return "False positive", comment, "No fix required.", decision.confidence

    if decision.classification == "Bug":
        if concrete_val is not None and concrete_val < 0:
            comment = (f"In {function}() at line {line}, `{suspect_var}` resolves to {concrete_val} and is then used "
                       f"as a size/index. Converting that negative error code to an unsigned quantity produces a very "
                       f"large value and can trigger a huge allocation or out-of-bounds access.")
        else:
            comment = (f"In {function}() at line {line}, `{suspect_var}` may be negative (e.g., -1 error) and is used "
                       f"as size/index without check (CWE-20, CERT ERR33-C). Cast to unsigned → ~4GB allocation / OOB.")
        fix = f"if ({suspect_var} < 0) return ERROR; // CWE-20 CERT ERR33-C\nptr = malloc((size_t){suspect_var});"
        comment = _apply_example_style('Bug', 'NEGATIVE_RETURNS', ctx, code,
                                       code_start_line, line, function, comment)
        return "Bug", comment, fix, decision.confidence

    comment = _build_comment_from_evidence(decision, ctx)
    return "Needs review", comment, f"if ({suspect_var}<0) return ERROR; // CWE-20", decision.confidence


# ---------------------------------------------------------------------------
# CHECKED_RETURN — error-handling checker that previously had no dedicated
# handler and therefore collapsed to "Needs review" on event-less (Excel)
# input. Decision model: explicit (void)/ignore -> Intentional; result actually
# used -> False positive; result discarded -> Bug (weighted by how critical the
# called function's return value is).
# ---------------------------------------------------------------------------

_CHECKED_RETURN_CRITICAL = re.compile(
    r'\b(socket|connect|accept|bind|listen|recv|recvfrom|recvmsg|send|sendto|sendmsg|'
    r'read|write|fread|fwrite|fopen|fclose|freopen|fgets|fputs|getline|getdelim|'
    r'pthread_mutex_lock|pthread_mutex_trylock|pthread_mutex_unlock|pthread_rwlock_|'
    r'pthread_create|pthread_join|pthread_cond_wait|pthread_cond_signal|'
    r'malloc|calloc|realloc|strdup|strndup|mmap|munmap|setenv|putenv|chmod|chown|'
    r'rename|remove|unlink|mkdir|rmdir|ioctl|fcntl|open|close|stat|fstat|lseek|'
    r'select|poll|epoll_wait|wait|waitpid|dlopen|sem_wait|sem_post|mlock|munlock)\b',
    re.I)

_CHECKED_RETURN_BENIGN = re.compile(
    r'\b(printf|fprintf|vprintf|vfprintf|snprintf|vsnprintf|sprintf|vsprintf|puts|putchar|'
    r'fputc|fflush|memcpy|memset|memmove|strcpy|strncpy|strcat|strncat|'
    r'strlen|strcmp|strncmp|strchr|strstr|strspn|strcspn|atoi|atol|strtol|'
    r'tolower|toupper|isspace|isdigit|log|debug|trace|DBG_|LOG_|assert|'
    r'va_end|va_copy|exit|abort)\b', re.I)

_CHECKED_RETURN_IGNORED = re.compile(
    r'\(\s*void\s*\)\s*\w+\s*\(|/\*\s*(?:ignore|intentional|by\s+design|not\s+checked|'
    r'deliberately\s+ignored)\s*\*/|//\s*(?:ignore|intentional|by\s+design|not\s+checked)',
    re.I)

# Tokens that regex call-scanning must never treat as CHECKED_RETURN candidates.
_CHECKED_RETURN_SKIP = frozenset({
    'if', 'else', 'while', 'for', 'switch', 'case', 'do', 'goto', 'return',
    'break', 'continue', 'sizeof', 'typedef', 'struct', 'union', 'enum',
    'static', 'const', 'volatile', 'unsigned', 'signed', 'register', 'extern',
    'int', 'char', 'void', 'bool', 'long', 'short', 'float', 'double',
    'int8_t', 'int16_t', 'int32_t', 'int64_t', 'uint8_t', 'uint16_t',
    'uint32_t', 'uint64_t', 'size_t', 'NULL', 'new', 'delete', 'template',
    'class', 'namespace', 'catch', 'throw', 'try',
})


def _analyze_checked_return(code: str, sub_checker: str, events: List[Dict],
                            file: str = "", line: int = 0, function: str = "", cid: int = 0,
                            called_function_codes: Optional[Dict[str, str]] = None,
                            code_start_line: int = 1, tree=None) -> Tuple[str, str, str, float]:
    ctx = _build_analysis_context(code, 'CHECKED_RETURN', events, file, line, function, cid,
                                  called_function_codes, code_start_line)
    sink = _get_sink_from_events(events) or ''
    if not sink:
        for ev in (events or []):
            desc = ev.get('description', '') or ''
            m = (re.search(r"['\"]([A-Za-z_]\w*)\s*\(", desc)
                 or re.search(r'return\s+value\s+of\s+(\w+)\s*\(', desc, re.I))
            if m:
                sink = m.group(1).lower()
                break

    def _call_fate(fn: str, text: str):
        """Return 'ignored' | 'used' | 'discard' for a call on a source line."""
        if _CHECKED_RETURN_IGNORED.search(text):
            return 'ignored'
        m = re.search(rf'\b{re.escape(fn)}\s*\(', text)
        if not m:
            return None
        pre = text[:m.start()]
        if re.search(r'[+\-*/%&|^<>]?=\s*[^=]', pre):
            return 'used'
        if re.search(r'\b(if|while|for|return|assert)\s*\(?\s*$', pre) or \
           re.search(r'(&&|\|\||\?|:)\s*$', pre):
            return 'used'
        return 'discard'

    lines = code.splitlines()
    candidates = []          # (abs_line, fn, text)
    seen_calls = set()
    def_name = (function or '').lower()
    # Robust call scanner that handles nested parentheses (the regex used by
    # _find_function_calls cannot see `send` inside `if (send(...) < 0)`).
    for m in re.finditer(r'\b([A-Za-z_]\w*)\s*\(', code):
        fn = m.group(1)
        fl = fn.lower()
        if fl in _CHECKED_RETURN_SKIP or fl == def_name:
            continue          # control keywords / the function's own signature
        rel = code.count('\n', 0, m.start()) + 1
        if 0 < rel <= len(lines):
            key = (rel, fl)
            if key in seen_calls:
                continue
            seen_calls.add(key)
            candidates.append((rel + code_start_line - 1, fn, lines[rel - 1]))
    if not candidates:
        return ("Needs review",
                f"The CHECKED_RETURN finding in {function}() at line {line} refers to a call that could not be located in the extracted context.",
                "Manual review required to locate the unchecked call.", 0.0)

    if sink:
        focused = [c for c in candidates if c[1].lower() == sink.lower()]
        candidates = focused or candidates
    else:
        # Excel mode (no events): several discarded calls may share the function.
        # Prefer the non-benign ones, because the org configures CHECKED_RETURN for
        # functions whose return value matters — a benign printf() would not be the
        # flagged call when a critical/unknown one is also present.
        non_benign = [c for c in candidates if not _CHECKED_RETURN_BENIGN.search(c[1])]
        if non_benign:
            candidates = non_benign

    candidates.sort(key=lambda c: (abs(c[0] - (line or 0)) if line else c[0], c[1]))

    for abs_line, fn, text in candidates:
        fate = _call_fate(fn, text)
        if fate == 'used':
            return ("False positive",
                    f"The CHECKED_RETURN finding at line {abs_line} in {function}() is a false positive — the return value of {fn}() is actually captured or tested on this line (`{text.strip()[:90]}`).",
                    "No fix required.", 0.80)
        if fate == 'ignored':
            return ("Intentional",
                    f"The return value of {fn}() at line {abs_line} is deliberately ignored — the code documents this with an explicit (void) cast or ignore comment (`{text.strip()[:90]}`).",
                    "No fix required.", 0.85)
        if fate == 'discard':
            if _CHECKED_RETURN_CRITICAL.search(fn):
                cls, conf, reason = "Bug", 0.72, (
                    f"the return value of {fn}() is discarded, but {fn}() reports errors that "
                    f"are essential for correctness/safety — a failure is silently swallowed.")
            elif _CHECKED_RETURN_BENIGN.search(fn):
                cls, conf, reason = "False positive", 0.65, (
                    f"the return value of {fn}() is informational/cosmetic; discarding it is normal practice.")
            else:
                cls, conf, reason = "Bug", 0.52, (
                    f"the return value of {fn}() is discarded; the project enables CHECKED_RETURN for "
                    f"this function, so failures are being silently ignored.")
            if cls == "Bug":
                comment = (f"The CHECKED_RETURN finding at line {abs_line} in {function}() is a bug — {reason}")
                fix = (f"Check the return value of {fn}() and handle the failure (log and/or propagate an error), "
                       f"or cast it to (void) explicitly if ignoring is intentional.")
                return cls, comment, fix, conf
            comment = (f"The CHECKED_RETURN finding at line {abs_line} in {function}() is a false positive — {reason}")
            return cls, comment, "No fix required.", conf

    return ("Needs review",
            f"The CHECKED_RETURN finding in {function}() could not be mapped to a concrete unchecked call in the extracted context.",
            "Manual review required to locate the unchecked call.", 0.0)


def _analyze_unused_value(code: str, sub_checker: str, events: List[Dict],
                         file: str = "", line: int = 0, function: str = "", cid: int = 0,
                         called_function_codes: Optional[Dict[str, str]] = None,
                         code_start_line: int = 1, tree=None) -> Tuple[str, str, str, float]:
    ctx = _build_analysis_context(code, 'UNUSED_VALUE', events, file, line, function, cid, called_function_codes, code_start_line)
    acc = EvidenceAccumulator()

    if re.search(r'\b(printf|log|debug|assert|cout|cerr|trace|LOG_|DBG_)\b', code):
        acc.add(Evidence(
            label="debug_logging_context",
            polarity="fp",
            weight=0.70,
            description="Value used in debug/logging context — may be stripped in release builds but is intentional."
        ))

    if re.search(r'\b(void)\s*\w+|\(void\)', code):
        acc.add(Evidence(
            label="explicit_void_cast",
            polarity="fp",
            weight=0.75,
            description="Return value explicitly cast to (void), documenting intent to ignore it."
        ))

    if _has_pattern(code, r'\breturn\b') and re.search(r'\b(\w+)\s*=\s*', code):
        acc.add(Evidence(
            label="assigned_before_return",
            polarity="neutral",
            weight=0.0,
            description="Value assigned before return or branch — consumption may be in a macro or later code."
        ))

    if not any(e.polarity in ("bug", "fp") for e in acc.evidence):
        acc.add(Evidence(
            label="value_computed_not_used",
            polarity="bug",
            weight=0.60,
            description="Value is computed or assigned but never consumed — possible incomplete implementation."
        ))

    decision = DecisionAgent.evaluate(acc, 'UNUSED_VALUE')

    if decision.classification == "False positive" or decision.classification == "Intentional":
        comment = _build_comment_from_evidence(decision, ctx)
        return "Intentional", comment, "No fix required if value is intentionally for diagnostics only.", decision.confidence

    if decision.classification == "Bug":
        loc = f" at line {line}" if line and line > 0 else ""
        comment = (f"A value is computed or assigned{loc} in {function}() but never consumed. "
                   f"This suggests either an incomplete implementation (forgot to use the result) or a copy-paste error.")
        fix = "Remove assignment or use the value in subsequent computation. Check for missing return, missing function call, or wrong variable name."
        return "Bug", comment, fix, decision.confidence

    # The evidence agent was torn between signals. Instead of dumping the defect
    # into Needs review, commit to the direction the (weak) evidence leans.
    bugs = any(e.polarity == "bug" for e in acc.evidence)
    fps  = any(e.polarity == "fp" for e in acc.evidence)
    if bugs and not fps:
        loc = f" at line {line}" if line and line > 0 else ""
        comment = (f"A value is computed or assigned{loc} in {function}() but never consumed. "
                   f"This suggests either an incomplete implementation (forgot to use the result) or a copy-paste error.")
        return "Bug", comment, "Remove assignment or use the value in subsequent computation.", 0.55
    if fps and not bugs:
        return "Intentional", _build_comment_from_evidence(decision, ctx), \
               "No fix required if value is intentionally for diagnostics only.", 0.55

    comment = _build_comment_from_evidence(decision, ctx)
    return "Needs review", comment, "Verify if assignment has necessary side effect. If not, remove assignment or use the value.", decision.confidence


_UNINIT_KEYWORDS = {
    'if', 'else', 'elif', 'while', 'for', 'do', 'switch', 'case', 'break', 'continue',
    'return', 'goto', 'sizeof', 'struct', 'union', 'enum', 'typedef', 'int', 'char',
    'void', 'bool', 'const', 'static', 'unsigned', 'signed', 'long', 'short', 'float',
    'double', 'true', 'false', 'NULL', 'auto', 'register', 'extern', 'volatile',
}


_UNINIT_STOPWORDS = _UNINIT_KEYWORDS | {
    'value', 'variable', 'in', 'of', 'the', 'for', 'and', 'to', 'is', 'at',
    'on', 'by', 'it', 'this', 'that',
}


def _extract_uninit_var(code: str, events: List[Dict], line: int,
                        code_start_line: int) -> str:
    """Best-effort name of the variable read before it is written.

    Prefers the Coverity event-description text (which usually names the offending
    variable, e.g. \"uninitialized value 'len'\"), then falls back to the identifiers
    on the flagged source line.
    """
    for ev in (events or []):
        desc = "{} {} {}".format(
            ev.get('description') or '', ev.get('var') or '', ev.get('type') or '')
        # 1) Explicit quoted identifier right after a trigger word: most reliable.
        for mm in re.finditer(
                r"(?:uninitialized|uninit|read before|read-before)[^'\"]*?['\"]([A-Za-z_]\w*)['\"]",
                desc, re.IGNORECASE):
            if mm.group(1).lower() not in _UNINIT_STOPWORDS:
                return mm.group(1)
        # 2) "... uninitialized value <name>" with the quotes optional.
        mm = re.search(
            r"uninitialized\s+(?:value|variable)?\s*(?:is\s+)?['\"]?([A-Za-z_]\w*)",
            desc, re.IGNORECASE)
        if mm and mm.group(1).lower() not in _UNINIT_STOPWORDS:
            return mm.group(1)
        # 3) Any quoted identifier in the event text is a strong hint.
        mm2 = re.search(r"['`]([A-Za-z_]\w*)['`]", desc)
        if mm2 and mm2.group(1).lower() not in _UNINIT_STOPWORDS:
            return mm2.group(1)

    # Fall back to identifiers on the flagged source line.
    for abs_no, text in enumerate(code.splitlines(), start=code_start_line):
        if abs_no != line:
            continue
        ids = re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)\b', text)
        candidates = [w for w in ids
                      if w.lower() not in _UNINIT_STOPWORDS and not w.startswith('_')]
        # The read-before-write operand is typically the right-most plain local.
        if candidates:
            return candidates[-1]
    return ""


def _analyze_uninitialized(code: str, sub_checker: str, events: List[Dict],
                         file: str = "", line: int = 0, function: str = "", cid: int = 0,
                         called_function_codes: Optional[Dict[str, str]] = None,
                         code_start_line: int = 1, tree=None) -> Tuple[str, str, str, float]:
    ctx = _build_analysis_context(code, 'UNINIT', events, file, line, function, cid, called_function_codes, code_start_line)
    var = _extract_uninit_var(code, events, line, code_start_line) or ''
    ctx['var'] = var

    # AST-driven enrichment: confirm the variable's declaration/type and look for
    # any partial prior initialisation on earlier lines. Falls back to regex-only
    # (no type info) when no tree-sitter tree is available.
    local_tree = tree
    locally_built = False
    if local_tree is None and code:
        try:
            from code_extractor import _get_parser
            local_tree = _get_parser('cpp').parse(bytes(code, 'utf-8'))
            locally_built = True
        except Exception:
            local_tree = None
    ctx['tree'] = local_tree
    # A locally-built tree is anchored at line 1 of the snippet, while a tree passed
    # in (whole-file, from context_builder) reports absolute file lines.
    line_off = (code_start_line - 1) if locally_built else 0
    target_line = line if not locally_built else (line - code_start_line + 1)
    if var and local_tree is not None:
        try:
            decl = find_declaration(local_tree, var)
        except Exception:
            decl = None
        if decl:
            ctx['uninit_type'] = (decl.get('type_name') or '').strip()
            ctx['uninit_decl_line'] = (decl.get('declaration_line') or 0) + line_off
            ctx['uninit_decl'] = decl.get('raw') or ''
        try:
            prior = find_assignment(local_tree, var, target_line)
        except Exception:
            prior = None
        if prior:
            ctx['uninit_prior_line'] = (prior.get('assignment_line') or 0) + line_off
            ctx['uninit_prior'] = prior.get('rhs_expression') or ''

    acc = EvidenceAccumulator()

    if _has_pattern(code, r'\bmemset\s*\(|\bcalloc\s*\(|\b=\s*\{0\}') or \
       _has_pattern(code, r'struct\s+\w+\s+\w+\s*=\s*\{0\}'):
        acc.add(Evidence(
            label="zero_initialization_present",
            polarity="fp",
            weight=0.85,
            description="Variable initialized via memset(), calloc(), or zero-initializer before use."
        ))

    if _has_pattern(code, r'\b=\s*\{[^}]*\}'):
        acc.add(Evidence(
            label="aggregate_initializer",
            polarity="fp",
            weight=0.80,
            description="Variable uses an aggregate initializer — all fields explicitly initialized."
        ))

    if not any(e.polarity == "fp" for e in acc.evidence):
        acc.add(Evidence(
            label="read_before_assignment",
            polarity="bug",
            weight=0.75,
            description="Variable is read before being assigned a definite value — contains indeterminate data."
        ))

    decision = DecisionAgent.evaluate(acc, 'UNINIT')

    if decision.classification == "False positive":
        comment = _build_comment_from_evidence(decision, ctx)
        comment = _apply_example_style("False positive", 'UNINIT', ctx,
                                       code, code_start_line, line, function, comment)
        return "False positive", comment, "No fix required.", decision.confidence

    if decision.classification == "Bug":
        _t = ctx.get('uninit_type') or 'int'
        _v2 = ctx.get('var') or 'var'
        comment = (f"In {function}() at line {line}, `{_v2}` (type `{_t}`) is read before definite assignment (CWE-457, CERT EXP33-C). "
                   f"Automatic storage not zeroed → indeterminate stack bytes → info leak / nondeterministic branch.")
        comment = _apply_example_style("Bug", 'UNINIT', ctx,
                                       code, code_start_line, line, function, comment)
        fix = f"{_t} {_v2} = 0; // or = {{0}} for struct // CWE-457 CERT EXP33-C"
        return "Bug", comment, fix, decision.confidence

    comment = _build_comment_from_evidence(decision, ctx)
    return "Needs review", comment, "Initialize at declaration or before first use.", decision.confidence


def _analyze_divide_by_zero(code: str, sub_checker: str, events: List[Dict],
                         file: str = "", line: int = 0, function: str = "", cid: int = 0,
                         called_function_codes: Optional[Dict[str, str]] = None,
                         code_start_line: int = 1, tree=None) -> Tuple[str, str, str, float]:
    ctx = _build_analysis_context(code, 'DIVIDE_BY_ZERO', events, file, line, function, cid, called_function_codes, code_start_line)
    acc = EvidenceAccumulator()
    resolution_sources = _gather_resolution_sources(
        code, file, called_function_codes, ctx.get('callers_list', []))

    defect_line_code = _line_text_at(code, line, code_start_line)
    op_info = _extract_binary_operation(defect_line_code or code, ('/', '%'))
    divisor_expr = ''
    divisor_var = ''
    divisor_val = None
    if op_info:
        _, _, divisor_expr = op_info
        divisor_val = _resolve_expr_value_before_line(code, divisor_expr, line, code_start_line, resolution_sources)
        vm = re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', divisor_expr)
        divisor_var = vm.group(0) if vm else ''

    if _has_pattern(code, r'if\s*\(.*!=\s*0\s*\)|if\s*\(.*>\s*0\s*\)|if\s*\(.*>=\s*1\s*\)'):
        acc.add(Evidence(
            label="nonzero_guard_present",
            polarity="fp",
            weight=0.85,
            description="Denominator explicitly checked for non-zero before division."
        ))

    desc = _event_descriptions(events).lower()
    if any(w in desc for w in ['check', 'guard', 'compare', 'test', 'verify']):
        acc.add(Evidence(
            label="coverity_shows_nonzero_check",
            polarity="fp",
            weight=0.80,
            description="Coverity event trace shows explicit non-zero validation before division."
        ))

    if divisor_var:
        flow = _extract_index_flow(code, divisor_var, line, code_start_line)
        if flow.get('guard_cond') and _guard_proves_nonzero(divisor_var, flow['guard_cond']):
            acc.add(Evidence(
                label="guard_proves_divisor_nonzero",
                polarity="fp",
                weight=0.90,
                description=f"Guard `{flow['guard_cond']}` proves `{divisor_var}` is non-zero on the flagged path."
            ))

    if divisor_val is not None:
        ctx['divisor_value'] = divisor_val
        if divisor_val == 0:
            acc.add(Evidence(
                label="concrete_zero_divisor",
                polarity="bug",
                weight=0.96,
                description=f"The divisor resolves to 0 on the flagged path."
            ))
        else:
            acc.add(Evidence(
                label="concrete_nonzero_divisor",
                polarity="fp",
                weight=0.92,
                description=f"The divisor resolves to non-zero constant {divisor_val} on the flagged path."
            ))

    if not any(e.polarity == "fp" for e in acc.evidence):
        acc.add(Evidence(
            label="division_without_guard",
            polarity="bug",
            weight=0.75,
            description="Division operation has no visible non-zero guard."
        ))

    decision = DecisionAgent.evaluate(acc, 'DIVIDE_BY_ZERO')

    _divisor = divisor_var or divisor_expr or ctx.get('var','divisor') or 'divisor'
    if decision.classification == "False positive":
        if divisor_val not in (None, 0):
            comment = (f"At line {line} in {function}(), the divisor `{_divisor}` resolves to {divisor_val} before "
                       f"the operation. The flagged division therefore cannot execute with a zero denominator on this path. "
                       f"False positive.")
        else:
            comment = _build_comment_from_evidence(decision, ctx)
        return "False positive", comment, "No fix required.", decision.confidence

    if decision.classification == "Bug":
        if divisor_val == 0:
            comment = (f"In {function}() at line {line}, the divisor `{_divisor}` resolves concretely to 0 on the flagged "
                       f"path. Executing this division triggers SIGFPE / undefined behavior immediately.")
        else:
            comment = (f"In {function}() at line {line}, division by `{_divisor}` has no visible non-zero guard (CWE-369, CERT INT33-C). "
                       f"If `{_divisor}` is zero, this triggers SIGFPE — denial of service.")
        fix = f"if ({_divisor} == 0) return ERROR; // CWE-369 CERT INT33-C\nresult = dividend / {_divisor};"
        return "Bug", comment, fix, decision.confidence

    comment = _build_comment_from_evidence(decision, ctx)
    return "Needs review", comment, f"if ({_divisor} == 0) return ERROR; // CWE-369", decision.confidence



def _analyze_use_after_free(code: str, sub_checker: str, events: List[Dict],
                         file: str = "", line: int = 0, function: str = "", cid: int = 0,
                         called_function_codes: Optional[Dict[str, str]] = None,
                         code_start_line: int = 1, tree=None) -> Tuple[str, str, str, float]:
    ctx = _build_analysis_context(code, 'USE_AFTER_FREE', events, file, line, function, cid, called_function_codes, code_start_line)
    acc = EvidenceAccumulator()

    _ptr = ctx.get('var') or _extract_var_from_deref(_line_text_at(code, line, code_start_line) or code) or 'ptr'
    try:
        _ml = re.search(r'free\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)', code)
        if _ml:
            _ptr = _ml.group(1)
    except Exception:
        pass
    facts = _use_after_free_facts(code, _ptr, line, code_start_line)

    if facts['null_line'] and facts['guard_line'] and facts['guard_line'] >= facts['null_line'] and        re.search(rf'!\s*{re.escape(_ptr)}|{re.escape(_ptr)}\s*==\s*NULL|{re.escape(_ptr)}\s*!=\s*NULL', facts['guard_cond']):
        acc.add(Evidence(
            label="null_after_free_with_check",
            polarity="fp",
            weight=0.88,
            description=(f"`{_ptr}` is set to NULL at line {facts['null_line']} and checked by `{facts['guard_cond']}` "
                         f"before the flagged use.")
        ))

    if facts['reassign_line'] and facts['reassign_line'] > facts['free_line']:
        acc.add(Evidence(
            label="reassigned_after_free_before_use",
            polarity="fp",
            weight=0.86,
            description=f"`{_ptr}` is reassigned at line {facts['reassign_line']} after free() and before the flagged use."
        ))

    if facts['free_line']:
        acc.add(Evidence(
            label="free_precedes_flagged_use",
            polarity="bug",
            weight=0.82,
            description=f"`free({_ptr})` appears at line {facts['free_line']} before the flagged use at line {line}."
        ))

    if not any(e.polarity == "fp" for e in acc.evidence):
        acc.add(Evidence(
            label="possible_use_after_free",
            polarity="bug",
            weight=0.70,
            description="Pointer may be dereferenced after being freed without subsequent NULL check."
        ))

    decision = DecisionAgent.evaluate(acc, 'USE_AFTER_FREE')

    if decision.classification == "False positive":
        if facts['reassign_line']:
            comment = (f"`{_ptr}` is freed at line {facts['free_line']} but is assigned a new value at line {facts['reassign_line']} "
                       f"before the flagged use at line {line}. The later access therefore targets the replacement object, "
                       f"not freed storage. False positive.")
        else:
            comment = (f"`{_ptr}` is freed at line {facts['free_line']} and then set to NULL at line {facts['null_line']}; "
                       f"the following guard `{facts['guard_cond']}` prevents the flagged path from dereferencing freed storage. "
                       f"False positive.")
        return "False positive", comment, "No fix required.", decision.confidence

    if decision.classification == "Bug":
        comment = (f"At line {line} in {function}(), `{_ptr}` may be dereferenced after being freed (CWE-416, CERT MEM30-C). "
                   f"`free({_ptr})` occurs at line {facts['free_line'] or 'an earlier line'} and no replacement value or effective NULL guard "
                   f"is proven before the later use. That leaves a dangling pointer and the access can corrupt the heap or crash the process.")
        fix = f"free({_ptr}); {_ptr} = NULL;\nif (!{_ptr}) return ERROR; // CWE-416 CERT MEM30-C"
        return "Bug", comment, fix, decision.confidence

    comment = _build_comment_from_evidence(decision, ctx)
    return "Needs review", comment, f"free({_ptr}); {_ptr}=NULL; if(!{_ptr}) return; // CWE-416", decision.confidence



def _analyze_sizeof_mismatch(code: str, sub_checker: str, events: List[Dict],
                         file: str = "", line: int = 0, function: str = "", cid: int = 0,
                         called_function_codes: Optional[Dict[str, str]] = None,
                         code_start_line: int = 1, tree=None) -> Tuple[str, str, str, float]:
    ctx = _build_analysis_context(code, 'SIZEOF_MISMATCH', events, file, line, function, cid, called_function_codes, code_start_line)
    acc = EvidenceAccumulator()

    if _has_pattern(code, r'sizeof\s*\(\s*\*'):
        acc.add(Evidence(
            label="sizeof_deref_safe",
            polarity="fp",
            weight=0.80,
            description="sizeof(*ptr) correctly captures the pointed-to type size — recommended idiom."
        ))

    if _has_pattern(code, r'sizeof\s*\(\s*\w+\s*\[0\]\s*\)'):
        acc.add(Evidence(
            label="sizeof_element_safe",
            polarity="fp",
            weight=0.75,
            description="sizeof(arr[0]) computes element size safely independent of actual type."
        ))

    if not any(e.polarity == "fp" for e in acc.evidence):
        acc.add(Evidence(
            label="sizeof_wrong_type",
            polarity="bug",
            weight=0.70,
            description="sizeof() may be applied to the wrong type (pointer vs element)."
        ))

    decision = DecisionAgent.evaluate(acc, 'SIZEOF_MISMATCH')

    if decision.classification == "False positive":
        comment = _build_comment_from_evidence(decision, ctx)
        comment = _apply_example_style("False positive", 'SIZEOF_MISMATCH', ctx,
                                       code, code_start_line, line, function, comment)
        return "False positive", comment, "No fix required.", decision.confidence

    _var = ctx.get('var') or 'ptr'
    try:
        _ml2 = __import__('re').search(r'sizeof\s*\(\s*([A-Za-z_][A-Za-z0-9_\*\s]+)\s*\)', code)
        if _ml2:
            _var = _ml2.group(1).strip().replace('*','').split()[-1]
    except Exception:
        pass
    if decision.classification == "Bug":
        comment = (f"In {function}() at line {line}, sizeof({_var}) is applied to the pointer type not the pointee (CWE-467, CERT ARR01-C). "
                   f"On 64-bit, pointer is 8 bytes vs object size — under-allocation → heap overflow.")
        comment = _apply_example_style("Bug", 'SIZEOF_MISMATCH', ctx,
                                       code, code_start_line, line, function, comment)
        fix = f"malloc(count * sizeof(*{_var})); // CWE-467 CERT ARR01-C — not sizeof({_var})"
        return "Bug", comment, fix, decision.confidence

    comment = _build_comment_from_evidence(decision, ctx)
    return "Needs review", comment, f"sizeof(*{_var}) // CWE-467", decision.confidence


def _analyze_constant_expression(code: str, sub_checker: str, events: List[Dict],
                         file: str = "", line: int = 0, function: str = "", cid: int = 0,
                         called_function_codes: Optional[Dict[str, str]] = None,
                         code_start_line: int = 1, tree=None) -> Tuple[str, str, str, float]:
    ctx = _build_analysis_context(code, 'CONSTANT_EXPRESSION_RESULT', events, file, line, function, cid, called_function_codes, code_start_line)
    acc = EvidenceAccumulator()

    if re.search(r'\bassert\s*\(|\bstatic_assert\s*\(', code):
        acc.add(Evidence(
            label="assert_or_static_assert",
            polarity="fp",
            weight=0.80,
            description="Constant expression inside assert() or static_assert() — intentional validation."
        ))

    if '#if' in code or '#ifdef' in code:
        acc.add(Evidence(
            label="preprocessor_conditional",
            polarity="fp",
            weight=0.65,
            description="Constant expression in preprocessor conditional — configuration logic."
        ))

    if not any(e.polarity == "fp" for e in acc.evidence):
        acc.add(Evidence(
            label="suspicious_constant_expression",
            polarity="bug",
            weight=0.55,
            description="Expression evaluates to constant — may indicate dead logic or missing variable."
        ))

    decision = DecisionAgent.evaluate(acc, 'CONSTANT_EXPRESSION_RESULT')

    if decision.classification == "False positive" or decision.classification == "Intentional":
        comment = _build_comment_from_evidence(decision, ctx)
        return "Intentional", comment, "No fix required.", decision.confidence

    if decision.classification == "Bug":
        comment = (f"At line {line} in {function}(), an expression evaluates to a constant result. "
                   f"This may indicate dead logic, a typo, or a missing variable.")
        fix = "Verify the expression was not meant to use a variable. If intentional, add a comment explaining why the constant is correct."
        return "Bug", comment, fix, decision.confidence

    comment = _build_comment_from_evidence(decision, ctx)
    return "Needs review", comment, "Verify if the constant expression is intentional or indicates missing logic.", decision.confidence


def _analyze_shift_overflow(code: str, sub_checker: str, events: List[Dict],
                         file: str = "", line: int = 0, function: str = "", cid: int = 0,
                         called_function_codes: Optional[Dict[str, str]] = None,
                         code_start_line: int = 1, tree=None) -> Tuple[str, str, str, float]:
    ctx = _build_analysis_context(code, 'SHIFT_OVERFLOW', events, file, line, function, cid, called_function_codes, code_start_line)
    acc = EvidenceAccumulator()
    resolution_sources = _gather_resolution_sources(
        code, file, called_function_codes, ctx.get('callers_list', []))
    defect_line_code = _line_text_at(code, line, code_start_line)
    op_info = _extract_binary_operation(defect_line_code or code, ('<<', '>>'))
    value_expr = shift_expr = shift_var = ''
    shift_val = None
    bit_width = 32
    if op_info:
        value_expr, op_token, shift_expr = op_info
        shift_val = _resolve_expr_value_before_line(code, shift_expr, line, code_start_line, resolution_sources)
        vm = re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', shift_expr)
        shift_var = vm.group(0) if vm else ''
        base_name_m = re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value_expr)
        if base_name_m:
            decl = _infer_integral_decl_bounds(base_name_m.group(0), resolution_sources)
            bit_width = decl.get('bits', 32)
            ctx['integer_type'] = decl.get('type_text') or 'int'
        else:
            ctx['integer_type'] = 'int'
        ctx['shift_operator'] = op_token
    else:
        ctx['integer_type'] = 'int'

    if _has_pattern(code, r'if\s*\(.*<\s*\d+|if\s*\(.*>=\s*\d+'):
        acc.add(Evidence(
            label="shift_amount_validated",
            polarity="fp",
            weight=0.80,
            description="Shift amount is validated against the operand bit-width before shifting."
        ))

    if shift_var:
        flow = _extract_index_flow(code, shift_var, line, code_start_line)
        limit_val = _resolve_integer_constant(flow.get('guard_limit', ''), resolution_sources) if flow.get('guard_limit') else None
        if limit_val is not None and flow.get('guard_op') in ('<', '<='):
            max_shift = limit_val - 1 if flow['guard_op'] == '<' else limit_val
            if max_shift < bit_width:
                acc.add(Evidence(
                    label="guard_keeps_shift_in_range",
                    polarity="fp",
                    weight=0.90,
                    description=(f"Guard `{flow['guard_cond']}` keeps `{shift_var}` below the {bit_width}-bit width of the shifted value.")
                ))

    if shift_val is not None:
        ctx['shift_value'] = shift_val
        ctx['shift_bits'] = bit_width
        if 0 <= shift_val < bit_width:
            acc.add(Evidence(
                label="concrete_shift_in_range",
                polarity="fp",
                weight=0.93,
                description=f"Shift amount {shift_val} is within the {bit_width}-bit width of the operand."
            ))
        else:
            acc.add(Evidence(
                label="concrete_shift_out_of_range",
                polarity="bug",
                weight=0.96,
                description=f"Shift amount {shift_val} is outside the valid range [0, {bit_width - 1}]."
            ))

    if not any(e.polarity == "fp" for e in acc.evidence):
        acc.add(Evidence(
            label="shift_without_guard",
            polarity="bug",
            weight=0.70,
            description="Shift operation has no guard against shift amount >= bit-width."
        ))

    decision = DecisionAgent.evaluate(acc, 'SHIFT_OVERFLOW')

    if decision.classification == "False positive":
        if shift_val is not None and 0 <= shift_val < bit_width:
            comment = (f"At line {line} in {function}(), the shift amount resolves to {shift_val}. That is inside the valid "
                       f"range [0, {bit_width - 1}] for `{ctx['integer_type']}`, so the flagged shift is defined on this path. "
                       f"False positive.")
        else:
            comment = _build_comment_from_evidence(decision, ctx)
        return "False positive", comment, "No fix required.", decision.confidence

    if decision.classification == "Bug":
        if shift_val is not None and shift_val >= bit_width:
            comment = (f"In {function}() at line {line}, the shift amount resolves to {shift_val}, but `{ctx['integer_type']}` is only "
                       f"{bit_width} bits wide. Shifting by {shift_val} is out of range and therefore undefined behavior in C.")
        else:
            comment = (f"In {function}() at line {line}, a shift operation has no guard against shift amount >= bit-width. "
                       f"In C, shifting by >= width is undefined behavior.")
        shift_ref = shift_var or shift_expr or 'shift'
        value_ref = value_expr or 'value'
        fix = f"if ({shift_ref} >= sizeof({value_ref})*8) return;\nresult = {value_ref} {ctx.get('shift_operator', '<<')} {shift_ref};"
        return "Bug", comment, fix, decision.confidence

    comment = _build_comment_from_evidence(decision, ctx)
    return "Needs review", comment, "Add explicit shift amount validation before all shift operations.", decision.confidence



def _analyze_missing_break(code: str, sub_checker: str, events: List[Dict],
                         file: str = "", line: int = 0, function: str = "", cid: int = 0,
                         called_function_codes: Optional[Dict[str, str]] = None,
                         code_start_line: int = 1, tree=None) -> Tuple[str, str, str, float]:
    ctx = _build_analysis_context(code, 'NO_BREAK', events, file, line, function, cid, called_function_codes, code_start_line)
    acc = EvidenceAccumulator()

    if re.search(r'//\s*fallthrough|/\*\s*fall.?through|FALLTHRU|FALLTHROUGH|\[\[fallthrough\]\]', code, re.I):
        acc.add(Evidence(
            label="documented_fallthrough",
            polarity="fp",
            weight=0.90,
            description="Switch case fall-through is explicitly documented."
        ))

    if not any(e.polarity == "fp" for e in acc.evidence):
        acc.add(Evidence(
            label="missing_break_statement",
            polarity="bug",
            weight=0.65,
            description="Switch case ends without break — control falls through to next case unintentionally."
        ))

    decision = DecisionAgent.evaluate(acc, 'NO_BREAK')

    if decision.classification == "False positive" or decision.classification == "Intentional":
        comment = _build_comment_from_evidence(decision, ctx)
        return "Intentional", comment, "No fix required.", decision.confidence

    if decision.classification == "Bug":
        comment = (f"In {function}() at line {line}, a switch case ends without a break, causing control to fall through to the next case. "
                   f"Unless this is intentional, it will execute unintended code.")
        fix = "Add break; at end of case if fall-through is unintended. If intentional, add /* fallthrough */ comment for clarity."
        return "Bug", comment, fix, decision.confidence

    comment = _build_comment_from_evidence(decision, ctx)
    return "Needs review", comment, "Verify if fall-through is intentional. If not, add break; statement.", decision.confidence


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def _generic_evidence_classify(checker: str, events: List[Dict], context: Dict,
                               file: str = "", line: int = 0, function: str = "",
                               cid: int = 0, no_code: bool = False,
                               analyzer_error: str = "") -> Tuple[str, str, str, float]:
    """Fallback classifier driven by the Coverity event trace (+ any code).

    Used when (a) there is no source code/context, or (b) the specialized
    _analyze_* handler for a checker raised an exception. Produces a reasoned
    verdict without requiring a dedicated checker function, and is safe when
    events are empty (e.g. Excel input).
    """
    events = events or []
    try:
        code = (context.get('function_code', '') or context.get('source_code', '')
                or context.get('code', '')) or ''
        if not events and not code:
            return ("Needs review",
                    f"No source code and no Coverity event trace were available for this "
                    f"{checker} finding in {function or 'unknown'}() at line {line}. "
                    f"A specific classification cannot be made reliably. Manual review required.",
                    "Manual review required to determine classification and remediation.", 0.0)

        ev = parse_coverity_events(events)
        ctx = {
            'code': code,
            'function_code': code,
            'source_code': code,
            'checker': checker,
            'file': file,
            'line': line,
            'function': function or '',
            'cid': cid,
            'ev': ev,
            'tree': context.get('function_tree'),
        }
        acc = build_evidence(ctx, ev, checker)
        decision = DecisionAgent.evaluate(acc, checker)

        classification = decision.classification
        confidence = float(decision.confidence)
        reasoning = (" ".join(decision.reasoning) if decision.reasoning
                     else "Insufficient evidence.")

        err_note = ""
        if analyzer_error:
            err_note = f" [specialized analyzer raised: {analyzer_error}]"

        where = (f" in {function}()" if function else "")
        loc = (f" at line {line}" if line else "")
        loc_s = f"{checker} finding{loc}{where}"

        if classification == "Bug":
            # Try to produce code-like fix with actual var if available
            _gv = ctx.get('var') or ctx.get('dest_var') or 'var'
            comment = (f"The {loc_s} is classified as a Bug. {reasoning}{err_note}")
            fix = f"Fix at {loc_s}: validate {_gv} before use // {checker} CWE"
        elif classification == "False positive":
            comment = (f"The {loc_s} is a false positive. {reasoning}{err_note}")
            fix = "No fix required."
        elif classification == "Intentional":
            comment = (f"The {loc_s} is intentional / by design. {reasoning}{err_note}")
            fix = "No fix required; consider documenting or suppressing if appropriate."
        else:
            comment = (f"The {loc_s} requires manual review. {reasoning}{err_note}")
            fix = "Manual review required to determine classification and remediation."
        code_start_line = context.get('code_start_line', 1)
        comment = _apply_example_style(classification, checker, ctx, code,
                                       code_start_line, line, function, comment)
        return classification, comment, fix, confidence
    except Exception:
        return ("Needs review",
                f"The {checker} finding could not be classified automatically (generic "
                f"fallback failed). Please review manually."
                + (f" [specialized analyzer raised: {analyzer_error}]" if analyzer_error else ""),
                "Manual review required to determine classification and remediation.", 0.0)



def analyze_defect(context: Dict, checker: str, events: List[Dict],
                   sub_checker: str = "", line_is_various: bool = False,
                   file: str = "", line: int = 0, function: str = "", cid: int = 0,
                   tree=None) -> Tuple[str, str, str, float]:
    """
    Returns: (classification, comment_paragraph, proposed_fix, confidence)
    """
    code = context.get('function_code', '') or context.get('source_code', '')
    called_function_codes: Dict[str, str] = dict(context.get('called_function_codes', {}))
    callers = context.get('callers', [])
    called_function_codes['__callers__'] = callers
    code_start_line = context.get('code_start_line', 1)   # <-- ADD THIS

    notes = []
    if line_is_various:
        notes.append("[Line 'Various'] Coverity could not pinpoint a single line; the "
                     "defect may span multiple lines or involve macros. Function or "
                     "whole-file context was used for this assessment.")

    # Retry harder before giving up on missing code: fall back to caller/callee
    # context snippets that were already extracted for cross-function analysis.
    used_fallback_code = False
    if not code:
        fallback_parts = []
        for name, fcode in called_function_codes.items():
            if name == '__callers__':
                continue
            if isinstance(fcode, str) and fcode.strip():
                fallback_parts.append(fcode)
        for c in callers:
            if isinstance(c, str) and c.strip():
                fallback_parts.append(c)
            elif isinstance(c, dict) and c.get('code'):
                fallback_parts.append(c['code'])
        if fallback_parts:
            code = "\n\n".join(fallback_parts)
            used_fallback_code = True
            notes.append("[Context] Primary function body was unavailable; assessment used "
                         "caller/callee context snippets.")

    dispatch = {
        'BUFFER_SIZE':        _analyze_buffer_size,
        'OVERRUN':            _analyze_overrun,
        'OVERRUN_STATIC':     _analyze_overrun,
        'OVERRUN_DYNAMIC':    _analyze_overrun,
        'INTEGER_OVERFLOW':   _analyze_integer_overflow,
        'STRING_NULL':        _analyze_string_null,
        'REVERSE_INULL':      _analyze_reverse_inull,
        'FORWARD_NULL':       _analyze_forward_null,
        'ARRAY_VS_SINGLETON': _analyze_array_vs_singleton,
        'NEGATIVE_RETURNS':   _analyze_negative_returns,
        'RESOURCE_LEAK':      _analyze_resource_leak,
        'DEADCODE':           _analyze_deadcode,
        'UNUSED_VALUE':       _analyze_unused_value,
        'UNINIT':             _analyze_uninitialized,
        'DIVIDE_BY_ZERO':     _analyze_divide_by_zero,
        'USE_AFTER_FREE':     _analyze_use_after_free,
        'SIZEOF_MISMATCH':    _analyze_sizeof_mismatch,
        'CONSTANT_EXPRESSION_RESULT': _analyze_constant_expression,
        'NO_BREAK':           _analyze_missing_break,
        'SHIFT_OVERFLOW':     _analyze_shift_overflow,
        'CHECKED_RETURN':     _analyze_checked_return,
        'CHECKED_QRS':        _analyze_checked_return,
    }

    def _finish(classification, comment, fix, confidence):
        # Annotate the comment with uncertainty notes, and cap confidence when the
        # assessment had to rely on fallback code or an approximate line.
        if used_fallback_code:
            confidence = min(float(confidence), 0.60)
        if line_is_various:
            confidence = min(float(confidence), 0.70)
        if notes:
            comment = (comment + "\n\n" + " ".join(notes)).strip()
        # A "Needs review" verdict means the tool could not prove a code-specific
        # remediation. Do not present a placeholder guard as if it were a valid
        # patch; keep the analysis open and explain why.
        if classification == 'Needs review' and str(fix or '').strip().lower() != 'no fix required.':
            fix = 'Manual review required.'
        # A fix must be a source-anchored patch, not generic secure-coding
        # advice.  Withhold templates that cannot be validated against this
        # function and explain the missing proof in the analysis instead.
        fix, withheld_reason = _gate_fix_on_source_evidence(
            fix, code, line, code_start_line, checker)
        if withheld_reason:
            comment = comment.rstrip() + "\n\n" + withheld_reason
        comment = _append_cwe_footer(comment, checker)
        fix = _expert_fix_suggestion(checker, context, fix)
        return classification, comment, fix, confidence

    if not code:
        # No code and no context at all -> attempt the event-trace based generic
        # classifier before falling back to an honest Needs review.
        return _finish(*_generic_evidence_classify(
            checker, events, context, file=file, line=line,
            function=function, cid=cid, no_code=True))

    fn = dispatch.get(checker)
    if fn:
        try:
            classification, comment, fix, confidence = fn(
                code, sub_checker, events,
                file=file, line=line, function=function, cid=cid,
                called_function_codes=called_function_codes,
                code_start_line=code_start_line,
                tree=tree,
            )
        except Exception as exc:
            # Specialized analyzer raised -> fall back to the generic evidence
            # classifier so the whole defect does not collapse to Needs review.
            classification, comment, fix, confidence = _generic_evidence_classify(
                checker, events, context, file=file, line=line,
                function=function, cid=cid, analyzer_error=str(exc))
        return _finish(classification, comment, fix, confidence)

    # Checker has no dedicated handler -> use the generic event-trace based
    # classifier so unhandled checkers still get a reasoned verdict instead of
    # always collapsing to Needs review.
    return _finish(*_generic_evidence_classify(
        checker, events, context, file=file, line=line,
        function=function, cid=cid))