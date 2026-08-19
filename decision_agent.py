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
    }
    CRITICAL_FP_LABELS = {
        "guard_dominates_all_paths", "explicit_null_termination", "raii_smart_pointer",
        "null_guard_dominates_dereference", "null_guard_covers_all_paths",
        "safe_bounded_api_with_sizeof", "release_function_found",
        "preprocessor_disabled_block", "documented_fallthrough",
        "unsigned_wrap_defined_behavior", "upcast_to_wider_type",
        "explicit_range_guard", "sizeof_loop_bound", "constant_index_within_bounds",
        "loop_bounds_check_covers_all", "bounded_sink_function",
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
                reasoning.append(f"{ev.label}: {ev.description}")
            else:
                reasoning.append(ev.label)

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
            acc.add(Evidence(
                label="taint_from_untrusted_source",
                polarity="bug",
                weight=0.80,
                description=f"Variable originates from untrusted source: {origin}."
            ))
        elif any(src in origin for src in ['literal', 'local', 'bounded', 'safe']):
            acc.add(Evidence(
                label="taint_from_safe_source",
                polarity="fp",
                weight=0.60,
                description=f"Variable originates from safe source: {origin}."
            ))
        elif 'alloc' in origin:
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
    if release_func and alloc_line > 0:
        acc.add(Evidence(
            label="release_function_found",
            polarity="fp",
            weight=0.85,
            description=f"Resource release function {release_func}() found."
        ))

    if code and re.search(r'\bif\s*\(.*\)\s*\{?\s*return\b', code):
        if not release_func:
            acc.add(Evidence(
                label="early_return_without_release",
                polarity="bug",
                weight=0.80,
                description="Early return detected without visible resource release."
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