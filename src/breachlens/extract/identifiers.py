"""SSN vs EIN / ITIN / NPI / provider-TIN disambiguation (`config/identifiers.yaml`).

Templates capture labelled identifiers; this module adds a generic scan so every
ID-shaped number on the page gets a kind from its nearest label (same line to the left,
or the line above). Business identifiers go to `excluded_identifiers`. Person SSNs that
are really ITINs (area 9xx with an ITIN group, ADR-035) or that equal a business id
are moved out of the mention.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from breachlens.ingest.tokens import Line, Token

BUSINESS_KINDS = ("EIN", "NPI", "PROVIDER_TIN")


class IdentifierConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    labels: dict[str, list[str]]
    shapes: dict[str, str]
    max_label_gap: float
    itin_group_ranges: list[tuple[int, int]]


def load_identifier_config(path: Path) -> IdentifierConfig:
    with path.open(encoding="utf-8") as fh:
        return IdentifierConfig.model_validate(yaml.safe_load(fh))


@dataclass(frozen=True)
class FoundId:
    kind: str
    value: str
    reason: str
    conf: float


def is_itin(digits: str, cfg: IdentifierConfig) -> bool:
    if len(digits) != 9 or digits[0] != "9":
        return False
    group = int(digits[3:5])
    return any(lo <= group <= hi for lo, hi in cfg.itin_group_ranges)


def _label_kind(text: str, cfg: IdentifierConfig, allowed: set[str]) -> tuple[str, str] | None:
    low = text.lower()
    for kind, words in cfg.labels.items():
        if kind not in allowed:
            continue
        for w in words:
            if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", low):
                return kind, w
    return None


def scan(lines: list[Line], cfg: IdentifierConfig) -> list[FoundId]:
    """Every business-ID-shaped token with a business label next to it."""
    found: list[FoundId] = []
    for i, line in enumerate(lines):
        for tok in line.tokens:
            text = "".join(ch for ch in tok.text if ch not in "~^`'\"")  # OCR stray marks
            shapes = [k for k in BUSINESS_KINDS if re.match(cfg.shapes[k], text)]
            if not shapes:
                continue
            left = " ".join(
                t.text for t in line.tokens if t.x1 <= tok.x0 and tok.x0 - t.x1 <= cfg.max_label_gap
            )
            hit = _label_kind(left, cfg, set(shapes))
            if hit is None and i > 0:
                above = [t for t in lines[i - 1].tokens if _x_overlap(t, tok, slack=40)]
                hit = _label_kind(" ".join(t.text for t in above), cfg, set(shapes))
            if hit is not None:
                found.append(FoundId(hit[0], text, f"label:{hit[1]}", tok.conf))
    return found


def _x_overlap(a: Token, b: Token, slack: float) -> bool:
    return a.x0 - slack <= b.x1 and b.x0 - slack <= a.x1


def dedupe(ids: list[FoundId]) -> list[FoundId]:
    seen: dict[tuple[str, str], FoundId] = {}
    for f in ids:
        seen.setdefault((f.kind, re.sub(r"\D", "", f.value)), f)
    return list(seen.values())
