"""Engineered pair features (ARCHITECTURE.md §resolve, DATA_SCHEMA `pair_features`).

Each feature is in [0, 1] or None when either side lacks the field.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

FEATURES = [
    "f_first_jw",
    "f_last_jw",
    "f_dob",
    "f_zip_eq",
    "f_addr_tsr",
    "f_ssn_key_eq",
    "f_dl_key_eq",
    "f_same_source_file",
    "f_mi_eq",
]


@dataclass(frozen=True)
class Side:
    """The matching view of one mention (keys and normalized fields only)."""

    first: str | None  # canonical (nicknames expanded)
    last: str | None
    mi: str | None
    dob: date | None
    zip5: str | None
    line1: str | None
    ssn_key: str | None
    dl_key: str | None
    passport_key: str | None
    source_file: str | None
    source_row: str | None  # file + row: two people on one sheet row are never one person
    related: str | None  # related_mention_id
    mention_id: str


def jw(a: str | None, b: str | None) -> float | None:
    if not a or not b:
        return None
    return round(JaroWinkler.normalized_similarity(a, b), 4)


def f_dob(a: date | None, b: date | None) -> float | None:
    """1 exact / 0.7 day-month transposed / 0.3 same year / 0 different / None."""
    if a is None or b is None:
        return None
    if a == b:
        return 1.0
    if a.year == b.year and a.month == b.day and a.day == b.month:
        return 0.7
    return 0.3 if a.year == b.year else 0.0


def eq(a: str | None, b: str | None) -> float | None:
    if not a or not b:
        return None
    return 1.0 if a == b else 0.0


def pair_features(a: Side, b: Side) -> dict[str, float | None]:
    return {
        "f_first_jw": jw(a.first, b.first),
        "f_last_jw": jw(a.last, b.last),
        "f_dob": f_dob(a.dob, b.dob),
        "f_zip_eq": eq(a.zip5, b.zip5),
        "f_addr_tsr": round(fuzz.token_set_ratio(a.line1, b.line1) / 100, 4)
        if a.line1 and b.line1
        else None,
        "f_ssn_key_eq": eq(a.ssn_key, b.ssn_key),
        "f_dl_key_eq": eq(a.dl_key, b.dl_key),
        "f_same_source_file": 1.0 if a.source_file and a.source_file == b.source_file else 0.0,
        "f_mi_eq": eq(a.mi, b.mi),
    }
