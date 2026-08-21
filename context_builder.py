"""Build rich context for a defect: called functions, callers, globals."""
import os
import re
from typing import Dict, List, Tuple
from code_extractor import extract_enclosing_function, find_function_line_by_name, _read_file
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


_CALLSITE_CACHE: Dict[str, Tuple[List[str], Dict[str, List[Tuple[int, int]]]]] = {}
# src_root -> (paths: normalized file paths, index: {func_name: [(path_id, line), ...]})


def _build_callsite_index(src_root: str) -> Tuple[List[str], Dict[str, List[Tuple[int, int]]]]:
    """Scan the workspace once and index every call site by callee name.

    Returns (paths, index) where `paths` is the list of normalized file paths and
    `index[func]` holds (path_id, line) tuples. Building this once per src_root
    replaces the old per-defect full-tree walk, which was the main cause of the
    tool appearing stuck on large reports. Skips build/output dirs and large files.
    """
    cached = _CALLSITE_CACHE.get(src_root)
    if cached is not None:
        return cached
    paths: List[str] = []
    pid_of: Dict[str, int] = {}
    index: Dict[str, List[Tuple[int, int]]] = {}
    pat = re.compile(r'\b([A-Za-z_]\w*)\s*\(')
    for root, _dirs, files in os.walk(src_root):
        # Skip build/output/VC dirs that bloat scanning
        _dirs[:] = [d for d in _dirs if d not in ('.git', '.hg', '.svn', '__pycache__', 'build', 'out', 'target', 'node_modules', '.venv', 'venv', 'dist', '.idea', '.vscode')]
        for f in files:
            if not f.endswith(('.c', '.cpp', '.h', '.hpp', '.C', '.cxx')):
                continue
            full = os.path.normpath(os.path.join(root, f))
            # Skip very large files
            try:
                if os.path.getsize(full) > 500_000:
                    continue
            except Exception:
                pass
            try:
                content = _read_file(full)
            except Exception:
                continue
            if not content:
                continue
            pid = pid_of.get(full)
            if pid is None:
                pid = len(paths)
                pid_of[full] = pid
                paths.append(full)
            for i, src_line in enumerate(content.splitlines(), 1):
                for m in pat.finditer(src_line):
                    name = m.group(1)
                    if name not in _SKIP_CALLEES:
                        index.setdefault(name, []).append((pid, i))
    cached = (paths, index)
    _CALLSITE_CACHE[src_root] = cached
    return cached


def _extract_enclosing_body(content: str, call_line: int) -> Tuple[str, int, int]:
    """Find the function whose body contains the 1-based `call_line`.

    Returns (func_name, start_line, end_line) or ('', 0, 0). Uses a backward
    signature scan plus forward brace counting, so it does not need the
    (expensive) tree-sitter symbol index.
    """
    lines = content.splitlines()
    if call_line < 1 or call_line > len(lines):
        return ('', 0, 0)
    for i in range(min(call_line - 1, len(lines) - 1), -1, -1):
        s = lines[i].strip()
        if not s or s.startswith(('#', '//', '/*', '*')):
            continue
        m = re.match(r'^[\w\s\*]+\b(\w+)\s*\([^;]*\)\s*\{?', s)
        if m and m.group(1) not in _SKIP_CALLEES:
            name = m.group(1)
            start = i + 1
            depth = 0
            for j in range(i, len(lines)):
                depth += lines[j].count('{') - lines[j].count('}')
                if depth <= 0 and j > i:
                    return (name, start, j + 1)
            return (name, start, min(len(lines), call_line + 25))
    return ('', 0, 0)


def _find_callers(function_name: str, src_root: str) -> List[Dict]:
    """Return list of {file, line, caller_function, code, start_line} dicts for
    sites that call function_name.

    Uses the cached workspace call-site index (built once per src_root) and
    slices each caller's body straight from the already-read file content, so a
    defect function is resolved in O(call sites) instead of O(whole workspace).
    """
    cache_key = (function_name, src_root)
    if cache_key in _CALLER_CACHE:
        return _CALLER_CACHE[cache_key]

    paths, callsite_index = _build_callsite_index(src_root)
    sites = callsite_index.get(function_name, [])
    # Cap pathological fan-outs (a function invoked thousands of times); the
    # typical number of real call sites is far below this.
    if len(sites) > 500:
        sites = sites[:500]

    # Group call sites by file so each file is read only once.
    by_file: Dict[str, List[int]] = {}
    for pid, cline in sites:
        by_file.setdefault(paths[pid], []).append(cline)

    callers = []
    for path, clines in by_file.items():
        try:
            content = _read_file(path)
        except Exception:
            content = ''
        if not content:
            continue
        lines = content.splitlines()
        for cline in clines:
            caller_fn, start_line, end_line = _extract_enclosing_body(content, cline)
            body = ''
            if start_line > 0 and end_line >= start_line:
                body = '\n'.join(lines[start_line - 1:end_line])[:12000]
            snippet = lines[cline - 1].strip()[:100] if 0 < cline <= len(lines) else ''
            callers.append({
                'file':        path,
                'line':        cline,
                'caller':      caller_fn,
                'snippet':     snippet,
                'code':        body,
                'start_line':  start_line or 1,
            })
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


def warm_workspace_index(src_root: str, language: str = 'c') -> bool:
    """Pre-build the cached workspace call-site index up front.

    Building this lazily on the first defect makes that one defect block with no
    progress and inflates the per-defect ETA. Calling it once at the start of an
    analysis (with a visible status message) moves the one-time cost out of the
    defect loop.

    IMPORTANT: this intentionally does NOT pre-build the tree-sitter symbol
    index (`build_symbol_index`), which parses every file and is very expensive
    on large trees. The symbol index stays lazy and cached, so it is only built
    once, and only when a defect function actually calls an in-tree callee.
    Per-file function extraction re-parsing is separately cached in
    code_extractor, so defects in the same file don't re-parse.
    """
    if not src_root or not os.path.isdir(src_root):
        return False
    try:
        _build_callsite_index(src_root)
        return True
    except Exception:
        return False


def build_defect_context(defect: Dict, src_root: str, language: str = 'c') -> Dict:
    if not defect.get('events'):
        return {
            'function_code': '', 'called_functions': [], 'callers': [],
            'global_vars': [], 'called_function_codes': {}, 'callee_signatures': {},
        }

    events = defect.get('events') or []
    # Prefer the defect-level file/function/line over the first path event:
    # first_event may point into a called function (interprocedural trace) or
    # at the taint source (e.g. var_decl / string_null_source), not the defect
    # site. When only events are available, resolve the *main* (sink) event.
    filepath  = defect.get('file') or ''
    func_name = defect.get('function', '')
    line      = defect.get('line') or 0
    if not line or not filepath:
        try:
            from coverity_events import line_source_from_events
            ev_line, _ = line_source_from_events(events, defect.get('checker', ''))
            if not line and ev_line:
                line = ev_line
            if not filepath:
                mains = [e for e in events if e.get('main') and e.get('file')]
                if mains:
                    filepath = max(mains, key=lambda e: e.get('step', 0)).get('file', '')
                elif events:
                    filepath = events[0].get('file', '')
        except Exception:
            pass

    if filepath and not os.path.isabs(filepath):
        filepath = os.path.join(src_root, filepath)

    func_code = ''
    func_tree = None
    code_start_line = 1
    if filepath and os.path.exists(filepath):
        # Resolve the precise function start from the AST when the name is known.
        extract_line = line
        if func_name:
            name_line = find_function_line_by_name(filepath, func_name, language)
            if name_line > 0:
                extract_line = name_line
        result = extract_enclosing_function(filepath, extract_line, language)
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

    # Build the workspace symbol index only when callee source is actually
    # needed (the defect function makes calls), then fetch callee source.
    symbol_index = build_symbol_index(src_root, language) \
        if (called and os.path.isdir(src_root)) else {}

    # Fetch callee source (top 5 by first appearance)
    called_function_codes: Dict[str, str] = {}
    callee_signatures:     Dict[str, str] = {}
    if called and symbol_index:
        # Sort callees by order they appear in the function code for relevance
        ordered = sorted(called, key=lambda n: func_code.find(n + '(') if func_code else 0)
        for name in ordered[:5]:
            code = get_function_code(name, symbol_index)
            if code:
                called_function_codes[name] = code
                entry = get_function_entry(name, symbol_index)
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