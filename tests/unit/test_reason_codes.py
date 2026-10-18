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


def test_every_code_has_positive_and_negative_cases():
    """All 63 codes (M4 and M5) are emitted by now."""
    c = counts()
    missing = [
        r.id
        for r in V.rules.rules
        if c.get(r.id, {}).get("pos", 0) < 1 or c.get(r.id, {}).get("neg", 0) < 1
    ]
    assert missing == []
    assert len(V.rules.rules) == 63


def test_cases_only_use_declared_codes():
    assert {c.code for c in CASES} <= set(V.severity)
