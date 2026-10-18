"""US Census Geocoder clients: single-line (address pool, M1) and batch (pipeline, M5).

Only the street/city/state/ZIP string is ever sent (PRIVACY.md §7). Every response is
cached; with `offline=True` the cache is the only source and a miss is an error.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests

from breachlens.address.cache import JsonCache

logger = logging.getLogger(__name__)

ONELINE_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
BENCHMARK = "Public_AR_Current"

MATCH = "Match"
NO_MATCH = "No_Match"
TIE = "Tie"


class CensusError(RuntimeError):
    """The Census service could not be reached or returned an unusable response."""


class CensusOfflineError(CensusError):
    """Offline mode and the request is not in the cache."""


@dataclass(frozen=True)
class OnelineResult:
    status: str
    n_matches: int
    matched_address: str | None
    city: str | None
    state: str | None
    zip5: str | None
    fetched_at: str
    from_cache: bool


def oneline_address(line1: str, city: str, state: str, zip5: str) -> str:
    return f"{line1}, {city}, {state} {zip5}"


def parse_oneline(response: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Return (status, matches) from a single-line geocoder JSON response."""
    try:
        matches = response["result"]["addressMatches"]
    except (KeyError, TypeError) as exc:
        raise CensusError("unexpected Census response shape") from exc
    if not matches:
        return NO_MATCH, []
    return (MATCH if len(matches) == 1 else TIE), matches


def geocode_oneline(
    line1: str,
    city: str,
    state: str,
    zip5: str,
    *,
    cache: JsonCache,
    offline: bool,
    session: requests.Session | None = None,
    timeout_s: float = 30.0,
    retries: int = 2,
    pause_s: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
) -> OnelineResult:
    """Geocode one address with the Census single-line endpoint (cached)."""
    params = {
        "address": oneline_address(line1, city, state, zip5),
        "benchmark": BENCHMARK,
        "format": "json",
    }
    key = JsonCache.key("GET", ONELINE_URL, params)
    entry = cache.get(key)
    from_cache = entry is not None
    if entry is None:
        if offline:
            raise CensusOfflineError(f"offline and not cached: {params['address']}")
        http = session or requests.Session()
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = http.get(ONELINE_URL, params=params, timeout=timeout_s)
                if resp.status_code >= 500:
                    raise CensusError(f"Census HTTP {resp.status_code}")
                resp.raise_for_status()
                payload = resp.json()
                parse_oneline(payload)  # validate before caching
                entry = cache.put(key, payload)
                break
            except (requests.RequestException, ValueError, CensusError) as exc:
                last_error = exc
                logger.warning("census attempt %d failed: %s", attempt + 1, exc)
                sleep(pause_s * (2**attempt))
        if entry is None:
            raise CensusError(f"Census request failed after {retries + 1} attempts") from last_error
        sleep(pause_s)

    status, matches = parse_oneline(entry.response)
    comps: dict[str, Any] = matches[0].get("addressComponents", {}) if status == MATCH else {}
    return OnelineResult(
        status=status,
        n_matches=len(matches),
        matched_address=matches[0].get("matchedAddress") if status == MATCH else None,
        city=comps.get("city"),
        state=comps.get("state"),
        zip5=comps.get("zip"),
        fetched_at=entry.fetched_at,
        from_cache=from_cache,
    )


# ---- batch endpoint (M5, ADR-063) -----------------------------------------------------
BATCH_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
BATCH_MAX_ROWS = 10_000


@dataclass(frozen=True)
class BatchResult:
    status: str  # Match / No_Match / Tie
    exact: bool | None  # Exact vs Non_Exact (Match only)
    matched_address: str | None  # "828 I ST, SACRAMENTO, CA, 95814"
    tiger_line_id: str | None
    fetched_at: str
    from_cache: bool


Address = tuple[str, str, str, str]  # line1 (no unit), city, state, zip5


def batch_key(addr: Address) -> str:
    """One cache entry per address, so a rerun with a new address set sends only misses."""
    return JsonCache.key("POST", BATCH_URL, {"benchmark": BENCHMARK, "address": "|".join(addr)})


def batch_csv(rows: list[tuple[str, Address]]) -> str:
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    for rid, (line1, city, state, zip5) in rows:
        w.writerow([rid, line1, city, state, zip5])
    return buf.getvalue()


def parse_batch(text: str) -> dict[str, list[str]]:
    """id -> response row: [id, input, status, exactness, matched, coords, tiger_id, side]."""
    import csv
    import io

    out = {}
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        if len(row) < 3 or row[2] not in {MATCH, NO_MATCH, TIE}:
            raise CensusError(f"unexpected batch row shape ({len(row)} fields)")
        out[row[0]] = row
    return out


def _result(row: list[str], fetched_at: str, from_cache: bool) -> BatchResult:
    status = row[2]
    if status != MATCH:
        return BatchResult(status, None, None, None, fetched_at, from_cache)
    return BatchResult(
        status,
        row[3] == "Exact",
        row[4] or None,
        row[6] if len(row) > 6 else None,
        fetched_at,
        from_cache,
    )


def geocode_batch(
    addresses: list[Address],
    *,
    cache: JsonCache,
    online: bool,
    session: requests.Session | None = None,
    timeout_s: float = 120.0,
    retries: int = 2,
    pause_s: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[Address, BatchResult | None]:
    """Geocode unique addresses. Cache hits never touch the network. Offline (the
    default, `online=False`), a miss gives None (NOT_CHECKED); online, misses are sent in
    batches of at most 10,000 rows."""
    out: dict[Address, BatchResult | None] = {}
    misses: list[Address] = []
    for a in dict.fromkeys(addresses):
        hit = cache.get(batch_key(a))
        if hit is not None:
            out[a] = _result(hit.response["row"], hit.fetched_at, True)
        else:
            out[a] = None
            misses.append(a)
    if not online or not misses:
        return out
    http = session or requests.Session()
    for start in range(0, len(misses), BATCH_MAX_ROWS):
        chunk = misses[start : start + BATCH_MAX_ROWS]
        rows = [(str(i + 1), a) for i, a in enumerate(chunk)]
        body = batch_csv(rows)
        for attempt in range(retries + 1):
            try:
                resp = http.post(
                    BATCH_URL,
                    data={"benchmark": BENCHMARK},
                    files={"addressFile": ("addresses.csv", body, "text/csv")},
                    timeout=timeout_s,
                )
                if resp.status_code >= 500:
                    raise CensusError(f"HTTP {resp.status_code}")
                resp.raise_for_status()
                parsed = parse_batch(resp.text)
                break
            except (requests.RequestException, CensusError) as exc:
                if attempt == retries:
                    raise CensusError(f"Census batch failed: {exc}") from exc
                sleep(pause_s * 2**attempt)
        logger.info("census batch: %d addresses sent, %d rows back", len(chunk), len(parsed))
        for rid, a in rows:
            row = parsed.get(rid)
            if row is None:
                continue
            entry = cache.put(batch_key(a), {"row": row})
            out[a] = _result(row, entry.fetched_at, False)
        sleep(pause_s)
    return out
