"""Driver license and passport format checks (`config/dl_formats.yaml`, simplified)."""

from __future__ import annotations

import re

PASSPORT = re.compile(r"^(?:[A-Z]\d{8}|\d{9})$")


def dl_codes(
    number: str | None, state: str | None, formats: dict[str, list[re.Pattern]]
) -> list[str]:
    if not number:
        return []
    if not state:
        return ["DL_STATE_MISSING"]
    pats = formats.get(state.upper())
    n = re.sub(r"[\s-]", "", number.upper())
    if pats and not any(p.fullmatch(n) for p in pats):
        return ["DL_FORMAT_STATE"]
    return []


def passport_codes(number: str | None) -> list[str]:
    if not number:
        return []
    return [] if PASSPORT.fullmatch(re.sub(r"\s", "", number.upper())) else ["PASSPORT_FORMAT"]
