"""Repair Excel damage in one cell, per mapped column label (SPREADSHEET_TRACK.md §5).

Each repair returns the cleaned value plus the reason codes it fired:

| problem | fix / code |
|---|---|
| ZIP lost its leading zero (4 digits, leading-zero state) | pad -> XL_ZIP_LEADING_ZERO_RESTORED |
| Excel date serial in a date column | epoch 1899-12-30 -> XL_DATE_SERIAL_CONVERTED |
| ambiguous day/month with no column evidence | DOB_AMBIGUOUS_FORMAT |
| long ID as a 16+ digit number / sci-notation | XL_NUMBER_PRECISION_LOST (present, invalid) |
| 8-digit numeric SSN | pad to 9 -> XL_SSN_ZERO_PADDED |
| Excel error value (#N/A …) | null -> XL_ERROR_VALUE |
| pre-masked value (XXX-XX-1234) | present, masked kept -> PREMASKED_VALUE |
| non-breaking spaces | normalized (leading/trailing spaces are kept for M4) |
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from breachlens.sheets.reader import Cell, as_text
from breachlens.sheets.settings import RepairCfg

EXCEL_EPOCH = date(1899, 12, 30)
TEXT, PRECISION_LOST, PREMASKED = "TEXT", "PRECISION_LOST", "PREMASKED"


@dataclass
class Fixed:
    value: str | None
    codes: list[str] = field(default_factory=list)
    status: str | None = None  # card / long-id status: TEXT, PRECISION_LOST, PREMASKED
    raw: str = ""


@dataclass(frozen=True)
class RepairContext:
    cfg: RepairCfg
    zip_states: frozenset[str]
    as_of: date
    day_first: bool | None = None  # dominant order of the column's ambiguous dates


def _clean(v: Cell) -> str:
    return as_text(v).replace(" ", " ")


def is_excel_error(v: Cell, cfg: RepairCfg) -> bool:
    return isinstance(v, str) and v.strip().upper() in {e.upper() for e in cfg.excel_errors}


def is_premasked(s: str, cfg: RepairCfg) -> bool:
    return bool(re.match(cfg.premasked_pattern, s.strip()))


def is_precision_lost(v: Cell, cfg: RepairCfg) -> bool:
    if isinstance(v, int | float) and not isinstance(v, bool):
        # Excel keeps 15 significant digits: a 16+ digit number stored numerically is damaged.
        return abs(v) >= 1e15
    return isinstance(v, str) and bool(re.match(cfg.sci_notation_pattern, v.strip()))


def _pivot(dt: date, as_of: date) -> date:
    yy = dt.year % 100
    return dt.replace(year=(1900 if yy > as_of.year % 100 else 2000) + yy)


def column_day_first(values: list[Cell]) -> bool | None:
    """True if the column's slash dates are day-first, False if month-first, None if unknown."""
    md = dm = 0
    for v in values:
        m = re.match(r"^(\d{1,2})/(\d{1,2})/\d{2,4}$", as_text(v).strip())
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a > 12 >= b:
            dm += 1
        elif b > 12 >= a:
            md += 1
    if md == dm:
        return None if md == 0 else False
    return dm > md


def repair_date(v: Cell, ctx: RepairContext) -> Fixed:
    raw = _clean(v)
    if isinstance(v, datetime):
        return Fixed(v.date().isoformat(), raw=raw)
    if isinstance(v, date):
        return Fixed(v.isoformat(), raw=raw)
    lo, hi = ctx.cfg.excel_serial_range
    num = None
    if isinstance(v, int | float) and not isinstance(v, bool):
        num = float(v)
    elif re.fullmatch(r"\d{4,5}", raw.strip()):
        num = float(raw.strip())
    if num is not None:
        if lo <= num <= hi and num.is_integer():
            d = EXCEL_EPOCH + timedelta(days=int(num))
            return Fixed(d.isoformat(), ["XL_DATE_SERIAL_CONVERTED"], raw=raw)
        return Fixed(None, raw=raw)
    s = " ".join(raw.split())
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})$", s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), m.group(3)
        codes: list[str] = []
        if a <= 12 and b <= 12 and a != b:
            if ctx.day_first is None:
                codes.append("DOB_AMBIGUOUS_FORMAT")
            day_first = bool(ctx.day_first)
        else:
            day_first = a > 12
        month, day = (b, a) if day_first else (a, b)
        year = int(y)
        try:
            d = date(year if len(y) == 4 else 2000 + year, month, day)
        except ValueError:
            return Fixed(None, raw=raw)
        if len(y) == 2:
            d = _pivot(d, ctx.as_of)
        return Fixed(d.isoformat(), codes, raw=raw)
    for fmt in ctx.cfg.date_formats:
        if "/" in fmt:
            continue
        try:
            return Fixed(datetime.strptime(s, fmt).date().isoformat(), raw=raw)
        except ValueError:
            continue
    return Fixed(None, raw=raw)


def repair_zip(v: Cell, state: str | None, ctx: RepairContext) -> tuple[Fixed, str | None]:
    """(zip5, zip4). A 4-digit ZIP in a leading-zero state gets its zero back."""
    s = _clean(v).strip()
    m = re.fullmatch(r"(\d{3,5})(?:-(\d{4}))?", s)
    if not m:
        return Fixed(s or None, raw=s), None
    z5, z4 = m.group(1), m.group(2)
    if len(z5) == 4 and state and state.strip().upper() in ctx.zip_states:
        return Fixed("0" + z5, ["XL_ZIP_LEADING_ZERO_RESTORED"], raw=s), z4
    return Fixed(z5, raw=s), z4


def repair_ssn(v: Cell, ctx: RepairContext) -> Fixed:
    raw = _clean(v).strip()
    if not raw:
        return Fixed(None)
    if is_premasked(raw, ctx.cfg):
        return Fixed(raw, ["PREMASKED_VALUE"], PREMASKED, raw=raw)
    if is_precision_lost(v, ctx.cfg):
        return Fixed(
            re.sub(r"\D", "", as_text(v).split(".")[0]),
            ["XL_NUMBER_PRECISION_LOST"],
            PRECISION_LOST,
            raw,
        )
    digits = re.sub(r"\D", "", raw)
    numeric = isinstance(v, int | float) or raw.isdigit()
    if numeric and len(digits) == 8:
        return Fixed("0" + digits, ["XL_SSN_ZERO_PADDED"], TEXT, raw=raw)
    return Fixed(digits or None, status=TEXT, raw=raw)


def repair_long_id(v: Cell, ctx: RepairContext) -> Fixed:
    """Cards, accounts, member IDs …: digits/text kept, precision loss and masks flagged."""
    raw = _clean(v).strip()
    if not raw:
        return Fixed(None)
    if is_premasked(raw, ctx.cfg):
        return Fixed(raw, ["PREMASKED_VALUE"], PREMASKED, raw=raw)
    if is_precision_lost(v, ctx.cfg):
        digits = re.sub(r"\D", "", f"{float(v):.0f}" if isinstance(v, float) else raw.split(".")[0])
        return Fixed(digits, ["XL_NUMBER_PRECISION_LOST"], PRECISION_LOST, raw=raw)
    compact = re.sub(r"[\s-]", "", raw) if re.fullmatch(r"[\d\s-]+", raw) else raw
    return Fixed(compact, status=TEXT, raw=raw)


def split_city_state_zip(s: str) -> tuple[str, str, str] | None:
    m = re.match(r"^\s*(.*?),\s*([A-Za-z]{2})\s+(\d{3,5}(?:-\d{4})?)\s*$", s or "")
    return (m.group(1).strip(), m.group(2).upper(), m.group(3)) if m else None


def split_address_full(s: str) -> dict[str, str]:
    import usaddress

    try:
        tagged, _ = usaddress.tag(s)
    except usaddress.RepeatedLabelError:
        return {}
    line1 = " ".join(
        tagged.get(k, "")
        for k in (
            "AddressNumber",
            "StreetNamePreDirectional",
            "StreetName",
            "StreetNamePostType",
            "StreetNamePostDirectional",
        )
    ).split()
    unit = " ".join(tagged.get(k, "") for k in ("OccupancyType", "OccupancyIdentifier")).split()
    return {
        "line1": " ".join(line1),
        "line2": " ".join(unit),
        "city": tagged.get("PlaceName", ""),
        "state": tagged.get("StateName", ""),
        "zip": tagged.get("ZipCode", ""),
    }
