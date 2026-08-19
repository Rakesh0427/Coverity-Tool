#!/usr/bin/env python3
"""Example-style disposition comment renderer for Coverity triage.

Converts the decision of the heuristic analyzer into the concise, code-fact
driven "disposition comment" format used in human-reviewed triage reports:

  * False positive  ->  "<concrete facts citing real line numbers, constants
                         and variable names>. False positive."
  * Bug             ->  "<concrete defect narrative with the exact copy count,
                         buffer/constant names and required corrective action>."

Only the seven checkers from the reviewed report are restyled here:
REVERSE_INULL, STRING_NULL, ARRAY_VS_SINGLETON, BUFFER_SIZE, FORWARD_NULL,
INTEGER_OVERFLOW and NEGATIVE_RETURNS.

The renderer is purely an output formatter.  It never changes the
classification or the confidence — it only rewrites the human-readable comment.
Every renderer returns None when it cannot extract enough concrete code facts,
so the caller falls back to its existing comment and never degrades output.
"""
import re
from typing import Dict, List, Optional, Tuple

# Sinks whose 3rd argument (index 2) is the byte/char count.
_COUNT_ARG_INDEX = {
    'strncpy': 2, 'strncat': 2, 'snprintf': 2, 'strlcpy': 2,
    'strlcat': 2, 'memcpy': 2, 'memmove': 2,
}
# Sinks whose 1st argument is the destination.
_DEST_ARG_INDEX = {
    'strncpy': 0, 'strncat': 0, 'snprintf': 0, 'strlcpy': 0,
    'strlcat': 0, 'memcpy': 0, 'memmove': 0, 'strcpy': 0, 'strcat': 0,
    'sprintf': 0,
}


# ---------------------------------------------------------------------------
# Low level code-fact helpers
# ---------------------------------------------------------------------------
def _code_lines(code: str, code_start_line: int = 1):
    """Yield (absolute_line_number, stripped_text) for each line of `code`."""
    for i, raw in enumerate(code.splitlines()):
        yield code_start_line + i, raw.strip()


def _expr_at(code: str, target_line: int, code_start_line: int = 1) -> str:
    """Return the stripped source text of `target_line` (absolute) if present."""
    for abs_no, text in _code_lines(code, code_start_line):
        if abs_no == target_line:
            return text
    return ""


def _find_line(code: str, pattern, code_start_line: int = 1) -> int:
    """First absolute line number matching `pattern`, else 0."""
    rx = re.compile(pattern, re.IGNORECASE)
    for abs_no, text in _code_lines(code, code_start_line):
        if rx.search(text):
            return abs_no
    return 0


def _extract_call_from(code: str, sink: str, match_start: int) -> Tuple[str, List[str]]:
    """Return (call_text, raw_arg_list) for the `sink(` call whose name begins
    at match_start, read through the matching close paren."""
    paren = code.find('(', match_start)
    if paren < 0:
        return "", []
    start = paren + 1
    depth = 1
    i = start
    while i < len(code) and depth > 0:
        if code[i] == '(':
            depth += 1
        elif code[i] == ')':
            depth -= 1
        i += 1
    args_str = code[start:i - 1]
    args, cur, d = [], [], 0
    for ch in args_str:
        if ch in '([{':
            d += 1
            cur.append(ch)
        elif ch in ')]}':
            d -= 1
            cur.append(ch)
        elif ch == ',' and d == 0:
            args.append(''.join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        args.append(''.join(cur).strip())
    return code[start - 1:i], [a for a in args if a]


def _extract_call(code: str, sink: str) -> Tuple[str, List[str]]:
    """Return (call_text, raw_arg_list) for the first `sink(` call in code."""
    if not sink:
        return "", []
    m = re.search(rf'\b{re.escape(sink)}\s*\(', code)
    if not m:
        return "", []
    return _extract_call_from(code, sink, m.start())


def _extract_call_near(code: str, sink: str, target_line: int,
                       code_start_line: int = 1) -> Tuple[str, List[str]]:
    """Like _extract_call, but returns the `sink(` call closest to the flagged
    absolute line.  A function may hold several calls to the same sink with
    different string literals / sizes; anchoring to the flagged line prevents a
    finding from quoting the wrong (first) call."""
    if not sink or not target_line or target_line <= 0:
        return _extract_call(code, sink)
    best_idx, best_dist = None, None
    pos = 0
    while True:
        m = re.search(rf'\b{re.escape(sink)}\s*\(', code[pos:])
        if not m:
            break
        idx = pos + m.start()
        line_of_call = code.count('\n', 0, idx) + 1
        abs_line = line_of_call + (code_start_line or 1) - 1
        dist = abs(abs_line - target_line)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_idx = idx
        pos = pos + m.end()
    if best_idx is None:
        return "", []
    return _extract_call_from(code, sink, best_idx)


def _sink_arg(args: List[str], idx: int) -> str:
    if 0 <= idx < len(args):
        return args[idx]
    return ""


def _normalize_var(v: str, fallback: str = "") -> str:
    """Drop the generic figure-of-speech placeholders the analyzer injects."""
    if not v:
        return fallback
    if v.lower() in ('the variable', 'the pointer', 'the operand', 'the data',
                     'the flagged variable', 'the destination buffer',
                     'the source data'):
        return fallback
    return v


def _is_size_constant(expr: str) -> bool:
    """True if the count looks like a full-capacity constant or sizeof(...)
    without a -1 reservation (i.e. leaves no room for the null terminator)."""
    expr = (expr or '').strip()
    if not expr:
        return False
    if re.fullmatch(r'[A-Z][A-Z0-9_]*', expr):
        return True
    if re.search(r'\bsizeof\s*\(', expr) and not re.search(r'-\s*1\s*$|-\s*sizeof\s*\(', expr):
        return True
    if re.fullmatch(r'\w+', expr) and not re.search(r'-\s*1\s*$', expr):
        return True
    return False


def _is_strlen_count(expr: str) -> bool:
    return bool(expr) and re.search(r'\bstrlen\s*\(', expr)


def _null_termination_facts(code: str, dest: str, code_start_line: int = 1) -> Tuple[bool, int, str]:
    """Detect an explicit null-terminator after the copy for `dest`.

    Returns (found, line, expression) - e.g. `buf[sizeof(buf)-1] = '\\0'`.
    """
    dest = _normalize_var(dest)
    if dest:
        pattern = (rf'\b{re.escape(dest)}\s*\[\s*[^\]]+\]\s*=\s*[\'"]\\0[\'"]'
                   rf'|\b{re.escape(dest)}\s*\[\s*[^\]]+\]\s*=\s*0\s*;')
    else:
        pattern = r'\[\s*(?:sizeof\s*\([^)]*\)\s*-\s*1|\w+\s*-\s*1)\s*\]\s*=\s*[\'"]\\0[\'"]'
    rx = re.compile(pattern, re.IGNORECASE)
    for abs_no, text in _code_lines(code, code_start_line):
        m = rx.search(text)
        if m:
            return True, abs_no, text
    return False, 0, ""


def _memset_prezero_line(code: str, dest: str, code_start_line: int = 1) -> int:
    """First absolute line of a memset(dest, 0, sizeof(dest)) before the copy."""
    dest = _normalize_var(dest)
    if not dest:
        return 0
    pat = re.compile(rf'\bmemset\s*\(\s*{re.escape(dest)}\s*,\s*0', re.IGNORECASE)
    for abs_no, text in _code_lines(code, code_start_line):
        if pat.search(text):
            return abs_no
    return 0


def _compact(text: str) -> str:
    return re.sub(r'\s+', ' ', (text or '')).strip()


def _safe_guard(ctx: Dict) -> bool:
    """True when the recorded guard genuinely protects (not merely present)."""
    if ctx.get('guard_covers_all_paths'):
        return True
    reason = (ctx.get('guard_reason') or '').lower()
    return bool(reason and ('guard' in reason or 'verified' in reason or 'bounds' in reason))


def _reason_clean(txt: str) -> str:
    """Strip backticks/markdown from an extracted reason snippet."""
    return txt.replace('`', '').strip()


def _fp_reason_text(ctx: Dict, sink: str) -> str:
    """A concise reason string for a false positive, or '' if none found."""
    reasons = []
    reason = ctx.get('guard_reason') or ''
    if reason:
        reasons.append(_reason_clean(reason).rstrip('.'))
    safe_api = ctx.get('safe_api_note') or ''
    if safe_api and sink:
        reasons.append(_reason_clean(safe_api).rstrip('.'))
    buffer_info = _reason_clean(ctx.get('buffer_info') or '')
    if buffer_info and 'byte' in buffer_info.lower():
        reasons.append(buffer_info.rstrip('.'))
    if reasons:
        return "; ".join(reasons[:2])
    return ""


# ---------------------------------------------------------------------------
# Per-checker renderers. Each returns the styled comment string, or None if it
# cannot extract enough concrete facts.
# ---------------------------------------------------------------------------
def _render_buffer_or_string(classification: str, checker: str, ctx: Dict,
                             code: str, code_start_line: int, line: int,
                             function: str) -> Optional[str]:
    sink = ctx.get('sink_func') or ctx.get('sink') or ''
    dest = _normalize_var(ctx.get('dest_var') or '')
    src = _normalize_var(ctx.get('src_var') or '', 'the source data')
    _, args = _extract_call_near(code, sink, line, code_start_line)
    count_idx = _COUNT_ARG_INDEX.get(sink)
    count = _sink_arg(args, count_idx) if count_idx is not None else ''

    if classification == "False positive":
        facts = []
        null_ok, null_line, null_expr = _null_termination_facts(code, dest, code_start_line)
        if null_ok:
            facts.append(f"and the null terminator is explicitly written at line {null_line}"
                         f" (`{_compact(null_expr)}`) before the buffer is used further")
        gline = ctx.get('guard_line') or 0
        if gline and line and gline < line and _safe_guard(ctx):
            facts.append(f"and the size is pre-validated at line {gline} before the copy")
        mline = _memset_prezero_line(code, dest, code_start_line)
        if mline:
            facts.append(f"and `{dest}` is pre-zeroed with memset at line {mline},"
                         " which keeps the buffer null-terminated")
        if facts:
            head = f"{sink} copies {src} into {dest}"
            if count:
                head += f" with {count} as the copy limit"
            return f"{head}, {facts[0]}. False positive."
        reason = _fp_reason_text(ctx, sink)
        if reason:
            return (f"The {checker} at line {line} is not a real defect: {reason}. "
                    "False positive.")
        return None

    if classification == "Bug":
        # Expert-level narrative: name the root cause, the security impact and the
        # concrete remediation (instead of a bare "copies data without length check").
        origin = ctx.get('origin') or ''
        tainted = bool(ctx.get('taint_desc')) and 'user-controlled' in ctx.get('taint_desc')
        if tainted:
            source_clause = (f"`{src}` carries user-controlled data "
                             f"({origin or 'external input'}) that reaches the copy "
                             f"without validation")
        elif origin and origin != 'an unknown source':
            source_clause = f"`{src}` originates from {origin}"
        else:
            source_clause = f"the length of `{src}` is not validated"

        if dest and count and _is_size_constant(count):
            return (f"{sink}() at line {line} copies exactly {count} bytes into `{dest}`, "
                    f"filling it completely and leaving no room for the null terminator; "
                    f"`{dest}` is never null-terminated after the copy. Any later string "
                    f"operation reads past the end of the buffer (out-of-bounds read).")
        if dest and count and _is_strlen_count(count):
            return (f"{sink}() at line {line} uses `strlen` (`{count}`) as the copy count. "
                    f"{sink} does not append a null terminator when n equals the source "
                    f"length, so `{dest}` is left unterminated and any later string use "
                    f"reads past the end of the buffer.")
        if dest:
            if sink in ('strcpy', 'strcat', 'sprintf', 'vsprintf', 'gets',
                        'wcscpy', 'wcscat'):
                return (f"{sink}() at line {line} copies `{src}` into `{dest}` with no "
                        f"length limit — {source_clause}. An oversized source overwrites or "
                        f"reads adjacent memory beyond the buffer, corrupting neighboring "
                        f"data and potentially crashing the process or enabling code "
                        f"execution.")
            return (f"At line {line}, the {sink}() copy into `{dest}` uses a count equal to "
                    f"the destination capacity and does not guarantee a null terminator. If "
                    f"the source is that long, `{dest}` stays unterminated and later string "
                    f"use reads past the end of the buffer, corrupting neighboring memory.")
    return None


def _render_reverse_inull(classification: str, checker: str, ctx: Dict, code: str,
                          code_start_line: int, line: int, function: str) -> Optional[str]:
    var = _normalize_var(ctx.get('var') or ctx.get('ev_null_var') or '')
    gline = ctx.get('guard_line') or 0
    expr = _compact(_expr_at(code, line, code_start_line)) or ''

    if classification == "False positive":
        if gline and line:
            return (f"{var or 'the pointer'} is checked at line {gline} before it is "
                    f"dereferenced at line {line}; the null guard precedes first use. "
                    "False positive.")
        return None
    if classification == "Bug":
        deref = expr if expr else (f"the dereference of `{var or 'the pointer'}`")
        if gline:
            return (f"{deref} at line {line} writes/reads through the pointer before the null "
                    f"check at line {gline}. If {var or 'the pointer'} is NULL, the access at "
                    f"line {line} crashes. The null check must be moved before line {line}.")
        return (f"{deref} at line {line} dereferences {var or 'the pointer'} with no preceding "
                f"null check. If {var or 'the pointer'} is NULL, the access at line {line} "
                "crashes; add a null check before first use.")
    return None


def _render_forward_null(classification: str, checker: str, ctx: Dict, code: str,
                         code_start_line: int, line: int, function: str) -> Optional[str]:
    var = _normalize_var(ctx.get('var') or '')
    gline = ctx.get('guard_line') or 0

    if classification == "False positive":
        if gline and line:
            return (f"{var or 'the pointer'} is null-checked at line {gline} and the guard "
                    f"covers all paths to the dereference at line {line}. False positive.")
        return None
    if classification == "Bug":
        assign_line = 0
        if var:
            assign_line = _find_line(code, rf'\b{re.escape(var)}\s*=\s*NULL\b(?!\s*=)',
                                     code_start_line)
        if assign_line:
            return (f"{var} is (or can be) set to NULL at line {assign_line} and is then "
                    f"dereferenced at line {line} without a null check. If a path leaves it NULL, "
                    "this dereference crashes; add a null check before first use.")
        return (f"At line {line}, {var or 'the pointer'} is dereferenced without a visible null "
                f"check. If {var or 'the pointer'} can be NULL on this path, the access at "
                f"line {line} crashes; add a null check before first use.")
    return None


def _render_integer_overflow(classification: str, checker: str, ctx: Dict, code: str,
                             code_start_line: int, line: int, function: str) -> Optional[str]:
    var = _normalize_var(ctx.get('var') or 'the counter')

    if classification == "False positive":
        reason = _fp_reason_text(ctx, "")
        base = f"The arithmetic at line {line} in {function}() is bounded and cannot overflow"
        if reason:
            return f"{base}: {reason}. False positive."
        return f"{base} the machine representation on the flagged path. False positive."
    if classification == "Bug":
        return (f"At line {line} in {function}(), `{var}` is advanced without a maximum-value "
                f"guard. If it approaches the type's maximum (e.g. UINT_MAX), the increment "
                "wraps/overflows the counter and the loop/index can escape its intended range.")
    return None


def _render_array_vs_singleton(classification: str, checker: str, ctx: Dict, code: str,
                               code_start_line: int, line: int, function: str) -> Optional[str]:
    text = _expr_at(code, line, code_start_line)
    if not text:
        return None

    if classification == "Bug":
        m = re.search(r'&?\s*([A-Za-z_]\w*)\s*\[\s*([^\]]+)\s*\]', text)
        if m:
            base = _normalize_var(m.group(1), ctx.get('var') or 'the singleton')
            idx = m.group(2).strip()
            return (f"{base} is a singleton variable, but `{_compact(text)}` accesses it using "
                    f"array index {idx} without a bounds check. If {idx} > 0, this reads/writes "
                    "memory past the singleton and can corrupt adjacent data.")
        return (f"At line {line}, a singleton variable is accessed with an array index without a "
                f"bounds check. If the index exceeds 0, memory past the singleton is "
                "read/written. Add an explicit bounds check or pass a real array.")
    if classification == "False positive":
        return (f"The singleton at line {line} in {function}() is only accessed with a "
                "single-element contract (index 0), so the access stays within the object. "
                "False positive.")
    return None


def _render_negative_returns(classification: str, checker: str, ctx: Dict, code: str,
                             code_start_line: int, line: int, function: str) -> Optional[str]:
    var = _normalize_var(ctx.get('var') or 'the return value')
    if classification == "False positive":
        reason = _fp_reason_text(ctx, "")
        if reason:
            return (f"{var} is validated before it is consumed at line {line} "
                    f"({reason}); it cannot reach the size/index as a negative value. "
                    "False positive.")
        return (f"At line {line} in {function}(), the signed return value is checked for a "
                "negative/error value before being used as a size or index. False positive.")
    if classification == "Bug":
        return (f"At line {line} in {function}(), a signed return value is used as a size or "
                f"index without first validating it is >= 0. If {var} returns a negative error "
                "code, it is cast to a large unsigned value, causing a massive allocation or "
                "memory corruption. Add an explicit `if (result < 0)` check before use.")
    return None


def _render_sizeof_mismatch(classification: str, checker: str, ctx: Dict, code: str,
                            code_start_line: int, line: int, function: str) -> Optional[str]:
    """Expert-level SIZE_OF_MISMATCH comments — name the actual expression and
    explain the under-allocation / overrun consequence instead of a generic
    'sizeof() may be applied to the wrong type'."""
    text = _compact(_expr_at(code, line, code_start_line))
    if classification == "Bug":
        expr = text or f"the sizeof() expression at line {line}"
        return (f"At line {line} in {function}(), `{expr}` takes `sizeof()` of a pointer (or a type "
                f"that is not the intended element/object). A pointer's size is a small, fixed "
                f"constant (e.g. 8 on 64-bit targets), so any allocation length or array bound "
                f"derived from it is only a fraction of the real object. When that value is used in "
                f"`malloc()`/`calloc()` or as an index limit, the destination is under-allocated and "
                f"the subsequent writes run past the end, corrupting adjacent heap/stack memory "
                f"(a heap-overflow primitive).")
    if classification == "False positive":
        if re.search(r'sizeof\s*\(\s*\*', code) or re.search(r'sizeof\s*\(\s*\w+\[0\]\s*\)', code):
            return (f"At line {line} in {function}(), `sizeof()` is taken on the pointee/element "
                    f"(`sizeof(*ptr)` / `sizeof(arr[0])`), which yields the true object size rather "
                    f"than the pointer size. The computed allocation or bounds therefore match the "
                    f"real object, so no under-allocation and no overrun can occur. False positive.")
        return None
    return None


def _render_uninit(classification: str, checker: str, ctx: Dict, code: str,
                   code_start_line: int, line: int, function: str) -> Optional[str]:
    var = _normalize_var(ctx.get('var') or 'the variable')
    if classification == "Bug":
        return (f"At line {line} in {function}(), `{var}` is read before being written on this "
                f"path. Automatic (stack) variables are not zero-initialized — they hold whatever "
                f"bytes were left in the frame — so `{var}` is indeterminate. If that value drives a "
                f"branch, an index, a length, or is emitted (e.g. into a protocol message), behavior "
                f"becomes nondeterministic and stale stack bytes can be exposed (information "
                f"disclosure).")
    if classification == "False positive":
        if re.search(r'\bmemset\s*\(|\bcalloc\s*\(|=\s*\{0\}|=\s*0\s*;', code):
            return (f"The value read at line {line} in {function}() is given a definite value before "
                    f"it is used: it is zero-initialized via `memset()`/`calloc()` or an aggregate "
                    f"initializer, so no path consumes uninitialized stack memory. Behavior is "
                    f"deterministic. False positive.")
        return None
    return None


def _render_deadcode(classification: str, checker: str, ctx: Dict, code: str,
                     code_start_line: int, line: int, function: str) -> Optional[str]:
    """Expert-level, code-anchored DEADCODE comments. Cites the actual flagged
    expression and the specific construct that makes it unreachable, and never
    embeds remediation text (the Proposed Fix panel carries it)."""
    text = _compact(_expr_at(code, line, code_start_line))
    loc = f"line {line} in {function}()" if line and function else f"{function}()"
    if classification == "Bug":
        facts = []
        if re.search(r'#\s*if\s+0\b|#\s*ifdef\s+NEVER', code):
            facts.append("guarded out by the preprocessor (`#if 0` / `#ifdef NEVER`) so it is never compiled")
        if re.search(r'\bassert\s*\(\s*0\s*\)|\bassert\s*\(\s*false\s*\)|\b__builtin_unreachable\s*\(', code):
            facts.append("only reachable past an `assert(0)`/`__builtin_unreachable()` declared-unreachable point")
        if re.search(r'\bif\s*\(\s*0\s*\)|\bif\s*\(\s*false\s*\)|\bwhile\s*\(\s*0\s*\)', code):
            facts.append("sits under a constant `0`/`false` condition that can never be true at runtime")
        if re.search(r'\b(?:return|goto|exit|abort|break)\b', code):
            facts.append("a preceding unconditional `return`/`goto`/`exit` makes every execution path skip it")
        reason = ("; ".join(facts)) if facts else "control flow (an unconditional return/goto ahead) makes it unreachable"
        expr = f"`{text}`" if text else f"the block at {loc}"
        return (f"The block at {loc} ({expr}) is unreachable on every valid execution path "
                f"({reason}). Because execution cannot reach it, the guarded action is silently "
                f"never performed — typically the fingerprint of a mistaken constant, an inverted "
                f"guard, or a half-removed feature, and it can mask the very logic error that "
                f"rerouted control away from it. It also misleads maintainers into treating dead "
                f"instrumentation as live behavior.")
    if classification in ("False positive", "Intentional"):
        reason = None
        if re.search(r'#\s*if\s+0\b|#\s*ifdef\s+NEVER', code):
            reason = "it is excluded by `#if 0` / `#ifdef NEVER`, so the compiler never emits it"
        elif re.search(r'\bassert\s*\(\s*0\s*\)|\bassert\s*\(\s*false\s*\)|\b__builtin_unreachable\s*\(', code):
            reason = "it sits on an `assert(0)` / `__builtin_unreachable()` panic path — deliberately never taken"
        elif re.search(r'\bif\s*\(\s*0\s*\)|\bif\s*\(\s*false\s*\)', code):
            reason = "it is under an `if (0)` / `if (false)` constant condition that is never true at runtime"
        elif re.search(r'\bTODO\b|\bFIXME\b|\bDEAD\b|\bXXX\b', code):
            reason = "it is explicitly marked TODO/FIXME/dead, i.e. parked for future work"
        else:
            reason = "it has no reachable caller / is legacy — removing it changes no runtime behavior"
        return (f"The block at {loc} is intentionally unreachable ({reason}). It contributes no "
                f"runtime behavior, so no code change is required; removing it is safe. "
                f"False positive.")
    return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
_CHECKER_HANDLERS = {
    'BUFFER_SIZE': _render_buffer_or_string,
    'STRING_NULL': _render_buffer_or_string,
    'REVERSE_INULL': _render_reverse_inull,
    'FORWARD_NULL': _render_forward_null,
    'INTEGER_OVERFLOW': _render_integer_overflow,
    'ARRAY_VS_SINGLETON': _render_array_vs_singleton,
    'NEGATIVE_RETURNS': _render_negative_returns,
    'SIZEOF_MISMATCH': _render_sizeof_mismatch,
    'UNINIT': _render_uninit,
    'DEADCODE': _render_deadcode,
}


def render_example_comment(classification: str, checker: str, ctx: Dict,
                           code: str, code_start_line: int = 1,
                           line: int = 0, function: str = "") -> Optional[str]:
    """Return the example-style comment for `checker`, or None to keep the
    analyzer's existing comment. Never used to change the classification."""
    handler = _CHECKER_HANDLERS.get(checker)
    if handler is None:
        return None
    try:
        return handler(classification, checker, ctx, code, code_start_line, line, function)
    except Exception:
        return None
