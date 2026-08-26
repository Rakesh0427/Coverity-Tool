"""AST Node Extractor using tree-sitter for precise structural queries.

Phase 1 of the Coverity Triage precision upgrade.
All line numbers are REAL FILE LINE NUMBERS (1-indexed).

Provides exact structural facts:
  - array accesses (handles ptr->arr[i], obj.arr[i], arr[i])
  - variable declarations (type, array size)
  - assignments (RHS expression, variables)
  - call expressions (function name, arguments)
  - enclosing guards (if/while/for conditions)

Each function tries AST-first, then falls back to regex for resilience.
"""

import re
import weakref
from typing import Dict, List, Tuple, Optional, Any

from code_extractor import _get_parser, _read_file

# Map tree-sitter Tree objects to their source strings (weak references)
_TREE_SOURCE_MAP: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _source_for(tree) -> str:
    """Return the cached source string for *tree*, or "" if unavailable.

    tree_sitter.Tree objects do not support weak references in some
    versions, so every WeakKeyDictionary access can raise TypeError
    ("cannot create weak reference to 'tree_sitter.Tree' object").  Treat
    that as "no cached source" instead of crashing the whole analysis.
    """
    try:
        return _TREE_SOURCE_MAP.get(tree, "")
    except TypeError:
        return ""


def parse_function_tree(filepath: str, line: int, language: str = "c") -> Tuple[str, int, Any]:
    """Parse the source file and return the function containing `line`.

    Returns:
        (function_code: str, start_line_in_file: int, tree: Tree)
        The tree object covers the ENTIRE file and can be passed to the
        find_* helpers below.  The source string is cached internally.
    """
    source = _read_file(filepath)
    if not source:
        return "", 0, None

    try:
        parser = _get_parser(language)
        tree = parser.parse(bytes(source, "utf-8"))
    except Exception:
        return "", 0, None  # tree-sitter unavailable — callers use regex paths
    try:
        _TREE_SOURCE_MAP[tree] = source
    except TypeError:
        pass  # tree_sitter.Tree has no weakref support in this version

    root = tree.root_node
    node = _find_node_at_line(root, line)

    # Walk up to enclosing function definition
    while node:
        if node.type in (
            "function_definition",
            "method_definition",
            "constructor_definition",
            "destructor_definition",
            "lambda_expression",
        ):
            start_byte = node.start_byte
            end_byte = node.end_byte
            start_line = node.start_point[0] + 1
            return source[start_byte:end_byte], start_line, tree
        node = node.parent

    # Fallback: return a 50-line window around target line
    lines = source.splitlines()
    start = max(0, line - 25)
    end = min(len(lines), line + 25)
    return "\n".join(lines[start:end]), start + 1, tree


def get_source(tree) -> str:
    """Retrieve the original source string associated with a tree."""
    return _source_for(tree)


def _find_node_at_line(root_node, line: int) -> Optional[Any]:
    """Return the smallest node that contains the given 1-indexed line."""
    target = None
    for child in root_node.children:
        start_line = child.start_point[0] + 1
        end_line = child.end_point[0] + 1
        if start_line <= line <= end_line:
            deeper = _find_node_at_line(child, line)
            if deeper is not None:
                return deeper
            target = child
    return target


def _node_text(node) -> str:
    """Extract text from a tree-sitter node, handling bytes vs str."""
    if node is None:
        return ""
    text = node.text
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace")
    return str(text)


def _subscript_index_text(node) -> str:
    """Return the index-expression text of a subscript_expression node.

    Older tree-sitter grammars expose the index as an ``index`` field.
    Newer grammars wrap it in a ``subscript_argument_list`` node
    (``[ index ]``) with no ``index`` field, so fall back to that node (or
    to a regex over the raw text) to keep ``arr[i]`` extraction working on
    both grammars.
    """
    index_node = node.child_by_field_name("index")
    if index_node is not None:
        return _node_text(index_node)
    sal = node.child_by_field_name("subscript_argument_list")
    if sal is None:
        for child in node.children:
            if child.type == "subscript_argument_list":
                sal = child
                break
    if sal is not None:
        text = _node_text(sal)
        if text.startswith("[") and text.endswith("]"):
            return text[1:-1].strip()
        return text.strip()
    raw = _node_text(node)
    m = re.search(r"\[([^\]]*)\]", raw)
    return m.group(1).strip() if m else ""


def _extract_identifiers(text: str) -> List[str]:
    """Extract C/C++ identifiers from a text snippet."""
    if not text:
        return []
    ids = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", text)
    keywords = {
        "if", "while", "for", "return", "sizeof", "NULL", "int", "char", "void",
        "struct", "const", "static", "unsigned", "signed", "long", "short",
        "float", "double", "true", "false", "bool", "auto", "break", "continue",
        "do", "else", "enum", "extern", "goto", "inline", "register", "restrict",
        "switch", "typedef", "union", "volatile", "wchar_t", "uint8_t", "uint16_t",
        "uint32_t", "uint64_t", "int8_t", "int16_t", "int32_t", "int64_t", "size_t",
    }
    return [v for v in ids if v not in keywords]


# ---------------------------------------------------------------------------
# Array Access
# ---------------------------------------------------------------------------


def find_array_access(tree, target_line: int) -> Optional[Dict[str, Any]]:
    """Find the array access expression closest to target_line.

    AST-first: handles arr[i], ptr->arr[i], obj.arr[i], arr[func(a,b)]
    Fallback: regex scan of source text.

    Returns:
        {
            "array_name":       resolved dotted name, e.g. "obj->field"
            "index_expression": raw index text
            "index_variables":  identifiers inside the index
            "access_line":      real file line number
            "is_write":         True if this is LHS of assignment
            "raw":              full text of the access expression
        }
    """
    result = _ast_find_array_access(tree, target_line)
    if result:
        return result

    source = _source_for(tree)
    if source:
        return _regex_find_array_access(source, target_line)
    return None


def _ast_find_array_access(tree, target_line: int) -> Optional[Dict[str, Any]]:
    root = tree.root_node
    best = None
    best_dist = 9999

    def walk(node):
        nonlocal best, best_dist
        if node.type in ("subscript_expression", "array_access"):
            access_line = node.start_point[0] + 1
            dist = abs(access_line - target_line)
            if dist < best_dist:
                best_dist = dist
                array_node = node.child_by_field_name("argument")
                index_expr = _subscript_index_text(node)

                array_name = _resolve_member_access(array_node)

                # Determine if write: parent is assignment_expression and we are left side
                is_write = False
                parent = node.parent
                if parent and parent.type == "assignment_expression":
                    left = parent.child_by_field_name("left")
                    if left and _node_contains(left, node):
                        is_write = True

                best = {
                    "array_name": array_name,
                    "index_expression": index_expr,
                    "index_variables": _extract_identifiers(index_expr),
                    "access_line": access_line,
                    "is_write": is_write,
                    "raw": _node_text(node),
                }
        for child in node.children:
            walk(child)

    walk(root)
    return best


def _resolve_member_access(node) -> str:
    """Resolve field_expression / identifier to a dotted name."""
    if node is None:
        return ""
    if node.type == "identifier":
        return _node_text(node)
    if node.type == "field_expression":
        arg = node.child_by_field_name("argument")
        field = node.child_by_field_name("field")
        arg_name = _resolve_member_access(arg)
        field_name = _node_text(field) if field else ""
        op = "."
        for child in node.children:
            if child.type == "->":
                op = "->"
                break
            elif child.type == ".":
                op = "."
                break
        if arg_name and field_name:
            return f"{arg_name}{op}{field_name}"
        return field_name or arg_name
    if node.type == "subscript_expression":
        arg = node.child_by_field_name("argument")
        arg_name = _resolve_member_access(arg)
        idx_expr = _subscript_index_text(node)
        if arg_name:
            return f"{arg_name}[{idx_expr}]"
    if node.type == "pointer_expression":
        op = "*"
        for child in node.children:
            if child.type in ("*", "&"):
                op = _node_text(child)
                break
        arg = node.child_by_field_name("argument")
        arg_name = _resolve_member_access(arg)
        if arg_name:
            return f"{op}{arg_name}"
    if node.type == "parenthesized_expression":
        return _resolve_member_access(node.child_by_field_name("expression"))
    return _node_text(node)


def _node_contains(parent, child) -> bool:
    """Check if parent node contains child node (by identity)."""
    if parent is child:
        return True
    for c in parent.children:
        if _node_contains(c, child):
            return True
    return False


def _regex_find_array_access(source: str, target_line: int) -> Optional[Dict[str, Any]]:
    lines = source.splitlines()
    best = None
    best_dist = 9999
    for i, line in enumerate(lines, 1):
        dist = abs(i - target_line)
        if dist >= best_dist:
            continue
        # Match array-like access: identifier[expr] or chain->field[expr] or chain.field[expr]
        m = re.search(r"\b(\w+(?:\s*(?:->|\.)\s*\w+)*)\s*\[([^\]]+)\]", line)
        if m:
            best_dist = dist
            arr = m.group(1).strip()
            idx = m.group(2).strip()
            # Heuristic write detection: access followed by = (but not ==, !=, <=, >=)
            access_end = line.find(m.group(0)) + len(m.group(0))
            rest = line[access_end:]
            is_write = bool(re.search(r"^\s*[^=<>!]*=", rest))
            best = {
                "array_name": arr,
                "index_expression": idx,
                "index_variables": _extract_identifiers(idx),
                "access_line": i,
                "is_write": is_write,
                "raw": line.strip(),
            }
    return best


# ---------------------------------------------------------------------------
# Variable Declaration
# ---------------------------------------------------------------------------


def find_declaration(tree, var_name: str) -> Optional[Dict[str, Any]]:
    """Find declaration of var_name inside the tree.

    Returns:
        {
            "type_name":        e.g. "char", "unsigned int"
            "size_expression":  for arrays, e.g. "256" or "MAX_BUF"
            "declaration_line": real file line
            "raw":              full declaration text
        }
    """
    result = _ast_find_declaration(tree, var_name)
    if result:
        return result
    source = _source_for(tree)
    if source:
        return _regex_find_declaration(source, var_name)
    return None


def _ast_find_declaration(tree, var_name: str) -> Optional[Dict[str, Any]]:
    root = tree.root_node
    result = None

    def walk(node):
        nonlocal result
        if result:
            return
        if node.type in ("declaration", "parameter_declaration"):
            # declaration has type and declarator fields
            decl_node = node.child_by_field_name("declarator")
            if decl_node and _declares_var(decl_node, var_name):
                type_node = node.child_by_field_name("type")
                type_name = _node_text(type_node) if type_node else ""
                size_expr = ""

                # Walk declarator for array_declarator size
                def find_array_size(n):
                    nonlocal size_expr
                    if n.type == "array_declarator":
                        sz = n.child_by_field_name("size")
                        if sz:
                            size_expr = _node_text(sz)
                        else:
                            # Check children for size expression
                            for c in n.children:
                                if c.type not in ("[", "]", "declarator"):
                                    size_expr = _node_text(c)
                                    break
                        # Continue deeper in case of multi-dimensional
                        deeper = n.child_by_field_name("declarator")
                        if deeper:
                            find_array_size(deeper)
                    elif n.type == "pointer_declarator":
                        deeper = n.child_by_field_name("declarator")
                        if deeper:
                            find_array_size(deeper)

                find_array_size(decl_node)

                result = {
                    "type_name": type_name,
                    "size_expression": size_expr,
                    "declaration_line": node.start_point[0] + 1,
                    "raw": _node_text(node),
                }
                return
        for child in node.children:
            walk(child)

    walk(root)
    return result


def _declares_var(node, var_name: str) -> bool:
    """Check if a declarator node declares var_name."""
    if node is None:
        return False
    if node.type == "identifier" and _node_text(node) == var_name:
        return True
    if node.type == "pointer_declarator":
        return _declares_var(node.child_by_field_name("declarator"), var_name)
    if node.type == "array_declarator":
        return _declares_var(node.child_by_field_name("declarator"), var_name)
    if node.type == "function_declarator":
        return _declares_var(node.child_by_field_name("declarator"), var_name)
    if node.type == "init_declarator":
        return _declares_var(node.child_by_field_name("left"), var_name)
    for child in node.children:
        if _declares_var(child, var_name):
            return True
    return False


def _regex_find_declaration(source: str, var_name: str) -> Optional[Dict[str, Any]]:
    # Look for: type var_name[...]; or type var_name = ...;
    # This is intentionally simple; AST is preferred.
    pat = re.compile(
        r"^\s*(?:\w+\s+){1,6}\b"
        + re.escape(var_name)
        + r"\s*(?:\[\s*([^\]]*)\s*\])?\s*(?:=|;)",
        re.MULTILINE,
    )
    m = pat.search(source)
    if m:
        size_expr = m.group(1) if m.group(1) else ""
        line = source[: m.start()].count("\n") + 1
        return {
            "type_name": "",
            "size_expression": size_expr,
            "declaration_line": line,
            "raw": m.group(0).strip(),
        }
    return None


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------


def find_assignment(tree, var_name: str, before_line: int) -> Optional[Dict[str, Any]]:
    """Find nearest preceding assignment to var_name before before_line.

    Returns:
        {
            "rhs_expression":   raw right-hand side text
            "rhs_variables":    identifiers on RHS
            "assignment_line":  real file line
            "raw":              full assignment text
        }
    """
    result = _ast_find_assignment(tree, var_name, before_line)
    if result:
        return result
    source = _source_for(tree)
    if source:
        return _regex_find_assignment(source, var_name, before_line)
    return None


def _ast_find_assignment(tree, var_name: str, before_line: int) -> Optional[Dict[str, Any]]:
    root = tree.root_node
    candidates = []

    def walk(node):
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            if left and _node_text(left) == var_name:
                line = node.start_point[0] + 1
                if line < before_line:
                    right = node.child_by_field_name("right")
                    rhs_text = _node_text(right) if right else ""
                    candidates.append(
                        {
                            "rhs_expression": rhs_text,
                            "rhs_variables": _extract_identifiers(rhs_text),
                            "assignment_line": line,
                            "raw": _node_text(node),
                        }
                    )
        elif node.type == "init_declarator":
            left = node.child_by_field_name("left")
            if left and _node_text(left) == var_name:
                line = node.start_point[0] + 1
                if line < before_line:
                    right = node.child_by_field_name("right")
                    rhs_text = _node_text(right) if right else ""
                    candidates.append(
                        {
                            "rhs_expression": rhs_text,
                            "rhs_variables": _extract_identifiers(rhs_text),
                            "assignment_line": line,
                            "raw": _node_text(node),
                        }
                    )
        for child in node.children:
            walk(child)

    walk(root)
    if not candidates:
        return None
    # Closest to before_line
    candidates.sort(key=lambda x: before_line - x["assignment_line"])
    return candidates[0]


def _regex_find_assignment(source: str, var_name: str, before_line: int) -> Optional[Dict[str, Any]]:
    lines = source.splitlines()
    for i in range(min(before_line - 1, len(lines) - 1), -1, -1):
        line = lines[i]
        # Match var_name = expr;  (but not ==, !=, <=, >=)
        m = re.search(r"\b" + re.escape(var_name) + r"\s*=\s*([^;]+);", line)
        if m:
            rhs = m.group(1).strip()
            return {
                "rhs_expression": rhs,
                "rhs_variables": _extract_identifiers(rhs),
                "assignment_line": i + 1,
                "raw": line.strip(),
            }
    return None


# ---------------------------------------------------------------------------
# Call Expression
# ---------------------------------------------------------------------------


def find_call_expression(tree, target_line: int) -> Optional[Dict[str, Any]]:
    """Find call expression at/near target_line.

    Returns:
        {
            "function_name":      resolved name e.g. "memcpy"
            "arguments":          list of raw argument strings
            "argument_variables": all identifiers in all arguments
            "call_line":          real file line
            "raw":                full call text
        }
    """
    result = _ast_find_call_expression(tree, target_line)
    if result:
        return result
    source = _source_for(tree)
    if source:
        return _regex_find_call_expression(source, target_line)
    return None


def _ast_find_call_expression(tree, target_line: int) -> Optional[Dict[str, Any]]:
    root = tree.root_node
    best = None
    best_dist = 9999

    def walk(node):
        nonlocal best, best_dist
        if node.type == "call_expression":
            line = node.start_point[0] + 1
            dist = abs(line - target_line)
            if dist < best_dist:
                best_dist = dist
                func_node = node.child_by_field_name("function")
                args_node = node.child_by_field_name("arguments")

                func_name = _resolve_call_name(func_node)
                args = []
                arg_vars = []
                if args_node:
                    for child in args_node.children:
                        if child.type not in ("(", ")", ","):
                            arg_text = _node_text(child)
                            args.append(arg_text)
                            arg_vars.extend(_extract_identifiers(arg_text))

                best = {
                    "function_name": func_name,
                    "arguments": args,
                    "argument_variables": arg_vars,
                    "call_line": line,
                    "raw": _node_text(node),
                }
        for child in node.children:
            walk(child)

    walk(root)
    return best


def _resolve_call_name(node) -> str:
    """Resolve function name from call expression function node."""
    if node is None:
        return ""
    if node.type == "identifier":
        return _node_text(node)
    if node.type == "field_expression":
        return _resolve_member_access(node)
    if node.type == "parenthesized_expression":
        return _resolve_call_name(node.child_by_field_name("expression"))
    return _node_text(node)


def _regex_find_call_expression(source: str, target_line: int) -> Optional[Dict[str, Any]]:
    lines = source.splitlines()
    best = None
    best_dist = 9999
    for i, line in enumerate(lines, 1):
        dist = abs(i - target_line)
        if dist >= best_dist:
            continue
        # Match function call: ident( ... )
        m = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)", line)
        if m:
            best_dist = dist
            func = m.group(1)
            args_str = m.group(2)
            args = [a.strip() for a in args_str.split(",") if a.strip()]
            arg_vars = []
            for a in args:
                arg_vars.extend(_extract_identifiers(a))
            best = {
                "function_name": func,
                "arguments": args,
                "argument_variables": arg_vars,
                "call_line": i,
                "raw": line.strip(),
            }
    return best


# ---------------------------------------------------------------------------
# Enclosing Guard
# ---------------------------------------------------------------------------


def find_enclosing_guard(tree, target_line: int) -> Optional[Dict[str, Any]]:
    """Walk up from target_line to find nearest enclosing if/while/for/do.

    Returns:
        {
            "condition_expression": raw condition text
            "condition_line":       real file line
            "condition_variables":  identifiers in condition
            "guard_type":           "if" / "while" / "for" / "do"
            "raw":                  full statement text
        }
    """
    result = _ast_find_enclosing_guard(tree, target_line)
    if result:
        return result
    source = _source_for(tree)
    if source:
        return _regex_find_enclosing_guard(source, target_line)
    return None


def _ast_find_enclosing_guard(tree, target_line: int) -> Optional[Dict[str, Any]]:
    root = tree.root_node
    target = _find_node_at_line(root, target_line)
    if not target:
        return None

    node = target.parent
    while node:
        if node.type in ("if_statement", "while_statement", "for_statement", "do_statement"):
            condition = None
            guard_type = node.type.replace("_statement", "")

            if node.type == "if_statement":
                condition = node.child_by_field_name("condition")
            elif node.type == "while_statement":
                condition = node.child_by_field_name("condition")
            elif node.type == "for_statement":
                condition = node.child_by_field_name("condition")
            elif node.type == "do_statement":
                condition = node.child_by_field_name("condition")

            cond_text = _node_text(condition) if condition else ""
            cond_vars = _extract_identifiers(cond_text)

            return {
                "condition_expression": cond_text,
                "condition_line": node.start_point[0] + 1,
                "condition_variables": cond_vars,
                "guard_type": guard_type,
                "raw": _node_text(node),
            }
        node = node.parent
    return None


def _regex_find_enclosing_guard(source: str, target_line: int) -> Optional[Dict[str, Any]]:
    lines = source.splitlines()
    for i in range(min(target_line - 1, len(lines) - 1), -1, -1):
        line = lines[i]
        m = re.search(r"\b(if|while|for)\s*\(([^)]+)\)", line)
        if m:
            cond = m.group(2).strip()
            return {
                "condition_expression": cond,
                "condition_line": i + 1,
                "condition_variables": _extract_identifiers(cond),
                "guard_type": m.group(1),
                "raw": line.strip(),
            }
    return None