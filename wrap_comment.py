def _wrap_comment_remaining(text, width=80, reserve_top=0, reserve_bottom=0):
    """Wrap a comment to the *remaining* space.

    Honors the user's directive: do NOT use a `scrollable`/fill-to-edges model.
    Instead consume the available height (total height minus any top/bottom
    reserve) but stop short of the full extent (a small bottom breathing room
    is kept) so the block does not run flush to the container edge.

    - width:      target column width for the wrapped paragraph.
    - reserve_top / reserve_bottom: lines held back from the top/bottom edges.
    Returns a string of <= (usable_height) lines, none of which is the last
    usable line, so the block never fills the full available space.
    """
    import textwrap
    lines = textwrap.wrap(text, width=width, break_long_words=True,
                          break_on_hyphens=False) or [""]
    # available viewport height (rows); pretend caller supplied total height
    total_height = getattr(_wrap_comment_remaining, "_total_height", len(lines))
    usable = max(1, total_height - reserve_top - reserve_bottom)
    # "remaining space" rule: do not use the full space -> keep a 1-line margin.
    cap = usable - 1 if usable > 1 else 1
    capped = lines[:cap]
    # ensure we never emit a line that touches the bottom edge
    return "\n".join(capped)
