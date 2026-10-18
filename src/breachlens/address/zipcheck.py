"""Offline ZIP check with the `zipcodes` package (no network; ADR-058).

- ADDR_ZIP_STATE_MISMATCH: the ZIP belongs to another state.
- ADDR_ZIP_CITY_MISMATCH: the city is not the ZIP's city or one of its acceptable
  cities. The closest acceptable city (similarity >= threshold) is the suggestion.

The data is USPS-based; the address pool uses Census ZIPs, which can differ
(README backlog). Unknown ZIPs give no code here; Census decides in M5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import zipcodes
from rapidfuzz import fuzz, process


@dataclass
class ZipCheck:
    known: bool
    codes: list[str] = field(default_factory=list)
    city_suggestion: str | None = None


@lru_cache(maxsize=4096)
def _lookup(zip5: str) -> tuple[str, tuple[str, ...]] | None:
    try:
        m = zipcodes.matching(zip5)
    except (TypeError, ValueError):
        return None
    if not m:
        return None
    z = m[0]
    cities = (z["city"].upper(), *[c.upper() for c in z.get("acceptable_cities") or []])
    return z["state"].upper(), cities


def check_zip(
    zip5: str | None, city: str | None, state: str | None, min_similarity: float
) -> ZipCheck:
    if not zip5 or len(zip5) != 5 or not zip5.isdigit():
        return ZipCheck(False)
    hit = _lookup(zip5)
    if hit is None:
        return ZipCheck(False)
    z_state, cities = hit
    res = ZipCheck(True)
    if state and state != z_state:
        res.codes.append("ADDR_ZIP_STATE_MISMATCH")
    if city and city.upper() not in cities:
        res.codes.append("ADDR_ZIP_CITY_MISMATCH")
        best = process.extractOne(city.upper(), cities, scorer=fuzz.ratio)
        if best and best[1] >= min_similarity * 100:
            res.city_suggestion = best[0]
    return res
