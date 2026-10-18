"""Resolve stage: block → score (passes A/B/C) → cluster → `person_id` → `people`.

Runs after privacy, so it sees HMAC keys and normalized fields only. Every scored pair
goes to `pair_features` (ADR-025). REVIEW pairs that end in different clusters get
DUPLICATE_CANDIDATE on both mentions; a same-SSN pair with conflicting DOBs gets
DOB_CONFLICT_IN_CLUSTER.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from itertools import combinations
from typing import Any

import pandas as pd

from breachlens.context import Context
from breachlens.normalize.dates import parse_iso
from breachlens.resolve.cluster import Clusters
from breachlens.resolve.features import FEATURES, Side
from breachlens.resolve.keys import canonical_first, fold, last_soundex, load_nicknames
from breachlens.resolve.scoring import MERGE, REVIEW, Scored, load_matching_config, score_pair
from breachlens.resolve.survivorship import build_people
from breachlens.validate.completeness import present
from breachlens.validate.engine import qc_status
from breachlens.validate.settings import load_validation_settings

logger = logging.getLogger(__name__)


def _v(r: dict[str, Any], k: str) -> str | None:
    v = r.get(k)
    return str(v).strip().upper() if present(v) else None


def side(r: dict[str, Any], nicknames: dict[str, str]) -> Side:
    row = (
        f"{r.get('source_file')}#{r.get('source_sheet') or ''}#{int(float(r['source_row']))}"
        if present(r.get("source_row"))
        else None
    )
    return Side(
        first=canonical_first(_v(r, "first_name"), nicknames),
        last=fold(_v(r, "last_name")),
        mi=_v(r, "middle_initial"),
        dob=parse_iso(r.get("dob")),
        zip5=_v(r, "zip5"),
        line1=_v(r, "address_line1"),
        ssn_key=_v(r, "ssn_key"),
        dl_key=_v(r, "dl_key"),
        passport_key=_v(r, "passport_key"),
        source_file=r.get("source_file"),
        source_row=row,
        related=r.get("related_mention_id") if present(r.get("related_mention_id")) else None,
        mention_id=r["mention_id"],
    )


def review_code(sc: Scored) -> str | None:
    """Reason code for a pair left in the gray zone (REVIEW), else None."""
    if sc.decision != REVIEW:
        return None
    return (
        "DOB_CONFLICT_IN_CLUSTER"
        if sc.guard == "DOB_CONFLICT" and sc.pass_ == "A"
        else "DUPLICATE_CANDIDATE"
    )


def candidate_pairs(
    sides: list[Side], blocking: tuple[str, ...]
) -> tuple[set[tuple[int, int]], int]:
    """Blocked pairs, plus the count of pairs dropped up front because both SSN keys are
    present and differ (the guard makes them NO_MERGE whatever the score; ADR-064)."""
    blocks: dict[tuple[str, Any], list[int]] = defaultdict(list)
    for i, s in enumerate(sides):
        for key in blocking:
            v = last_soundex(s.last) if key == "last_soundex" else getattr(s, key)
            if v:
                blocks[(key, v)].append(i)
    pairs: set[tuple[int, int]] = set()
    guarded = 0
    for members in blocks.values():
        by_key: dict[str, list[int]] = defaultdict(list)
        unkeyed = []
        for i in members:
            (by_key[sides[i].ssn_key] if sides[i].ssn_key else unkeyed).append(i)
        for same in by_key.values():  # same SSN key
            pairs.update(combinations(same, 2))
        keyed = [i for same in by_key.values() for i in same]
        pairs.update(tuple(sorted(x)) for x in combinations(unkeyed, 2))
        pairs.update(tuple(sorted((u, k))) for u in unkeyed for k in keyed)
        n = len(keyed)
        guarded += n * (n - 1) // 2 - sum(len(v) * (len(v) - 1) // 2 for v in by_key.values())
    return pairs, guarded


def resolve(df: pd.DataFrame, ctx: Context) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cfg = load_matching_config(ctx.paths.config_dir)
    nick = load_nicknames(ctx.paths.config_dir / "nicknames.csv")
    rows = df.to_dict("records")
    sides = [side(r, nick) for r in rows]
    blocked, ssn_guarded = candidate_pairs(sides, cfg.blocking)
    pairs = sorted(blocked)
    ctx.tables["_ssn_guarded_pairs"] = ssn_guarded
    scored: list[tuple[int, int, Scored]] = [
        (i, j, score_pair(sides[i], sides[j], cfg)) for i, j in pairs
    ]
    uf = Clusters.of([s.ssn_key for s in sides], [s.dob for s in sides])
    refused: set[tuple[int, int]] = set()
    for i, j, sc in sorted(scored, key=lambda x: (-x[2].score, x[0], x[1])):
        if sc.decision == MERGE and not uf.union(i, j, sc.score):
            refused.add((i, j))
    roots = sorted({uf.find(i) for i in range(len(rows))}, key=lambda r: rows[r]["mention_id"])
    pid = {r: f"P{n:04d}" for n, r in enumerate(roots, start=1)}
    person = [pid[uf.find(i)] for i in range(len(rows))]
    conf = {pid[r]: uf.min_edge[r] for r in roots}
    extra: dict[int, list[str]] = defaultdict(list)
    pf = []
    for i, j, sc in scored:
        guard = "CLUSTER_CONFLICT" if (i, j) in refused else sc.guard
        decision = "NO_MERGE" if (i, j) in refused else sc.decision
        pf.append(
            {
                "mention_a": rows[i]["mention_id"],
                "mention_b": rows[j]["mention_id"],
                **sc.features,
                "score": sc.score,
                "pass": sc.pass_,
                "decision": decision,
                "guard_fired": guard,
                "same_person_id": person[i] == person[j],
            }
        )
        if decision == REVIEW and person[i] != person[j] and (code := review_code(sc)):
            extra[i].append(code)
            extra[j].append(code)
        if decision == MERGE:
            ctx.audit.log(
                "resolve",
                "MERGE",
                item_id=f"{rows[i]['mention_id']}~{rows[j]['mention_id']}",
                detail={"score": sc.score, "pass": sc.pass_},
            )
    s = load_validation_settings(ctx.paths.config_dir)
    reasons, statuses = [], []
    for k, r in enumerate(rows):
        codes = [c for c in str(r.get("qc_reasons") or "").split(";") if c]
        for c in extra.get(k, []):
            if c not in codes:
                codes.append(c)
                ctx.audit.log(
                    "resolve",
                    "RULE_FIRED",
                    item_id=r["mention_id"],
                    code=c,
                    detail={"severity": s.severity[c]},
                )
        reasons.append(";".join(codes) or None)
        statuses.append(qc_status(codes, s))
    out = df.copy()
    out["person_id"] = person
    out["cluster_confidence"] = [round(conf[p], 4) for p in person]
    out["qc_reasons"], out["qc_status"] = reasons, statuses
    out["review_status"] = ["PENDING" if q != "PASS" else None for q in statuses]
    pair_df = pd.DataFrame(
        pf,
        columns=[
            "mention_a",
            "mention_b",
            *FEATURES,
            "score",
            "pass",
            "decision",
            "guard_fired",
            "same_person_id",
        ],
    )
    people = build_people(out, conf, ctx.as_of_date)
    return out, pair_df, people


def stage_resolve(df: pd.DataFrame, ctx: Context) -> pd.DataFrame:
    if df.empty:
        return df
    out, pairs, people = resolve(df, ctx)
    ctx.tables["pair_features"] = pairs
    ctx.tables["people"] = people
    summary = {
        "mentions": len(out),
        "candidate_pairs": len(pairs),
        "ssn_guarded_unscored": ctx.tables.pop("_ssn_guarded_pairs", 0),
        "merge_edges": int((pairs["decision"] == MERGE).sum()),
        "review_pairs": int((pairs["decision"] == REVIEW).sum()),
        "guarded": int(pairs["guard_fired"].notna().sum()),
        "people": len(people),
    }
    ctx.tables["resolve_summary"] = summary
    logger.info("resolve: %s", summary)
    return out
