"""Address normalization (VALIDATION_RULES.md, address rules).

PDF mentions carry a printed block (`raw_address`, `STREET [UNIT]\\nCITY, ST ZIP`);
spreadsheet mentions are already split. Street lines are kept as printed, upper-cased
(ADR-059: suffix standardization is left to matching). Units move to line 2 in the
USPS form `APT 6F`; UPPER/LOWER stand alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from breachlens.validate.settings import AddressAbbrev

LAST_LINE = re.compile(
    r"^(?P<city>.*?),?\s+(?P<state>[A-Z]{2})\s+(?P<zip>\d{3,5})(?:-(?P<zip4>\d{4}))?$"
)


@dataclass
class AddressResult:
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    zip5: str | None = None
    zip4: str | None = None
    country: str = "US"
    zip_suggestion: str | None = None  # padded ZIP for a leading-zero state
    codes: list[str] = field(default_factory=list)


def _s(v: Any) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return ""
    return " ".join(str(v).split()).upper()


def _unit_regexes(cfg: AddressAbbrev) -> tuple[re.Pattern, re.Pattern, re.Pattern]:
    names = "|".join(re.escape(k) for k in sorted(cfg.unit_designators, key=len, reverse=True))
    spaced = re.compile(rf"(?:^|\s)({names})\s+(\w*\d\w*|[A-Z])$")  # APT 6F, STE 200, UNIT B
    joined = re.compile(rf"(?:^|\s)({names})(\d\w*)$")  # APT6F
    alone = re.compile(rf"\s({'|'.join(sorted(cfg.standalone_units))})$")  # UPPER / LOWER
    return spaced, joined, alone


def format_unit(text: str, cfg: AddressAbbrev) -> tuple[str, bool]:
    """`APT6F` -> `APT 6F`, `SUITE 200` -> `STE 200`. Returns (unit, reformatted)."""
    t = _s(text)
    spaced, joined, _ = _unit_regexes(cfg)
    if m := joined.match(" " + t):
        return f"{cfg.unit_designators[m.group(1)]} {m.group(2)}", True
    if m := spaced.match(" " + t):
        std = f"{cfg.unit_designators[m.group(1)]} {m.group(2)}"
        return std, std != t
    return t, False


def split_unit(line1: str, cfg: AddressAbbrev) -> tuple[str, str | None, bool]:
    """(street, unit or None, reformatted) for a unit printed at the end of line 1."""
    spaced, joined, alone = _unit_regexes(cfg)
    for rx in (joined, spaced):
        if (m := rx.search(line1)) and m.start(1) > 0:
            unit, changed = format_unit(line1[m.start(1) :], cfg)
            return line1[: m.start(1)].strip(), unit, changed or rx is joined
    if m := alone.search(line1):
        return line1[: m.start()].strip(), m.group(1), False
    return line1, None, False


def normalize_address(
    row: dict[str, Any], cfg: AddressAbbrev, leading_zero_states: frozenset[str]
) -> AddressResult:
    res = AddressResult()
    line1, line2 = _s(row.get("address_line1")), _s(row.get("address_line2"))
    city, state = _s(row.get("city")), _s(row.get("state"))
    zip5, zip4 = _s(row.get("zip5")), _s(row.get("zip4"))
    raw = row.get("raw_address")
    if not line1 and isinstance(raw, str) and raw.strip():
        lines = [_s(x) for x in raw.split("\n") if x.strip()]
        if lines and (m := LAST_LINE.match(lines[-1])):
            city, state, zip5, zip4 = m["city"], m["state"], m["zip"], m["zip4"] or ""
            lines = lines[:-1]
        line1 = lines[0] if lines else ""
        line2 = " ".join(lines[1:2])
    if line1:
        street, unit, reformatted = split_unit(line1, cfg)
        if unit and not line2:
            line1, line2 = street, unit
            res.codes.append("ADDR_LINE2_SPLIT")
            if reformatted:
                res.codes.append("ADDR_UNIT_FORMAT")
    if line2:
        unit, changed = format_unit(line2, cfg)
        if changed and "ADDR_UNIT_FORMAT" not in res.codes:
            res.codes.append("ADDR_UNIT_FORMAT")
        line2 = unit
    if not line1:
        res.codes.append("ADDR_MISSING")
    elif re.match(cfg.po_box_pattern, line1):
        res.codes.append("ADDR_PO_BOX")
    if state and state not in cfg.states:
        res.codes.append("ADDR_STATE_INVALID")
    if zip5 and not re.fullmatch(r"\d{5}", zip5):
        res.codes.append("ADDR_ZIP_FORMAT")
        if re.fullmatch(r"\d{4}", zip5) and state in leading_zero_states:
            res.zip_suggestion = "0" + zip5
    res.address_line1, res.address_line2 = line1 or None, line2 or None
    res.city, res.state, res.zip5, res.zip4 = (
        city or None,
        state or None,
        zip5 or None,
        zip4 or None,
    )
    return res
