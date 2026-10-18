"""Blocking keys and name canonicalization for entity resolution."""

from __future__ import annotations

import csv
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import jellyfish


@lru_cache(maxsize=4)
def load_nicknames(path: Path) -> dict[str, str]:
    """nickname -> canonical given name (upper case)."""
    with path.open(encoding="utf-8") as fh:
        rows = csv.DictReader(line for line in fh if not line.startswith("#"))
        return {r["nickname"].strip().upper(): r["canonical"].strip().upper() for r in rows}


def fold(s: str | None) -> str | None:
    """Upper case without accents (JOSÉ MUÑOZ -> JOSE MUNOZ) for comparisons only."""
    if not s:
        return None
    decomposed = unicodedata.normalize("NFKD", s.strip().upper())
    return "".join(c for c in decomposed if not unicodedata.combining(c)) or None


def canonical_first(first: str | None, nicknames: dict[str, str]) -> str | None:
    f = fold(first)
    return nicknames.get(f, f) if f else None


def last_soundex(last: str | None) -> str | None:
    """Soundex of the surname letters (DE LA VEGA -> DELAVEGA; accents dropped)."""
    if not last:
        return None
    letters = re.sub(r"[^A-Z]", "", fold(last) or "")
    return jellyfish.soundex(letters) if letters else None
