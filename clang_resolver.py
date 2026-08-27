#!/usr/bin/env python3
"""
clang_resolver.py — libclang-backed type-aware buffer/macro resolution.

Extracted from deep_analyzer._libclang_buffer_info and expanded.
Falls back gracefully when libclang is unavailable or the code cannot be parsed.
Windows: set LIBCLANG_PATH env var to the path of libclang.dll if auto-discovery fails.
"""
import atexit
import re
import os
import tempfile
from typing import Dict, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Clang finalizer safety patch
# ---------------------------------------------------------------------------

def _patch_clang_cindex() -> None:
    """Patch clang.cindex finalizers to prevent AttributeError during interpreter shutdown.

    In standard libclang python bindings, TranslationUnit.__del__, Index.__del__, etc.
    invoke methods on `conf.lib`. During Python process shutdown, module globals (like `conf`)
    are cleared in arbitrary order, often becoming None before surviving AST objects are
    garbage collected. This causes `AttributeError: 'NoneType' object has no attribute 'lib'`
    messages to be emitted to stderr on exit.
    """
    try:
        import clang.cindex as cx
    except (ImportError, Exception):
        return

    if getattr(cx, '_cov_tool_patched', False):
        return

    classes = (
        'TranslationUnit',
        'Index',
        'Diagnostic',
        'TokenGroup',
        'CodeCompletionResults',
        'CompilationDatabase',
        'CompileCommands',
        '_CXString',
    )
    for cls_name in classes:
        cls = getattr(cx, cls_name, None)
        if cls and hasattr(cls, '__del__'):
            orig_del = cls.__del__

            def _make_safe_del(orig, module):
                def _safe_del(self, _orig=orig, _mod=module):
                    try:
                        conf = getattr(_mod, 'conf', None)
                        if conf is not None and getattr(conf, 'lib', None) is not None:
                            _orig(self)
                    except Exception:
                        pass
                return _safe_del

            cls.__del__ = _make_safe_del(orig_del, cx)

    cx._cov_tool_patched = True


# Apply finalizer safety patch immediately if clang.cindex is available
_patch_clang_cindex()


# ---------------------------------------------------------------------------
# Windows DLL discovery
# ---------------------------------------------------------------------------

def _init_libclang() -> bool:
    """Attempt to locate and configure libclang. Returns True if available."""
    try:
        import clang.cindex as cx
        _patch_clang_cindex()
        # Try default (auto-discovered via PATH / LD_LIBRARY_PATH)
        try:
            cx.Index.create()
            return True
        except Exception:
            pass
        # Try env var override
        env_path = os.environ.get('LIBCLANG_PATH', '')
        if env_path and os.path.isfile(env_path):
            cx.Config.set_library_file(env_path)
            cx.Index.create()
            return True
        # Windows: scan common LLVM install dirs
        if os.name == 'nt':
            candidates = []
            for drive in ('C:', 'D:'):
                for prog in (r'\Program Files\LLVM\bin', r'\Program Files (x86)\LLVM\bin'):
                    candidates.append(os.path.join(drive + prog, 'libclang.dll'))
            for path in candidates:
                if os.path.isfile(path):
                    cx.Config.set_library_file(path)
                    try:
                        cx.Index.create()
                        return True
                    except Exception:
                        continue
        return False
    except ImportError:
        return False


_LIBCLANG_AVAILABLE: Optional[bool] = None


def _clang_available() -> bool:
    global _LIBCLANG_AVAILABLE
    if _LIBCLANG_AVAILABLE is None:
        _LIBCLANG_AVAILABLE = _init_libclang()
    return _LIBCLANG_AVAILABLE


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Translation-unit context
#
# Parsing a bare function snippet in an empty temp file makes libclang almost
# useless: every project type is unknown, every #define is missing, so
# CONSTANTARRAY never resolves and get_array_size() returns (0, ''). The
# regex fallback then does all the work, and the "libclang is installed"
# claim is hollow.
#
# set_translation_context() lets the caller supply the real file plus the
# workspace include directories, so the snippet is parsed *in situ* with the
# project's own headers and macros visible.
# ---------------------------------------------------------------------------

_TU_FILE: Optional[str] = None        # real path of the file under analysis
_INCLUDE_DIRS: Tuple[str, ...] = ()   # -I paths discovered from the workspace
_EXTRA_ARGS: Tuple[str, ...] = ()     # e.g. -D flags supplied by the caller
_TU_CACHE: Dict[str, object] = {}     # real path -> parsed TranslationUnit

#: Cap on how many -I flags are passed; huge trees would otherwise slow parsing.
MAX_INCLUDE_DIRS = 60


def set_translation_context(file_path: str = '',
                            include_dirs: Optional[Sequence[str]] = None,
                            extra_args: Optional[Sequence[str]] = None) -> None:
    """Tell the resolver which real file (and headers) the snippet came from.

    Called once per defect by the context builder. Passing an empty
    ``file_path`` restores snippet-only behaviour.
    """
    global _TU_FILE, _INCLUDE_DIRS, _EXTRA_ARGS
    _TU_FILE = file_path or None
    _INCLUDE_DIRS = tuple(include_dirs or ())
    _EXTRA_ARGS = tuple(extra_args or ())


def discover_include_dirs(src_root: str, limit: int = MAX_INCLUDE_DIRS) -> list:
    """Collect plausible -I directories under ``src_root``.

    Any directory containing a header is an include candidate. Directories
    conventionally named include/inc/api/public are listed first so they
    survive the cap on large trees.
    """
    if not src_root or not os.path.isdir(src_root):
        return []
    preferred, others = [], []
    skip = {'.git', '.hg', '.svn', '__pycache__', 'build', 'out', 'target',
            'node_modules', '.venv', 'venv', 'dist', 'CMakeFiles'}
    for root, dirs, files in os.walk(src_root):
        dirs[:] = [d for d in dirs if d not in skip]
        if not any(f.endswith(('.h', '.hpp', '.hh', '.hxx', '.inc')) for f in files):
            continue
        base = os.path.basename(root).lower()
        (preferred if base in ('include', 'inc', 'api', 'public', 'headers',
                               'interface') else others).append(root)
    ordered = preferred + others
    if src_root not in ordered:
        ordered.insert(0, src_root)
    return ordered[:limit]


def _build_args(for_cpp: bool = False) -> list:
    """Compiler arguments: language standard, include paths, error tolerance."""
    args = ['-std=c++14' if for_cpp else '-std=c11']
    # Keep going despite missing system headers -- a partial AST with real
    # project types still beats a regex guess.
    args += ['-ferror-limit=0', '-Wno-everything']
    for inc in _INCLUDE_DIRS:
        args += ['-I', inc]
    args += list(_EXTRA_ARGS)
    return args


def parse_real_file(file_path: str = ''):
    """Parse the actual source file (with project headers) and cache the TU.

    Returns the TranslationUnit, or None when libclang or the file is
    unavailable. The TU is cached per path because several defects usually
    land in the same file.
    """
    target = file_path or _TU_FILE
    if not target or not os.path.isfile(target) or not _clang_available():
        return None
    cached = _TU_CACHE.get(target)
    if cached is not None:
        return cached
    try:
        import clang.cindex as cx
        idx = cx.Index.create()
        opts = (cx.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD |
                cx.TranslationUnit.PARSE_INCOMPLETE)
        tu = idx.parse(target,
                       args=_build_args(target.endswith(('.cpp', '.cc', '.cxx', '.hpp'))),
                       options=opts)
    except Exception:
        tu = None
    if tu is not None:
        _TU_CACHE[target] = tu
    return tu


def clear_tu_cache() -> None:
    """Drop cached translation units (after edits, or to release memory)."""
    _TU_CACHE.clear()


atexit.register(clear_tu_cache)


def _parse_code(code: str, extra_args=None):
    """Parse a C snippet into a TranslationUnit. Returns (tu, tmp_path).

    The snippet is written next to the real file when one is known, so that
    relative ``#include "local.h"`` directives resolve and the project's own
    include paths apply. ``tmp_path`` is returned for cleanup by the caller.
    """
    if not _clang_available():
        return None, None
    tmp = None
    try:
        import clang.cindex as cx
        idx = cx.Index.create()
        # Prefer a sibling of the real file: relative includes then resolve.
        target_dir, for_cpp = None, False
        if _TU_FILE and os.path.isfile(_TU_FILE):
            target_dir = os.path.dirname(_TU_FILE)
            for_cpp = _TU_FILE.endswith(('.cpp', '.cc', '.cxx', '.hpp'))
        suffix = '.cpp' if for_cpp else '.c'
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, mode='w', delete=False,
                                             encoding='utf-8', dir=target_dir) as f:
                f.write(code)
                tmp = f.name
        except Exception:
            # Read-only source tree: fall back to the system temp dir.
            with tempfile.NamedTemporaryFile(suffix=suffix, mode='w', delete=False,
                                             encoding='utf-8') as f:
                f.write(code)
                tmp = f.name
        args = _build_args(for_cpp) + list(extra_args or [])
        tu = idx.parse(tmp, args=args,
                       options=cx.TranslationUnit.PARSE_INCOMPLETE)
        return (tu, tmp) if tu else (None, tmp)
    except Exception:
        return None, tmp


def _cleanup(tmp_path: Optional[str]) -> None:
    if tmp_path:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _array_size_from_tu(tu, var_name: str, code: str) -> Tuple[int, str]:
    """Search a parsed TranslationUnit for var_name's array size."""
    if tu is None:
        return 0, ''
    try:
        import clang.cindex as cx
    except Exception:
        return 0, ''

    def _walk(cursor):
        if cursor.spelling == var_name:
            t = cursor.type
            if t.kind == cx.TypeKind.CONSTANTARRAY:
                sz = t.get_array_size()
                elem_sz = t.get_array_element_type().get_size()
                return sz * max(elem_sz, 1), str(sz)
            if t.kind in (cx.TypeKind.POINTER, cx.TypeKind.INCOMPLETEARRAY):
                try:
                    tokens = ' '.join(tok.spelling for tok in cursor.get_tokens())
                except Exception:
                    tokens = ''
                m = re.search(r'(?:malloc|calloc|realloc)\s*\(([^)]+)\)', tokens)
                if m:
                    from deep_analyzer import _resolve_constant
                    expr = m.group(1).strip()
                    return _resolve_constant(expr, code), expr
        for child in cursor.get_children():
            r = _walk(child)
            if r[0]:
                return r
        return 0, ''

    try:
        return _walk(tu.cursor)
    except Exception:
        return 0, ''


def get_array_size(code: str, var_name: str, line_hint: int = 0) -> Tuple[int, str]:
    """
    Resolve the byte size of var_name's array declaration via libclang.
    Returns (size_bytes, size_expr). size_bytes==0 means unresolved.
    Handles: stack arrays, macro-expanded sizes, typedef chains.

    The real translation unit is tried first: parsed with the project's own
    headers and macros, it resolves declarations whose element type or size
    constant is defined in a header the snippet does not contain. The snippet
    parse remains as a fallback for callers that set no context.
    """
    real_tu = parse_real_file()
    if real_tu is not None:
        size, expr = _array_size_from_tu(real_tu, var_name, code)
        if size > 0:
            return size, expr

    tu, tmp = _parse_code(code)
    try:
        if tu is None:
            return 0, ''
        import clang.cindex as cx

        def _walk(cursor):
            if cursor.spelling == var_name:
                t = cursor.type
                if t.kind == cx.TypeKind.CONSTANTARRAY:
                    sz = t.get_array_size()
                    elem_sz = t.get_array_element_type().get_size()
                    total = sz * max(elem_sz, 1)
                    return total, str(sz)
                # pointer backed by malloc
                if t.kind in (cx.TypeKind.POINTER, cx.TypeKind.INCOMPLETEARRAY):
                    tokens = ' '.join(tok.spelling for tok in cursor.get_tokens())
                    m = re.search(r'(?:malloc|calloc|realloc)\s*\(([^)]+)\)', tokens)
                    if m:
                        from deep_analyzer import _resolve_constant
                        expr = m.group(1).strip()
                        return _resolve_constant(expr, code), expr
            for child in cursor.get_children():
                r = _walk(child)
                if r[0]:
                    return r
            return 0, ''

        return _walk(tu.cursor)
    finally:
        _cleanup(tmp)


def get_type_size(code: str, type_name: str) -> int:
    """Return sizeof(type_name) via libclang. Returns 0 if unresolvable."""
    probe = code + f'\nstatic int __sz_probe = sizeof({type_name});\n'
    tu, tmp = _parse_code(probe)
    try:
        if tu is None:
            return 0
        import clang.cindex as cx

        def _walk(cursor):
            if cursor.spelling == '__sz_probe':
                t = cursor.type
                return t.get_size() if t.get_size() > 0 else 0
            for child in cursor.get_children():
                r = _walk(child)
                if r:
                    return r
            return 0

        return _walk(tu.cursor)
    finally:
        _cleanup(tmp)


def _macro_from_real_tu(macro_name: str) -> Optional[int]:
    """Read an integer #define from the real file's preprocessor record.

    parse_real_file() requests PARSE_DETAILED_PROCESSING_RECORD, so macro
    definitions pulled in from project headers are present in the AST even
    though they never appear in the extracted function snippet.
    """
    tu = parse_real_file()
    if tu is None:
        return None
    try:
        import clang.cindex as cx
        for cursor in tu.cursor.walk_preorder():
            if cursor.kind != cx.CursorKind.MACRO_DEFINITION:
                continue
            if cursor.spelling != macro_name:
                continue
            tokens = [t.spelling for t in cursor.get_tokens()]
            # tokens[0] is the macro name; the body follows.
            body = tokens[1:]
            if len(body) == 1:
                try:
                    return int(body[0], 0)
                except ValueError:
                    return None
            # Simple parenthesised integer, e.g. #define N (64)
            joined = ''.join(body)
            m = re.fullmatch(r'\(?(-?(?:0[xX][0-9a-fA-F]+|\d+))[uUlL]*\)?', joined)
            if m:
                try:
                    return int(m.group(1), 0)
                except ValueError:
                    return None
            return None
    except Exception:
        return None
    return None


def expand_macro(code: str, macro_name: str) -> Optional[int]:
    """
    Resolve a #define integer macro to its integer value.
    Returns None if the macro is not found or not an integer literal.
    """
    # Fast regex path (handles simple #define NAME value)
    m = re.search(rf'#\s*define\s+{re.escape(macro_name)}\s+(\d+)\b', code)
    if m:
        return int(m.group(1))
    # Hex literal
    m = re.search(rf'#\s*define\s+{re.escape(macro_name)}\s+(0[xX][0-9a-fA-F]+)\b', code)
    if m:
        return int(m.group(1), 16)
    # The macro is usually #defined in a header, not in the extracted snippet.
    # Ask the real translation unit's preprocessor record before giving up.
    val = _macro_from_real_tu(macro_name)
    if val is not None:
        return val
    # Expression macro — evaluate via libclang sizeof probe
    probe = code + f'\nstatic int __macro_probe = {macro_name};\n'
    tu, tmp = _parse_code(probe)
    try:
        if tu is None:
            return None
        import clang.cindex as cx

        def _walk(cursor):
            if cursor.spelling == '__macro_probe' and cursor.kind == cx.CursorKind.VAR_DECL:
                for child in cursor.get_children():
                    if child.kind == cx.CursorKind.INTEGER_LITERAL:
                        tokens = list(child.get_tokens())
                        if tokens:
                            try:
                                return int(tokens[0].spelling)
                            except ValueError:
                                pass
            for child in cursor.get_children():
                r = _walk(child)
                if r is not None:
                    return r
            return None

        return _walk(tu.cursor)
    finally:
        _cleanup(tmp)


def resolve_typedef(code: str, type_name: str) -> str:
    """
    Follow a typedef chain to its base type name.
    E.g. 'BYTE' -> 'unsigned char'. Returns type_name if not found.
    """
    # Common Windows/embedded typedefs (fast path)
    _KNOWN: Dict[str, str] = {
        'BYTE': 'unsigned char', 'WORD': 'unsigned short', 'DWORD': 'unsigned long',
        'BOOL': 'int', 'UINT8': 'unsigned char', 'UINT16': 'unsigned short',
        'UINT32': 'unsigned int', 'UINT64': 'unsigned long long',
        'INT8': 'signed char', 'INT16': 'short', 'INT32': 'int', 'INT64': 'long long',
    }
    if type_name in _KNOWN:
        return _KNOWN[type_name]

    tu, tmp = _parse_code(code)
    try:
        if tu is None:
            return type_name
        import clang.cindex as cx

        def _walk(cursor):
            if (cursor.kind == cx.CursorKind.TYPEDEF_DECL and
                    cursor.spelling == type_name):
                t = cursor.underlying_typedef_type
                canon = t.get_canonical()
                return canon.spelling if canon.spelling else t.spelling
            for child in cursor.get_children():
                r = _walk(child)
                if r:
                    return r
            return ''

        result = _walk(tu.cursor)
        return result if result else type_name
    finally:
        _cleanup(tmp)


def get_struct_member_info(code: str, struct_type: str, member_name: str) -> Dict:
    """
    Return {'type': str, 'size_bytes': int, 'array_size': int} for a struct member.
    array_size==0 means it is not an array member.
    """
    info = {'type': '', 'size_bytes': 0, 'array_size': 0}
    tu, tmp = _parse_code(code)
    try:
        if tu is None:
            return info
        import clang.cindex as cx

        def _find_struct(cursor):
            if cursor.kind in (cx.CursorKind.STRUCT_DECL, cx.CursorKind.TYPEDEF_DECL):
                name = cursor.spelling or cursor.type.spelling
                if struct_type in name:
                    for field in cursor.get_children():
                        if field.spelling == member_name:
                            t = field.type
                            info['type'] = t.spelling
                            info['size_bytes'] = t.get_size() if t.get_size() > 0 else 0
                            if t.kind == cx.TypeKind.CONSTANTARRAY:
                                info['array_size'] = t.get_array_size()
                            return True
            for child in cursor.get_children():
                if _find_struct(child):
                    return True
            return False

        _find_struct(tu.cursor)
        return info
    finally:
        _cleanup(tmp)
