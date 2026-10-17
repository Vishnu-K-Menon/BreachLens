"""Build `data/reference/address_pool.csv` from hand-collected public-building candidates.

Run: `python -m breachlens.synth.address_pool [--offline]`

Input `data/reference/address_candidates.csv` (name, line1, city, state, zip5,
source_url) lists public, non-residential buildings: libraries, city halls and post
offices (ADR-006, ADR-043). Each candidate is checked live with the Census single-line
geocoder (cached in `data/cache/census/`). A candidate is kept only if it is a `Match`
in the same state. Output columns: pool_id, name, line1, city, state, zip5, census_match,
verified_on, matched_address, source_url.

This is the only M1 code that uses the network; the pipeline default stays offline.
"""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from breachlens.address.cache import JsonCache
from breachlens.address.census import MATCH, CensusError, geocode_oneline

logger = logging.getLogger(__name__)

CANDIDATE_COLUMNS = ["name", "line1", "city", "state", "zip5", "source_url"]
POOL_COLUMNS = [
    "pool_id",
    "name",
    "line1",
    "city",
    "state",
    "zip5",
    "census_match",
    "verified_on",
    "matched_address",
    "source_url",
]

# Sources must be a building's official page or the USPS locator, never a page that
# lists individuals (ADR-048). This is a guard against obvious mistakes, not proof.
_PERSON_PAGE_HINTS = re.compile(r"staff|directory|people|employee|team|bio|council-?member", re.I)


@dataclass(frozen=True)
class Candidate:
    name: str
    line1: str
    city: str
    state: str
    zip5: str
    source_url: str


@dataclass(frozen=True)
class Verdict:
    candidate: Candidate
    status: str
    kept: bool
    reason: str
    zip5: str
    verified_on: str
    matched_address: str


def read_candidates(path: Path) -> list[Candidate]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != CANDIDATE_COLUMNS:
            raise ValueError(
                f"{path}: columns must be {CANDIDATE_COLUMNS}, got {reader.fieldnames}"
            )
        rows = [Candidate(**{k: (v or "").strip() for k, v in row.items()}) for row in reader]
    for c in rows:
        if not c.source_url.startswith("https://"):
            raise ValueError(f"{c.name}: source_url must be an https URL")
        if _PERSON_PAGE_HINTS.search(c.source_url):
            raise ValueError(f"{c.name}: source_url looks like a page about people: {c.source_url}")
        if not re.fullmatch(r"\d{5}", c.zip5) or not re.fullmatch(r"[A-Z]{2}", c.state):
            raise ValueError(f"{c.name}: bad state/ZIP {c.state} {c.zip5}")
    return rows


def verify(candidate: Candidate, cache: JsonCache, offline: bool) -> Verdict:
    c = candidate
    result = geocode_oneline(c.line1, c.city, c.state, c.zip5, cache=cache, offline=offline)
    verified_on = result.fetched_at[:10]
    if result.status != MATCH:
        return Verdict(c, result.status, False, result.status, c.zip5, verified_on, "")
    if (result.state or "").upper() != c.state:
        return Verdict(
            c,
            result.status,
            False,
            f"state mismatch ({result.state})",
            c.zip5,
            verified_on,
            result.matched_address or "",
        )
    zip5 = result.zip5 or c.zip5
    reason = "ok" if zip5 == c.zip5 else f"ok, ZIP corrected {c.zip5}->{zip5}"
    return Verdict(c, result.status, True, reason, zip5, verified_on, result.matched_address or "")


def build_pool(verdicts: list[Verdict]) -> list[dict[str, str]]:
    kept = sorted(
        (v for v in verdicts if v.kept),
        key=lambda v: (v.candidate.state, v.candidate.city, v.candidate.name),
    )
    return [
        {
            "pool_id": f"A{i:03d}",
            "name": v.candidate.name,
            "line1": v.candidate.line1.upper(),
            "city": v.candidate.city.upper(),
            "state": v.candidate.state,
            "zip5": v.zip5,
            "census_match": v.status,
            "verified_on": v.verified_on,
            "matched_address": v.matched_address,
            "source_url": v.candidate.source_url,
        }
        for i, v in enumerate(kept, start=1)
    ]


def write_pool(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=POOL_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def report(verdicts: list[Verdict]) -> str:
    lines = [
        "| name | city | state | ZIP | match status | kept | note |",
        "|---|---|---|---|---|---|---|",
    ]
    for v in sorted(
        verdicts, key=lambda v: (v.candidate.state, v.candidate.city, v.candidate.name)
    ):
        c = v.candidate
        lines.append(
            f"| {c.name} | {c.city} | {c.state} | {v.zip5} | {v.status} | "
            f"{'yes' if v.kept else 'NO'} | {v.reason} |"
        )
    return "\n".join(lines)


def main(
    candidates: Annotated[Path, typer.Option()] = Path("data/reference/address_candidates.csv"),
    out: Annotated[Path, typer.Option()] = Path("data/reference/address_pool.csv"),
    cache_dir: Annotated[Path, typer.Option()] = Path("data/cache/census"),
    offline: Annotated[bool, typer.Option(help="Use cached responses only.")] = False,
) -> None:
    """Verify every candidate with the Census geocoder and write the address pool."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cache = JsonCache(cache_dir)
    verdicts: list[Verdict] = []
    for c in read_candidates(candidates):
        try:
            verdicts.append(verify(c, cache, offline))
        except CensusError as exc:
            verdicts.append(Verdict(c, "ERROR", False, str(exc), c.zip5, "", ""))
    rows = build_pool(verdicts)
    write_pool(rows, out)
    typer.echo(report(verdicts))
    by_state: dict[str, int] = {}
    for r in rows:
        by_state[r["state"]] = by_state.get(r["state"], 0) + 1
    typer.echo(f"\nkept {len(rows)} of {len(verdicts)}; by state: {dict(sorted(by_state.items()))}")


if __name__ == "__main__":
    typer.run(main)
