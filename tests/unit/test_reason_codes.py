"""Every reason code: positive and negative cases (VALIDATION_RULES.md, M4 AC)."""

import pytest
from code_cases import CASES, V, counts


@pytest.mark.parametrize(
    "case",
    CASES,
    ids=[f"{c.code}-{'pos' if c.positive else 'neg'}-{i}" for i, c in enumerate(CASES)],
)
def test_case(case):
    fired = case.fn()
    assert (case.code in fired) is case.positive, (case.code, case.note, sorted(fired))


def test_every_m4_code_has_positive_and_negative_cases():
    c = counts()
    missing = [
        code
        for code in V.m4_codes()
        if c.get(code, {}).get("pos", 0) < 1 or c.get(code, {}).get("neg", 0) < 1
    ]
    assert missing == []


def test_cases_only_use_declared_codes():
    assert {c.code for c in CASES} <= set(V.severity)


def test_m5_codes_are_declared_but_deferred():
    m5 = {r.id for r in V.rules.rules if r.milestone == "M5"}
    assert m5 == {
        "ADDR_GEOCODE_NOMATCH",
        "ADDR_GEOCODE_TIE",
        "DOB_CONFLICT_IN_CLUSTER",
        "DUPLICATE_CANDIDATE",
        "NOTIFY_STATE_UNKNOWN",
    }
