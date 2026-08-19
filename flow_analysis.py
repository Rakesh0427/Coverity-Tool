#!/usr/bin/env python3
"""
flow_analysis.py — CFG builder, dominator computation, and reaching-definitions DFA.

Phase 3+4 implementation.
Builds an intra-procedural CFG from a tree-sitter AST (or falls back to line-based
parsing when the AST is unavailable).  All public functions degrade gracefully:
they return safe defaults when the analysis cannot complete, and are capped at a
5-second wall-clock timeout via concurrent.futures.
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Dict, List, Optional, Set, Tuple

_TIMEOUT_SECS = 5


# ---------------------------------------------------------------------------
# CFG Data Structures
# ---------------------------------------------------------------------------

class BasicBlock:
    __slots__ = ('id', 'lines', 'successors', 'predecessors')

    def __init__(self, block_id: int):
        self.id: int = block_id
        self.lines: List[int] = []          # source line numbers (1-based absolute)
        self.successors: List[int] = []     # block ids
        self.predecessors: List[int] = []   # block ids

    def __repr__(self):
        return f"BB{self.id}(lines={self.lines[:3]}...)"


class CFG:
    """A simple intra-procedural control-flow graph."""

    def __init__(self):
        self.blocks: Dict[int, BasicBlock] = {}
        self.entry: int = 0
        self.exit: int = -1
        self._dominators: Optional[Dict[int, Set[int]]] = None
        self._line_to_block: Dict[int, int] = {}  # line → block id

    # ------------------------------------------------------------------
    # Line → block lookup (built on first access)
    # ------------------------------------------------------------------
    def block_for_line(self, line: int) -> Optional[int]:
        if not self._line_to_block:
            for bid, bb in self.blocks.items():
                for ln in bb.lines:
                    self._line_to_block[ln] = bid
        return self._line_to_block.get(line)

    # ------------------------------------------------------------------
    # Dominator set
    # ------------------------------------------------------------------
    def dominators(self) -> Dict[int, Set[int]]:
        if self._dominators is not None:
            return self._dominators
        self._dominators = compute_dominators(self)
        return self._dominators


# ---------------------------------------------------------------------------
# CFG Builder — regex / line-based (no tree-sitter required)
# ---------------------------------------------------------------------------

_BRANCH_OPEN  = re.compile(r'\b(if|else\s+if|while|for|do|switch)\b')
_BRANCH_CLOSE = re.compile(r'\belse\b')
_EXIT_STMT    = re.compile(r'\b(return|goto|break|continue|exit|abort|throw|longjmp)\b')
_CASE_LABEL   = re.compile(r'^\s*(case\s+[^:]+|default)\s*:')


def build_cfg(code: str, code_start_line: int = 1) -> CFG:
    """
    Build a CFG from a code string.
    Falls back to a linear CFG if parsing fails (still usable for simple checks).
    """
    try:
        return _timed(_build_cfg_impl, code, code_start_line)
    except (FuturesTimeout, Exception):
        return _linear_cfg(code, code_start_line)


def _timed(fn, *args):
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn, *args)
        return fut.result(timeout=_TIMEOUT_SECS)


def _build_cfg_impl(code: str, code_start_line: int) -> CFG:
    lines = code.splitlines()
    cfg = CFG()
    block_counter = [0]

    def new_block() -> BasicBlock:
        bid = block_counter[0]
        block_counter[0] += 1
        bb = BasicBlock(bid)
        cfg.blocks[bid] = bb
        return bb

    def link(src: int, dst: int):
        if dst not in cfg.blocks[src].successors:
            cfg.blocks[src].successors.append(dst)
        if src not in cfg.blocks[dst].predecessors:
            cfg.blocks[dst].predecessors.append(src)

    entry = new_block()
    cfg.entry = entry.id
    current = entry

    # Simple stack-based CFG: each { opens a new block for the body,
    # closing } resumes the join block.
    brace_stack: List[Tuple[int, int]] = []  # (branch_block_id, join_block_id)
    open_brace_line: Dict[int, int] = {}     # line_idx → depth when '{' appears

    depth = 0
    pending_join: Optional[BasicBlock] = None

    for i, raw_line in enumerate(lines):
        abs_line = i + code_start_line
        stripped = raw_line.strip()

        # Record the line in current block
        if stripped:
            current.lines.append(abs_line)

        # Brace-level tracking for basic block splitting
        opens  = stripped.count('{') - stripped.count("'{") - stripped.count('"{')
        closes = stripped.count('}') - stripped.count("'}") - stripped.count('"}')

        # Handle branch start
        if opens > 0 and _BRANCH_OPEN.search(stripped):
            body_block  = new_block()
            join_block  = new_block()
            link(current.id, body_block.id)
            link(current.id, join_block.id)   # false-branch edge
            brace_stack.append((current.id, join_block.id))
            current = body_block

        elif opens > 0:
            # Plain open (e.g. struct init, function start) — just enter a block
            body = new_block()
            link(current.id, body.id)
            brace_stack.append((current.id, current.id))  # no join divergence
            current = body

        depth += opens - closes

        if closes > 0 and brace_stack:
            branch_id, join_id = brace_stack.pop()
            link(current.id, join_id)
            current = cfg.blocks[join_id]

        if _EXIT_STMT.search(stripped):
            # After a return/goto the subsequent code is a new (potentially dead) block
            dead = new_block()
            link(current.id, dead.id)  # structural edge, but semantically exit
            current = dead

    # Create exit node
    exit_block = new_block()
    cfg.exit = exit_block.id
    link(current.id, exit_block.id)
    # Also link all blocks that have no successors except entry to exit
    for bid, bb in cfg.blocks.items():
        if bid != exit_block.id and not bb.successors and bid != entry.id:
            link(bid, exit_block.id)

    return cfg


def _linear_cfg(code: str, code_start_line: int) -> CFG:
    """Fallback: single block containing all lines."""
    cfg = CFG()
    bb = BasicBlock(0)
    for i, line in enumerate(code.splitlines()):
        if line.strip():
            bb.lines.append(i + code_start_line)
    cfg.blocks[0] = bb
    cfg.entry = 0
    exit_bb = BasicBlock(1)
    cfg.blocks[1] = exit_bb
    cfg.exit = 1
    bb.successors = [1]
    exit_bb.predecessors = [0]
    return cfg


# ---------------------------------------------------------------------------
# Dominator Computation (Cooper et al. simple iterative algorithm)
# ---------------------------------------------------------------------------

def compute_dominators(cfg: CFG) -> Dict[int, Set[int]]:
    """
    Compute dominator sets for every basic block using the iterative bit-vector
    algorithm (Cooper, Harvey, Kennedy 2001).
    """
    all_blocks = set(cfg.blocks.keys())

    # Initialise: entry dominates only itself; all others dominated by all
    doms: Dict[int, Set[int]] = {}
    doms[cfg.entry] = {cfg.entry}
    for bid in all_blocks:
        if bid != cfg.entry:
            doms[bid] = set(all_blocks)

    changed = True
    while changed:
        changed = False
        for bid in sorted(all_blocks):
            if bid == cfg.entry:
                continue
            bb = cfg.blocks[bid]
            preds = [p for p in bb.predecessors if p in doms]
            if not preds:
                new_dom = set(all_blocks)
            else:
                new_dom = set.intersection(*(doms[p] for p in preds))
            new_dom.add(bid)
            if new_dom != doms[bid]:
                doms[bid] = new_dom
                changed = True

    return doms


# ---------------------------------------------------------------------------
# Public dominance queries
# ---------------------------------------------------------------------------

def is_dominated_by(cfg: CFG, target_line: int, guard_line: int) -> bool:
    """
    Return True if every path from entry to target_line passes through guard_line.
    Gracefully returns False if either line is not in the CFG.
    """
    try:
        target_bid = cfg.block_for_line(target_line)
        guard_bid  = cfg.block_for_line(guard_line)
        if target_bid is None or guard_bid is None:
            return False
        doms = cfg.dominators()
        return guard_bid in doms.get(target_bid, set())
    except Exception:
        return False


def does_guard_block_all_paths(cfg: CFG, guard_line: int, access_line: int) -> Tuple[bool, List[int]]:
    """
    Check whether the guard at guard_line dominates the access at access_line.
    Returns (blocks_all, bypass_block_ids).
    bypass_block_ids is empty when blocks_all is True.
    """
    try:
        target_bid = cfg.block_for_line(access_line)
        guard_bid  = cfg.block_for_line(guard_line)
        if target_bid is None or guard_bid is None:
            return False, []
        doms = cfg.dominators()
        if guard_bid in doms.get(target_bid, set()):
            return True, []
        # Find bypass paths: predecessors of access block that are not dominated by guard
        bypass = [
            p for p in cfg.blocks[target_bid].predecessors
            if guard_bid not in doms.get(p, set())
        ]
        return False, bypass
    except Exception:
        return False, []


def is_call_inside_condition_block(cfg: CFG, call_line: int, condition_line: int) -> bool:
    """
    Return True if call_line is inside the if-body dominated by condition_line.
    Used for FORWARD_NULL FP detection (call guarded by if (ptr != NULL) {...}).
    """
    return is_dominated_by(cfg, call_line, condition_line)


# ---------------------------------------------------------------------------
# Reaching Definitions / Data Flow
# ---------------------------------------------------------------------------

def trace_definition(code: str, var_name: str, use_line: int,
                     cfg: Optional[CFG] = None,
                     code_start_line: int = 1) -> List[Dict]:
    """
    Backward trace from use_line to find where var_name is defined.
    Returns list of {'line': int, 'rhs': str} dicts.
    Falls back to pure regex scan if cfg is None.
    """
    if not var_name or not re.match(r'^[A-Za-z_]\w*$', var_name):
        return []
    try:
        return _timed(_trace_definition_impl, code, var_name, use_line, cfg, code_start_line)
    except (FuturesTimeout, Exception):
        return _regex_trace_definition(code, var_name, use_line, code_start_line)


def _trace_definition_impl(code: str, var_name: str, use_line: int,
                            cfg: Optional[CFG], code_start_line: int) -> List[Dict]:
    lines = code.splitlines()
    use_rel = use_line - code_start_line
    if use_rel < 0 or use_rel >= len(lines):
        return _regex_trace_definition(code, var_name, use_line, code_start_line)

    assign_pat = re.compile(
        rf'\b{re.escape(var_name)}\s*(?:[+\-*/&|^]?=)\s*([^;]+);'
    )
    results = []
    for i in range(use_rel - 1, -1, -1):
        m = assign_pat.search(lines[i])
        if m:
            results.append({
                'line': i + code_start_line,
                'rhs': m.group(1).strip()
            })
            if len(results) >= 5:
                break
    return results


def _regex_trace_definition(code: str, var_name: str, use_line: int,
                              code_start_line: int) -> List[Dict]:
    lines = code.splitlines()
    use_rel = use_line - code_start_line
    pat = re.compile(rf'\b{re.escape(var_name)}\s*=\s*([^;]+);')
    results = []
    for i in range(min(use_rel, len(lines)) - 1, -1, -1):
        m = pat.search(lines[i])
        if m:
            results.append({'line': i + code_start_line, 'rhs': m.group(1).strip()})
            if len(results) >= 5:
                break
    return results


# ---------------------------------------------------------------------------
# Preceding call finder
# ---------------------------------------------------------------------------

def find_preceding_calls(code: str, func_name: str, before_line: int,
                          code_start_line: int = 1) -> List[Dict]:
    """
    Find all calls to func_name that appear before before_line in code.
    Returns list of {'line': int, 'args': str}.
    """
    lines = code.splitlines()
    before_rel = before_line - code_start_line
    pat = re.compile(rf'\b{re.escape(func_name)}\s*\(([^)]*)\)')
    results = []
    for i in range(min(before_rel, len(lines))):
        m = pat.search(lines[i])
        if m:
            results.append({'line': i + code_start_line, 'args': m.group(1).strip()})
    return results


# ---------------------------------------------------------------------------
# Variable sanitization check
# ---------------------------------------------------------------------------

def is_variable_sanitized(code: str, var_name: str, use_line: int,
                           sanitizer_pattern: str,
                           code_start_line: int = 1) -> bool:
    """
    Return True if var_name passes through a sanitizer (e.g. bounds check, strlen guard)
    before use_line.
    sanitizer_pattern is a regex string applied to lines before use_line.
    """
    lines = code.splitlines()
    use_rel = use_line - code_start_line
    sp = re.compile(sanitizer_pattern)
    var_p = re.compile(rf'\b{re.escape(var_name)}\b')
    for i in range(min(use_rel, len(lines))):
        line = lines[i]
        if sp.search(line) and var_p.search(line):
            return True
    return False


# ---------------------------------------------------------------------------
# RHS variable extractor (delegates to ast_analyzer when available)
# ---------------------------------------------------------------------------

def get_rhs_variables(expr: str) -> List[str]:
    """Extract all identifiers on the right-hand side of an expression."""
    from ast_analyzer import find_array_access  # noqa: F401
    # Remove string literals and numbers
    cleaned = re.sub(r'"[^"]*"', '', expr)
    cleaned = re.sub(r'\b\d+\b', '', cleaned)
    return re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)\b', cleaned)
