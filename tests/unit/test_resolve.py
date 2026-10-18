"""Entity resolution: features, the three passes, guards, clustering, survivorship."""

from datetime import date
from pathlib import Path

import pytest

from breachlens.resolve.cluster import Clusters
from breachlens.resolve.features import Side, f_dob
from breachlens.resolve.keys import canonical_first, last_soundex, load_nicknames
from breachlens.resolve.scoring import (
    MERGE,
    NO_MERGE,
    REVIEW,
    load_matching_config,
    score_pair,
    weighted,
)
from breachlens.resolve.stage import candidate_pairs
from breachlens.resolve.survivorship import golden_record, pick_address

ROOT = Path(__file__).resolve().parents[2]
CFG = load_matching_config(ROOT / "config")
NICK = load_nicknames(ROOT / "config" / "nicknames.csv")


def side(
    mid="M1",
    first="JOHN",
    last="SMITH",
    dob=date(1980, 1, 2),
    zip5="10001",
    line1="1 MAIN ST",
    ssn=None,
    dl=None,
    passport=None,
    file="a.csv",
    row=None,
    related=None,
    mi=None,
) -> Side:
    return Side(
        canonical_first(first, NICK),
        last,
        mi,
        dob,
        zip5,
        line1,
        ssn,
        dl,
        passport,
        file,
        row,
        related,
        mid,
    )


@pytest.mark.parametrize(
    ("a", "b", "want"),
    [
        (date(1980, 1, 2), date(1980, 1, 2), 1.0),
        (date(1980, 1, 2), date(1980, 2, 1), 0.7),
        (date(1980, 1, 2), date(1980, 5, 9), 0.3),
        (date(1980, 1, 2), date(1981, 1, 2), 0.0),
        (None, date(1980, 1, 2), None),
    ],
)
def test_f_dob(a, b, want):
    assert f_dob(a, b) == want


def test_nicknames_and_soundex():
    assert canonical_first("BOB", NICK) == "ROBERT" and canonical_first("ROBERT", NICK) == "ROBERT"
    assert last_soundex("DE LA VEGA") == last_soundex("DELAVEGA") and last_soundex(
        "MUÑOZ"
    ) == last_soundex("MUNOZ")


def test_pass_a_same_ssn_merges_even_with_another_address():
    s = score_pair(
        side(ssn="k1", zip5="23510", line1="1 A ST"), side("M2", ssn="k1", zip5="23219"), CFG
    )
    assert (s.pass_, s.decision, s.score) == ("A", MERGE, 1.0)


def test_pass_a_dob_conflict_goes_to_review():
    s = score_pair(side(ssn="k1"), side("M2", ssn="k1", dob=date(1975, 3, 3)), CFG)
    assert (s.decision, s.guard) == (REVIEW, "DOB_CONFLICT")


def test_different_ssn_never_merges():
    s = score_pair(side(ssn="k1"), side("M2", ssn="k2"), CFG)
    assert (s.decision, s.guard) == (NO_MERGE, "SSN_KEY_DIFFERS")


def test_pass_b_license_key():
    assert score_pair(side(dl="d1"), side("M2", first="X", last="Y", dl="d1"), CFG).pass_ == "B"


def test_pass_c_nickname_with_address_merges_and_nulls_are_reweighted():
    s = score_pair(side(first="ROBERT", dob=None), side("M2", first="BOB", dob=None), CFG)
    assert (s.pass_, s.decision, s.score) == ("C", MERGE, 1.0)
    assert weighted({"f_first_jw": 1.0, "f_last_jw": 1.0}, CFG.weights) == 1.0


def test_name_only_pairs_stay_in_review():
    s = score_pair(
        side(dob=None, zip5=None, line1=None), side("M2", dob=None, zip5=None, line1=None), CFG
    )
    assert (s.decision, s.guard, s.score) == (REVIEW, "NAME_ONLY", 0.89)


def test_dob_conflict_caps_pass_c():
    s = score_pair(side(dob=date(1998, 5, 8)), side("M2", dob=date(1998, 5, 9)), CFG)
    assert (s.decision, s.guard, s.score) == (NO_MERGE, "DOB_CONFLICT", 0.69)


def test_same_row_and_related_mentions_never_merge():
    assert score_pair(side(row="f#1"), side("M2", row="f#1"), CFG).guard == "SAME_SOURCE_ROW"
    assert score_pair(side(related="M2"), side("M2"), CFG).guard == "RELATED_MENTIONS"


def test_cluster_guard_keeps_twins_apart():
    """A no-SSN, no-DOB row scores high against both twins; it may join only one."""
    c = Clusters.of(["s1", "s2", None], [date(1998, 5, 8), date(1998, 5, 9), None])
    assert c.union(2, 0, 1.0)  # the customer row joins Jessica
    assert not c.union(2, 1, 0.93)  # ... so it cannot also pull in Jennifer
    assert c.find(1) != c.find(0) and c.min_edge[c.find(0)] == 1.0


def test_cluster_dob_transposition_is_compatible():
    c = Clusters.of([None, None], [date(1980, 1, 2), date(1980, 2, 1)])
    assert c.union(0, 1, 0.95)


def test_candidate_pairs_skip_different_ssn_keys():
    sides = [side("M1", ssn="a"), side("M2", ssn="b"), side("M3", ssn="a"), side("M4", ssn=None)]
    pairs, guarded = candidate_pairs(sides, ("last_soundex",))
    assert pairs == {(0, 2), (0, 3), (1, 3), (2, 3)} and guarded == 2


def test_survivorship_newest_address_nulls_last():
    ms = [
        {
            "mention_id": "M1",
            "address_line1": "OLD ST",
            "doc_date": "2024-12-31",
            "address_status": "VERIFIED",
        },
        {
            "mention_id": "M2",
            "address_line1": "NEW ST",
            "doc_date": "2026-09-30",
            "address_status": "VERIFIED",
        },
        {
            "mention_id": "M3",
            "address_line1": "NEW ST",
            "doc_date": None,
            "address_status": "VERIFIED",
        },
    ]
    assert pick_address(ms)["mention_id"] == "M2"


def test_golden_record_flags_and_review():
    ms = [
        {
            "mention_id": "M1",
            "first_name": "JOAN",
            "last_name": "HENDERSON",
            "middle_name": "JANE",
            "middle_initial": "J",
            "ssn_present": True,
            "card_present": True,
            "card_valid": "CARD_LUHN_FAIL",
            "dob": "2012-05-01",
            "source_file": "a.pdf",
            "source_type": "PDF",
            "qc_reasons": "",
        },
        {
            "mention_id": "M2",
            "first_name": "JOAN",
            "last_name": "HENDERSON",
            "mrn_present": "True",
            "source_file": "b.csv",
            "source_type": "SPREADSHEET",
            "qc_reasons": "DUPLICATE_CANDIDATE",
        },
    ]
    r = golden_record("P0001", ms, 0.95, date(2026, 10, 1))
    assert (r["middle_initial"], r["is_minor"], r["mention_count"]) == ("J", True, 2)
    assert (
        r["gov_id_exposed"]
        and r["financial_exposed"]
        and r["medical_exposed"]
        and r["needs_review"]
    )
    assert r["elements_exposed"] == "SSN; PAYMENT CARD; MEDICAL INFO; DATE OF BIRTH"
    assert r["source_types"] == "PDF;SPREADSHEET"
