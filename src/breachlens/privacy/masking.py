"""Masking (PRIVACY.md §2, ADR-060): only the last 4 characters stay visible.

- SSN: `***-**-1234`
- other identifiers: `*` for every character but the last 4 (`************1234`)
- values already masked at the source keep their own mask, upper-cased
- free text (snippets, notes): SSN-, card- and account-like digit runs are masked
"""

from __future__ import annotations

import re


def mask_ssn(digits: str | None) -> str | None:
    if not digits:
        return None
    d = re.sub(r"\D", "", digits)
    return f"***-**-{d[-4:]}" if d else None


def mask_id(value: str | None) -> str | None:
    if not value:
        return None
    v = re.sub(r"\s", "", str(value))
    if len(v) <= 4:
        return "*" * len(v)
    return "*" * (len(v) - 4) + v[-4:]


def mask_premasked(value: str | None) -> str | None:
    """A pre-masked value keeps its mask; any digit run longer than 4 is re-masked."""
    if not value:
        return None
    return re.sub(r"\d{5,}", lambda m: "*" * (len(m.group()) - 4) + m.group()[-4:], value.upper())


_DIGIT_RUN = re.compile(r"\d[\d -]{7,}\d")


def mask_text(text: str | None) -> str | None:
    """Mask digit runs of 9+ digits (with optional spaces/dashes) in free text."""
    if not text:
        return text

    def sub(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group())
        return m.group() if len(digits) < 9 else "*" * (len(digits) - 4) + digits[-4:]

    return _DIGIT_RUN.sub(sub, text)
