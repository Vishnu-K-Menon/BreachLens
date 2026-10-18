"""Flat synthetic records for the scale test (ADR-026, ADR-031).

`flat_records(n, …)` builds N claim-like rows in memory (used by `scale-test`), and
`write_large_claims` writes the 50,000-row `data/raw/scale/large_claims.csv`. Values are
drawn from small seeded pools, so 50k rows take seconds. Not part of accuracy metrics.
"""

from __future__ import annotations

import csv
import hashlib
import random
from datetime import timedelta
from pathlib import Path
from typing import Any

import zipcodes
from faker import Faker

from breachlens.synth import identifiers as ids
from breachlens.synth.settings import SynthSettings

COLUMNS = [
    "claim_id",
    "member_name",
    "dob",
    "ssn",
    "member_id",
    "address",
    "city",
    "state",
    "zip",
    "service_date",
    "cpt",
    "dx",
    "billed_amount",
]


def flat_records(n: int, settings: SynthSettings, seed: int | None = None) -> list[dict[str, Any]]:
    cfg = settings.config
    rng = random.Random((cfg.seed if seed is None else seed) + 909)
    fake = Faker("en_US")
    fake.seed_instance(rng.randint(0, 2**31))
    firsts = [fake.first_name() for _ in range(400)]
    lasts = [fake.last_name() for _ in range(600)]
    streets = [fake.street_name() for _ in range(400)]
    states = list(cfg.base_people_per_state)
    zips = sorted(
        (
            z
            for z in zipcodes.filter_by()
            if z.get("zip_code_type") == "STANDARD" and z["state"] in states
        ),
        key=lambda z: z["zip_code"],
    )
    ref = cfg.as_of_date
    rows = []
    for i in range(1, n + 1):
        z = rng.choice(zips)
        dob = ref - timedelta(days=rng.randint(365, 95 * 365))
        rows.append(
            {
                "claim_id": f"C{i:07d}",
                "member_name": f"{rng.choice(firsts)} {rng.choice(lasts)}",
                "dob": dob.strftime("%m/%d/%Y"),
                "ssn": ids.ssn(rng, settings.known_invalid_ssns),
                "member_id": ids.member_id(rng),
                "address": f"{rng.randint(1, 9999)} {rng.choice(streets)}",
                "city": z["city"].title(),
                "state": z["state"],
                "zip": z["zip_code"],
                "service_date": (ref - timedelta(days=rng.randint(1, 365))).strftime("%m/%d/%Y"),
                "cpt": ids.procedure_code(rng),
                "dx": ids.diagnosis_code(rng),
                "billed_amount": f"{rng.uniform(40, 4000):.2f}",
            }
        )
    return rows


def write_large_claims(settings: SynthSettings, path: Path) -> dict[str, Any]:
    n = settings.config.scale.large_claims_rows
    rows = flat_records(n, settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write("# SYNTHETIC - NOT REAL: scale-test data, not part of accuracy metrics\n")
        w = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return {"file": path.name, "rows": n, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
