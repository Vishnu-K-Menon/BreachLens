"""HMAC keys for matching (PRIVACY.md §2, ADR-060).

`key = HMAC-SHA256(salt, "<KIND>:<normalized value>")`, first 16 hex characters. The
kind prefix keeps an SSN and a license with the same digits apart. The salt
(`BREACHLENS_SALT`) never leaves `Context.salt`.
"""

from __future__ import annotations

import hashlib
import hmac
import re

KEY_HEX = 16


def hmac_key(salt: bytes, kind: str, value: str | None) -> str | None:
    if not value:
        return None
    msg = f"{kind}:{value}".encode()
    return hmac.new(salt, msg, hashlib.sha256).hexdigest()[:KEY_HEX]


def ssn_key(salt: bytes, ssn: str | None) -> str | None:
    d = re.sub(r"\D", "", ssn or "")
    return hmac_key(salt, "SSN", d) if len(d) == 9 else None


def dl_key(salt: bytes, number: str | None, state: str | None) -> str | None:
    n = re.sub(r"[\s-]", "", (number or "").upper())
    return hmac_key(salt, "DL", f"{(state or '').upper()}:{n}") if n else None


def passport_key(salt: bytes, number: str | None, country: str | None) -> str | None:
    n = re.sub(r"\s", "", (number or "").upper())
    return hmac_key(salt, "PASSPORT", f"{(country or 'US').upper()}:{n}") if n else None
