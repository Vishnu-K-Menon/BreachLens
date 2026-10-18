"""CARD_LUHN_FAIL. The checksum itself lives with the generator (`synth/identifiers.py`)."""

from __future__ import annotations

import re

from breachlens.synth.identifiers import luhn_valid


def card_codes(value: str | None, status: str | None) -> list[str]:
    """Only full printed numbers are checked; pre-masked and precision-lost values
    already carry PREMASKED_VALUE / XL_NUMBER_PRECISION_LOST."""
    if not value or status in {"PREMASKED", "PRECISION_LOST"}:
        return []
    d = re.sub(r"\D", "", value)
    return [] if d and luhn_valid(d) else ["CARD_LUHN_FAIL"]
