"""Validation engine (VALIDATION_RULES.md, ADR-059).

Merges every code source into `qc_reasons` and sets `qc_status`:
1. normalizer codes (`_norm_codes`)
2. spreadsheet repair codes (`_repair_codes`, M3)
3. column-level WARN codes, copied to the mentions that took a value from that column
4. the checks below (identifiers, DOB, completeness, name variants)

Severities come only from `config/rules.yaml`; an undeclared code is a config error.
Doc-level codes go to `doc_codes`; exclusion codes go to the `reason` of the excluded_*
rows. Every fired code is an audit event (`RULE_FIRED`, masked).
"""

from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd

from breachlens.context import Context
from breachlens.validate.aba import routing_codes
from breachlens.validate.completeness import (
    ferpa_codes,
    low_ocr_codes,
    present,
    qualifying_codes,
)
from breachlens.validate.dl import dl_codes, passport_codes
from breachlens.validate.dob import dob_codes
from breachlens.validate.luhn import card_codes
from breachlens.validate.settings import ValidationSettings, load_validation_settings
from breachlens.validate.ssn import ssn_codes

COLUMN_WARN = ("COL_MAPPING_LOW_CONF", "COL_MAPPING_ML_OVERRIDE", "COL_UNMAPPED_SENSITIVE")
# column label -> mention fields that receive its values (sheet_track._person_from)
LABEL_FIELDS = {
    "FULL_NAME": ("raw_name",),
    "FIRST_NAME": ("first_name",),
    "MIDDLE_NAME": ("middle_name",),
    "LAST_NAME": ("last_name",),
    "SUFFIX": ("name_suffix",),
    "ADDRESS_FULL": ("address_line1",),
    "ADDRESS_LINE1": ("address_line1",),
    "ADDRESS_LINE2": ("address_line2",),
    "CITY": ("city",),
    "STATE": ("state",),
    "ZIP": ("zip5",),
    "CITY_STATE_ZIP": ("city",),
    "PHONE": ("phone",),
    "EMAIL": ("email",),
    "DOB": ("dob",),
    "SSN": ("_raw_ssn",),
    "DL_NUMBER": ("_raw_dl",),
    "DL_STATE": ("dl_state",),
    "PASSPORT": ("_raw_passport",),
    "BANK_ACCOUNT": ("_raw_bank_account",),
    "ROUTING": ("_raw_routing",),
    "CARD": ("_raw_card",),
    "MRN": ("_raw_mrn",),
    "MEMBER_ID": ("_raw_member_id",),
    "GROUP_NUMBER": ("_raw_group_number",),
    "DIAGNOSIS": ("_raw_diagnosis",),
    "STUDENT_ID": ("_raw_student_id",),
    "SCHOOL": ("school_name",),
    "GUARDIAN_NAME": ("raw_name",),
    "EMPLOYEE_ID": ("_raw_employee_id",),
    "ORG_NAME": ("employer_name", "insurer_name"),
    "FREE_TEXT": ("_freetext_hits",),
}
EXCLUSION_CODES = {
    "EIN": "EIN_EXCLUDED",
    "PROVIDER_TIN": "EIN_EXCLUDED",
    "NPI": "NPI_EXCLUDED",
    "ITIN": "ITIN_DETECTED",
    "ORG": "NAME_ORG_LIKE",
}


def _s(v: Any) -> str:
    return str(v) if present(v) else ""


def _split(v: Any) -> list[str]:
    return [c for c in str(v).split(";") if c] if present(v) else []


def check_row(
    row: dict[str, Any], s: ValidationSettings, ctx: Context
) -> tuple[list[str], dict[str, Any]]:
    """Codes from the engine's own checks, plus derived values (age, flags, ITIN)."""
    cfg = s.rules
    codes: list[str] = []
    out: dict[str, Any] = {}
    if present(row.get("_raw_freetext")):  # PII in notes is exposed PII (ADR-060)
        hits = json.loads(row["_raw_freetext"])
        for kind, field, status in (
            ("SSN", "_raw_ssn", "_ssn_status"),
            ("MRN", "_raw_mrn", None),
            ("CARD", "_raw_card", "_card_status"),
        ):
            if kind in hits and not present(row.get(field)):
                row[field] = out[field] = hits[kind]
                if status:
                    row[status] = out[status] = "TEXT"
    if present(row.get("_raw_ssn")) and row.get("_ssn_status") not in {
        "PREMASKED",
        "PRECISION_LOST",
    }:
        sc = ssn_codes(str(row["_raw_ssn"]), s.identifiers, cfg.known_invalid_ssns)
        if sc == ["ITIN_DETECTED"]:
            out["_itin"] = re.sub(r"\D", "", str(row["_raw_ssn"]))
            row["_raw_ssn"] = out["_raw_ssn"] = None
        else:
            codes += sc
    codes += dl_codes(
        row.get("_raw_dl") if present(row.get("_raw_dl")) else None,
        row.get("dl_state") if present(row.get("dl_state")) else None,
        s.dl_regex,
    )
    codes += passport_codes(row.get("_raw_passport") if present(row.get("_raw_passport")) else None)
    codes += card_codes(
        row.get("_raw_card") if present(row.get("_raw_card")) else None, row.get("_card_status")
    )
    codes += routing_codes(row.get("_raw_routing") if present(row.get("_raw_routing")) else None)
    dc, age = dob_codes(
        row.get("dob"), row.get("_raw_dob"), ctx.as_of_date, cfg.max_age_years, cfg.minor_age_years
    )
    codes += dc
    out["age_at_run"] = age
    out["is_minor"] = "DOB_MINOR" in dc
    codes += qualifying_codes(row, cfg.qualifying_elements)
    codes += low_ocr_codes(row, cfg.ocr_conf_threshold)
    fc = ferpa_codes(row)
    codes += fc
    out["ferpa_flag"] = bool(fc)
    return codes, out


def column_codes(
    df: pd.DataFrame,
    mapping: pd.DataFrame | None,
    wide_pattern: str,
    affected: dict[Any, int] | None = None,
) -> dict[int, list[str]]:
    """Mention index -> COL_* WARN codes of the columns its values came from.

    `affected` (optional) receives, per `mapping` row index, how many mentions took a value
    from that warned column (reviewed columns included); M6 `review_items` (ADR-062)."""
    out: dict[int, list[str]] = {}
    if mapping is None or mapping.empty:
        return out
    rx = re.compile(wide_pattern, re.I)
    sheets = df[df["source_type"] == "SPREADSHEET"]
    for map_idx, col in mapping.iterrows():
        warn = [c for c in _split(col.get("codes")) if c in COLUMN_WARN]
        if not warn:
            continue
        reviewed = present(col.get("reviewed_label"))  # a human resolved it (ADR-061)
        same = sheets[
            (sheets["doc_id"] == col["doc_id"])
            & (sheets["source_sheet"].fillna("") == (col["sheet"] or ""))
        ]
        wide = bool(rx.match(str(col["header_raw"]).strip()))
        role = same["person_role"]
        same = same[role == "DEPENDENT"] if wide else same[role != "DEPENDENT"]
        if col["final_label"] == "GUARDIAN_NAME":
            same = same[same["person_role"] == "GUARDIAN"]
        elif col["final_label"] != "OTHER":
            same = same[same["person_role"] != "GUARDIAN"]
        fields = LABEL_FIELDS.get(col["final_label"], ())
        n = 0
        for idx, r in same.iterrows():
            if col["final_label"] == "OTHER" or any(f in r and present(r[f]) for f in fields):
                n += 1
                if not reviewed:
                    out.setdefault(idx, []).extend(warn)
        if affected is not None:
            affected[map_idx] = n
    return out


def _severity(code: str, s: ValidationSettings) -> str:
    try:
        return s.severity[code]
    except KeyError as exc:
        raise ValueError(f"reason code {code} is not declared in config/rules.yaml") from exc


def qc_status(codes: list[str], s: ValidationSettings) -> str:
    sev = {_severity(c, s) for c in codes}
    return "FAIL" if "ERROR" in sev else ("REVIEW" if "WARN" in sev else "PASS")


def name_variant_codes(df: pd.DataFrame) -> set[int]:
    """Mentions whose SSN appears in the same document under another spelling."""
    flagged: set[int] = set()
    if "_raw_ssn" not in df:
        return flagged
    d = df[df["_raw_ssn"].map(present)]
    if d.empty:
        return flagged
    key = d["doc_id"].astype(str) + "|" + d["_raw_ssn"].astype(str)
    name = (
        d.get("first_name", pd.Series("", index=d.index)).fillna("").astype(str)
        + "|"
        + d.get("last_name", pd.Series("", index=d.index)).fillna("").astype(str)
    )
    spellings = name.groupby(key).transform("nunique")
    return set(d.index[spellings > 1])


def doc_codes(ctx: Context, s: ValidationSettings) -> pd.DataFrame:
    rows = []
    sheet_codes = ctx.tables.get("sheet_codes")
    if sheet_codes is not None and not sheet_codes.empty:
        rows += sheet_codes.to_dict("records")
    inv = ctx.tables.get("inventory")
    if inv is not None and not inv.empty:
        unknown = inv[
            (inv["file_kind"] == "PDF")
            & (inv["doc_type"] == "UNKNOWN")
            & ~inv["is_exact_duplicate"]
        ]
        rows += [
            {
                "doc_id": d,
                "sheet": None,
                "col_idx": None,
                "code": "DOC_TYPE_UNKNOWN",
                "detail": "doc type",
            }
            for d in unknown["doc_id"]
        ]
    out = pd.DataFrame(rows, columns=["doc_id", "sheet", "col_idx", "code", "detail"])
    out["severity"] = [_severity(c, s) for c in out["code"]]
    return out


def exclusion_reason(kind: str, reason: Any) -> str:
    """`reason` of an excluded_* row, led by its reason code (EIN_EXCLUDED (label: ...))."""
    code = EXCLUSION_CODES.get(kind, kind)
    r = _s(reason)
    return r if r.startswith(code) else f"{code} ({r})"


def _annotate_excluded(ctx: Context) -> None:
    for name in ("excluded_identifiers", "excluded_entities"):
        t = ctx.tables.get(name)
        if t is None or t.empty:
            continue
        t = t.copy()
        t["reason"] = [exclusion_reason(k, r) for k, r in zip(t["kind"], t["reason"], strict=True)]
        ctx.tables[name] = t


def stage_validate(df: pd.DataFrame, ctx: Context) -> pd.DataFrame:
    if df.empty and "inventory" not in ctx.tables:
        return df  # nothing was ingested
    s = load_validation_settings(ctx.paths.config_dir)
    ctx.tables["doc_codes"] = doc_codes(ctx, s)
    _annotate_excluded(ctx)
    if df.empty:
        return df
    from breachlens.sheets.settings import load_sheet_settings

    wide = load_sheet_settings(ctx.paths.config_dir).sheets.reshape.wide_group_pattern
    mapping = ctx.tables.get("column_mapping")
    affected: dict[Any, int] = {}
    col = column_codes(df, mapping, wide, affected)
    if mapping is not None and not mapping.empty:
        mapping = mapping.copy()
        mapping["affected_rows"] = [affected.get(i, 0) for i in mapping.index]
        ctx.tables["column_mapping"] = mapping
    variants = name_variant_codes(df)
    rows = df.to_dict("records")
    updates, reasons, statuses, itins = [], [], [], []
    for idx, row in zip(df.index, rows, strict=True):
        own, derived = check_row(row, s, ctx)
        codes = (
            _split(row.get("_norm_codes"))
            + _split(row.get("_repair_codes"))
            + col.get(idx, [])
            + own
        )
        if idx in variants:
            codes.append("NAME_VARIANT_IN_DOC")
        codes = list(dict.fromkeys(codes))
        if itin := derived.pop("_itin", None):
            itins.append(
                {
                    "doc_id": row["doc_id"],
                    "page": row.get("page"),
                    "kind": "ITIN",
                    "_raw_value": itin,
                    "value_masked": None,
                    "reason": "ITIN_DETECTED (SSN field)",
                }
            )
            ctx.audit.log(
                "validate",
                "ROUTED_EXCLUDED",
                item_id=row["mention_id"],
                field="ssn",
                code="ITIN_DETECTED",
            )
        updates.append(derived)
        reasons.append(";".join(codes) or None)
        statuses.append(qc_status(codes, s))
        notes = json.loads(row["_norm_notes"]) if present(row.get("_norm_notes")) else {}
        for c in codes:
            detail = {"severity": _severity(c, s)}
            if c == "NAME_SUFFIX_INVALID" and "suffix_suggestion" in notes:
                detail["suggestion"] = notes["suffix_suggestion"]
            if c == "ADDR_ZIP_CITY_MISMATCH" and "city_suggestion" in notes:
                detail["suggestion"] = notes["city_suggestion"]
            ctx.audit.log(
                "validate", "RULE_FIRED", item_id=row["mention_id"], code=c, detail=detail
            )
    # Per-row updates: a key one row changes (e.g. an ITIN routed out) must not touch others.
    out = pd.DataFrame([r | u for r, u in zip(rows, updates, strict=True)], index=df.index)
    out["qc_reasons"] = reasons
    out["qc_status"] = statuses
    out["review_status"] = ["PENDING" if st != "PASS" else None for st in statuses]
    if itins:
        prev = ctx.tables.get("excluded_identifiers")
        new = pd.DataFrame(itins)
        ctx.tables["excluded_identifiers"] = (
            new if prev is None or prev.empty else pd.concat([prev, new], ignore_index=True)
        )
    return out
