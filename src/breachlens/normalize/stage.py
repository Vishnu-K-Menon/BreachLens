"""Normalize stage: names, addresses (+ offline ZIP check), contact, country.

Codes go to the transient `_norm_codes` (`;`-joined) and suggestions to `_norm_notes`
(JSON); the validation engine merges them into `qc_reasons`.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from breachlens.address.zipcheck import check_zip
from breachlens.context import Context
from breachlens.normalize.addresses import normalize_address
from breachlens.normalize.contact import normalize_email, normalize_phone
from breachlens.normalize.names import normalize_parts, parse_full_name
from breachlens.sheets.features import default_lexicons
from breachlens.validate.completeness import present
from breachlens.validate.settings import ValidationSettings, load_validation_settings


def normalize_row(
    row: dict[str, Any], s: ValidationSettings, lex_first: frozenset[str]
) -> dict[str, Any]:
    cfg = s.rules
    out: dict[str, Any] = {}
    codes: list[str] = []
    notes: dict[str, str] = {}
    if any(present(row.get(k)) for k in ("first_name", "last_name")):
        n = normalize_parts(
            row.get("first_name"),
            row.get("middle_name"),
            row.get("last_name"),
            row.get("name_suffix"),
            cfg,
        )
    else:
        labelled = row.get("source_type") == "PDF"  # template field labels fix the order
        n = parse_full_name(
            row.get("raw_name") or "", row.get("name_order_detected"), cfg, lex_first, labelled
        )
    out.update(
        name_title=n.name_title,
        first_name=n.first_name,
        middle_name=n.middle_name,
        middle_initial=n.middle_initial,
        last_name=n.last_name,
        name_suffix=n.name_suffix,
    )
    codes += n.codes
    notes.update(n.notes)

    a = normalize_address(row, s.address, cfg.zip_leading_zero_states)
    if "ADDR_MISSING" in a.codes and present(row.get("related_mention_id")):
        a.codes.remove("ADDR_MISSING")  # dependents/guardians use the linked household address
    zc = check_zip(
        a.zip5,
        a.city,
        a.state if a.state in s.address.states else None,
        cfg.zip_city_suggest_min_similarity,
    )
    a.codes += zc.codes
    out.update(
        address_line1=a.address_line1,
        address_line2=a.address_line2,
        city=a.city,
        state=a.state,
        zip5=a.zip5,
        zip4=a.zip4,
        country=a.country,
    )
    if a.zip_suggestion or zc.city_suggestion:
        line = ", ".join(x for x in (a.address_line1, a.address_line2) if x)
        out["address_suggestion"] = (
            f"{line}, {zc.city_suggestion or a.city}, {a.state} {a.zip_suggestion or a.zip5}"
        )
        if zc.city_suggestion:
            notes["city_suggestion"] = zc.city_suggestion
    invalid = "ADDR_STATE_INVALID" in a.codes or (
        "ADDR_ZIP_FORMAT" in a.codes and not a.zip_suggestion
    )
    out["address_status"] = "INVALID" if invalid else ("NOT_CHECKED" if a.address_line1 else None)
    out["address_source"] = "ZIPCHECK" if zc.known else None
    codes += a.codes

    out["phone"] = normalize_phone(row.get("phone"))
    out["email"] = normalize_email(row.get("email"))
    out["_norm_codes"] = ";".join(dict.fromkeys(codes))
    out["_norm_notes"] = json.dumps(notes, sort_keys=True) if notes else None
    return out


def stage_normalize(df: pd.DataFrame, ctx: Context) -> pd.DataFrame:
    if df.empty:
        return df
    s = load_validation_settings(ctx.paths.config_dir)
    lex_first = default_lexicons().first_names
    rows = df.to_dict("records")
    norm = pd.DataFrame([normalize_row(r, s, lex_first) for r in rows], index=df.index)
    keep = df.drop(columns=[c for c in norm.columns if c in df.columns])
    return pd.concat([keep, norm], axis=1)
