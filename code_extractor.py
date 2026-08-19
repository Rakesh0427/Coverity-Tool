"""Extract full function code using tree-sitter for C/C++."""

import tree_sitter
from tree_sitter import Language, Parser
import tree_sitter_c
import tree_sitter_cpp
import os
from typing import Optional, Any

# Cache parsers per language to avoid re-creation
_PARSERS = {}

def _get_parser(language: str) -> Parser:
    lang_key = language.lower()
    if lang_key not in _PARSERS:
        if lang_key in ('c', 'cpp', 'c++'):
            grammar = tree_sitter_cpp.language()
        else:
            raise ValueError(f"Unsupported language: {language}")

        # Handle multiple tree-sitter API versions
        # 0.23+: Parser(Language(ptr)), set_language removed
        # 0.20-0.22: Parser(), parser.set_language(Language(ptr, name))
        # 0.19 and earlier: Parser(), parser.set_language(language_obj)
        excs = []

        # Strategy 1: New API (0.23+) - Language() wraps pointer, Parser() takes it
        try:
            lang_obj = Language(grammar) if not isinstance(grammar, Language) else grammar
            parser = Parser(lang_obj)
            _PARSERS[lang_key] = parser
            return parser
        except Exception as e:
            excs.append(f"new API: {e}")

        # Strategy 2: Old API (0.20-0.22) - Parser(), set_language()
        try:
            parser = Parser()
            lang_obj = Language(grammar) if not isinstance(grammar, Language) else grammar
            parser.set_language(lang_obj)
            _PARSERS[lang_key] = parser
            return parser
        except Exception as e:
            excs.append(f"old API: {e}")

        # Strategy 3: Very old API - Language(ptr, name)
        try:
            parser = Parser()
            lang_obj = Language(grammar, 'cpp')
            parser.set_language(lang_obj)
            _PARSERS[lang_key] = parser
            return parser
        except Exception as e:
            excs.append(f"very old API: {e}")

        raise RuntimeError(f"Failed to create tree-sitter parser. Tried: {excs}")
    return _PARSERS[lang_key]

# Cache file text to avoid re-reading — bounded LRU to avoid OOM on large trees
_FILE_CACHE = {}
_FILE_CACHE_MAX = 500  # max files cached; ~500*~50KB = 25MB
import collections as _coll
_FILE_CACHE_ORDER = _coll.OrderedDict()

def _read_file(filepath: str) -> Optional[str]:
    if filepath in _FILE_CACHE:
        # Move to MRU
        try:
            _FILE_CACHE_ORDER.move_to_end(filepath)
        except Exception:
            pass
        return _FILE_CACHE[filepath]
    try:
        # Skip caching huge files (>1MB) — they are rare and bloat cache
        try:
            if os.path.getsize(filepath) > 1_000_000:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    return f.read()
        except Exception:
            pass
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        _FILE_CACHE[filepath] = content
        _FILE_CACHE_ORDER[filepath] = True
        # Evict oldest if over limit
        if len(_FILE_CACHE) > _FILE_CACHE_MAX:
            oldest, _ = _FILE_CACHE_ORDER.popitem(last=False)
            _FILE_CACHE.pop(oldest, None)
        return content
    except Exception:
        return None

def clear_file_cache():
    """Clear file content cache (call when source root changes)."""
    _FILE_CACHE.clear()
    _FILE_CACHE_ORDER.clear()

# Cache parsed trees per (filepath, language) keyed by mtime, so a source file is
# tree-sitter-parsed ONCE even when many defects live in the same file. Repeated
# parsing was a dominant per-defect cost on large reports.
_PARSE_CACHE = {}

def _parse_file(filepath: str, language: str) -> tuple[Optional[str], Any]:
    """Return (source, tree) using a cached parse when the file is unchanged."""
    key = f"{filepath}::{language.lower()}"
    try:
        mtime = os.stat(filepath).st_mtime_ns
    except Exception:
        mtime = 0
    cached = _PARSE_CACHE.get(key)
    if cached and cached[0] == mtime:
        return cached[1], cached[2]
    source = _read_file(filepath)
    if not source:
        return None, None
    parser = _get_parser(language)
    tree = parser.parse(bytes(source, 'utf-8'))
    _PARSE_CACHE[key] = (mtime, source, tree)
    return source, tree

def invalidate_parse_cache(filepath: Optional[str] = None):
    """Drop cached parses (e.g. after a source file is edited)."""
    if filepath:
        for k in [k for k in _PARSE_CACHE if k.startswith(filepath + '::')]:
            del _PARSE_CACHE[k]
    else:
        _PARSE_CACHE.clear()

def _find_node_at_line(root_node, line: int):
    """Return the smallest node that contains the given line."""
    target = None
    for child in root_node.children:
        start_line = child.start_point[0] + 1  # tree-sitter rows are 0-indexed
        end_line = child.end_point[0] + 1
        if start_line <= line <= end_line:
            deeper = _find_node_at_line(child, line)
            if deeper is not None:
                return deeper
            target = child
    return target

def extract_enclosing_function(filepath: str, line: int, language: str = 'c') -> tuple[str, int, Any]:
    """
    Extract the source code of the smallest function (C/C++) containing line.
    If no function found, return 50 lines around the line.
    Returns (code, start_line_in_file).
    """
    source, tree = _parse_file(filepath, language)
    if not source:
        return ""

    root = tree.root_node

    node = _find_node_at_line(root, line)
    # Look upwards for a function_definition node (or method_definition, etc.)
    while node:
        if node.type in ('function_definition', 'method_definition', 'constructor_definition',
                         'destructor_definition', 'lambda_expression'):
            start_byte = node.start_byte
            end_byte = node.end_byte
            start_line = node.start_point[0] + 1
            return source[start_byte:end_byte], start_line, tree
        node = node.parent

    # Fallback: return a window of 50 lines around the target line
    lines = source.splitlines()
    start = max(0, line - 25)
    end = min(len(lines), line + 25)
    return '\n'.join(lines[start:end]), start + 1, tree



def _get_function_name(node) -> str:
    """Extract the function name from a function_definition AST node."""
    # Walk the declarator subtree to find the identifier
    def _walk_for_name(n):
        if n.type == 'identifier' or n.type == 'field_identifier':
            return n.text.decode('utf-8') if isinstance(n.text, bytes) else n.text
        for child in n.children:
            result = _walk_for_name(child)
            if result:
                return result
        return None

    # The declarator is usually the second child (after type qualifiers)
    for child in node.children:
        if child.type in ('function_declarator', 'pointer_declarator', 'init_declarator'):
            return _walk_for_name(child)
        if child.type == 'declarator':
            return _walk_for_name(child)
    return None


def find_function_line_by_name(filepath: str, func_name: str, language: str = 'c') -> int:
    """
    Parse a source file and return the line number of the function definition
    matching func_name. Returns 0 if not found.
    """
    source, tree = _parse_file(filepath, language)
    if not source or not func_name:
        return 0

    root = tree.root_node

    def _scan(node):
        if node.type == 'function_definition':
            name = _get_function_name(node)
            if name == func_name:
                return node.start_point[0] + 1  # tree-sitter is 0-indexed
        for child in node.children:
            result = _scan(child)
            if result:
                return result
        return 0

    try:
        return _scan(root)
    except Exception:
        return 0

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print("Usage: python code_extractor.py <file> <line> [language]")
        sys.exit(1)
    file = sys.argv[1]
    line = int(sys.argv[2])
    lang = sys.argv[3] if len(sys.argv) > 3 else 'c'
    code = extract_enclosing_function(file, line, lang)
    print(code)