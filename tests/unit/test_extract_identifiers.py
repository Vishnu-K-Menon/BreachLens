from pathlib import Path

import pytest

from breachlens.extract.identifiers import FoundId, dedupe, is_itin, load_identifier_config, scan
from breachlens.ingest.tokens import Token, group_lines

ROOT = Path(__file__).resolve().parents[2]
CFG = load_identifier_config(ROOT / "config" / "identifiers.yaml")


def words(text, x0, top, size=10.0):
    out, x = [], x0
    for w in text.split():
        out.append(Token(w, x, top, x + 6 * len(w), top + size))
        x += 6 * len(w) + 6
    return out


def test_ein_by_label_on_the_left_and_ssn_shape_ignored():
    toks = words("a Employee's social security number 481-62-7217", 44, 85) + words(
        "b Employer identification number (EIN) 65-1043321", 314, 85
    )
    found = scan(group_lines(toks), CFG)
    assert [(f.kind, f.value) for f in found] == [("EIN", "65-1043321")]


def test_label_on_the_line_above_and_stray_marks():
    toks = words("PROVIDER TIN", 45, 367, 7.5) + words("66~-8637940", 47, 381)
    assert [(f.kind, f.value) for f in scan(group_lines(toks), CFG)] == [
        ("PROVIDER_TIN", "66-8637940")
    ]


def test_npi_next_to_its_label_and_unlabelled_numbers_ignored():
    toks = words("NPI 2235116151", 46, 453) + words("2235116151", 300, 500)
    found = scan(group_lines(toks), CFG)
    assert len(found) == 1 and found[0].kind == "NPI"


@pytest.mark.parametrize(
    ("value", "itin"),
    [("912501234", True), ("912491234", False), ("812701234", False), ("999941234", True)],
)
def test_itin_group_ranges(value, itin):
    assert is_itin(value, CFG) is itin


def test_dedupe_by_kind_and_digits():
    a = FoundId("NPI", "2235116151", "template", 1.0)
    b = FoundId("NPI", "2235116151", "label:npi", 1.0)
    assert dedupe([a, b]) == [a]
