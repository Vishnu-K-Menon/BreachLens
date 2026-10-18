"""SSN checks, one reason code per defect (VALIDATION_RULES.md, identifier rules).

ITIN precedence (ADR-035): a 9xx number whose group is in an ITIN range is an ITIN
(ITIN_DETECTED, routed to `excluded_identifiers`) and gets no SSN codes. A 9xx number
outside the ITIN ranges stays an SSN and fails SSN_AREA_INVALID. Never infer a state
from an SSN.
"""

from __future__ import annotations

import re

from breachlens.extract.identifiers import IdentifierConfig, is_itin


def ssn_codes(value: str | None, ids: IdentifierConfig, known_invalid: frozenset[str]) -> list[str]:
    if not value:
        return []
    d = re.sub(r"\D", "", value)
    if len(d) != 9:
        return ["SSN_FORMAT"]
    if is_itin(d, ids):
        return ["ITIN_DETECTED"]
    codes = []
    if d[:3] in {"000", "666"} or d[0] == "9":
        codes.append("SSN_AREA_INVALID")
    if d[3:5] == "00":
        codes.append("SSN_GROUP_INVALID")
    if d[5:] == "0000":
        codes.append("SSN_SERIAL_INVALID")
    if d in known_invalid:
        codes.append("SSN_KNOWN_INVALID")
    return codes
