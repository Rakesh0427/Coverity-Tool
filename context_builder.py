"""Build rich context for a defect: called functions, callers, globals."""
import os
import re
from typing import Dict, List, Tuple
from code_extractor import extract_enclosing_function, _read_file
from workspace_indexer import build_symbol_index, get_function_code, get_function_entry

_CALLER_CACHE: Dict[Tuple, List[Dict]] = {}

# C stdlib / common functions whose source we don't need to fetch
_SKIP_CALLEES = frozenset({
    'if', 'for', 'while', 'switch', 'return', 'sizeof', 'printf', 'fprintf',
    'sprintf', 'snprintf', 'scanf', 'malloc', 'calloc', 'realloc', 'free',
    'memcpy', 'memset', 'memmove', 'strlen', 'strcpy', 'strncpy', 'strcat',
    'strncat', 'strcmp', 'strncmp', 'strchr', 'strstr', 'fopen', 'fclose',
    'fread', 'fwrite', 'fgets', 'fputs', 'recv', 'send', 'open', 'close',
    'read', 'write', 'exit', 'abort', 'assert', 'getenv', 'atoi', 'atol',
})


def _find_callers(function_name: str, src_root: str) -> List[Dict]:
    """Return list of {file, line, caller_function} dicts for sites that call function_name."""
    cache_key = (function_name, src_root)
    if cache_key in _CALLER_CACHE:
        return _CALLER_CACHE[cache_key]
    callers = []
    pat = re.compile(r'\b' + re.escape(function_name) + r'\s*\(')
    for root, _dirs, files in os.walk(src_root):
        for f in files:
            if not f.endswith(('.c', '.cpp', '.h', '.hpp', '.C', '.cxx')):
                continue
            full_path = os.path.join(root, f)
            try:
                content = _read_file(full_path)
                if not content or function_name not in content:
                    continue
                for i, src_line in enumerate(content.splitlines(), 1):
                    if pat.search(src_line):
                        # Try to extract enclosing function name from prior lines
                        caller_fn = _guess_enclosing_function(content, i)
                        callers.append({
                            'file':     full_path,
                            'line':     i,
                            'caller':   caller_fn,
                            'snippet':  src_line.strip()[:100],
                        })
            except Exception:
                pass
    _CALLER_CACHE[cache_key] = callers
    return callers


def _guess_enclosing_function(source: str, call_line: int) -> str:
    """Walk backwards from call_line to find the most recent function signature."""
    lines = source.splitlines()
    for i in range(min(call_line - 1, len(lines) - 1), -1, -1):
        m = re.match(r'^[\w\s\*]+\b(\w+)\s*\([^;]*\)\s*\{?\s*$', lines[i])
        if m and m.group(1) not in _SKIP_CALLEES:
            return m.group(1)
    return ''


def _extract_func_name_from_code(func_code: str) -> str:
    """Extract the function name from the first meaningful line of extracted code."""
    for line_text in func_code.splitlines():
        stripped = line_text.strip()
        if not stripped or stripped.startswith(('#', '//', '/*', '*')):
            continue
        m = re.match(r'[\w\s\*]+\b(\w+)\s*\(', stripped)
        if m:
            return m.group(1)
    return ''


def build_defect_context(defect: Dict, src_root: str, language: str = 'c') -> Dict:
    if not defect.get('events'):
        return {
            'function_code': '', 'called_functions': [], 'callers': [],
            'global_vars': [], 'called_function_codes': {}, 'callee_signatures': {},
        }

    first_event = defect['events'][0]
    filepath = first_event.get('file', '')
    line     = first_event.get('line', 0)

    if filepath and not os.path.isabs(filepath):
        filepath = os.path.join(src_root, filepath)

    func_code = ''
    func_tree = None
    code_start_line = 1
    if filepath and os.path.exists(filepath):
        result = extract_enclosing_function(filepath, line, language)
        if isinstance(result, tuple):
            if len(result) >= 3:
                func_code, code_start_line, func_tree = result
            elif len(result) == 2:
                func_code, code_start_line = result
            else:
                func_code = result
        else:
            func_code = result

    # Collect all function calls in the defect function
    called: set = set()
    if func_code:
        for m in re.finditer(r'\b(\w+)\s*\(', func_code):
            name = m.group(1)
            if name not in _SKIP_CALLEES:
                called.add(name)

    # Build workspace symbol index and fetch callee source (top 5 by first appearance)
    called_function_codes: Dict[str, str] = {}
    callee_signatures:     Dict[str, str] = {}
    if called and os.path.isdir(src_root):
        index = build_symbol_index(src_root, language)
        # Sort callees by order they appear in the function code for relevance
        ordered = sorted(called, key=lambda n: func_code.find(n + '(') if func_code else 0)
        for name in ordered[:5]:
            code = get_function_code(name, index)
            if code:
                called_function_codes[name] = code
                entry = get_function_entry(name, index)
                callee_signatures[name] = entry.signature if entry else ''

    func_name = _extract_func_name_from_code(func_code) if func_code else ''
    callers   = _find_callers(func_name, src_root) if func_name else []

    return {
        'function_code':        func_code,
        'function_tree':        func_tree,
        'code_start_line':      code_start_line,
        'called_functions':     list(called),
        'called_function_codes': called_function_codes,
        'callee_signatures':    callee_signatures,
        'callers':              callers,
        'global_vars':          [],
    }