"""Privacy stage: trio columns + HMAC keys, masked exclusions, then `drop_raw()`.

`<e>_present` / `<e>_masked` / `<e>_valid` (PASS, the element's first reason code, or
null when absent) and `<e>_key` for strong identifiers (DATA_SCHEMA.md, ADR-060).
After this stage no `_`-prefixed column is left, and `mentions` follows the schema
column order.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from breachlens.context import Context
from breachlens.privacy.hashing import dl_key, passport_key, ssn_key
from breachlens.privacy.masking import mask_id, mask_premasked, mask_ssn
from breachlens.validate.completeness import present

# element -> (raw column, codes that make it not-PASS, in priority order)
ELEMENT_CODES = {
    "ssn": (
        "_raw_ssn",
        (
            "SSN_FORMAT",
            "SSN_AREA_INVALID",
            "SSN_GROUP_INVALID",
            "SSN_SERIAL_INVALID",
            "SSN_KNOWN_INVALID",
            "XL_SSN_ZERO_PADDED",
        ),
    ),
    "dl": ("_raw_dl", ("DL_STATE_MISSING", "DL_FORMAT_STATE")),
    "state_id": ("_raw_state_id", ()),
    "passport": ("_raw_passport", ("PASSPORT_FORMAT",)),
    "bank_account": ("_raw_bank_account", ()),
    "card": ("_raw_card", ("CARD_LUHN_FAIL",)),
}
STATUS_CODES = {"PREMASKED": "PREMASKED_VALUE", "PRECISION_LOST": "XL_NUMBER_PRECISION_LOST"}

MENTION_COLUMNS = [
    "mention_id",
    "source_type",
    "doc_id",
    "page",
    "source_file",
    "source_sheet",
    "source_row",
    "related_mention_id",
    "doc_type",
    "doc_date",
    "person_role",
    "entity_type",
    "source_snippet",
    "raw_name",
    "name_title",
    "first_name",
    "middle_name",
    "middle_initial",
    "last_name",
    "name_suffix",
    "name_order_detected",
    "raw_address",
    "address_line1",
    "address_line2",
    "city",
    "state",
    "zip5",
    "zip4",
    "country",
    "address_status",
    "address_suggestion",
    "address_source",
    "phone",
    "email",
    "dob",
    "age_at_run",
    "is_minor",
    "ssn_present",
    "ssn_masked",
    "ssn_valid",
    "ssn_key",
    "dl_present",
    "dl_masked",
    "dl_valid",
    "dl_key",
    "dl_state",
    "state_id_present",
    "state_id_masked",
    "state_id_valid",
    "state_id_key",
    "state_id_state",
    "passport_present",
    "passport_masked",
    "passport_valid",
    "passport_key",
    "passport_country",
    "bank_account_present",
    "bank_account_masked",
    "bank_account_valid",
    "routing_number_present",
    "routing_number_valid",
    "card_present",
    "card_masked",
    "card_valid",
    "mrn_present",
    "mrn_masked",
    "health_member_id_present",
    "health_member_id_masked",
    "health_group_number_present",
    "insurer_name",
    "diagnosis_present",
    "procedure_present",
    "date_of_service_present",
    "employee_id_present",
    "employer_name",
    "student_id_present",
    "student_id_masked",
    "school_name",
    "ferpa_flag",
    "field_confidence",
    "extraction_method",
    "qc_status",
    "qc_reasons",
    "person_id",
    "cluster_confidence",
    "review_status",
    "run_id",
    "processed_at",
]


def _codes(row: dict[str, Any]) -> list[str]:
    v = row.get("qc_reasons")
    return [c for c in str(v).split(";") if c] if present(v) else []


def trio(row: dict[str, Any], element: str, status_col: str | None = None) -> dict[str, Any]:
    raw_col, element_codes = ELEMENT_CODES[element]
    raw = row.get(raw_col)
    if not present(raw):
        return {f"{element}_present": False, f"{element}_masked": None, f"{element}_valid": None}
    status = row.get(status_col) if status_col else None
    codes = _codes(row)
    if status in STATUS_CODES:
        valid = STATUS_CODES[status]
    else:
        valid = next((c for c in element_codes if c in codes), "PASS")
    if status == "PREMASKED":
        masked = mask_premasked(str(raw))
    elif element == "ssn":
        masked = mask_ssn(str(raw))
    else:
        masked = mask_id(str(raw))
    return {f"{element}_present": True, f"{element}_masked": masked, f"{element}_valid": valid}


def privacy_row(row: dict[str, Any], salt: bytes) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out |= trio(row, "ssn", "_ssn_status")
    out |= trio(row, "dl")
    out |= trio(row, "state_id")
    out |= trio(row, "passport")
    out |= trio(row, "bank_account")
    out |= trio(row, "card", "_card_status")
    usable_ssn = row.get("_ssn_status") not in STATUS_CODES and present(row.get("_raw_ssn"))
    out["ssn_key"] = ssn_key(salt, str(row["_raw_ssn"])) if usable_ssn else None
    out["dl_key"] = (
        dl_key(salt, row.get("_raw_dl"), row.get("dl_state"))
        if present(row.get("_raw_dl"))
        else None
    )
    out["passport_key"] = (
        passport_key(salt, row.get("_raw_passport"), row.get("passport_country"))
        if present(row.get("_raw_passport"))
        else None
    )
    out["state_id_key"] = None
    routing = row.get("_raw_routing")
    out["routing_number_present"] = present(routing)
    out["routing_number_valid"] = (
        ("ROUTING_CHECKSUM_FAIL" if "ROUTING_CHECKSUM_FAIL" in _codes(row) else "PASS")
        if present(routing)
        else None
    )
    for element, raw_col in (
        ("mrn", "_raw_mrn"),
        ("health_member_id", "_raw_member_id"),
        ("student_id", "_raw_student_id"),
    ):
        out[f"{element}_present"] = present(row.get(raw_col))
        out[f"{element}_masked"] = mask_id(str(row[raw_col])) if present(row.get(raw_col)) else None
    for flag, raw_col in (
        ("health_group_number_present", "_raw_group_number"),
        ("diagnosis_present", "_raw_diagnosis"),
        ("procedure_present", "_raw_procedure"),
        ("date_of_service_present", "_raw_date_of_service"),
        ("employee_id_present", "_raw_employee_id"),
    ):
        out[flag] = row.get(flag) is True or present(row.get(raw_col))
    return out


def drop_raw(df: pd.DataFrame) -> pd.DataFrame:
    """Remove every transient (`_`-prefixed) column, raw identifiers included."""
    return df.drop(columns=[c for c in df.columns if str(c).startswith("_")])


def mask_excluded(t: pd.DataFrame | None) -> pd.DataFrame | None:
    if t is None or t.empty:
        return t
    t = t.copy()
    if "_raw_value" in t:
        t["value_masked"] = [
            mask_id(re.sub(r"\D", "", str(v))) if present(v) else m
            for v, m in zip(t["_raw_value"], t.get("value_masked", [None] * len(t)), strict=True)
        ]
    return drop_raw(t)


def stage_privacy(df: pd.DataFrame, ctx: Context) -> pd.DataFrame:
    for name in ("excluded_identifiers", "excluded_entities"):
        ctx.tables[name] = mask_excluded(ctx.tables.get(name))
    if df.empty:
        return df
    rows = df.to_dict("records")
    priv = pd.DataFrame([privacy_row(r, ctx.salt) for r in rows], index=df.index)
    out = drop_raw(df.drop(columns=[c for c in priv.columns if c in df.columns]).join(priv))
    for c in MENTION_COLUMNS:
        if c not in out:
            out[c] = None
    extra = [c for c in out.columns if c not in MENTION_COLUMNS]
    return out[MENTION_COLUMNS + extra]
