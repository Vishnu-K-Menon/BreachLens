"""Data-quality profiles per sheet and per column (SPREADSHEET_TRACK.md §2).

`file_profile` and `column_profile` columns follow DATA_SCHEMA.md. Column profiles keep
only masked shapes (`ddd-dd-dddd`) and statistics, never sample values (PRIVACY.md §10).
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime
from typing import Any

from breachlens.sheets.layout import Table
from breachlens.sheets.reader import Cell, as_text


def shape(s: str, max_len: int = 14) -> str:
    """Masked shape: digits -> d, letters -> a (A if upper), other characters kept."""
    out = "".join(
        "d" if c.isdigit() else ("A" if c.isupper() else "a") if c.isalpha() else c for c in s
    )
    return out if len(out) <= max_len else out[:max_len] + "…"


def inferred_type(values: list[Cell]) -> str:
    kinds = set()
    for v in values:
        if isinstance(v, datetime | date):
            kinds.add("date")
        elif isinstance(v, int | float) and not isinstance(v, bool):
            kinds.add("number")
        elif isinstance(v, str):
            kinds.add("number" if re.fullmatch(r"-?\d+(\.\d+)?", v.strip()) else "string")
    return kinds.pop() if len(kinds) == 1 else ("mixed" if kinds else "empty")


def file_profile(t: Table) -> dict[str, Any]:
    s = t.raw
    return {
        "doc_id": s.doc_id,
        "sheet": s.sheet,
        "n_rows": len(t.rows),
        "n_cols": s.n_cols,
        "header_row": t.header_row,
        "merged_ranges": ";".join(f"R{r1}C{c1}:R{r2}C{c2}" for r1, c1, r2, c2 in s.merged),
        "hidden_rows": len(t.hidden_data_rows),
        "hidden_cols": len(s.hidden_cols),
        "title_rows_dropped": t.title_rows_dropped,
        "total_rows_dropped": t.total_rows_dropped,
        "encoding": s.encoding,
        "delimiter": s.delimiter,
        "skipped": t.skipped,
        "skip_reason": t.skip_reason,
    }


def column_profiles(t: Table) -> list[dict[str, Any]]:
    out = []
    n = len(t.rows)
    for j, header in enumerate(t.headers):
        values = [vals[j] for _, vals in t.rows]
        texts = [as_text(v).strip() for v in values]
        non_null = [x for x in texts if x]
        shapes = Counter(shape(x) for x in non_null).most_common(3)
        out.append(
            {
                "doc_id": t.raw.doc_id,
                "sheet": t.raw.sheet,
                "col_idx": j + 1,
                "header_raw": header,
                "null_pct": round(1 - len(non_null) / n, 4) if n else 1.0,
                "distinct_pct": round(len(set(non_null)) / len(non_null), 4) if non_null else 0.0,
                "inferred_type": inferred_type([v for v in values if v not in (None, "")]),
                "top_shapes": ";".join(f"{s} ({c})" for s, c in shapes),
                "min_len": min((len(x) for x in non_null), default=0),
                "max_len": max((len(x) for x in non_null), default=0),
            }
        )
    return out
