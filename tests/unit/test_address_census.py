import pytest
import requests

from breachlens.address.cache import JsonCache
from breachlens.address.census import (
    MATCH,
    NO_MATCH,
    TIE,
    CensusError,
    CensusOfflineError,
    geocode_oneline,
    oneline_address,
    parse_oneline,
)


def _match(street="100 MAIN ST", city="SPRINGFIELD", state="IL", zip5="62701"):
    return {
        "matchedAddress": f"{street}, {city}, {state}, {zip5}",
        "addressComponents": {"city": city, "state": state, "zip": zip5},
    }


def _response(*matches):
    return {"result": {"addressMatches": list(matches)}}


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append(params)
        return self.responses.pop(0)


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        (_response(_match()), MATCH),
        (_response(), NO_MATCH),
        (_response(_match(), _match(street="102 MAIN ST")), TIE),
    ],
)
def test_parse_status(payload, status):
    assert parse_oneline(payload)[0] == status


def test_parse_rejects_bad_shape():
    with pytest.raises(CensusError):
        parse_oneline({"oops": 1})


def test_only_address_string_is_sent(tmp_path):
    session = FakeSession(FakeResponse(_response(_match())))
    geocode_oneline(
        "100 Main St",
        "Springfield",
        "IL",
        "62701",
        cache=JsonCache(tmp_path),
        offline=False,
        session=session,
        sleep=lambda s: None,
    )
    assert session.calls == [
        {
            "address": oneline_address("100 Main St", "Springfield", "IL", "62701"),
            "benchmark": "Public_AR_Current",
            "format": "json",
        }
    ]


def test_match_is_parsed_and_cached(tmp_path):
    cache = JsonCache(tmp_path)
    session = FakeSession(FakeResponse(_response(_match())))
    first = geocode_oneline(
        "100 Main St",
        "Springfield",
        "IL",
        "62701",
        cache=cache,
        offline=False,
        session=session,
        sleep=lambda s: None,
    )
    assert (first.status, first.zip5, first.state, first.from_cache) == (
        MATCH,
        "62701",
        "IL",
        False,
    )
    # Second call: cache hit, no network (the fake session has no responses left).
    second = geocode_oneline(
        "100 Main St",
        "Springfield",
        "IL",
        "62701",
        cache=cache,
        offline=False,
        session=session,
        sleep=lambda s: None,
    )
    assert second.from_cache and second.fetched_at == first.fetched_at
    assert len(session.calls) == 1


def test_offline_miss_raises_without_network(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network used in offline mode")

    monkeypatch.setattr(requests.Session, "get", boom)
    with pytest.raises(CensusOfflineError):
        geocode_oneline("1 A St", "X", "CA", "90001", cache=JsonCache(tmp_path), offline=True)


def test_server_errors_are_retried_then_raise(tmp_path):
    session = FakeSession(*(FakeResponse({}, 503) for _ in range(3)))
    with pytest.raises(CensusError):
        geocode_oneline(
            "1 A St",
            "X",
            "CA",
            "90001",
            cache=JsonCache(tmp_path),
            offline=False,
            session=session,
            sleep=lambda s: None,
        )
    assert len(session.calls) == 3
    assert list(tmp_path.iterdir()) == []  # failures are never cached


def test_retry_recovers(tmp_path):
    session = FakeSession(FakeResponse({}, 502), FakeResponse(_response()))
    result = geocode_oneline(
        "1 A St",
        "X",
        "CA",
        "90001",
        cache=JsonCache(tmp_path),
        offline=False,
        session=session,
        sleep=lambda s: None,
    )
    assert result.status == NO_MATCH


def test_cache_key_is_order_independent():
    a = JsonCache.key("get", "https://x", {"a": "1", "b": "2"})
    b = JsonCache.key("GET", "https://x", {"b": "2", "a": "1"})
    assert a == b and len(a) == 64
