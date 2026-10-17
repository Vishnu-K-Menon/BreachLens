import random
import re
from pathlib import Path

import pytest
import yaml

from breachlens.synth import identifiers as ids

ROOT = Path(__file__).resolve().parents[2]
KNOWN_INVALID = frozenset({"078051120", "123456789", "219099999"})


@pytest.fixture
def rng():
    return random.Random(7)


@pytest.mark.parametrize(
    ("number", "ok"),
    [
        ("4111111111111111", True),
        ("4111111111111112", False),
        ("5555555555554444", True),
        ("12", False),
        ("41a1", False),
    ],
)
def test_luhn(number, ok):
    assert ids.luhn_valid(number) is ok


def test_cards_use_test_iins_and_pass_luhn(rng):
    for _ in range(300):
        card = ids.card_number(rng, ["411111", "555555"])
        assert len(card) == 16 and card[:6] in {"411111", "555555"}
        assert ids.luhn_valid(card)
        assert not ids.luhn_valid(ids.break_luhn(card))


@pytest.mark.parametrize(
    ("number", "ok"), [("011000015", True), ("011000016", False), ("12345", False)]
)
def test_aba(number, ok):
    assert ids.aba_valid(number) is ok


def test_generated_routing_numbers_pass_aba(rng):
    assert all(ids.aba_valid(ids.routing_number(rng)) for _ in range(300))


def test_npi_check_digit():
    assert ids.luhn_check_digit("80840" + "123456789") == "3"  # CMS example NPI 1234567893


def test_generated_npis_are_valid(rng):
    for _ in range(100):
        n = ids.npi(rng)
        assert len(n) == 10 and ids.luhn_valid("80840" + n)


@pytest.mark.parametrize(
    ("ssn", "ok"),
    [
        ("123456788", True),
        ("000123456", False),
        ("666123456", False),
        ("912345678", False),
        ("123006789", False),
        ("123450000", False),
    ],
)
def test_ssn_shape(ssn, ok):
    assert ids.ssn_valid_shape(ssn) is ok


def test_generated_ssns_are_valid_and_avoid_known_invalid(rng):
    for _ in range(500):
        s = ids.ssn(rng, KNOWN_INVALID)
        assert ids.ssn_valid_shape(s) and s not in KNOWN_INVALID
    assert all(ids.ssn(rng, KNOWN_INVALID, leading_zero=True)[0] == "0" for _ in range(50))


def test_dl_patterns_generate_matching_values(rng):
    formats = yaml.safe_load((ROOT / "config" / "dl_formats.yaml").read_text(encoding="utf-8"))
    for patterns in formats.values():
        for pattern in patterns:
            for _ in range(50):
                assert re.fullmatch(pattern, ids.from_pattern(rng, pattern))


def test_unsupported_pattern_raises(rng):
    with pytest.raises(ValueError):
        ids.from_pattern(rng, r"^[A-Z]{2}\w+$")


def test_phone_is_fictional_e164(rng):
    for _ in range(100):
        assert re.fullmatch(r"\+1(415|916)55501\d\d", ids.phone(rng, ["415", "916"]))


def test_ein_shape(rng):
    assert all(re.fullmatch(r"\d{2}-\d{7}", ids.ein(rng)) for _ in range(50))
