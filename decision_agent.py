"""Custom weighted evidence decision agent for Coverity triage.
Replaces first-signal-wins cascades with evidence accumulation,
conflict resolution, and confidence scoring.
Zero new dependencies — uses only stdlib.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
import re


@dataclass
class Evidence:
    label: str
    polarity: str       # "bug", "fp", "neutral"
    weight: float       # 0.0–1.0
    description: str = ""


@dataclass
class AgentDecision:
    classification: str
    confidence: float
    reasoning: List[str] = field(default_factory=list)
    dominant_signals: List[Evidence] = field(default_factory=list)


class EvidenceAccumulator:
    def __init__(self):
        self.evidence: List[Evidence] = []

    def add(self, evidence: Evidence):
        self.evidence.append(evidence)

    def score(self) -> Dict[str, float]:
        bug_score = 0.0
        fp_score = 0.0
        for ev in self.evidence:
            if ev.polarity == "bug":
                bug_score += ev.weight
            elif ev.polarity == "fp":
                fp_score += ev.weight
        return {"bug_score": bug_score, "fp_score": fp_score}

    def conflicts(self) -> List[Tuple[Evidence, Evidence]]:
        bugs = [e for e in self.evidence if e.polarity == "bug"]
        fps = [e for e in self.evidence if e.polarity == "fp"]
        pairs = []
        for b in bugs:
            for f in fps:
                if self._same_domain(b, f):
                    pairs.append((b, f))
        return pairs

    def _same_domain(self, a: Evidence, b: Evidence) -> bool:
        a_vars = set(re.findall(r'\b\w+\b', a.label.lower()))
        b_vars = set(re.findall(r'\b\w+\b', b.label.lower()))
        generic = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'could', 'should', 'may', 'might', 'must', 'shall',
            'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in', 'for',
            'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through',
            'during', 'before', 'after', 'above', 'below', 'between',
            'under', 'again', 'further', 'then', 'once', 'here', 'there',
            'when', 'where', 'why', 'how', 'all', 'each', 'few', 'more',
            'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
            'own', 'same', 'so', 'than', 'too', 'very', 'just', 'and',
            'but', 'if', 'or', 'because', 'until', 'while', 'this', 'that',
            'these', 'those', 'now', 'also', 'back', 'still',
            'its', 'his', 'her', 'our', 'out', 'up', 'down', 'off', 'over',
        }
        common = a_vars & b_vars - generic
        if common:
            return True
        domain_keywords = ['guard', 'taint', 'sink', 'buffer', 'null', 'bounds', 'check']
        return any(k in a.label.lower() and k in b.label.lower() for k in domain_keywords)


class DecisionAgent:
    CRITICAL_BUG_LABELS = {
        "strncpy_no_null_terminator", "unsafe_sink_function", "memcpy_without_size_guard",
        "coverity_confirmed_oob", "coverity_confirmed_null", "coverity_confirmed_null_deref",
        "always_unsafe_sink", "taint_from_untrusted_source", "unsafe_sink",
        "early_return_without_release", "null_deref_confirmed",
        "leak_exit_without_release", "allocation_not_null_checked",
    }
    CRITICAL_FP_LABELS = {
        "guard_dominates_all_paths", "explicit_null_termination", "raii_smart_pointer",
        "null_guard_dominates_dereference", "null_guard_covers_all_paths",
        "safe_bounded_api_with_sizeof", "release_function_found",
        "preprocessor_disabled_block", "documented_fallthrough",
        "unsigned_wrap_defined_behavior", "upcast_to_wider_type",
        "explicit_range_guard", "sizeof_loop_bound", "constant_index_within_bounds",
        "loop_bounds_check_covers_all", "bounded_sink_function",
        "all_exits_release_resource",
        "memset_prezeroes_destination", "protocol_field_strncpy",
        "strncpy_count_from_strlen", "dest_larger_than_copy",
        "string_already_terminated_or_not_cstring",
        "pointer_first_element_alias",
    }


    @staticmethod
    def evaluate(accumulator: EvidenceAccumulator, checker: str = "") -> AgentDecision:
        scores = accumulator.score()
        bug_score = scores["bug_score"]
        fp_score = scores["fp_score"]
        total = bug_score + fp_score

        labels = {e.label for e in accumulator.evidence}
        has_critical_bug = bool(DecisionAgent.CRITICAL_BUG_LABELS & labels)
        has_critical_fp = bool(DecisionAgent.CRITICAL_FP_LABELS & labels)

        if total > 0:
            winner = max(bug_score, fp_score)
            loser = min(bug_score, fp_score)
            margin = winner - loser
            dominance = winner / total          # 0.5 (perfect tie) .. 1.0 (one-sided)
            if loser == 0:
                confidence = min(1.0, 0.55 + winner * 0.22 + dominance * 0.15)
            else:
                confidence = min(1.0, 0.45 + margin * 0.30 + winner * 0.12 + dominance * 0.15)
        else:
            confidence = 0.0
            dominance = 0.0

        if has_critical_bug and not has_critical_fp and fp_score < 0.3:
            confidence = min(1.0, confidence + 0.15)
        if has_critical_fp and not has_critical_bug and bug_score < 0.3:
            confidence = min(1.0, confidence + 0.15)

        for ev in accumulator.evidence:
            if ev.label == "insufficient_context":
                confidence = max(0.0, confidence - 0.20)

        # The strongest single piece of evidence is used to resolve dead-even
        # contests toward the most specific, best-supported signal instead of
        # surrendering to a Needs-review tie.
        strongest = max(accumulator.evidence, key=lambda e: e.weight, default=None)

        classification = "Needs review"

        if total == 0:
            classification = "Needs review"
        elif has_critical_bug and not has_critical_fp and bug_score > fp_score:
            classification = "Bug"
        elif has_critical_fp and not has_critical_bug and fp_score > bug_score:
            classification = "False positive"
        elif confidence >= 0.45 and dominance >= 0.62 and margin >= 0.12:
            # A clear relative majority backed by a reasonable absolute lead.
            classification = "Bug" if bug_score > fp_score else "False positive"
        elif confidence >= 0.50 and bug_score > fp_score:
            classification = "Bug"
        elif confidence >= 0.50 and fp_score > bug_score:
            classification = "False positive"
        elif confidence >= 0.35 and bug_score > fp_score + 0.15:
            classification = "Bug"
        elif confidence >= 0.35 and fp_score > bug_score + 0.15:
            classification = "False positive"
        elif (strongest is not None and strongest.weight >= 0.75
              and strongest.polarity in ("bug", "fp")
              and total > 0 and abs(bug_score - fp_score) <= 0.02):
            # Dead-even contest resolved by the strongest, most concrete signal.
            confidence = max(confidence, 0.50)
            classification = "Bug" if strongest.polarity == "bug" else "False positive"
        else:
            classification = "Needs review"

        reasoning = []
        sorted_ev = sorted(accumulator.evidence, key=lambda e: e.weight, reverse=True)

        if classification == "Bug":
            dominant = [e for e in sorted_ev if e.polarity == "bug"][:3]
        elif classification == "False positive":
            dominant = [e for e in sorted_ev if e.polarity == "fp"][:3]
        else:
            bugs = [e for e in sorted_ev if e.polarity == "bug"][:2]
            fps = [e for e in sorted_ev if e.polarity == "fp"][:2]
            dominant = bugs + fps

        for ev in dominant:
            if ev.description:
                # Reviewer-facing text: use the human sentence, not the
                # machine label ("explicit_null_termination: ...").
                reasoning.append(ev.description)
            else:
                reasoning.append(ev.label.replace('_', ' '))

        if not reasoning:
            reasoning = ["Insufficient evidence for automatic classification."]

        if confidence >= 0.80:
            reasoning.insert(0, "High confidence.")
        elif confidence >= 0.55:
            reasoning.insert(0, "Moderate confidence — review recommended.")
        else:
            reasoning.insert(0, "Low confidence — manual review required.")

        return AgentDecision(
            classification=classification,
            confidence=round(confidence, 2),
            reasoning=reasoning,
            dominant_signals=dominant
        )


# Checkers for which the *provenance* of the flagged value is part of the
# defect semantics (attacker-controlled data reaching a buffer/memory sink).
# For value-semantics checkers (INTEGER_OVERFLOW, DIVIDE_BY_ZERO, SHIFT_OVERFLOW,
# CONSTANT_EXPRESSION_RESULT, UNINIT, ...) a parameter or local origin is NOT
# evidence of a bug — the value, not the source, decides the verdict.
_TAINT_RELEVANT_CHECKERS = frozenset({
    "OVERRUN", "OVERRUN_STATIC", "OVERRUN_DYNAMIC",
    "BUFFER_SIZE", "BUFFER_SIZE_WARNING", "STRING_OVERFLOW", "STRING_NULL",
    "TAINTED_STRING", "WRAPPER_OVERRUN",
})
# Checkers where an allocation-failure origin (malloc/fopen/...) is a genuine
# defect signal (the pointer may be NULL on the flagged path).
_ALLOC_RELEVANT_CHECKERS = frozenset({
    "FORWARD_NULL", "REVERSE_INULL", "RESOURCE_LEAK",
})
# Checkers whose verdict is a leak-path question. Only for these does the
# generic evidence builder run the path-aware leak scan.
LEAK_CHECKERS = frozenset({"RESOURCE_LEAK", "UNRELEASED_RESOURCE"})


def analyze_leak_exits(code: str, resource: str, release_func: str,
                       alloc_line: int, code_start_line: int = 1) -> Optional[Dict]:
    """Path-aware leak scan for one resource.

    Walk the function snippet from the allocation to the end and treat every
    exit point (``return`` / ``exit()`` / ``abort()`` / ``goto``) as a leak
    candidate unless the resource is released on the path leading to that
    exit — the release is on the same line, on one of the up-to-two
    straight-line statements immediately before it, or sits in a shared
    cleanup label (``goto cleanup; ... cleanup: free(p);``) that the exit
    jumps into.

    Returns ``None`` when the inputs are too thin to analyse, otherwise::

        {'has_exit': bool, 'leak_exits': [abs_line, ...],
         'release_found': bool, 'all_exits_clear': bool}
    """
    lines = (code or "").splitlines()
    n = len(lines)
    if not resource or not release_func or alloc_line <= 0 or n == 0:
        return None
    alloc_rel = alloc_line - (code_start_line or 1)
    if not (0 <= alloc_rel < n):
        return None

    resource = resource.strip()
    rel_pat = re.compile(rf"\b{re.escape(release_func)}\s*\(")

    def _releases(line_idx: int) -> bool:
        # The release may sit on the exit line itself (``free(p); return;``)
        # or on the immediately preceding straight-line statements.
        for j in (line_idx, line_idx - 1, line_idx - 2):
            if 0 <= j < n and rel_pat.search(lines[j]) and re.search(rf"\b{re.escape(resource)}\b", lines[j]):
                return True
        return False

    # Labels that release the resource (goto-cleanup idiom).
    releasing_labels = set()
    for i, l in enumerate(lines):
        lm = re.match(r"\s*([A-Za-z_]\w*)\s*:", l)
        if not lm or lm.group(1) in ("case", "default"):
            continue
        for j in range(i, min(n, i + 10)):
            if rel_pat.search(lines[j]) and re.search(rf"\b{re.escape(resource)}\b", lines[j]):
                releasing_labels.add(lm.group(1))
                break

    has_exit = False
    leak_exits: List[int] = []
    release_found = False
    for i in range(alloc_rel, n):
        l = lines[i]
        if rel_pat.search(l) and re.search(rf"\b{re.escape(resource)}\b", l):
            release_found = True
        if re.search(r"\breturn\b", l):
            has_exit = True
            if not _releases(i):
                leak_exits.append(i + (code_start_line or 1))
        elif re.search(r"\b(exit|abort)\s*\(", l):
            has_exit = True
            if not _releases(i):
                leak_exits.append(i + (code_start_line or 1))
        else:
            gm = re.search(r"\bgoto\s+([A-Za-z_]\w*)", l)
            if gm:
                has_exit = True
                if gm.group(1) not in releasing_labels:
                    leak_exits.append(i + (code_start_line or 1))

    return {
        "has_exit": has_exit,
        "leak_exits": leak_exits,
        "release_found": release_found,
        "all_exits_clear": has_exit and not leak_exits,
    }


def build_evidence(context: Dict, events_parsed: Dict, checker: str = "") -> EvidenceAccumulator:
    """Translate context and parsed events into weighted Evidence objects."""
    acc = EvidenceAccumulator()
    code = context.get('code', '') or context.get('function_code', '') or context.get('source_code', '')
    ev = events_parsed if events_parsed else context.get('ev', {})

    if ev.get('defect_confirmed'):
        acc.add(Evidence(
            label="coverity_confirmed_defect",
            polarity="bug",
            weight=0.30,
            description="Coverity event trace reports a defect on this path."
        ))

    if ev.get('taint_confirmed'):
        acc.add(Evidence(
            label="coverity_confirmed_taint",
            polarity="bug",
            weight=0.25,
            description="Coverity reports tainted data reaches this sink."
        ))

    if ev.get('guard_on_path') and ev.get('guard_takes_true'):
        acc.add(Evidence(
            label="guard_confirmed_on_path",
            polarity="fp",
            weight=0.35,
            description="Coverity event trace shows a guard was verified on this path."
        ))
    elif ev.get('guard_on_path'):
        acc.add(Evidence(
            label="guard_present_uncertain",
            polarity="neutral",
            weight=0.0,
            description="A guard exists but its branch outcome is uncertain."
        ))

    origin = context.get('origin', '')
    if origin:
        if any(src in origin for src in ['network', 'args', 'env', 'file', 'caller-controlled', 'tainted', 'external']):
            if checker in _TAINT_RELEVANT_CHECKERS:
                # For the null-termination checkers the source being
                # caller-controlled is only a contributing factor: the copy
                # count already caps how many bytes are written, and the
                # dedicated analyzer weighs terminator facts (pre-zeroing,
                # sizeof-1, struct-field use). Record taint at a modest,
                # non-critical weight so it cannot veto those facts.
                if checker in ("BUFFER_SIZE", "BUFFER_SIZE_WARNING", "STRING_NULL") and \
                        context.get('sink_func', '') in ('strncpy', 'strncat', 'strlcpy',
                                                         'snprintf', 'memcpy', 'memmove',
                                                         'memcpy_s', 'strcpy_s'):
                    acc.add(Evidence(
                        label="taint_context_untrusted_source",
                        polarity="bug",
                        weight=0.35,
                        description=(f"The copied data originates from {origin}; a long "
                                     f"source is what makes a full-capacity copy leave "
                                     f"the destination unterminated.")
                    ))
                else:
                    acc.add(Evidence(
                        label="taint_from_untrusted_source",
                        polarity="bug",
                        weight=0.80,
                        description=f"Variable originates from untrusted source: {origin}."
                    ))
            # For value-semantics checkers the origin is not defect evidence;
            # the concrete value/width decides. Record it as neutral context.
        elif any(src in origin for src in ['literal', 'local', 'bounded', 'safe']):
            acc.add(Evidence(
                label="taint_from_safe_source",
                polarity="fp",
                weight=0.60,
                description=f"Variable originates from safe source: {origin}."
            ))
        elif 'alloc' in origin:
            if checker in _ALLOC_RELEVANT_CHECKERS:
                acc.add(Evidence(
                    label="taint_from_allocation",
                    polarity="bug",
                    weight=0.65,
                    description="Variable may be NULL from allocation failure."
                ))

    guard_line = context.get('guard_line', 0)
    guard_reason = context.get('guard_reason', '')
    if guard_line > 0:
        if 'covers all paths' in guard_reason.lower() or context.get('guard_covers_all_paths'):
            acc.add(Evidence(
                label="guard_dominates_all_paths",
                polarity="fp",
                weight=0.90,
                description=f"Guard at line {guard_line} dominates all paths to the defect."
            ))
        elif 'may not cover' in guard_reason.lower():
            acc.add(Evidence(
                label="guard_partial_coverage",
                polarity="neutral",
                weight=0.0,
                description=f"Guard at line {guard_line} may not cover all execution paths."
            ))
        else:
            acc.add(Evidence(
                label="guard_present",
                polarity="fp",
                weight=0.55,
                description=f"Guard condition present at line {guard_line}."
            ))

    sink = context.get('sink_func', '')
    if sink in ('strcpy', 'strcat', 'wcscpy', 'wcscat', 'gets', 'sprintf', 'vsprintf'):
        acc.add(Evidence(
            label="unsafe_sink_function",
            polarity="bug",
            weight=0.85,
            description=f"Always-unsafe sink function {sink}() detected."
        ))
    elif sink in ('strncpy', 'strncat', 'snprintf', 'strlcpy', 'strlcat', 'memcpy_s', 'strcpy_s'):
        _bounded_is_fp = True
        if checker in ('BUFFER_SIZE', 'STRING_NULL') and sink in ('strncpy', 'strncat', 'strlcpy'):
            # For the null-termination checkers, "the API is bounded" does NOT
            # answer the flagged question: strncpy(dst, src, sizeof(dst)) is
            # exactly the pattern that fills the buffer and leaves it
            # unterminated. Only treat the bounded API as FP evidence when the
            # code shows a terminator guarantee.
            code = context.get('code', '') or ''
            _has_nul_guarantee = (
                re.search(r'\bmemset\s*\(\s*\w+\s*,\s*0', code)
                or re.search(r"\[\s*[^\]]+\]\s*=\s*['\"]\\0['\"]", code)
                or re.search(r'sizeof\s*\([^)]*\)\s*-\s*1', code)
                or re.search(r'strlen\s*\([^)]*\)\s*\+\s*1', code)
            )
            if not _has_nul_guarantee:
                _bounded_is_fp = False
        if _bounded_is_fp:
            acc.add(Evidence(
                label="bounded_sink_function",
                polarity="fp",
                weight=0.85,
                description=f"Bounded/safe sink function {sink}() detected."
            ))
    elif sink == 'memcpy':
        acc.add(Evidence(
            label="memcpy_sink",
            polarity="bug",
            weight=0.60,
            description="memcpy() requires manual size validation."
        ))

    release_func = context.get('release_func', '')
    alloc_line = context.get('alloc_line', 0)
    release_line = context.get('release_line', 0)
    resource = (context.get('resource') or '').strip()

    if checker in LEAK_CHECKERS and code and resource and release_func and alloc_line > 0:
        # Path-aware leak verdict: a release call that exists somewhere in the
        # function is NOT evidence against a leak unless every exit path
        # between the allocation and function end actually reaches it.
        leak_facts = analyze_leak_exits(code, resource, release_func,
                                        alloc_line, context.get('code_start_line', 1))
        if leak_facts:
            if leak_facts['leak_exits']:
                acc.add(Evidence(
                    label="leak_exit_without_release",
                    polarity="bug",
                    weight=0.80,
                    description=(f"`{resource}` is acquired at line {alloc_line} but exit path(s) "
                                 f"at line(s) {leak_facts['leak_exits']} return without releasing it.")
                ))
            elif leak_facts['has_exit'] and leak_facts['release_found']:
                acc.add(Evidence(
                    label="all_exits_release_resource",
                    polarity="fp",
                    weight=0.85,
                    description=(f"Every exit path after the acquisition at line {alloc_line} "
                                 f"releases `{resource}` via {release_func}().")
                ))
    elif release_func and alloc_line > 0 and release_line > 0:
        # Non-leak checker: only credit a release that is actually present in
        # the snippet. `release_func` is the allocator's *expected* releaser —
        # crediting it without a matching call marked every malloc'd pointer
        # as "released" (flipping unchecked NULL derefs to false positives).
        acc.add(Evidence(
            label="release_function_found",
            polarity="fp",
            weight=0.60,
            description=f"Resource release function {release_func}() present in the function body."
        ))

    if code and re.search(r'\bstd::unique_ptr|\bstd::shared_ptr|\bauto_ptr|\bQScopedPointer|\bg_auto', code):
        acc.add(Evidence(
            label="raii_smart_pointer",
            polarity="fp",
            weight=0.90,
            description="RAII smart pointer manages resource automatically."
        ))

    if code and re.search(r'\[\s*(?:sizeof.*-\s*1|\w+\s*-\s*1)\s*\]\s*=\s*["\']\\0["\']', code):
        acc.add(Evidence(
            label="explicit_null_termination",
            polarity="fp",
            weight=0.85,
            description="Explicit null terminator assignment after bounded copy."
        ))

    if code and re.search(r'\(\s*(long long|int64_t|uint64_t|size_t)\s*\)', code):
        acc.add(Evidence(
            label="upcast_to_wider_type",
            polarity="fp",
            weight=0.80,
            description="Explicit upcast to wider integer type before arithmetic."
        ))

    if code and re.search(r'\bif\s*\(.*>\s*(INT_MAX|UINT_MAX|0x7[Ff]+|32767|65535)\)', code):
        acc.add(Evidence(
            label="explicit_range_guard",
            polarity="fp",
            weight=0.90,
            description="Explicit range check against INT_MAX/UINT_MAX before operation."
        ))

    if '#if 0' in code or '#ifdef NEVER' in code:
        acc.add(Evidence(
            label="preprocessor_disabled_block",
            polarity="fp",
            weight=0.95,
            description="Code is inside #if 0 or #ifdef NEVER — intentionally disabled."
        ))

    if code and re.search(r'//\s*fallthrough|/\*\s*fall.?through|FALLTHRU|FALLTHROUGH|\[\[fallthrough\]\]', code, re.I):
        acc.add(Evidence(
            label="documented_fallthrough",
            polarity="fp",
            weight=0.90,
            description="Switch case fall-through is explicitly documented."
        ))

    line_count = len(code.splitlines()) if code else 0
    if line_count < 5:
        acc.add(Evidence(
            label="insufficient_context",
            polarity="neutral",
            weight=0.0,
            description=f"Extracted context is only {line_count} lines — insufficient for reliable analysis."
        ))

    if context.get('semgrep_rule'):
        acc.add(Evidence(
            label="semgrep_confirms",
            polarity="bug",
            weight=0.45,
            description=f"Semgrep rule {context['semgrep_rule']} independently confirms finding."
        ))

    return acc