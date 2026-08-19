# -*- coding: utf-8 -*-
"""Pure-logic tests for checker_categories.py (no GUI required).

Run:  python _test_categories.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import checker_categories as m

_failures = []


def _check(cond, label):
    print(("PASS  " if cond else "FAIL  ") + label)
    if not cond:
        _failures.append(label)


# --- category_for_checker ---------------------------------------------------
_check(m.category_for_checker("BUFFER_SIZE") == "Buffer overflow",
       "BUFFER_SIZE -> Buffer overflow")
_check(m.category_for_checker("ovERRUN") == "Buffer overflow",
       "case-insensitive ovERRUN -> Buffer overflow")
_check(m.category_for_checker("FORWARD_NULL") == "Null pointer dereferences",
       "FORWARD_NULL -> Null pointer dereferences")
_check(m.category_for_checker("REVERSE_INULL") == "Null pointer dereferences",
       "REVERSE_INULL -> Null pointer dereferences")
_check(m.category_for_checker("INTEGER_OVERFLOW") == "Integer handling",
       "INTEGER_OVERFLOW -> Integer handling")
_check(m.category_for_checker("RESOURCE_LEAK") == "Resource leaks",
       "RESOURCE_LEAK -> Resource leaks")
_check(m.category_for_checker("DEADCODE") == "Control flow / code quality",
       "DEADCODE -> Control flow / code quality")
_check(m.category_for_checker("") == "Uncategorized",
       "empty checker -> Uncategorized")
_check(m.category_for_checker("MYSTERY_CHECKER") == "Uncategorized",
       "unknown checker -> Uncategorized")
_check(m.category_for_checker(None) == "Uncategorized",
       "None checker -> Uncategorized")

# --- group_results_by_category ----------------------------------------------
_groups = m.group_results_by_category([
    {"cid": 1, "checker": "BUFFER_SIZE"},
    {"cid": 2, "checker": "ovarfun"},
    {"cid": 3, "checker": "OVERRUN"},
    {"cid": 4, "checker": "FORWARD_NULL"},
    {"cid": 5, "checker": "WHATEVER"},
])
_check(list(_groups.keys()) == ["Buffer overflow", "Null pointer dereferences",
                                "Uncategorized"],
       "group keys follow CATEGORY_ORDER")
_check(len(_groups["Buffer overflow"]) == 2,
       "Buffer overflow group holds 2 (including case-insensitive match)")
_check(len(_groups["Null pointer dereferences"]) == 1,
       "Null pointer dereferences group holds 1")
_check(len(_groups["Uncategorized"]) == 2,
       "Uncategorized group holds 2 (ovarfun + WHATEVER)")
_check(not m.group_results_by_category([]),
       "empty results -> no groups")

# --- category_counts --------------------------------------------------------
_counts = m.category_counts([
    {"checker": "BUFFER_SIZE"},
    {"checker": "OVERRUN"},
    {"checker": "FORWARD_NULL"},
    {"checker": ""},
])
_check(_counts["Buffer overflow"] == 2, "category_counts Buffer overflow == 2")
_check(_counts["Null pointer dereferences"] == 1,
       "category_counts Null pointer dereferences == 1")
_check(_counts["Uncategorized"] == 1, "category_counts Uncategorized == 1")

# --- misc -------------------------------------------------------------------
_check("BUFFER_SIZE" in m.checkers_in_category("Buffer overflow"),
       "checkers_in_category contains BUFFER_SIZE")
_check(len(m.checkers_in_category("Unknown cat")) == 0,
       "checkers_in_category unknown -> empty")
_check(set(m.all_categories()) == set(m.CATEGORY_ORDER),
       "all_categories returns CATEGORY_ORDER")

print()
if _failures:
    print("FAILED: %d test(s) -> %s" % (len(_failures), ", ".join(_failures)))
    sys.exit(1)
print("All checker_categories tests passed.")