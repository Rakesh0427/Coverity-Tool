#!/usr/bin/env python3
"""
checker_categories.py — Coverity checker → category mapping.

Single source of truth for grouping Coverity checkers into human-friendly
categories (e.g. "Buffer overflow", "Null pointer dereferences").

Used by:
  * local_gui.py            — ResultsPage tree grouping, category summary chips,
                              toolbar category filter, exported CSV columns
  * coverity_triage.py      — HTML-report triage interface

Mapping follows Coverity's well-known checker taxonomy. Unknown checkers fall
back to "Uncategorized" so nothing is ever silently hidden.
"""

from collections import Counter, OrderedDict

# ---------------------------------------------------------------------------
# Canonical category order (stable display order; "Uncategorized" always last)
# ---------------------------------------------------------------------------
CATEGORY_ORDER = [
    "Buffer overflow",
    "Memory - corruptions",
    "Memory - illegal accesses",
    "Null pointer dereferences",
    "Integer handling",
    "Resource leaks",
    "Error handling",
    "Control flow / code quality",
    "Uncategorized",
]

# ---------------------------------------------------------------------------
# Checker → category mapping
# ---------------------------------------------------------------------------
CHECKER_CATEGORIES = {
    "Buffer overflow": [
        "BUFFER_SIZE", "BUFFER_SIZE_WARNING", "OVERRUN", "OVERRUN_STATIC",
        "OVERRUN_DYNAMIC", "STRING_OVERFLOW", "STRING_NULL", "TAINTED_STRING",
        "WRAPPER_OVERRUN",
    ],
    "Memory - corruptions": [
        "DOUBLE_FREE", "FREE_RETURNS", "SIZEOF_MISMATCH", "WRAPPER_ESCAPE",
    ],
    "Memory - illegal accesses": [
        "ARRAY_VS_SINGLETON", "UNINIT", "UNINIT_CTOR", "UNREACHABLE",
        "USE_AFTER_FREE", "NULL_RETURNS",
    ],
    "Null pointer dereferences": [
        "FORWARD_NULL", "REVERSE_INULL", "NULL_DEREF",
    ],
    "Integer handling": [
        "CONSTANT_EXPRESSION_RESULT", "DIVIDE_BY_ZERO", "INTEGER_OVERFLOW",
        "SHIFT_OVERFLOW", "SIGN_EXTENSION",
    ],
    "Resource leaks": [
        "RESOURCE_LEAK", "UNRELEASED_RESOURCE",
    ],
    "Error handling": [
        "CHECKED_RETURN", "NEGATIVE_RETURNS", "NEGATIVE_RELEASE", "MISSING_LOCK",
    ],
    "Control flow / code quality": [
        "DEADCODE", "UNUSED_VALUE", "MISSING_BREAK", "NO_BREAK",
        "IDENTICAL_BRANCHES",
    ],
}

# Uppercase checker name → category (built once)
_CHECKER_TO_CATEGORY = {
    _chk.upper(): _cat
    for _cat, _chks in CHECKER_CATEGORIES.items()
    for _chk in _chks
}

UNCATEGORIZED = "Uncategorized"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------
def category_for_checker(checker):
    """Return the category name for a Coverity checker (case-insensitive).

    Unknown / empty checkers map to ``Uncategorized`` so they remain visible.
    """
    if not checker:
        return UNCATEGORIZED
    return _CHECKER_TO_CATEGORY.get(str(checker).strip().upper(), UNCATEGORIZED)


def all_categories():
    """Return all category names in canonical display order."""
    return list(CATEGORY_ORDER)


def checkers_in_category(category):
    """Return the checker names mapped under ``category``."""
    return list(CHECKER_CATEGORIES.get(category, []))


def group_results_by_category(results):
    """Group defect dicts into an ordered ``{category: [defects]}`` mapping.

    Keys follow :data:`CATEGORY_ORDER` (stable even when a category's members
    first appear late in a run); unknown checkers land under "Uncategorized".
    """
    groups = OrderedDict((cat, []) for cat in CATEGORY_ORDER)
    for r in results or []:
        cat = category_for_checker(r.get("checker", ""))
        groups.setdefault(cat, []).append(r)
    return OrderedDict((cat, items) for cat, items in groups.items() if items)


def category_counts(results):
    """Return ``Counter`` of category → defect count for a list of defect dicts."""
    return Counter(category_for_checker(r.get("checker", "")) for r in (results or []))