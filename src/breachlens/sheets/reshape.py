"""Unpivot wide dependent columns (SPREADSHEET_TRACK.md §6).

`Dep1_First, Dep1_Last, Dep1_DOB, Dep2_First …` become one dependent per group per row,
with `person_role=DEPENDENT` and a link to the row's subscriber.
"""

from __future__ import annotations

import re


def wide_groups(headers: list[str], pattern: str) -> dict[int, dict[int, str]]:
    """group number -> {column index (0-based): field suffix}."""
    rx = re.compile(pattern, re.I)
    groups: dict[int, dict[int, str]] = {}
    for j, h in enumerate(headers):
        m = rx.match(h.strip())
        if m:
            groups.setdefault(int(m.group(1)), {})[j] = m.group(2).strip()
    return {g: cols for g, cols in sorted(groups.items()) if len(cols) >= 2}
