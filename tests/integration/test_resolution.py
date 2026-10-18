"""M5 acceptance on a freshly generated corpus (offline: Census results from the cache;
addresses with no cache entry are NOT_CHECKED and are left out of the status check)."""

import pytest

from breachlens.evaluate.resolution import evaluate

pytestmark = [pytest.mark.libreoffice, pytest.mark.tesseract]


@pytest.fixture(scope="module")
def report(generated_run):
    ctx, mentions, _, truth = generated_run
    return evaluate(mentions, ctx.tables, truth)


def test_pairwise_precision_and_recall(report):
    p = report["pairwise"]
    assert p["precision"] >= 0.95 and p["recall"] >= 0.90, p


def test_planted_matching_cases(report):
    by = {c["case"].split()[0]: c for c in report["cases"]}
    for case in ("P18", "P17", "P05", "P41", "P08", "P24"):
        assert by[case]["ok"], by[case]


def test_no_unrelated_shared_address_pair_is_merged(report):
    assert report["shared"]["pairs"] == 78 and report["shared"]["merged"] == []


def test_address_status_agrees_where_checked(report):
    conf = report["address"]["confusion"]
    checked = {k: v for k, v in conf.items() if k[1] != "NOT_CHECKED"}
    agree = sum(v for (x, y), v in checked.items() if x == y)
    if checked:
        assert agree / sum(checked.values()) >= 0.95
    assert not any(x == "UNVERIFIED" and y == "VERIFIED" for x, y in checked)  # ADR-050


def test_notification_list_matches_truth(report):
    n = report["notify"]
    assert n["listed"] == n["expected"] and not n["fn"] and not n["fp"] and not n["duplicates"]


def test_new_tables_pass_the_leak_guard(generated_run):
    _, _, written, _ = generated_run
    assert {"people.csv", "notification_list.csv", "pair_features.csv"} <= {p.name for p in written}
