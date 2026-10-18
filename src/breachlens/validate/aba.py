"""ROUTING_CHECKSUM_FAIL: 3(d1+d4+d7) + 7(d2+d5+d8) + (d3+d6+d9) ≡ 0 mod 10."""

from __future__ import annotations

import re

from breachlens.synth.identifiers import aba_valid


def routing_codes(value: str | None) -> list[str]:
    if not value:
        return []
    return [] if aba_valid(re.sub(r"\D", "", value)) else ["ROUTING_CHECKSUM_FAIL"]
