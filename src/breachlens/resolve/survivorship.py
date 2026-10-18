"""Golden records (`people`, DATA_SCHEMA.md) from clustered mentions.

- name: the most complete version (most name parts, then the longest middle name)
- address: newest `doc_date` (nulls last), then the most frequent VERIFIED address, then
  the highest confidence (ADR-029)
- DOB: the mode of the valid values; `is_minor` at `as_of_date`
- element flags: OR across mentions; category flags per ADR-028
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from typing import Any

import pandas as pd

from breachlens.normalize.dates import age_at, parse_iso
from breachlens.validate.completeness import present

# element -> mention presence column, display name (DATA_SCHEMA §Element display names)
ELEMENTS = {
    "ssn": ("ssn_present", "SSN"),
    "dl": ("dl_present", "DRIVER LICENSE"),
    "state_id": ("state_id_present", "STATE ID"),
    "passport": ("passport_present", "PASSPORT"),
    "bank_account": ("bank_account_present", "FINANCIAL ACCOUNT"),
    "card": ("card_present", "PAYMENT CARD"),
    "mrn": ("mrn_present", "MEDICAL INFO"),
    "diagnosis": ("diagnosis_present", "MEDICAL INFO"),
    "procedure": ("procedure_present", "MEDICAL INFO"),
    "date_of_service": ("date_of_service_present", "MEDICAL INFO"),
    "health_member_id": ("health_member_id_present", "HEALTH INSURANCE INFO"),
    "health_group_number": ("health_group_number_present", "HEALTH INSURANCE INFO"),
    "dob": ("dob", "DATE OF BIRTH"),
    "student_id": ("student_id_present", "STUDENT RECORD"),
}
CATEGORIES = {
    "gov_id_exposed": ("ssn", "dl", "state_id", "passport"),
    "financial_exposed": ("bank_account", "card"),
    "medical_exposed": ("mrn", "diagnosis", "procedure", "date_of_service"),
    "health_insurance_exposed": ("health_member_id", "health_group_number"),
    "education_exposed": ("student_id",),
}
BAD_DOB = {"DOB_UNPARSEABLE", "DOB_FUTURE", "DOB_IMPLAUSIBLE"}
REVIEW_CARD = {"XL_NUMBER_PRECISION_LOST", "CARD_LUHN_FAIL"}
REVIEW_CODES = {"DUPLICATE_CANDIDATE", "DOB_CONFLICT_IN_CLUSTER"}


def truthy(v: Any) -> bool:
    return v is True or (isinstance(v, str) and v == "True")


def codes(r: dict[str, Any]) -> set[str]:
    return set(str(r.get("qc_reasons") or "").split(";")) - {""}


def _name_rank(r: dict[str, Any]) -> tuple:
    parts = sum(
        present(r.get(k))
        for k in ("first_name", "middle_name", "last_name", "name_suffix", "name_title")
    )
    return (-parts, -len(str(r.get("middle_name") or "")), r["mention_id"])


def _conf(r: dict[str, Any]) -> float:
    if not present(r.get("field_confidence")):
        return 0.0
    vals = list(json.loads(r["field_confidence"]).values())
    return sum(map(float, vals)) / len(vals) if vals else 0.0


def address_of(r: dict[str, Any]) -> tuple:
    return tuple(
        str(r.get(k) or "") for k in ("address_line1", "address_line2", "city", "state", "zip5")
    )


def pick_address(ms: list[dict[str, Any]]) -> dict[str, Any] | None:
    cands = [m for m in ms if present(m.get("address_line1"))]
    if not cands:
        return None
    verified = Counter(address_of(m) for m in cands if m.get("address_status") == "VERIFIED")

    def rank(m: dict[str, Any]) -> tuple:
        d = parse_iso(m.get("doc_date"))
        return (
            d is None,
            -(d.toordinal() if d else 0),
            -verified[address_of(m)],
            -_conf(m),
            m["mention_id"],
        )

    return min(cands, key=rank)


def golden_record(
    pid: str, ms: list[dict[str, Any]], confidence: float, as_of: date
) -> dict[str, Any]:
    name = min(ms, key=_name_rank)
    addr = pick_address(ms)
    dobs = [m["dob"] for m in ms if present(m.get("dob")) and not (codes(m) & BAD_DOB)]
    dob = Counter(dobs).most_common(1)[0][0] if dobs else None
    d = parse_iso(dob)
    exposed = {
        e: any(present(m.get(col)) if e == "dob" else truthy(m.get(col)) for m in ms)
        for e, (col, _) in ELEMENTS.items()
    }
    names = list(dict.fromkeys(label for e, (_, label) in ELEMENTS.items() if exposed[e]))
    all_codes = set().union(*(codes(m) for m in ms))
    card_review = any(m.get("card_valid") in REVIEW_CARD for m in ms)
    rec = {
        "person_id": pid,
        "first_name": name.get("first_name"),
        "middle_initial": name.get("middle_initial"),
        "last_name": name.get("last_name"),
        "name_suffix": name.get("name_suffix"),
        **{
            k: (addr or {}).get(k)
            for k in ("address_line1", "address_line2", "city", "state", "zip5")
        },
        "country": (addr or {}).get("country") or "US",
        "address_status": (addr or {}).get("address_status") or None,
        "dob": dob,
        "is_minor": bool(d and age_at(d, as_of) < 18),
        **{f"{e}_exposed": v for e, v in exposed.items()},
        "elements_exposed": "; ".join(names),
        **{cat: any(exposed[e] for e in els) for cat, els in CATEGORIES.items()},
        "mention_count": len(ms),
        "source_docs": ";".join(sorted({str(m.get("source_file")) for m in ms})),
        "source_types": ";".join(sorted({str(m.get("source_type")) for m in ms})),
        "cluster_confidence": round(confidence, 4),
        "ferpa_flag": any(truthy(m.get("ferpa_flag")) for m in ms),
        "needs_review": card_review or bool(all_codes & REVIEW_CODES),
        "notify_required": None,
    }
    return rec


def build_people(mentions: pd.DataFrame, confidence: dict[str, float], as_of: date) -> pd.DataFrame:
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in mentions.to_dict("records"):
        groups.setdefault(str(r["person_id"]), []).append(r)
    rows = [
        golden_record(pid, ms, confidence.get(pid, 1.0), as_of)
        for pid, ms in sorted(groups.items())
    ]
    return pd.DataFrame(rows)
