"""M4 acceptance on a freshly generated corpus: every planted validation case is
caught, normalized fields match ground truth, and element presence flags agree with it."""

import pytest

from breachlens.evaluate.validation import evaluate

pytestmark = [pytest.mark.libreoffice, pytest.mark.tesseract]


@pytest.fixture(scope="module")
def report(generated_run):
    ctx, mentions, _, truth = generated_run
    return evaluate(mentions, ctx.tables, ctx.audit.events, truth)


def test_every_planted_validation_case_is_caught(report):
    missed = [p for p in report["planted"] if p["caught"] != p["tagged"]]
    assert missed == []
    assert {p["case"] for p in report["planted"]} >= {
        f"P{n:02d}" for n in (1, 2, 3, 4, 6, 7, 9, 10, 11, 12, 13, 14, 15, 16)
    }


def test_planted_rules_do_not_fire_elsewhere(report):
    unexpected = {
        p["code"]: p["outside_planted"] for p in report["precision"] if p["outside_planted"]
    }
    # one known extra: a scan whose member ID OCR misread (M2) has no qualifying element left
    assert unexpected in ({}, {"PERSON_NO_QUALIFYING_ELEMENT": 1})


def test_normalized_fields_match_truth(report):
    for n in report["normalized"]:
        if n["n"] and n["field"] in {"first", "last", "line1", "city", "state", "zip5", "dob"}:
            assert n["ok"] / n["n"] >= 0.97, n


def test_presence_flags_agree_with_truth(report):
    for p in report["presence"]:
        assert p["agree"] / p["n"] >= 0.99, p
