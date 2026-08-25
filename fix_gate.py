#!/usr/bin/env python3
"""
fix_gate.py — decide whether a proposed remediation is a real, source-anchored
patch, and repair it when the only problem is a stock error path.

Background
----------
Remediations are produced by template interpolation (``generate_contextual_fix``
and the per-checker ``fix = f"..."`` sites in ``heuristic_analyzer``).  A gate
then decides whether the result is fit to show.  The original gate was a
case-insensitive substring blacklist::

    generic_markers = ('ARRAY_SIZE', 'return ERROR', 'handle error',
                       'the pointer', 'the index', ...)

That rejected the tool's *own* correctly-interpolated output: every null-deref
template contains ``return ERROR``, every integer-overflow template contains
``return ERROR_OVERFLOW``, and ``the pointer`` is ordinary English that the
comment builders emit as a fallback noun.  Fixes that named real variables from
the analysed function were discarded, and the operator was told a placeholder
would have been required — which was usually false.

This module replaces that with three ordered decisions:

1. **Substitute, don't reject.**  A stock ``return ERROR;`` is not a defect in
   the patch, it is an unknown error convention.  :func:`infer_error_convention`
   reads the enclosing function's own ``return`` / ``goto`` statements and
   rewrites the error path to match.  Only if nothing can be inferred is the
   patch downgraded — and then to "adjust the error path", not to nothing.
2. **Reject only genuine placeholders.**  :func:`unresolved_placeholders`
   looks for unsubstituted format fields (``{var}``), the ``?`` emitted by
   argument-parse fallbacks, and macro-like identifiers that appear in the
   patch but in neither the source nor the C standard library.
3. **Require anchoring.**  The patch must name at least one real identifier
   from the analysed function.  This is what actually catches generic advice,
   and it is now reached instead of being short-circuited by the blacklist.
"""
from __future__ import annotations

import re
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

__all__ = [
    "ErrorConvention", "GateResult", "infer_error_convention",
    "unresolved_placeholders", "gate_fix", "has_nested_subscript_at_line",
    "ERROR_RETURN_SENTINEL",
]

#: Templates may emit this token instead of hardcoding ``return ERROR;``.
#: :func:`gate_fix` replaces it with the convention inferred from the source.
ERROR_RETURN_SENTINEL = "<<ERROR_RETURN>>"

# Stock error returns that older templates hardcode.  These are *normalised*
# to the sentinel, not treated as evidence of a bad patch.
_STOCK_ERROR_RETURN = re.compile(
    r'\breturn\s+(?:ERROR|ERROR_OVERFLOW|ERROR_UNDERFLOW|ERR|FAILURE|'
    r'ERROR_CODE|E_ERROR)\s*;',
    re.IGNORECASE)

# Boilerplate the templates wrap around the error path.  Once the real
# convention is substituted in, these read as noise.
_STOCK_ERROR_COMMENT = re.compile(
    r'//\s*handle error[^\n]*\n?', re.IGNORECASE)

# Identifiers that may legitimately appear in a patch without being defined in
# the analysed function.
_STDLIB_IDENTIFIERS = frozenset({
    'NULL', 'nullptr', 'true', 'false', 'TRUE', 'FALSE', 'EOF',
    'INT_MAX', 'INT_MIN', 'UINT_MAX', 'LONG_MAX', 'LONG_MIN', 'ULONG_MAX',
    'SIZE_MAX', 'SHRT_MAX', 'SHRT_MIN', 'CHAR_BIT', 'SSIZE_MAX',
    'INT8_MAX', 'INT16_MAX', 'INT32_MAX', 'INT64_MAX',
    'UINT8_MAX', 'UINT16_MAX', 'UINT32_MAX', 'UINT64_MAX',
    'INT32_MIN', 'INT64_MIN', 'EINVAL', 'ENOMEM', 'ERANGE', 'EOK',
    'CWE', 'CERT', 'OWASP', 'TODO', 'FIXME', 'RAII',
})

# C keywords / common type names that carry no anchoring value.
_NON_ANCHORING = frozenset({
    'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'default', 'break',
    'continue', 'return', 'goto', 'sizeof', 'struct', 'union', 'enum',
    'typedef', 'static', 'const', 'volatile', 'extern', 'inline', 'register',
    'void', 'char', 'short', 'int', 'long', 'float', 'double', 'signed',
    'unsigned', 'size_t', 'ssize_t', 'ptrdiff_t', 'wchar_t', 'bool',
    'int8_t', 'int16_t', 'int32_t', 'int64_t',
    'uint8_t', 'uint16_t', 'uint32_t', 'uint64_t',
    'Suggestion', 'Replace', 'Add', 'Ensure', 'Verify', 'Validate', 'Check',
    'Or', 'Also', 'Consider', 'Use', 'Remove', 'Prefer', 'with', 'before',
    'after', 'the', 'a', 'an', 'and', 'to', 'is', 'of', 'in', 'on', 'at',
    'not', 'or', 'be', 'it', 'this', 'that', 'all', 'any', 'here', 'safe',
}) | _STDLIB_IDENTIFIERS

# Error-looking return values, most specific first.  Used to pick the
# function's own convention out of its return statements.
_ERROR_VALUE_PATTERNS = (
    re.compile(r'^-\s*\d+$'),                                  # -1, -22
    re.compile(r'^[A-Z][A-Z0-9_]*(?:ERROR|ERR|FAIL|FAILURE|INVALID|BAD)[A-Z0-9_]*$'),
    re.compile(r'^(?:E_|ERR_|ERROR_|STATUS_ERR)[A-Z0-9_]*$'),
    re.compile(r'^(?:FALSE|false)$'),
)

_PREFERRED_GOTO_LABELS = ('cleanup', 'error', 'err', 'fail', 'failure',
                          'exit', 'out', 'done', 'end', 'finish')


class ErrorConvention(NamedTuple):
    """How the analysed function signals failure."""
    statement: str      # e.g. 'return -1;', 'goto cleanup;', 'return;'
    kind: str           # 'goto' | 'return_value' | 'return_void' | 'unknown'
    evidence: str       # why this was chosen, for the comment
    confidence: float   # 0.0 - 1.0

    @property
    def known(self) -> bool:
        return self.kind != 'unknown'


class GateResult(NamedTuple):
    """Outcome of gating one proposed fix."""
    fix: str                # patch to display, or a disposition string
    reason: str             # why it was withheld/adjusted ('' when clean)
    accepted: bool          # True when a real patch survived
    adjusted: bool          # True when the error path was rewritten
    convention: Optional[ErrorConvention] = None


# --------------------------------------------------------------------------- #
# error-convention inference
# --------------------------------------------------------------------------- #
def _strip_comments_and_strings(code: str) -> str:
    """Blank out comments and string literals so scans do not match inside them."""
    out = re.sub(r'/\*.*?\*/', ' ', code, flags=re.S)
    out = re.sub(r'//[^\n]*', ' ', out)
    out = re.sub(r'"(?:\\.|[^"\\])*"', '""', out)
    out = re.sub(r"'(?:\\.|[^'\\])*'", "''", out)
    return out


def _looks_like_error_value(expr: str) -> bool:
    expr = expr.strip()
    if not expr:
        return False
    return any(p.match(expr) for p in _ERROR_VALUE_PATTERNS)


def _function_returns_void(code: str) -> bool:
    """Best-effort read of the signature at the top of the extracted snippet."""
    head = _strip_comments_and_strings(code).lstrip()
    # e.g. 'static void foo(' / 'void foo(' — but not 'void *foo('
    return bool(re.match(r'^(?:static\s+|inline\s+|extern\s+)*void\s+\w+\s*\(',
                         head))


def _collect_goto_targets(code: str) -> List[str]:
    """Return goto labels that are both jumped to and defined in this function."""
    clean = _strip_comments_and_strings(code)
    jumped = [m.group(1) for m in re.finditer(r'\bgoto\s+([A-Za-z_]\w*)\s*;', clean)]
    if not jumped:
        return []
    defined = {m.group(1) for m in
               re.finditer(r'^[ \t]*([A-Za-z_]\w*)[ \t]*:(?!:)', clean, re.M)}
    # Preserve first-seen order, keep only labels with a matching definition.
    seen, ordered = set(), []
    for label in jumped:
        if label in defined and label not in seen:
            seen.add(label)
            ordered.append(label)
    return ordered


def _collect_return_exprs(code: str) -> List[str]:
    clean = _strip_comments_and_strings(code)
    return [m.group(1).strip()
            for m in re.finditer(r'\breturn\b([^;]*);', clean)]


def infer_error_convention(code: str,
                           extra_sources: Optional[Sequence[str]] = None
                           ) -> ErrorConvention:
    """Infer how *this* function reports failure.

    Order of preference:

    1. A ``goto cleanup``-style label already used in the function — jumping to
       existing cleanup is always safer than an early ``return`` that could
       leak the resources the function has already acquired.
    2. An error-looking value the function already returns (``-1``, ``E_FAIL``,
       ``STATUS_ERROR``, ``FALSE`` ...), chosen by frequency.
    3. ``return;`` when the function is ``void``.
    4. Callee/caller snippets, if the defect function itself is inconclusive.

    Returns a convention with ``kind == 'unknown'`` when nothing can be read
    from the source; callers must not invent one in that case.
    """
    if not code or not code.strip():
        return ErrorConvention('', 'unknown', 'no source available', 0.0)

    # 1. existing cleanup path
    labels = _collect_goto_targets(code)
    if labels:
        preferred = next(
            (l for l in labels if l.lower() in _PREFERRED_GOTO_LABELS), labels[0])
        return ErrorConvention(
            f'goto {preferred};', 'goto',
            f'the function already uses `goto {preferred};` for its failure path',
            0.9)

    # 2. an error value the function itself returns
    exprs = _collect_return_exprs(code)
    error_exprs = [e for e in exprs if _looks_like_error_value(e)]
    if error_exprs:
        counts: Dict[str, int] = {}
        for e in error_exprs:
            counts[e] = counts.get(e, 0) + 1
        # Most frequent wins; ties break toward the earliest occurrence.
        best = max(counts, key=lambda e: (counts[e], -error_exprs.index(e)))
        return ErrorConvention(
            f'return {best};', 'return_value',
            f'the function already returns `{best}` on its failure paths', 0.85)

    # 3. void function
    if _function_returns_void(code):
        if any(e == '' for e in exprs):
            return ErrorConvention(
                'return;', 'return_void',
                'the function is void and returns early elsewhere', 0.75)
        return ErrorConvention(
            'return;', 'return_void', 'the function has a void return type', 0.6)

    # 4. widen to callee/caller context
    for extra in (extra_sources or ()):
        if not extra or not isinstance(extra, str):
            continue
        nested = infer_error_convention(extra)
        if nested.known and nested.kind == 'return_value':
            return nested._replace(
                confidence=max(nested.confidence - 0.25, 0.4),
                evidence=nested.evidence + ' (observed in related function)')

    return ErrorConvention('', 'unknown',
                           'no return or goto convention could be read from the '
                           'analysed function', 0.0)


# --------------------------------------------------------------------------- #
# placeholder detection
# --------------------------------------------------------------------------- #
def _code_part_of_fix(fix: str) -> str:
    """Strip trailing ``//`` annotations so scans see only the patch itself.

    Templates append provenance comments such as ``// CWE-416 CERT MEM30-C``.
    Those are documentation, not code to compile, and their identifiers must
    never be mistaken for unresolved placeholders.
    """
    lines = []
    for line in (fix or '').splitlines():
        lines.append(re.sub(r'/\*.*?\*/', ' ', line).split('//', 1)[0])
    return '\n'.join(lines)


def unresolved_placeholders(fix: str, code: str) -> List[str]:
    """Return the genuinely unresolved tokens in ``fix``.

    A token counts as a placeholder when it could not have come from the
    analysed source:

    * ``{var}`` — a format field the interpolation failed to fill;
    * ``?`` — the fallback emitted when argument parsing gives up;
    * an ALL_CAPS macro-like identifier that appears in neither the source nor
      the C standard set (``ARRAY_SIZE`` in a codebase that never defines it).

    An ALL_CAPS name that *does* appear in the source is not a placeholder — it
    is the project's own macro and the patch is right to use it.  Only the
    executable part of the patch is scanned; ``// CWE-…`` trailers are not.
    """
    if not fix:
        return []
    body = _code_part_of_fix(fix)
    found: List[str] = []

    for m in re.finditer(r'\{[A-Za-z_]\w*\}', body):
        found.append(m.group(0))

    # '?' standing in for an argument the parser could not recover.
    if re.search(r'(?:^|[\s(,])\?(?:[\s),;]|$)', body):
        found.append('?')

    source_ids = set(re.findall(r'\b[A-Za-z_]\w*\b', code or ''))
    for m in re.finditer(r'\b[A-Z][A-Z0-9_]{2,}\b', body):
        name = m.group(0)
        if name in _STDLIB_IDENTIFIERS or name in source_ids:
            continue
        if name.startswith('CWE') or name.startswith('CERT'):
            continue
        if name not in found:
            found.append(name)

    return found


# --------------------------------------------------------------------------- #
# nested subscript detection
# --------------------------------------------------------------------------- #
def has_nested_subscript_at_line(code: str, line: int, code_start_line: int) -> bool:
    """True when the flagged statement indexes through another subscript.

    ``table[index_map[i]]`` has two independent bounds and cannot be repaired
    by a single-index guard.  The previous implementation counted ``[``
    characters, so it also fired on ``foo(a[i], b[j])`` — two unrelated,
    individually-boundable subscripts on one line — and withheld a perfectly
    good patch.  This matches actual nesting: a ``[`` that opens while another
    subscript is still open.
    """
    if not code:
        return False
    source_lines = code.splitlines()
    offset = line - code_start_line
    if not (0 <= offset < len(source_lines)):
        return False
    depth = 0
    for ch in source_lines[offset]:
        if ch == '[':
            depth += 1
            if depth >= 2:          # a subscript opened inside a subscript
                return True
        elif ch == ']':
            depth = max(0, depth - 1)
    return False


# --------------------------------------------------------------------------- #
# the gate
# --------------------------------------------------------------------------- #
def _apply_error_convention(fix: str, convention: ErrorConvention
                            ) -> Tuple[str, bool]:
    """Rewrite stock error returns to the function's own convention."""
    normalised = _STOCK_ERROR_RETURN.sub(ERROR_RETURN_SENTINEL, fix)
    if ERROR_RETURN_SENTINEL not in normalised:
        return fix, False
    if not convention.known:
        return normalised, False
    out = normalised.replace(ERROR_RETURN_SENTINEL, convention.statement)
    out = _STOCK_ERROR_COMMENT.sub('', out)
    # Collapse the blank line the removed comment may leave behind.
    out = re.sub(r'\n[ \t]*\n', '\n', out)
    return out, True


def gate_fix(fix: str, code: str, line: int, code_start_line: int, checker: str,
             extra_sources: Optional[Sequence[str]] = None,
             depth_note: str = "") -> GateResult:
    """Validate — and where possible repair — a proposed remediation.

    Returns a :class:`GateResult`.  ``reason`` is non-empty whenever the
    operator needs to be told something: either why no patch is shown, or that
    the shown patch had its error path adapted and should be reviewed.
    """
    candidate = (fix or '').strip()
    if not candidate:
        return GateResult('', '', False, False)

    # Terminal dispositions are not patches; pass them through untouched.
    low = candidate.lower()
    if low.startswith('no fix required'):
        return GateResult('No fix required.', '', False, False)
    if low.startswith('manual review required'):
        return GateResult('Manual review required.', '', False, False)

    if not code:
        note = ('No code-specific fix was generated because the source for the '
                'Coverity event path is unavailable.')
        if depth_note:
            note += ' ' + depth_note
        return GateResult('Manual review required.', note, False, False)

    convention = infer_error_convention(code, extra_sources)
    candidate, adjusted = _apply_error_convention(candidate, convention)
    candidate = candidate.strip()
    unresolved_error_path = ERROR_RETURN_SENTINEL in candidate

    # Genuine placeholders — the patch is not applicable as written.  The
    # sentinel is excluded here: it marks a known-unknown error path, which is
    # reported separately below rather than voiding an otherwise valid guard.
    scanned = candidate.replace(ERROR_RETURN_SENTINEL, '')
    placeholders = unresolved_placeholders(scanned, code)
    if placeholders:
        shown = ', '.join(f'`{p}`' for p in placeholders[:4])
        note = ('No code-specific fix was generated: the remediation still '
                f'contains unresolved placeholder(s) {shown} that do not exist '
                'in the analysed source, so applying it verbatim would not '
                'compile.')
        if depth_note:
            note += ' ' + depth_note
        return GateResult('Manual review required.', note, False, False)

    # Anchoring: the patch must name something real from this function.
    source_ids = set(re.findall(r'\b[A-Za-z_]\w*\b', code))
    patch_ids = set(re.findall(r'\b[A-Za-z_]\w*\b', scanned))
    if not ((patch_ids - _NON_ANCHORING) & source_ids):
        note = ('No code-specific fix was generated because the suggested '
                'change could not be anchored to identifiers in the analysed '
                'function.')
        if depth_note:
            note += ' ' + depth_note
        return GateResult('Manual review required.', note, False, False)

    # Nested subscripts have two independent bounds; one guard cannot prove both.
    if checker.startswith('OVERRUN') and \
            has_nested_subscript_at_line(code, line, code_start_line):
        return GateResult(
            'Manual review required.',
            'No code-specific fix was generated: the flagged expression uses a '
            'nested index, so the inner and outer bounds must be proved '
            'independently.',
            False, False, convention)

    # The guard is anchored and placeholder-free, but the module's failure
    # convention could not be read.  Show the patch with the branch marked,
    # rather than discarding a correct bounds check over its last line.
    if unresolved_error_path:
        readable = candidate.replace(ERROR_RETURN_SENTINEL,
                                     '/* report failure here */')
        return GateResult(
            readable,
            'The proposed guard is anchored to this function, but its error '
            f'path could not be matched to the module\'s convention: '
            f'{convention.evidence}. Replace the marked branch with whatever '
            'this file uses to report failure (error return code, goto '
            'cleanup, or an error callback) before applying.',
            True, False, convention)

    reason = ''
    if adjusted:
        reason = (f'Proposed fix uses this module\'s own error path — '
                  f'{convention.evidence}. Confirm it matches the surrounding '
                  f'code before applying.')
    return GateResult(candidate, reason, True, adjusted, convention)
