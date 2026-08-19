from checker_categories import (
    UNCATEGORIZED,
    category_for_checker,
    category_counts,
    group_results_by_category,
)


def test_category_lookup_is_case_insensitive():
    assert category_for_checker("buffer_size") == "Buffer overflow"


def test_unknown_checker_is_visible_as_uncategorized():
    assert category_for_checker("NOT_A_COVERITY_CHECKER") == UNCATEGORIZED


def test_grouping_and_counts_preserve_known_categories():
    results = [
        {"checker": "BUFFER_SIZE"},
        {"checker": "FORWARD_NULL"},
        {"checker": "UNKNOWN"},
    ]

    grouped = group_results_by_category(results)
    counts = category_counts(results)

    assert list(grouped) == [
        "Buffer overflow",
        "Null pointer dereferences",
        UNCATEGORIZED,
    ]
    assert counts["Buffer overflow"] == 1
    assert counts["Null pointer dereferences"] == 1
    assert counts[UNCATEGORIZED] == 1
