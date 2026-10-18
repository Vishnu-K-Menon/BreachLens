from pathlib import Path

from breachlens.sheets.freetext import scan_text
from breachlens.sheets.reshape import wide_groups
from breachlens.sheets.settings import load_sheet_settings

ROOT = Path(__file__).resolve().parents[2]
S = load_sheet_settings(ROOT / "config")


def test_freetext_finds_valid_ssn_card_and_mrn():
    hits = scan_text(
        "Verified SSN 123-45-6789; card 4111 1111 1111 1111; MRN# 00123456", S.sheets.freetext
    )
    assert {(h.kind, h.value) for h in hits} == {
        ("SSN", "123456789"),
        ("CARD", "4111111111111111"),
        ("MRN", "00123456"),
    }


def test_freetext_ignores_invalid_shapes():
    # 000 area SSN and a Luhn-failing 16-digit number are not PII hits
    assert scan_text("ref 000-12-3456 and 4111 1111 1111 1112", S.sheets.freetext) == []
    assert scan_text("", S.sheets.freetext) == []


def test_wide_groups():
    headers = [
        "Subscriber",
        "Dep1_First",
        "Dep1_Last",
        "Dep1_DOB",
        "Dep2_First",
        "Dep2_Last",
        "Dep3_Rel",
    ]
    g = wide_groups(headers, S.sheets.reshape.wide_group_pattern)
    assert g == {
        1: {1: "First", 2: "Last", 3: "DOB"},
        2: {4: "First", 5: "Last"},
    }  # Dep3 alone dropped
    assert wide_groups(["Name", "DOB"], S.sheets.reshape.wide_group_pattern) == {}
