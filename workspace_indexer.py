"""
Workspace-wide symbol index using tree-sitter.
Builds a function-name → (filepath, start_line, end_line, signature) map
by scanning all C/C++ source files under a root directory.
"""
import os
import re
from typing import Dict, List, NamedTuple, Optional

# Reuse the already-configured parser from code_extractor
from code_extractor import _get_parser, _read_file

_INDEX_CACHE: Dict[str, Dict] = {}  # src_root → symbol index


class FunctionEntry(NamedTuple):
    filepath:   str
    start_line: int
    end_line:   int
    signature:  str   # first non-blank line of the function


_CONTROL_KEYWORDS = frozenset({
    'if', 'while', 'for', 'switch', 'catch', 'return', 'sizeof', 'sizeof...',
    'define', 'include', 'typedef', 'struct', 'union', 'enum', 'case', 'default',
})

_FUNC_PAT = re.compile(
    r'^(?:[A-Za-z_][A-Za-z0-9_\s\*:<>,~]*[\s\*])?([A-Za-z_]\w*)\s*\([^;]*\)\s*\{?'
)


def _extract_signature(source: str, start_byte: int, end_byte: int) -> str:
    snippet = source[start_byte:start_byte + 200]
    for line in snippet.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(('//', '/*', '*')):
            return stripped[:120]
    return ''


def _scan_file(filepath: str, language: str) -> Dict[str, List[FunctionEntry]]:
    source = _read_file(filepath)
    if not source:
        return {}

    # Fast line scan first (avoids expensive full-AST tree-sitter parse for entire workspace)
    lines = source.splitlines()
    result: Dict[str, List[FunctionEntry]] = {}
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i].strip()
        if not line or line.startswith(('#', '//', '/*', '*')):
            i += 1
            continue
        m = _FUNC_PAT.match(line)
        if m and m.group(1) not in _CONTROL_KEYWORDS:
            name = m.group(1)
            start_line = i + 1
            sig = line[:120]
            has_brace = '{' in line
            k = i
            while not has_brace and k < min(n - 1, i + 4):
                k += 1
                if '{' in lines[k]:
                    has_brace = True
                    break
                if ';' in lines[k]:
                    break
            if has_brace:
                depth = 0
                end_line = min(n, start_line + 50)
                for j in range(k, n):
                    depth += lines[j].count('{') - lines[j].count('}')
                    if depth <= 0 and j >= k:
                        end_line = j + 1
                        i = j
                        break
                entry = FunctionEntry(filepath, start_line, end_line, sig)
                result.setdefault(name, []).append(entry)
        i += 1

    if result:
        return result

    # Fallback to tree-sitter AST parse if regex found nothing
    try:
        parser = _get_parser(language)
        tree = parser.parse(bytes(source, 'utf-8'))
        def _walk(node):
            if node.type in ('function_definition', 'method_definition'):
                name = _get_func_name(node)
                if name:
                    start = node.start_point[0] + 1   # tree-sitter rows are 0-indexed
                    end   = node.end_point[0] + 1
                    sig   = _extract_signature(source, node.start_byte, node.end_byte)
                    entry = FunctionEntry(filepath, start, end, sig)
                    result.setdefault(name, []).append(entry)
            for child in node.children:
                _walk(child)
        _walk(tree.root_node)
    except Exception:
        pass

    return result


def _get_func_name(node) -> Optional[str]:
    """Extract identifier from a function_definition node."""
    def _find_id(n):
        if n.type == 'identifier':
            return n.text.decode('utf-8') if isinstance(n.text, bytes) else n.text
        for c in n.children:
            r = _find_id(c)
            if r:
                return r
        return None

    for child in node.children:
        if child.type in ('function_declarator', 'pointer_declarator',
                          'init_declarator', 'declarator'):
            name = _find_id(child)
            if name:
                return name
    return None


def build_symbol_index(src_root: str, language: str = 'c') -> Dict[str, List[FunctionEntry]]:
    """
    Scan all C/C++ files under src_root and return a combined function index.
    Results are cached per src_root+language. Skips files >500KB and handles
    parse errors gracefully to avoid stalls on large/generated files.
    """
    cache_key = f"{src_root}::{language}"
    if cache_key in _INDEX_CACHE:
        return _INDEX_CACHE[cache_key]

    combined: Dict[str, List[FunctionEntry]] = {}
    lang_key = language.lower()
    extensions = ('.c', '.h', '.cpp', '.hpp', '.cxx', '.cc', '.C')
    skipped_large = 0

    for root, _dirs, files in os.walk(src_root):
        # Skip common build/output dirs that bloat indexing
        _dirs[:] = [d for d in _dirs if d not in ('.git', '.hg', '.svn', '__pycache__', 'build', 'out', 'target', 'node_modules', '.venv', 'venv', 'dist')]
        for fname in files:
            if not fname.endswith(extensions):
                continue
            full = os.path.join(root, fname)
            # Skip very large files (generated)
            try:
                if os.path.getsize(full) > 500_000:
                    skipped_large += 1
                    continue
            except Exception:
                pass
            file_lang = 'cpp' if fname.endswith(('.cpp', '.hpp', '.cxx', '.cc')) else lang_key
            try:
                entries = _scan_file(full, file_lang)
            except Exception:
                continue
            for name, items in entries.items():
                combined.setdefault(name, []).extend(items)

    _INDEX_CACHE[cache_key] = combined
    return combined


def get_function_code(func_name: str, index: Dict[str, List[FunctionEntry]]) -> Optional[str]:
    """Return source code of func_name using the pre-built index, or None."""
    entries = index.get(func_name)
    if not entries:
        return None
    entry = entries[0]
    source = _read_file(entry.filepath)
    if not source:
        return None
    lines = source.splitlines()
    # Lines are 1-indexed; clamp to valid range
    start = max(0, entry.start_line - 1)
    end   = min(len(lines), entry.end_line)
    return '\n'.join(lines[start:end])


def get_function_entry(func_name: str, index: Dict[str, List[FunctionEntry]]) -> Optional[FunctionEntry]:
    """Return the first FunctionEntry for func_name, or None."""
    entries = index.get(func_name)
    return entries[0] if entries else None


def invalidate_cache(src_root: Optional[str] = None):
    """Clear the index cache (e.g., after source files are modified)."""
    if src_root:
        keys = [k for k in _INDEX_CACHE if k.startswith(src_root)]
        for k in keys:
            del _INDEX_CACHE[k]
    else:
        _INDEX_CACHE.clear()
