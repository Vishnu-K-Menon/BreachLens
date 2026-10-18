"""Three-pass pair decision (ARCHITECTURE.md §resolve, ADR-064).

- A: same `ssn_key` → MERGE, unless the DOBs conflict (then REVIEW).
- B: same `dl_key` (includes the state) or same `passport_key` → MERGE.
- C: weighted score over the features present (nulls re-weighted). ≥ merge_min MERGE,
  ≥ review_min REVIEW. A DOB conflict caps the score at 0.69. A pair with no DOB, ZIP or
  address evidence is at most REVIEW.

Guards (never merge): both `ssn_key` present and different; two mentions on the same
source row (subscriber/dependent); mentions linked by `related_mention_id`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from breachlens.resolve.features import Side, pair_features

MERGE, REVIEW, NO_MERGE = "MERGE", "REVIEW", "NO_MERGE"


class MatchingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    weights: dict[str, float]
    merge_min: float
    review_min: float
    dob_conflict_cap: float
    dob_conflict_max: float
    name_only_cap: float
    evidence_features: tuple[str, ...]
    blocking: tuple[str, ...]


def load_matching_config(config_dir: Path) -> MatchingConfig:
    with (config_dir / "matching.yaml").open(encoding="utf-8") as fh:
        return MatchingConfig.model_validate(yaml.safe_load(fh))


@dataclass(frozen=True)
class Scored:
    features: dict[str, float | None]
    score: float
    pass_: str  # A / B / C
    decision: str
    guard: str | None


def weighted(f: dict[str, float | None], weights: dict[str, float]) -> float | None:
    present = {k: w for k, w in weights.items() if f.get(k) is not None}
    total = sum(present.values())
    if not total:
        return None
    return sum(w * float(f[k]) for k, w in present.items()) / total


def score_pair(a: Side, b: Side, cfg: MatchingConfig) -> Scored:
    f = pair_features(a, b)
    dob_conflict = f["f_dob"] is not None and f["f_dob"] <= cfg.dob_conflict_max
    if (a.related and a.related == b.mention_id) or (b.related and b.related == a.mention_id):
        return Scored(f, 0.0, "C", NO_MERGE, "RELATED_MENTIONS")
    if a.source_row and a.source_row == b.source_row:
        return Scored(f, 0.0, "C", NO_MERGE, "SAME_SOURCE_ROW")
    if f["f_ssn_key_eq"] == 1.0:
        if dob_conflict:
            return Scored(f, cfg.dob_conflict_cap, "A", REVIEW, "DOB_CONFLICT")
        return Scored(f, 1.0, "A", MERGE, None)
    if f["f_ssn_key_eq"] == 0.0:
        return Scored(
            f, round(weighted(f, cfg.weights) or 0.0, 4), "A", NO_MERGE, "SSN_KEY_DIFFERS"
        )
    if f["f_dl_key_eq"] == 1.0 or (a.passport_key and a.passport_key == b.passport_key):
        return Scored(f, 1.0, "B", MERGE, None)
    s = weighted(f, cfg.weights)
    if s is None:
        return Scored(f, 0.0, "C", NO_MERGE, None)
    guard = None
    if dob_conflict and s > cfg.dob_conflict_cap:
        s, guard = cfg.dob_conflict_cap, "DOB_CONFLICT"
    if all(f.get(k) is None for k in cfg.evidence_features) and s > cfg.name_only_cap:
        s, guard = cfg.name_only_cap, "NAME_ONLY"
    decision = MERGE if s >= cfg.merge_min else (REVIEW if s >= cfg.review_min else NO_MERGE)
    return Scored(f, round(s, 4), "C", decision, guard)
