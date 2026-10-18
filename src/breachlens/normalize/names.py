"""Name normalization (VALIDATION_RULES.md, name rules).

Input is either a printed full name (`raw_name`, PDFs and FULL_NAME columns) or split
parts (FIRST/MIDDLE/LAST/SUFFIX columns). Output parts are upper-cased; hyphens,
apostrophes, accents and particles (DE LA VEGA) are kept.

Comma rule: `A, B` is `LAST, FIRST` unless the field label says otherwise
(`name_order_detected` from the template). `LAST SFX, FIRST M` and `LAST, FIRST, M`
are handled. Without a comma or a label, two tokens that are both plausible first
names give NAME_ORDER_AMBIGUOUS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz.distance import Levenshtein

from breachlens.validate.settings import RulesConfig

SUFFIX_LIKE = re.compile(r"^(?:[JS][A-Z]|[IVX]{1,4}|\d(?:ST|ND|RD|TH))$")


@dataclass
class NameResult:
    name_title: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    middle_initial: str | None = None
    last_name: str | None = None
    name_suffix: str | None = None
    codes: list[str] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)  # e.g. suffix suggestion


def _ws(s: str, codes: list[str]) -> str:
    clean = " ".join(s.split())
    if clean != s and "NAME_WHITESPACE" not in codes:
        codes.append("NAME_WHITESPACE")
    return clean


def _punct(s: str, codes: list[str]) -> str:
    fixed = re.sub(r"(?<=\w)\s*([’'])\s*(?=\w)", "'", s)
    fixed = re.sub(r"(?<=\w)\s*-\s*(?=\w)", "-", fixed)
    if fixed != s and "NAME_PUNCT_FIXED" not in codes:
        codes.append("NAME_PUNCT_FIXED")
    return fixed


def _clean(s: Any, codes: list[str]) -> str:
    if s is None or (isinstance(s, float) and s != s):
        return ""
    return _punct(_ws(str(s), codes), codes).upper()


def _suffix(tok: str, cfg: RulesConfig, res: NameResult) -> str | None:
    """Normalized suffix for a suffix-like token, else None. Invalid ones are kept."""
    t = tok.strip(".").upper()
    if t in cfg.valid_suffixes:
        return t
    if t in cfg.suffix_variants:
        return cfg.suffix_variants[t]
    if SUFFIX_LIKE.match(t):
        best = min(cfg.valid_suffixes, key=lambda v: Levenshtein.distance(t, v))
        if "NAME_SUFFIX_INVALID" not in res.codes:
            res.codes.append("NAME_SUFFIX_INVALID")
        if Levenshtein.distance(t, best) <= 1:
            res.notes["suffix_suggestion"] = best
        return t
    return None


def _split_tail_suffix(
    tokens: list[str], cfg: RulesConfig, res: NameResult, single_letter: bool = True
) -> list[str]:
    """Move a trailing suffix-like token to `name_suffix`. In given names a single letter
    (V, I, X) is a middle initial, not a suffix (`single_letter=False`)."""
    if len(tokens) < 2 or (not single_letter and len(tokens[-1].strip(".")) == 1):
        return tokens
    if s := _suffix(tokens[-1], cfg, res):
        res.name_suffix = s
        return tokens[:-1]
    return tokens


def _first_middle_last(tokens: list[str], cfg: RulesConfig) -> tuple[str, str, str]:
    if not tokens:
        return "", "", ""
    if len(tokens) == 1:
        return "", "", tokens[0]
    first = tokens[0]
    rest = tokens[1:]
    start = next((i for i, t in enumerate(rest[:-1]) if t in cfg.name_particles), len(rest) - 1)
    return first, " ".join(rest[:start]), " ".join(rest[start:])


def parse_full_name(
    raw: str,
    order: str | None,
    cfg: RulesConfig,
    lex_first: frozenset[str] | None = None,
    labelled: bool = True,
) -> NameResult:
    res = NameResult()
    s = _clean(raw, res.codes).replace(".", " ")
    s = " ".join(s.split())
    tokens = s.replace(",", " , ").split()
    if tokens and tokens[0] in cfg.titles:
        res.name_title = tokens[0]
        res.codes.append("NAME_TITLE_REMOVED")
        tokens = tokens[1:]
    text = " ".join(tokens).replace(" , ", ", ")
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) >= 2 and len(parts[-1].split()) == 1 and _suffix(parts[-1], cfg, NameResult()):
        res.name_suffix = _suffix(parts[-1], cfg, res)  # "JOHN SMITH, JR"
        parts = parts[:-1]
    if len(parts) >= 2 and order != "FIRST_LAST":
        last_toks = _split_tail_suffix(parts[0].split(), cfg, res)
        given = " ".join(parts[1:]).split()
        if res.name_suffix is None:
            given = _split_tail_suffix(given, cfg, res, single_letter=False)
        res.last_name = " ".join(last_toks)
        res.first_name = given[0] if given else ""
        res.middle_name = " ".join(given[1:])
    else:
        toks = _split_tail_suffix(" ".join(parts).split(), cfg, res)
        first, middle, last = _first_middle_last(toks, cfg)
        res.first_name, res.middle_name, res.last_name = first, middle, last
        if (
            not labelled
            and lex_first is not None
            and len(toks) == 2
            and all(t in lex_first for t in toks)
        ):
            res.codes.append("NAME_ORDER_AMBIGUOUS")
    _finish(res)
    return res


def normalize_parts(
    first: Any, middle: Any, last: Any, suffix: Any, cfg: RulesConfig
) -> NameResult:
    """Split FIRST/MIDDLE/LAST/SUFFIX columns."""
    res = NameResult()
    f, m, la, sx = (_clean(x, res.codes).replace(".", "") for x in (first, middle, last, suffix))
    if sx:
        res.name_suffix = _suffix(sx, cfg, res) or sx
    for value, which in ((la, "last"), (f, "first")):
        toks = value.split()
        if (
            len(toks) >= 2
            and _suffix(toks[-1], cfg, NameResult())
            and toks[-1] not in cfg.name_particles
        ):
            moved = _suffix(toks[-1], cfg, res)
            if res.name_suffix is None:
                res.name_suffix = moved
            res.codes.append("NAME_SUFFIX_IN_NAME")
            value = " ".join(toks[:-1])
        if which == "last":
            la = value
        else:
            f = value
    res.first_name, res.middle_name, res.last_name = f, m, la
    _finish(res)
    return res


def _finish(res: NameResult) -> None:
    for attr in ("first_name", "middle_name", "last_name", "name_suffix", "name_title"):
        v = getattr(res, attr)
        setattr(res, attr, v.strip() or None if isinstance(v, str) else v)
    res.middle_initial = res.middle_name[0] if res.middle_name else None
    if not res.last_name or not res.first_name:
        res.codes.append("NAME_MISSING")
