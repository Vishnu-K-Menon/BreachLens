"""Contact normalization: phones to E.164 (US default region), emails lower-case."""

from __future__ import annotations

from typing import Any

import phonenumbers


def normalize_phone(v: Any) -> str | None:
    if v is None or (isinstance(v, float) and v != v) or not str(v).strip():
        return None
    try:
        n = phonenumbers.parse(str(v), "US")
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_possible_number(n):
        return None
    return phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164)


def normalize_email(v: Any) -> str | None:
    if v is None or (isinstance(v, float) and v != v):
        return None
    s = str(v).strip().lower()
    return s if "@" in s else None
