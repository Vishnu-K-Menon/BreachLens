"""Date-of-birth checks at `as_of_date` (ADR-053)."""

from __future__ import annotations

from datetime import date
from typing import Any

from breachlens.normalize.dates import age_at, parse_iso, printed_two_digit_year


def dob_codes(
    dob: Any, raw: Any, as_of: date, max_age: int, minor_age: int
) -> tuple[list[str], int | None]:
    """(codes, age_at_run)."""
    d = parse_iso(dob)
    raw_present = isinstance(raw, str) and bool(raw.strip())
    if d is None:
        return (["DOB_UNPARSEABLE"] if raw_present else []), None
    codes = []
    if printed_two_digit_year(raw):
        codes.append("DOB_TWO_DIGIT_YEAR")
    if d > as_of:
        return [*codes, "DOB_FUTURE"], None
    age = age_at(d, as_of)
    if age > max_age:
        codes.append("DOB_IMPLAUSIBLE")
    elif age < minor_age:
        codes.append("DOB_MINOR")
    return codes, age
