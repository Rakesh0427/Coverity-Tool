#!/usr/bin/env python3
"""
clang_resolver.py — libclang-backed type-aware buffer/macro resolution.

Extracted from deep_analyzer._libclang_buffer_info and expanded.
Falls back gracefully when libclang is unavailable or the code cannot be parsed.
Windows: set LIBCLANG_PATH env var to the path of libclang.dll if auto-discovery fails.
"""
import re
import os
import tempfile
from typing import Optional, Dict, Tuple

# ---------------------------------------------------------------------------
# Windows DLL discovery
# ---------------------------------------------------------------------------

def _init_libclang() -> bool:
    """Attempt to locate and configure libclang. Returns True if available."""
    try:
        import clang.cindex as cx
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

def _parse_code(code: str, extra_args=None):
    """Parse C code string into a libclang TranslationUnit. Returns (tu, tmp_path) or (None, None)."""
    if not _clang_available():
        return None, None
    try:
        import clang.cindex as cx
        idx = cx.Index.create()
        with tempfile.NamedTemporaryFile(suffix='.c', mode='w', delete=False, encoding='utf-8') as f:
            f.write(code)
            tmp = f.name
        args = ['-std=c11'] + (extra_args or [])
        tu = idx.parse(tmp, args=args)
        return (tu, tmp) if tu else (None, tmp)
    except Exception:
        return None, None


def _cleanup(tmp_path: Optional[str]) -> None:
    if tmp_path:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_array_size(code: str, var_name: str, line_hint: int = 0) -> Tuple[int, str]:
    """
    Resolve the byte size of var_name's array declaration via libclang.
    Returns (size_bytes, size_expr). size_bytes==0 means unresolved.
    Handles: stack arrays, macro-expanded sizes, typedef chains.
    """
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
