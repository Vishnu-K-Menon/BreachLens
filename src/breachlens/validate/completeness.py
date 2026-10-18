"""Completeness and person-level checks (VALIDATION_RULES.md)."""

from __future__ import annotations

import json
from typing import Any

# qualifying element -> transient/raw column that carries it on a mention
ELEMENT_FIELDS = {
    "ssn": "_raw_ssn",
    "dl": "_raw_dl",
    "state_id": "_raw_state_id",
    "passport": "_raw_passport",
    "dob": "dob",
    "bank_account": "_raw_bank_account",
    "card": "_raw_card",
    "mrn": "_raw_mrn",
    "health_member_id": "_raw_member_id",
    "student_id": "_raw_student_id",
}


def present(v: Any) -> bool:
    return v is not None and not (isinstance(v, float) and v != v) and str(v).strip() != ""


def qualifying_codes(row: dict[str, Any], qualifying: tuple[str, ...]) -> list[str]:
    has = any(present(row.get(ELEMENT_FIELDS[e])) for e in qualifying if e in ELEMENT_FIELDS)
    return [] if has else ["PERSON_NO_QUALIFYING_ELEMENT"]


def low_ocr_codes(row: dict[str, Any], threshold: float) -> list[str]:
    """OCR mentions only: the sheet confidences are column-mapping probabilities."""
    if row.get("extraction_method") != "OCR" or not present(row.get("field_confidence")):
        return []
    conf = json.loads(row["field_confidence"])
    return ["LOW_OCR_CONFIDENCE"] if any(float(v) < threshold for v in conf.values()) else []


def ferpa_codes(row: dict[str, Any]) -> list[str]:
    return (
        ["FERPA_RECORD"]
        if present(row.get("_raw_student_id")) or present(row.get("school_name"))
        else []
    )
