"""Date helpers: age at `as_of_date` (ADR-053) and printed two-digit years."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

TWO_DIGIT_YEAR = re.compile(r"^\s*\d{1,2}[/\-. ]\d{1,2}[/\-. ]\d{2}\s*$")


def parse_iso(v: Any) -> date | None:
    if isinstance(v, date):
        return v
    if not isinstance(v, str) or not v.strip():
        return None
    try:
        return date.fromisoformat(v.strip()[:10])
    except ValueError:
        return None


def age_at(dob: date, as_of: date) -> int:
    return as_of.year - dob.year - ((as_of.month, as_of.day) < (dob.month, dob.day))


def printed_two_digit_year(raw: Any) -> bool:
    return isinstance(raw, str) and bool(TWO_DIGIT_YEAR.match(raw))
