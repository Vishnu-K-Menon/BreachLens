"""Scan notes / comment columns for PII (SPREADSHEET_TRACK.md §7).

The same validators as the identifier rules: SSN-shaped and SSN-valid, card numbers
that pass Luhn, labelled MRNs. A hit attaches to the row's person and fires
FREE_TEXT_PII_FOUND (WARN, a reviewer should confirm).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from breachlens.sheets.settings import FreetextCfg
from breachlens.synth.identifiers import luhn_valid, ssn_valid_shape


@dataclass(frozen=True)
class Hit:
    kind: str  # SSN / CARD / MRN
    value: str
    start: int
    end: int


def scan_text(text: str, cfg: FreetextCfg) -> list[Hit]:
    hits: list[Hit] = []
    for m in re.finditer(cfg.ssn, text or ""):
        digits = re.sub(r"\D", "", m.group(0))
        if ssn_valid_shape(digits):
            hits.append(Hit("SSN", digits, m.start(), m.end()))
    for m in re.finditer(cfg.card, text or ""):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and luhn_valid(digits):
            hits.append(Hit("CARD", digits, m.start(), m.end()))
    for m in re.finditer(cfg.mrn, text or "", re.I):
        hits.append(Hit("MRN", m.group(1), m.start(), m.end()))
    return hits
