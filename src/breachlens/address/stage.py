"""Address stage: Census batch geocoding → `address_status` (VALIDATION_RULES.md, ADR-063).

Only street line 1 (no unit), city, state and ZIP are sent (PRIVACY.md §7). The pipeline
default is `offline: true`. Then only cached results are used, and an address with no
cache entry is NOT_CHECKED. `breachlens run --online` fills the cache once.

| evidence | address_status |
|---|---|
| Census Match + Exact, ZIP check OK | VERIFIED |
| ZIP check made an accepted city fix (M4) | CORRECTED |
| Census Match + Non_Exact on the same house number and street | CORRECTED + suggestion |
| Census Match + Non_Exact to another street/ZIP (rejected) | UNVERIFIED + ADDR_GEOCODE_NOMATCH |
| Census Tie | UNVERIFIED + ADDR_GEOCODE_TIE |
| Census No_Match | UNVERIFIED + ADDR_GEOCODE_NOMATCH |
| invalid state / unfixable ZIP (M4) | INVALID |
| offline cache miss | NOT_CHECKED |
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any

import pandas as pd
from rapidfuzz import fuzz

from breachlens.address.cache import JsonCache
from breachlens.address.census import MATCH, TIE, BatchResult, geocode_batch
from breachlens.context import Context
from breachlens.validate.completeness import present
from breachlens.validate.engine import qc_status
from breachlens.validate.settings import load_validation_settings

logger = logging.getLogger(__name__)
STREET_MIN_SIMILARITY = 95  # a correction keeps the house number and the street


def _s(v: Any) -> str:
    return str(v).strip().upper() if present(v) else ""


def address_of(row: dict[str, Any]) -> tuple[str, str, str, str] | None:
    line1 = _s(row.get("address_line1"))
    if not line1 or row.get("address_status") == "INVALID":
        return None
    return (line1, _s(row.get("city")), _s(row.get("state")), _s(row.get("zip5")))


def accept_non_exact(addr: tuple[str, str, str, str], matched: str | None) -> bool:
    """A Non_Exact match is a correction only if it is the same house number and street
    and keeps the ZIP or the city; the geocoder otherwise snaps fake streets to a real
    nearby one (e.g. 4603 ANDERSON KEYS 32825 -> 4603 ANDERSON RD 32812)."""
    if not matched:
        return False
    parts = [p.strip() for p in matched.split(",")]
    if len(parts) < 4:
        return False
    m_line, m_city, m_zip = parts[0].upper(), parts[1].upper(), parts[3][:5]
    line1, city, _, zip5 = addr
    same_number = line1.split()[:1] == m_line.split()[:1]
    same_street = fuzz.token_sort_ratio(line1, m_line) >= STREET_MIN_SIMILARITY
    return same_number and same_street and (m_zip == zip5 or m_city == city)


def status_for(
    row: dict[str, Any], res: BatchResult | None, addr: tuple[str, str, str, str]
) -> tuple[str, list[str], str | None]:
    """(address_status, new codes, suggestion)."""
    codes = str(row.get("qc_reasons") or "").split(";")
    city_fixed = "ADDR_ZIP_CITY_MISMATCH" in codes and present(row.get("address_suggestion"))
    zip_ok = not {"ADDR_ZIP_CITY_MISMATCH", "ADDR_ZIP_STATE_MISMATCH"} & set(codes)
    if city_fixed:
        return "CORRECTED", [], None
    if res is None:
        return "NOT_CHECKED", [], None
    if res.status == MATCH and res.exact:
        return ("VERIFIED" if zip_ok else "UNVERIFIED"), [], None
    if res.status == MATCH:
        if accept_non_exact(addr, res.matched_address):
            return "CORRECTED", [], res.matched_address
        return "UNVERIFIED", ["ADDR_GEOCODE_NOMATCH"], None
    if res.status == TIE:
        return "UNVERIFIED", ["ADDR_GEOCODE_TIE"], None
    return "UNVERIFIED", ["ADDR_GEOCODE_NOMATCH"], None


def stage_address(df: pd.DataFrame, ctx: Context) -> pd.DataFrame:
    if df.empty:
        return df
    s = load_validation_settings(ctx.paths.config_dir)
    rows = df.to_dict("records")
    addrs = [address_of(r) for r in rows]
    cache = JsonCache(ctx.paths.cache_dir / "census")
    online = not ctx.offline
    results = geocode_batch([a for a in addrs if a], cache=cache, online=online)
    statuses, sources, suggestions, reasons, qcs = [], [], [], [], []
    for r, a in zip(rows, addrs, strict=True):
        if a is None:
            statuses.append(r.get("address_status"))
            sources.append(r.get("address_source"))
            suggestions.append(r.get("address_suggestion"))
            reasons.append(r.get("qc_reasons"))
            qcs.append(r.get("qc_status"))
            continue
        res = results.get(a)
        status, new, suggestion = status_for(r, res, a)
        codes = [c for c in str(r.get("qc_reasons") or "").split(";") if c]
        for c in new:
            if c not in codes:
                codes.append(c)
                detail = {"severity": s.severity[c], "census": res.status if res else None}
                ctx.audit.log(
                    "address", "RULE_FIRED", item_id=r["mention_id"], code=c, detail=detail
                )
        statuses.append(status)
        sources.append("CENSUS" if res is not None else r.get("address_source"))
        suggestions.append(suggestion or r.get("address_suggestion"))
        reasons.append(";".join(codes) or None)
        qcs.append(qc_status(codes, s))
    out = df.copy()
    out["address_status"], out["address_source"] = statuses, sources
    out["address_suggestion"], out["qc_reasons"], out["qc_status"] = suggestions, reasons, qcs
    out["review_status"] = ["PENDING" if q != "PASS" else None for q in qcs]
    unique = {a for a in addrs if a}
    summary = {
        "online": online,
        "unique_addresses": len(unique),
        "from_cache": sum(1 for a in unique if results.get(a) and results[a].from_cache),
        "fetched": sum(1 for a in unique if results.get(a) and not results[a].from_cache),
        "not_checked": sum(1 for a in unique if results.get(a) is None),
        "status": dict(Counter(x for x in statuses if x)),
    }
    ctx.tables["address_summary"] = summary
    logger.info("address: %s", json.dumps(summary, sort_keys=True))
    return out
