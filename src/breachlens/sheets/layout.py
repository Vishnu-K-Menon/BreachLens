"""Fix the layout of a raw sheet (SPREADSHEET_TRACK.md §3).

- Merged cells are filled with their top-left value.
- Header detection scores the first rows: the header is the first row where at least
  60% of the used cells are non-empty strings, few are numeric, and the following rows
  look like data. Not at the first row -> SHEET_HEADER_OFFSET.
- A header row directly under a row of merged group labels ("Employee" over "SSN") is
  joined into one header ("Employee SSN") -> SHEET_MERGED_HEADER.
- Title rows above the header, total rows (`total_row_pattern` on the first non-empty
  cell) and blank rows are dropped; hidden rows are kept and flagged (SHEET_HIDDEN_ROWS).
- A sheet without a usable header or data is skipped (SHEET_SKIPPED).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from breachlens.sheets.reader import Cell, RawSheet, as_text
from breachlens.sheets.settings import LayoutCfg


@dataclass
class Table:
    raw: RawSheet
    header_row: int | None
    headers: list[str]
    rows: list[tuple[int, list[Cell]]]  # (excel row, values)
    codes: list[tuple[str, str]] = field(default_factory=list)  # (code, detail)
    title_rows_dropped: int = 0
    total_rows_dropped: int = 0
    blank_rows_dropped: int = 0
    skipped: bool = False
    skip_reason: str = ""

    @property
    def hidden_data_rows(self) -> list[int]:
        return [r for r, _ in self.rows if r in self.raw.hidden_rows]


def fill_merged(sheet: RawSheet) -> dict[int, list[Cell]]:
    rows = {r: list(v) for r, v in sheet.rows.items()}
    for r1, c1, r2, c2 in sheet.merged:
        top = rows.get(r1, [None] * sheet.n_cols)[c1 - 1] if c1 - 1 < sheet.n_cols else None
        for r in range(r1, r2 + 1):
            if r in rows:
                for c in range(c1, min(c2, sheet.n_cols) + 1):
                    rows[r][c - 1] = top
    return rows


def _is_num(v: Cell) -> bool:
    if isinstance(v, int | float) and not isinstance(v, bool):
        return True
    return isinstance(v, str) and bool(re.fullmatch(r"[-+]?\d[\d,]*(\.\d+)?", v.strip()))


def _is_date(v: Cell) -> bool:
    return isinstance(v, datetime | date)


def _header_like(vals: list[Cell], cfg: LayoutCfg, width: int) -> bool:
    used = [v for v in vals if v not in (None, "")]
    if width == 0 or len(used) < max(2, round(cfg.header_min_string_share * width)):
        return False
    strings = [v for v in used if isinstance(v, str) and not _is_num(v)]
    numeric = [v for v in used if _is_num(v) or _is_date(v)]
    digit_heavy = [v for v in strings if sum(ch.isdigit() for ch in v) >= 4]
    return (
        len(strings) / len(used) >= cfg.header_min_string_share
        and len(numeric) / len(used) <= cfg.header_max_numeric_share
        and not digit_heavy
    )


def _data_like(vals: list[Cell]) -> bool:
    used = [v for v in vals if v not in (None, "")]
    if not used:
        return False
    return any(
        _is_num(v) or _is_date(v) or (isinstance(v, str) and any(ch.isdigit() for ch in v))
        for v in used
    )


def fix_layout(sheet: RawSheet, cfg: LayoutCfg) -> Table:
    rows = fill_merged(sheet)
    order = sorted(rows)
    width = sheet.n_cols
    header_row = None
    for idx, r in enumerate(order[: cfg.header_scan_rows]):
        if not _header_like(rows[r], cfg, width):
            continue
        following = [rows[x] for x in order[idx + 1 : idx + 1 + cfg.data_like_rows] if any(rows[x])]
        if following and all(_data_like(v) for v in following):
            header_row = r
            break
    if header_row is None or width < cfg.min_columns:
        t = Table(sheet, None, [], [], skipped=True, skip_reason="no tabular header found")
        t.codes.append(("SHEET_SKIPPED", t.skip_reason))
        return t
    headers = [as_text(v).strip() for v in rows[header_row]]
    codes: list[tuple[str, str]] = []
    # Two-row header: the row above holds merged group labels spanning this header row.
    above = order[order.index(header_row) - 1] if order.index(header_row) > 0 else None
    groups = [m for m in sheet.merged if above is not None and m[0] == above and m[2] >= above]
    if groups:
        group_label = [""] * width
        for _r1, c1, _r2, c2 in groups:
            for c in range(c1, min(c2, width) + 1):
                group_label[c - 1] = as_text(rows[above][c - 1]).strip()
        joined = []
        for g, h in zip(group_label, headers, strict=True):
            joined.append(h if not g or g == h else f"{g} {h}".strip())
        headers = joined
        codes.append(("SHEET_MERGED_HEADER", f"rows {above}-{header_row}"))
    first = order[0]
    if header_row != first:
        codes.append(("SHEET_HEADER_OFFSET", f"header at row {header_row}"))
    title_rows = sum(
        1 for r in order if r < header_row and (not groups or r != above) and any(rows[r])
    )
    total_rx = re.compile(cfg.total_row_pattern, re.I)
    data, totals, blanks = [], 0, 0
    for r in order:
        if r <= header_row:
            continue
        vals = rows[r]
        used = [v for v in vals if v not in (None, "")]
        if not used:
            blanks += 1
            continue
        if total_rx.search(as_text(used[0]).strip()):
            totals += 1
            codes.append(("SHEET_TOTAL_ROW_DROPPED", f"row {r}"))
            continue
        data.append((r, vals))
    t = Table(sheet, header_row, headers, data, codes, title_rows, totals, blanks)
    if len(data) < cfg.min_data_rows:
        t.skipped, t.skip_reason = True, "fewer than min_data_rows data rows"
        t.codes.append(("SHEET_SKIPPED", t.skip_reason))
    hidden = t.hidden_data_rows
    if hidden:
        t.codes.append(("SHEET_HIDDEN_ROWS", f"{len(hidden)} hidden rows kept"))
    if sheet.encoding and sheet.encoding.lower().replace("_", "-") not in {"utf-8", "ascii"}:
        t.codes.append(("CSV_ENCODING_DETECTED", sheet.encoding))
    return t
