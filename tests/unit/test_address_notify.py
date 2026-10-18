"""Census batch client, address status mapping, notification triggers."""

from pathlib import Path

import pytest

from breachlens.address.cache import JsonCache
from breachlens.address.census import CensusError, batch_csv, geocode_batch, parse_batch
from breachlens.address.stage import accept_non_exact, status_for
from breachlens.notify.triggers import hits_for, load_jurisdictions

ROOT = Path(__file__).resolve().parents[2]
# Recorded shape of a live addressbatch response (2026-10-18), addresses only.
RESPONSE = (
    '"1","2090 KITTREDGE ST, BERKELEY, CA, 94704","Match","Exact",'
    '"2090 KITTREDGE ST, BERKELEY, CA, 94704","-122.26,37.86","124994072","R"\n'
    '"2","828 I ST, SACRAMNETO, CA, 95814","Match","Non_Exact",'
    '"828 I ST, SACRAMENTO, CA, 95814","-121.4,38.5","133323343","R"\n'
    '"3","4603 ANDERSON KEYS, ORLANDO, FL, 32825","Match","Non_Exact",'
    '"4603 ANDERSON RD, ORLANDO, FL, 32812","-81.3,28.5","94426794","L"\n'
    '"4","5441 CHARLES FOREST, HOUSTON, TX, 77065","No_Match"\n'
)
A1 = ("2090 KITTREDGE ST", "BERKELEY", "CA", "94704")
A2 = ("828 I ST", "SACRAMNETO", "CA", "95814")
A3 = ("4603 ANDERSON KEYS", "ORLANDO", "FL", "32825")
A4 = ("5441 CHARLES FOREST", "HOUSTON", "TX", "77065")


class FakeSession:
    def __init__(self, text: str):
        self.text, self.calls = text, []

    def post(self, url, data, files, timeout):
        self.calls.append(files["addressFile"][1])
        return type(
            "R", (), {"status_code": 200, "text": self.text, "raise_for_status": lambda self: None}
        )()


def test_parse_batch_and_csv():
    rows = parse_batch(RESPONSE)
    assert rows["1"][2:4] == ["Match", "Exact"] and rows["4"][2] == "No_Match"
    assert batch_csv([("1", A1)]) == "1,2090 KITTREDGE ST,BERKELEY,CA,94704\n"
    with pytest.raises(CensusError):
        parse_batch('"1","x","Maybe"\n')


def test_offline_uses_cache_only_and_online_fills_it(tmp_path):
    cache = JsonCache(tmp_path)
    assert geocode_batch([A1, A2], cache=cache, online=False) == {A1: None, A2: None}
    s = FakeSession(RESPONSE)
    out = geocode_batch([A1, A2, A3, A4], cache=cache, online=True, session=s, sleep=lambda _: None)
    assert (
        out[A1].exact and not out[A2].exact and out[A4].status == "No_Match" and len(s.calls) == 1
    )
    again = geocode_batch([A1, A4], cache=cache, online=False)
    assert again[A1].from_cache and again[A4].status == "No_Match"
    s2 = FakeSession("")
    geocode_batch([A1, A2], cache=cache, online=True, session=s2, sleep=lambda _: None)
    assert s2.calls == []  # all cached: no request at all


def test_only_address_fields_are_sent(tmp_path):
    s = FakeSession(RESPONSE)
    geocode_batch([A1], cache=JsonCache(tmp_path), online=True, session=s, sleep=lambda _: None)
    assert s.calls == ["1,2090 KITTREDGE ST,BERKELEY,CA,94704\n"]


def test_non_exact_acceptance():
    assert accept_non_exact(A2, "828 I ST, SACRAMENTO, CA, 95814")  # city typo corrected
    assert not accept_non_exact(A3, "4603 ANDERSON RD, ORLANDO, FL, 32812")  # another street


@pytest.mark.parametrize(
    ("addr", "row", "want", "codes"),
    [
        (A1, {}, "VERIFIED", []),
        (A2, {}, "CORRECTED", []),
        (A3, {}, "UNVERIFIED", ["ADDR_GEOCODE_NOMATCH"]),
        (A4, {}, "UNVERIFIED", ["ADDR_GEOCODE_NOMATCH"]),
        (A1, {"qc_reasons": "ADDR_ZIP_STATE_MISMATCH"}, "UNVERIFIED", []),
        (A2, {"qc_reasons": "ADDR_ZIP_CITY_MISMATCH", "address_suggestion": "x"}, "CORRECTED", []),
    ],
)
def test_status_mapping(tmp_path, addr, row, want, codes):
    s = FakeSession(RESPONSE)
    res = geocode_batch(
        [A1, A2, A3, A4], cache=JsonCache(tmp_path), online=True, session=s, sleep=lambda _: None
    )
    status, new, _ = status_for(row, res[addr], addr)
    assert (status, new) == (want, codes)


def test_tie_and_cache_miss():
    from breachlens.address.census import BatchResult

    tie = BatchResult("Tie", None, None, None, "t", True)
    assert status_for({}, tie, A1)[:2] == ("UNVERIFIED", ["ADDR_GEOCODE_TIE"])
    assert status_for({}, None, A1)[0] == "NOT_CHECKED"


JUR, RULES = load_jurisdictions(ROOT / "config")


@pytest.mark.parametrize(
    ("person", "mentions", "state", "want"),
    [
        ({"ssn_exposed": True}, [], "CA", {"ssn"}),
        ({"mrn_exposed": True}, [], "VA", set()),  # VA does not cover medical info
        ({"mrn_exposed": True}, [], "CA", {"mrn"}),
        (
            {"bank_account_exposed": True},
            [{"bank_account_present": True}],
            "NY",
            set(),
        ),  # no routing
        (
            {"bank_account_exposed": True},
            [{"bank_account_present": True, "routing_number_present": True}],
            "NY",
            {"bank_account"},
        ),
        (
            {"card_exposed": True},
            [{"card_present": True, "card_valid": "PREMASKED_VALUE"}],
            "TX",
            set(),
        ),
        (
            {"card_exposed": True},
            [{"card_present": True, "card_valid": "CARD_LUHN_FAIL"}],
            "TX",
            {"card"},
        ),
        (
            {"card_exposed": True},
            [{"card_present": True, "card_valid": "XL_NUMBER_PRECISION_LOST"}],
            "TX",
            {"card"},
        ),
        ({"dob_exposed": True}, [], "FL", set()),
    ],
)
def test_trigger_rules(person, mentions, state, want):
    assert hits_for(person, mentions, set(JUR[state].covered_elements), RULES) == want


def test_states_missing_from_config_use_default():
    assert "NJ" not in JUR and "MA" not in JUR and "default" in JUR
