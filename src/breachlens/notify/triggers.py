"""Notification triggers (ARCHITECTURE.md §Notification, ADR-065). ILLUSTRATIVE, NOT LEGAL ADVICE.

- Jurisdiction = the golden record's state. A state missing from
  `config/jurisdictions.yaml` uses `default` and adds NOTIFY_STATE_UNKNOWN to the
  person's mentions.
- `notify_required` = the person has at least one covered element for the jurisdiction.
  - Card (ADR-052): pre-masked values do not trigger. Precision-lost and Luhn-failing
    values trigger and need review.
  - Bank account: counts only with a routing number in the same mention (demo rule).
- A person without an address of their own (dependent, minor) uses the household
  address of the linked mention's person: notify the parent/guardian there.
- Notes: minor → "Notify parent/guardian (P…)". FERPA → education-record note
  (informational, not a trigger).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from breachlens.context import Context
from breachlens.resolve.survivorship import ELEMENTS, truthy
from breachlens.synth.settings import ElementRules, Jurisdiction
from breachlens.validate.completeness import present
from breachlens.validate.engine import qc_status
from breachlens.validate.settings import load_validation_settings

logger = logging.getLogger(__name__)
CARD_STATUS = {
    "PASS": "TEXT",
    "CARD_LUHN_FAIL": "LUHN_FAIL",
    "XL_NUMBER_PRECISION_LOST": "PRECISION_LOST",
    "PREMASKED_VALUE": "PREMASKED",
}
NOTIFY_COLUMNS = [
    "person_id",
    "jurisdiction",
    "last_name",
    "first_name",
    "middle_initial",
    "name_suffix",
    "address_line1",
    "address_line2",
    "city",
    "state",
    "zip5",
    "country",
    "elements_exposed",
    "notify_required",
    "notify_reason",
    "notify_note",
    "ferpa_flag",
    "address_status",
    "notify_status",
]
ADDRESS = ("address_line1", "address_line2", "city", "state", "zip5", "country", "address_status")
FERPA_NOTE = "Education record exposed - FERPA considerations for the institution"


def load_jurisdictions(config_dir: Path) -> tuple[dict[str, Jurisdiction], ElementRules]:
    with (config_dir / "jurisdictions.yaml").open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    rules = ElementRules.model_validate(raw.pop("element_rules"))
    return {k: Jurisdiction.model_validate(v) for k, v in raw.items()}, rules


def jurisdiction_for(state: str | None, juris: dict[str, Jurisdiction]) -> tuple[str, list[str]]:
    """(rule set, codes): a state missing from config uses `default` + NOTIFY_STATE_UNKNOWN."""
    if state in juris and state != "default":
        return state, []
    return "default", ["NOTIFY_STATE_UNKNOWN"]


def hits_for(
    p: dict[str, Any], ms: list[dict[str, Any]], covered: set[str], rules: ElementRules
) -> set[str]:
    hits = {e for e in covered if p.get(f"{e}_exposed")}
    if "bank_account" in hits and not any(
        truthy(m.get("bank_account_present")) and truthy(m.get("routing_number_present"))
        for m in ms
    ):
        hits.discard("bank_account")
    if "card" in hits:
        statuses = {
            CARD_STATUS.get(str(m.get("card_valid")), "TEXT")
            for m in ms
            if truthy(m.get("card_present"))
        }
        if not any(rules.card.triggers(s) for s in statuses):
            hits.discard("card")
    return hits


def stage_notify(df: pd.DataFrame, ctx: Context) -> pd.DataFrame:
    people = ctx.tables.get("people")
    if df.empty or people is None or people.empty:
        return df
    juris, rules = load_jurisdictions(ctx.paths.config_dir)
    by_person: dict[str, list[dict[str, Any]]] = {}
    for r in df.to_dict("records"):
        by_person.setdefault(r["person_id"], []).append(r)
    pid_of_mention = dict(zip(df["mention_id"], df["person_id"], strict=True))
    people = people.copy()
    precs = {r["person_id"]: r for r in people.to_dict("records")}
    unknown: set[str] = set()
    out_rows, notify_rows = [], []
    for pid, p in precs.items():
        ms = by_person[pid]
        linked = sorted(
            {
                pid_of_mention[m["related_mention_id"]]
                for m in ms
                if present(m.get("related_mention_id"))
                and m["related_mention_id"] in pid_of_mention
            }
            - {pid}
        )
        notes = []
        if not present(p.get("address_line1")) and linked:  # household address of the linked person
            h = precs[linked[0]]
            p.update({k: h.get(k) for k in ADDRESS})
            notes.append(f"Address from household {linked[0]}")
        state = p.get("state") if present(p.get("state")) else None
        j, codes = jurisdiction_for(state, juris)
        if codes:
            unknown.add(pid)
        hits = hits_for(p, ms, set(juris[j].covered_elements), rules)
        if p.get("is_minor"):
            notes.insert(
                0, "Notify parent/guardian" + (f" ({', '.join(linked)})" if linked else "")
            )
        if p.get("ferpa_flag"):
            notes.append(FERPA_NOTE)
        p["notify_required"] = bool(hits)
        status = (
            "NOT_REQUIRED" if not hits else ("NEEDS_REVIEW" if p.get("needs_review") else "READY")
        )
        out_rows.append(p)
        notify_rows.append(
            {
                **{k: p.get(k) for k in NOTIFY_COLUMNS if k in p},
                "jurisdiction": state or "UNKNOWN",
                "notify_required": bool(hits),
                "notify_reason": ";".join(sorted(hits)) or None,
                "notify_note": "; ".join(notes) or None,
                "notify_status": status,
            }
        )
    s = load_validation_settings(ctx.paths.config_dir)
    reasons, statuses = [], []
    for r in df.to_dict("records"):
        codes = [c for c in str(r.get("qc_reasons") or "").split(";") if c]
        if r["person_id"] in unknown and "NOTIFY_STATE_UNKNOWN" not in codes:
            codes.append("NOTIFY_STATE_UNKNOWN")
            ctx.audit.log(
                "notify",
                "RULE_FIRED",
                item_id=r["mention_id"],
                code="NOTIFY_STATE_UNKNOWN",
                detail={"severity": s.severity["NOTIFY_STATE_UNKNOWN"]},
            )
        reasons.append(";".join(codes) or None)
        statuses.append(qc_status(codes, s))
    out = df.copy()
    out["qc_reasons"], out["qc_status"] = reasons, statuses
    out["review_status"] = ["PENDING" if q != "PASS" else None for q in statuses]
    ctx.tables["people"] = pd.DataFrame(out_rows)
    nl = pd.DataFrame(notify_rows, columns=NOTIFY_COLUMNS)
    ctx.tables["notification_list"] = nl
    summary = {
        "people": len(nl),
        "notify_required": int(nl["notify_required"].sum()),
        "needs_review": int((nl["notify_status"] == "NEEDS_REVIEW").sum()),
        "default_jurisdiction": len(unknown),
    }
    ctx.tables["notify_summary"] = summary
    logger.info("notify: %s", summary)
    return out


__all__ = ["ELEMENTS", "load_jurisdictions", "stage_notify"]
