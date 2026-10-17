"""US Census Geocoder client (single-line endpoint; the batch endpoint arrives in M5).

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
