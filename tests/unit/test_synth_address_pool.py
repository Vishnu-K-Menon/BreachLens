import csv

import pytest

from breachlens.address.cache import JsonCache
from breachlens.address.census import BENCHMARK, ONELINE_URL, oneline_address
from breachlens.synth.address_pool import (
    CANDIDATE_COLUMNS,
    POOL_COLUMNS,
    Candidate,
    build_pool,
    read_candidates,
    verify,
    write_pool,
)

URL = "https://www.example.gov/library"


def _seed_cache(cache, c, matches):
    params = {
        "address": oneline_address(c.line1, c.city, c.state, c.zip5),
        "benchmark": BENCHMARK,
        "format": "json",
    }
    cache.put(JsonCache.key("GET", ONELINE_URL, params), {"result": {"addressMatches": matches}})


def _m(state, zip5):
    return {
        "matchedAddress": f"1 MAIN ST, TOWN, {state}, {zip5}",
        "addressComponents": {"city": "TOWN", "state": state, "zip": zip5},
    }


def _write_candidates(path, rows):
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(CANDIDATE_COLUMNS)
        w.writerows(rows)


def test_read_candidates_ok(tmp_path):
    p = tmp_path / "c.csv"
    _write_candidates(p, [["Town Library", "1 Main St", "Town", "NJ", "07102", URL]])
    assert read_candidates(p)[0].zip5 == "07102"


@pytest.mark.parametrize(
    "row",
    [
        ["Town Library", "1 Main St", "Town", "NJ", "7102", URL],
        ["Town Library", "1 Main St", "Town", "nj", "07102", URL],
        ["Town Library", "1 Main St", "Town", "NJ", "07102", "http://insecure.example"],
        ["Town Library", "1 Main St", "Town", "NJ", "07102", "https://x.gov/staff-directory"],
    ],
)
def test_read_candidates_rejects_bad_rows(tmp_path, row):
    p = tmp_path / "c.csv"
    _write_candidates(p, [row])
    with pytest.raises(ValueError):
        read_candidates(p)


def test_verify_keeps_match_and_corrects_zip(tmp_path):
    cache = JsonCache(tmp_path)
    c = Candidate("Lib", "1 Main St", "Town", "MA", "02116", URL)
    _seed_cache(cache, c, [_m("MA", "02117")])
    v = verify(c, cache, offline=True)
    assert v.kept and v.zip5 == "02117" and "corrected" in v.reason


@pytest.mark.parametrize(
    ("matches", "reason"),
    [
        ([], "No_Match"),
        ([_m("MA", "02116"), _m("MA", "02116")], "Tie"),
        ([_m("NH", "03101")], "state"),
    ],
)
def test_verify_drops_non_matches(tmp_path, matches, reason):
    cache = JsonCache(tmp_path)
    c = Candidate("Lib", "1 Main St", "Town", "MA", "02116", URL)
    _seed_cache(cache, c, matches)
    v = verify(c, cache, offline=True)
    assert not v.kept and reason in v.reason


def test_pool_is_sorted_numbered_and_keeps_leading_zeros(tmp_path):
    cache = JsonCache(tmp_path / "cache")
    cands = [
        Candidate("B Lib", "2 Main St", "Boston", "MA", "02116", URL),
        Candidate("A Lib", "1 Main St", "Austin", "TX", "78701", URL),
    ]
    for c in cands:
        _seed_cache(cache, c, [_m(c.state, c.zip5)])
    rows = build_pool([verify(c, cache, offline=True) for c in cands])
    assert [r["pool_id"] for r in rows] == ["A001", "A002"]
    assert [r["state"] for r in rows] == ["MA", "TX"]
    out = tmp_path / "pool.csv"
    write_pool(rows, out)
    text = out.read_text(encoding="utf-8")
    assert text.splitlines()[0] == ",".join(POOL_COLUMNS)
    assert ",02116," in text
