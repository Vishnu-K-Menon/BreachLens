"""Synthetic identifier generators and the checksums they satisfy.

Every value is random and fake by construction (ADR-048): cards use test IIN prefixes,
phones use 555-01xx, SSNs avoid unassigned ranges and the known-invalid list.
All functions take an explicit `random.Random` so output depends only on the seed.
"""

from __future__ import annotations

import random
import re

# IRS campus EIN prefixes (a valid-looking subset).
_EIN_PREFIXES = [
    f"{p:02d}" for p in [*range(20, 28), *range(30, 39), *range(41, 49), *range(50, 69)]
]
_ICD10 = [
    "E11.9",
    "I10",
    "J45.909",
    "M54.50",
    "K21.9",
    "F41.1",
    "Z00.00",
    "E78.5",
    "J06.9",
    "R51.9",
]
_CPT = ["99213", "99214", "99203", "93000", "80053", "71046", "85025", "36415"]


def digits(rng: random.Random, n: int) -> str:
    return "".join(str(rng.randrange(10)) for _ in range(n))


def luhn_check_digit(payload: str) -> str:
    """Check digit that makes `payload + digit` pass the Luhn test."""
    total = 0
    for i, ch in enumerate(reversed(payload)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def luhn_valid(number: str) -> bool:
    return number.isdigit() and len(number) > 1 and luhn_check_digit(number[:-1]) == number[-1]


def card_number(rng: random.Random, iins: list[str], length: int = 16) -> str:
    prefix = rng.choice(iins)
    payload = prefix + digits(rng, length - len(prefix) - 1)
    return payload + luhn_check_digit(payload)


def break_luhn(number: str) -> str:
    """Same number with a wrong check digit (planted case P14)."""
    return number[:-1] + str((int(number[-1]) + 1) % 10)


def aba_check_digit(first8: str) -> str:
    w = [3, 7, 1, 3, 7, 1, 3, 7]
    total = sum(int(d) * k for d, k in zip(first8, w, strict=True))
    return str((10 - total % 10) % 10)


def aba_valid(number: str) -> bool:
    """3(d1+d4+d7) + 7(d2+d5+d8) + (d3+d6+d9) ≡ 0 (mod 10)."""
    if not re.fullmatch(r"\d{9}", number):
        return False
    d = [int(c) for c in number]
    return (3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + d[2] + d[5] + d[8]) % 10 == 0


def routing_number(rng: random.Random) -> str:
    first8 = f"{rng.randint(1, 12):02d}" + digits(rng, 6)
    return first8 + aba_check_digit(first8)


def bank_account(rng: random.Random) -> str:
    return str(rng.randint(1, 9)) + digits(rng, rng.randint(9, 11))


def ssn_valid_shape(ssn: str) -> bool:
    """Area not 000/666/9xx, group not 00, serial not 0000."""
    if not re.fullmatch(r"\d{9}", ssn):
        return False
    area, group, serial = ssn[:3], ssn[3:5], ssn[5:]
    return area not in {"000", "666"} and area[0] != "9" and group != "00" and serial != "0000"


def ssn(rng: random.Random, known_invalid: frozenset[str], leading_zero: bool = False) -> str:
    while True:
        area = rng.randint(1, 99) if leading_zero else rng.randint(1, 899)
        value = f"{area:03d}{rng.randint(1, 99):02d}{rng.randint(1, 9999):04d}"
        if ssn_valid_shape(value) and value not in known_invalid:
            return value


def ein(rng: random.Random) -> str:
    return f"{rng.choice(_EIN_PREFIXES)}-{digits(rng, 7)}"


def npi(rng: random.Random) -> str:
    """10-digit NPI-like number with the CMS check digit (Luhn over 80840 + 9 digits)."""
    base = str(rng.choice([1, 2])) + digits(rng, 8)
    return base + luhn_check_digit("80840" + base)


_TOKEN = re.compile(r"\[A-Z\]|\\d\{(\d+)(?:,(\d+))?\}|\\d")


def from_pattern(rng: random.Random, pattern: str) -> str:
    """Generate a string for the simple regexes used in dl_formats.yaml."""
    body = pattern.removeprefix("^").removesuffix("$")
    out, pos = [], 0
    for m in _TOKEN.finditer(body):
        if m.start() != pos:
            raise ValueError(f"unsupported pattern: {pattern}")
        if m.group(0) == "[A-Z]":
            out.append(chr(rng.randint(65, 90)))
        elif m.group(0) == r"\d":
            out.append(digits(rng, 1))
        else:
            lo = int(m.group(1))
            hi = int(m.group(2)) if m.group(2) else lo
            out.append(digits(rng, rng.randint(lo, hi)))
        pos = m.end()
    if pos != len(body):
        raise ValueError(f"unsupported pattern: {pattern}")
    return "".join(out)


def drivers_license(rng: random.Random, state: str, formats: dict[str, list[str]]) -> str:
    return from_pattern(rng, rng.choice(formats[state]))


def passport(rng: random.Random) -> str:
    return chr(rng.randint(65, 90)) + digits(rng, 8)


def mrn(rng: random.Random) -> str:
    return str(rng.randint(1, 9)) + digits(rng, 7)


def member_id(rng: random.Random) -> str:
    return "".join(chr(rng.randint(65, 90)) for _ in range(3)) + digits(rng, 9)


def group_number(rng: random.Random) -> str:
    return digits(rng, 6)


def diagnosis_code(rng: random.Random) -> str:
    return rng.choice(_ICD10)


def procedure_code(rng: random.Random) -> str:
    return rng.choice(_CPT)


def employee_id(rng: random.Random) -> str:
    return str(rng.randint(1, 9)) + digits(rng, 5)


def student_id(rng: random.Random) -> str:
    return "S" + digits(rng, 7)


def phone(rng: random.Random, area_codes: list[str]) -> str:
    """E.164 phone in the fictional 555-0100..0199 range."""
    return f"+1{rng.choice(area_codes)}55501{rng.randint(0, 99):02d}"
