from datetime import date

import pytest

from breachlens.synth.ground_truth import _flags, address_source, expected_status
from breachlens.synth.people import Address, Person
from breachlens.synth.records import Mention

POOL_ADDR = Address("828 I ST", "", "SACRAMENTO", "CA", "95814", "A005")
FAKE_ADDR = Address("12 ELM ST", "", "DAVIS", "CA", "95616", None)


def _person(addr=POOL_ADDR, old=None):
    return Person(
        pid="T0001",
        cast="BASE",
        household="H0001",
        first="Lee",
        last="Hernandez",
        dob=date(1965, 12, 8),
        ssn="152562089",
        address=addr,
        old_address=old,
    )


def _mention(p, line1, planted=()):
    return Mention("pdf/x.pdf", "PDF", "PATIENT", p, fields={"line1": line1}, planted=set(planted))


@pytest.mark.parametrize(
    ("addr", "planted", "status"),
    [
        (POOL_ADDR, (), "VERIFIED"),
        (FAKE_ADDR, (), "UNVERIFIED"),
        (POOL_ADDR, ("P10",), "CORRECTED"),
        (POOL_ADDR, ("P11",), "INVALID"),
    ],
)
def test_expected_status(addr, planted, status):
    p = _person(addr)
    assert expected_status(_mention(p, addr.line1, planted)) == status


def test_expected_status_uses_the_printed_old_address():
    p = _person(POOL_ADDR, old=FAKE_ADDR)
    assert expected_status(_mention(p, FAKE_ADDR.line1)) == "UNVERIFIED"
    assert expected_status(_mention(p, POOL_ADDR.line1)) == "VERIFIED"


def test_no_address_no_status():
    assert expected_status(_mention(_person(), "")) == ""
    assert address_source(None) == ""


def test_element_flags_include_free_text_and_damaged_cards():
    f = _flags(
        {"notes_pii": "MRN", "card": "", "card_status": "PRECISION_LOST", "member_id": "ABC1"}
    )
    assert f["mrn"] and f["card"] and f["health_member_id"] and not f["ssn"]
    assert _flags({"notes_pii": "SSN"})["ssn"]
    assert not _flags({"card_status": "TEXT"})["card"]


@pytest.mark.parametrize(
    ("status", "triggers"),
    [("TEXT", True), ("PREMASKED", False), ("PRECISION_LOST", True), ("LUHN_FAIL", True)],
)
def test_card_trigger_rule(status, triggers):
    from pathlib import Path

    from breachlens.synth.settings import load_synth_settings

    rule = load_synth_settings(Path(__file__).resolve().parents[2] / "config").element_rules.card
    assert rule.triggers(status) is triggers
    assert (status in rule.review_on) is (status in {"PRECISION_LOST", "LUHN_FAIL"})
