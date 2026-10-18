"""Spreadsheet track stage: read -> layout -> profile -> map columns -> repair -> reshape
-> free-text scan -> `mentions` rows (source_type=SPREADSHEET).

Provenance on every mention: `source_file`, `source_sheet`, `source_row` (1-based Excel
row; CSV physical line). Raw identifiers stay in transient `_raw_*` columns (ADR-044);
row-level reason codes go to `_repair_codes`, sheet/column-level codes to
`ctx.tables["sheet_codes"]`. Side tables (ADR-054): `file_profile`, `column_profile`,
`column_mapping`, `sheet_codes`; organizations and EINs are appended to
`excluded_entities` / `excluded_identifiers`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from breachlens.context import Context
from breachlens.extract.entity_type import ORG, classify_entity, load_entity_config
from breachlens.ingest.inventory import build_inventory
from breachlens.ml.column_classifier import ColumnClassifier, load_model
from breachlens.sheets import repair as R
from breachlens.sheets.features import column_features, default_lexicons
from breachlens.sheets.freetext import scan_text
from breachlens.sheets.layout import Table, fix_layout
from breachlens.sheets.mapping import decide, rule_label, unmapped_sensitive
from breachlens.sheets.profile import column_profiles, file_profile
from breachlens.sheets.reader import as_text, read_file
from breachlens.sheets.reshape import wide_groups
from breachlens.sheets.settings import SheetSettings, load_sheet_settings

logger = logging.getLogger(__name__)
SHEET_KINDS = {"XLSX", "XLS", "CSV"}
ROLE_ORDER = {
    "SUBSCRIBER": 0,
    "STUDENT": 0,
    "PATIENT": 0,
    "CUSTOMER": 0,
    "EMPLOYEE": 0,
    "MEMBER": 0,
    "DEPENDENT": 1,
    "GUARDIAN": 2,
}
LONG_IDS = {
    "DL_NUMBER": "_raw_dl",
    "PASSPORT": "_raw_passport",
    "BANK_ACCOUNT": "_raw_bank_account",
    "ROUTING": "_raw_routing",
    "CARD": "_raw_card",
    "MRN": "_raw_mrn",
    "MEMBER_ID": "_raw_member_id",
    "GROUP_NUMBER": "_raw_group_number",
    "STUDENT_ID": "_raw_student_id",
    "EMPLOYEE_ID": "_raw_employee_id",
    "DIAGNOSIS": "_raw_diagnosis",
}


@dataclass
class SheetMapping:
    labels: list[str]  # final label per column (0-based index)
    proba: list[float | None]
    groups: dict[int, dict[int, str]]
    rows: list[dict[str, Any]] = field(default_factory=list)  # column_mapping rows


def map_columns(
    t: Table, s: SheetSettings, model: ColumnClassifier | None, ctx: Context
) -> SheetMapping:
    lex = default_lexicons(s.org_suffixes)
    groups = wide_groups(t.headers, s.sheets.reshape.wide_group_pattern)
    labels, probas, rows = [], [], []
    n = len(t.headers)
    for j, header in enumerate(t.headers):
        values = [vals[j] for _, vals in t.rows]
        rule = rule_label(header, s.aliases)
        if model is not None:
            ml, p = model.predict(header, values, j / max(n - 1, 1), ctx.as_of_date, lex)
        else:
            ml, p = None, None
        d = decide(rule, ml, p, s.thresholds)
        codes = list(d.codes)
        feats = column_features(header, values, j / max(n - 1, 1), ctx.as_of_date, lex)
        if unmapped_sensitive(d.final_label, feats):
            codes.append("COL_UNMAPPED_SENSITIVE")
        labels.append(d.final_label)
        probas.append(p)
        rows.append(
            {
                "doc_id": t.raw.doc_id,
                "sheet": t.raw.sheet,
                "col_idx": j + 1,
                "header_raw": header,
                "rule_label": rule,
                "ml_label": ml,
                "ml_proba": None if p is None else round(p, 4),
                "final_label": d.final_label,
                "decision": d.decision,
                "reviewed_label": None,
                "codes": ";".join(codes),
            }
        )
    return SheetMapping(labels, probas, groups, rows)


def _first(labels: list[str], label: str, skip: set[int]) -> int | None:
    return next((j for j, lab in enumerate(labels) if lab == label and j not in skip), None)


def _role(labels: list[str], groups: dict, s: SheetSettings) -> str:
    present = set(labels) | ({"DEPENDENT_GROUP"} if groups else set())
    for rule in s.sheets.roles:
        if all(lab in present for lab in rule.labels):
            return rule.role
    return s.sheets.default_role


@dataclass
class RowOut:
    mentions: list[dict[str, Any]] = field(default_factory=list)
    excluded_ids: list[dict[str, Any]] = field(default_factory=list)
    excluded_ents: list[dict[str, Any]] = field(default_factory=list)


def _person_from(
    vals: list[Any], cols: dict[str, int], t: Table, rc: R.RepairContext, s: SheetSettings
) -> tuple[dict[str, Any], list[str]]:
    """Fields for the row's main person from mapped columns, with repair codes."""
    out: dict[str, Any] = {}
    codes: list[str] = []

    def cell(label: str) -> Any:
        j = cols.get(label)
        if j is None:
            return None
        v = vals[j]
        if R.is_excel_error(v, s.sheets.repair):
            codes.append("XL_ERROR_VALUE")
            return None
        return v

    if (v := cell("FULL_NAME")) is not None:
        out["raw_name"] = as_text(v)
        out["name_order_detected"] = "LAST_COMMA_FIRST" if "," in as_text(v) else "FIRST_LAST"
    else:
        parts = {
            k: cell(lab)
            for k, lab in (
                ("first_name", "FIRST_NAME"),
                ("middle_name", "MIDDLE_NAME"),
                ("last_name", "LAST_NAME"),
                ("name_suffix", "SUFFIX"),
            )
        }
        parts = {k: as_text(x) for k, x in parts.items() if x not in (None, "")}
        out.update(parts)
        if parts:
            out["raw_name"] = " ".join(
                parts[k].strip()
                for k in ("first_name", "middle_name", "last_name", "name_suffix")
                if k in parts
            )
            out["name_order_detected"] = "FIRST_LAST"
    state = cell("STATE")
    city = cell("CITY")
    zip_raw = cell("ZIP")
    if (csz := cell("CITY_STATE_ZIP")) is not None and (
        parts3 := R.split_city_state_zip(as_text(csz))
    ):
        city, state, zip_raw = parts3
    line1 = cell("ADDRESS_LINE1")
    line2 = cell("ADDRESS_LINE2")
    if (full := cell("ADDRESS_FULL")) is not None:
        a = R.split_address_full(as_text(full))
        line1, line2 = a.get("line1") or line1, a.get("line2") or line2
        city, state, zip_raw = (
            a.get("city") or city,
            a.get("state") or state,
            a.get("zip") or zip_raw,
        )
    state_s = as_text(state).strip().upper() if state not in (None, "") else None
    if zip_raw not in (None, ""):
        fz, z4 = R.repair_zip(zip_raw, state_s, rc)
        out["zip5"], out["zip4"] = fz.value, z4
        codes += fz.codes
    if line1 not in (None, ""):
        out["address_line1"] = as_text(line1)
    if line2 not in (None, ""):
        out["address_line2"] = as_text(line2)
    if city not in (None, ""):
        out["city"] = as_text(city)
    if state_s:
        out["state"] = state_s
    if "address_line1" in out:
        street = " ".join(
            x for x in (out.get("address_line1", ""), out.get("address_line2", "")) if x
        )
        tail = f"{out.get('city', '')}, {out.get('state', '')} {out.get('zip5', '')}".strip(", ")
        out["raw_address"] = f"{street}\n{tail}" if tail else street
    if (v := cell("DOB")) is not None:
        fd = R.repair_date(v, rc)
        out["dob"], out["_raw_dob"] = fd.value, fd.raw
        codes += fd.codes
    if (v := cell("SSN")) is not None:
        fs = R.repair_ssn(v, rc)
        out["_raw_ssn"], out["_ssn_status"] = fs.value, fs.status
        codes += fs.codes
    for label, target in LONG_IDS.items():
        if (v := cell(label)) is not None:
            fl = R.repair_long_id(v, rc)
            out[target] = fl.value
            if label == "CARD":
                out["_card_status"] = fl.status
            codes += fl.codes
    for label, target in (("DL_STATE", "dl_state"), ("EMAIL", "email"), ("SCHOOL", "school_name")):
        if (v := cell(label)) is not None:
            out[target] = as_text(v).strip()
    phone_j = next((j for lab, j in cols.items() if lab == "PHONE"), None)
    if phone_j is not None and (v := cell("PHONE")) is not None:
        out["phone"] = as_text(v).strip()
    return out, codes


def process_sheet(
    t: Table, m: SheetMapping, s: SheetSettings, ctx: Context, ent_cfg: Any
) -> RowOut:
    out = RowOut()
    raw = t.raw
    wide_cols = {j for g in m.groups.values() for j in g}
    gw = s.sheets.guardian_header_words
    iw = s.sheets.insurer_header_words
    guardian_phone = next(
        (
            j
            for j, (lab, h) in enumerate(zip(m.labels, t.headers, strict=True))
            if lab == "PHONE" and any(w in h.lower() for w in gw)
        ),
        None,
    )
    cols: dict[str, int] = {}
    for j, lab in enumerate(m.labels):
        if j in wide_cols or j == guardian_phone or lab in cols:
            continue
        cols[lab] = j
    org_cols = [j for j, lab in enumerate(m.labels) if lab == "ORG_NAME" and j not in wide_cols]
    ein_cols = [j for j, lab in enumerate(m.labels) if lab == "EIN"]
    free_cols = [j for j, lab in enumerate(m.labels) if lab == "FREE_TEXT"]
    role = _role(m.labels, m.groups, s)
    day_first = {
        j: R.column_day_first([v[j] for _, v in t.rows])
        for j, lab in enumerate(m.labels)
        if lab == "DOB"
    }
    seen: dict[tuple, dict[str, Any]] = {}
    conf = {lab: (m.proba[j] if m.proba[j] is not None else 1.0) for lab, j in cols.items()}
    base = {
        "source_type": "SPREADSHEET",
        "doc_id": raw.doc_id,
        "page": None,
        "source_file": raw.path,
        "source_sheet": raw.sheet or None,
        "doc_type": "SPREADSHEET",
        "doc_date": raw.doc_date,
        "entity_type": "PERSON",
        "extraction_method": "SHEET",
        "run_id": ctx.run_id,
    }
    for row_no, vals in t.rows:
        key = tuple(as_text(v) for v in vals)
        if key in seen:  # P42: exact duplicate row, kept once
            seen[key]["_codes"].append("ROW_DUPLICATE_IN_FILE")
            continue
        rc = R.RepairContext(
            s.sheets.repair,
            s.zip_leading_zero_states,
            ctx.as_of_date,
            day_first.get(cols.get("DOB", -1)),
        )
        has_error = any(R.is_excel_error(v, s.sheets.repair) for v in vals)
        if has_error:  # P43: error cells anywhere in the row are nulled and flagged
            vals = [None if R.is_excel_error(v, s.sheets.repair) else v for v in vals]
        person, codes = _person_from(vals, cols, t, rc, s)
        if has_error:
            codes.append("XL_ERROR_VALUE")
        for j in ein_cols:
            if vals[j] not in (None, ""):
                out.excluded_ids.append(
                    {
                        "doc_id": raw.doc_id,
                        "page": None,
                        "sheet": raw.sheet,
                        "row": row_no,
                        "kind": "EIN",
                        "_raw_value": as_text(vals[j]),
                        "value_masked": None,
                        "reason": f"column:{t.headers[j]}",
                    }
                )
        for j in org_cols:
            org = as_text(vals[j]).strip()
            if not org:
                continue
            key_name = (
                "insurer_name" if any(w in t.headers[j].lower() for w in iw) else "employer_name"
            )
            if person.get("raw_name"):
                person.setdefault(key_name, org)
            else:
                out.excluded_ents.append(
                    {
                        "doc_id": raw.doc_id,
                        "page": None,
                        "sheet": raw.sheet,
                        "row": row_no,
                        "kind": ORG,
                        "value_masked": org,
                        "reason": f"column:{t.headers[j]}",
                    }
                )
        name = person.get("raw_name", "")
        if not name.strip():
            continue
        kind, reason = classify_entity(name, ent_cfg)
        if kind == ORG:  # P21: an organization in the person columns
            out.excluded_ents.append(
                {
                    "doc_id": raw.doc_id,
                    "page": None,
                    "sheet": raw.sheet,
                    "row": row_no,
                    "kind": ORG,
                    "value_masked": name.strip(),
                    "reason": reason,
                }
            )
            continue
        hits = []
        for j in free_cols:
            hits += scan_text(as_text(vals[j]), s.sheets.freetext)
        if hits:
            codes.append("FREE_TEXT_PII_FOUND")
            person["_freetext_hits"] = ";".join(sorted({h.kind for h in hits}))
            person["_raw_freetext"] = json.dumps({h.kind: h.value for h in hits}, sort_keys=True)
        if row_no in raw.hidden_rows:
            codes.append("SHEET_HIDDEN_ROWS")
        main = {
            **base,
            **person,
            "source_row": row_no,
            "person_role": role,
            "_codes": codes,
            "_local": "main",
            "field_confidence": json.dumps({k: round(v, 4) for k, v in sorted(conf.items())}),
        }
        seen[key] = main
        out.mentions.append(main)
        for g, gcols in m.groups.items():  # P37: one dependent per group
            dep: dict[str, Any] = {}
            dcodes: list[str] = []
            for j in gcols:
                v = vals[j]
                if v in (None, ""):
                    continue
                lab = m.labels[j]
                if lab == "FIRST_NAME":
                    dep["first_name"] = as_text(v)
                elif lab == "LAST_NAME":
                    dep["last_name"] = as_text(v)
                elif lab == "DOB":
                    fd = R.repair_date(v, rc)
                    dep["dob"], dep["_raw_dob"] = fd.value, fd.raw
                    dcodes += fd.codes
                else:
                    dep["_relationship"] = as_text(v)
            if not dep.get("first_name") and not dep.get("last_name"):
                continue
            dep["raw_name"] = " ".join(dep.get(k, "") for k in ("first_name", "last_name")).strip()
            out.mentions.append(
                {
                    **base,
                    **dep,
                    "source_row": row_no,
                    "person_role": "DEPENDENT",
                    "_codes": dcodes,
                    "_related": main,
                    "_local": f"dep{g}",
                }
            )
        gj = cols.get("GUARDIAN_NAME")
        if gj is not None and vals[gj] not in (None, ""):  # P40: guardian on the student row
            gname = as_text(vals[gj])
            if classify_entity(gname, ent_cfg)[0] != ORG:
                g = {
                    **base,
                    "raw_name": gname,
                    "name_order_detected": "LAST_COMMA_FIRST" if "," in gname else "FIRST_LAST",
                    "source_row": row_no,
                    "person_role": "GUARDIAN",
                    "_codes": [],
                    "_related": main,
                    "_local": "guardian",
                }
                if guardian_phone is not None and vals[guardian_phone] not in (None, ""):
                    g["phone"] = as_text(vals[guardian_phone]).strip()
                out.mentions.append(g)
    return out


def stage_sheet_track(df: pd.DataFrame, ctx: Context) -> pd.DataFrame:
    """Input: mentions so far. Output: the same plus spreadsheet mentions."""
    if not ctx.paths.input_dir.is_dir():
        ctx.tables["sheet_summary"] = {"sheet_files": 0}
        return df
    inventory = ctx.tables.get("inventory")
    if inventory is None:
        inventory = build_inventory(ctx.paths.input_dir)
        ctx.tables["inventory"] = inventory
    files = inventory[inventory["file_kind"].isin(SHEET_KINDS) & ~inventory["is_exact_duplicate"]]
    if files.empty:
        ctx.tables["sheet_summary"] = {"sheet_files": 0}
        return df
    s = load_sheet_settings(ctx.paths.config_dir)
    ent_cfg = load_entity_config(ctx.paths.config_dir / "entities.yaml")
    model = load_model(ctx.paths.models_dir / "column_classifier.joblib")
    if model is None:
        logger.warning(
            "sheet_track: no column classifier in %s; rules only (RULE_ONLY)", ctx.paths.models_dir
        )
    profiles, col_profiles, mappings, codes = [], [], [], []
    mentions: list[dict[str, Any]] = []
    ex_ids: list[dict[str, Any]] = []
    ex_ents: list[dict[str, Any]] = []
    for idx, f in files.iterrows():
        for sheet in read_file(
            ctx.paths.input_dir / f["path"], f["doc_id"], f["path"], f["file_kind"], s.sheets.reader
        ):
            t = fix_layout(sheet, s.sheets.layout)
            profiles.append(file_profile(t))
            codes += [
                {
                    "doc_id": f["doc_id"],
                    "sheet": sheet.sheet,
                    "col_idx": None,
                    "code": c,
                    "detail": d,
                }
                for c, d in t.codes
            ]
            if sheet.doc_date:
                inventory.loc[idx, "doc_date"] = sheet.doc_date
            inventory.loc[idx, "doc_type"] = "SPREADSHEET"
            inventory.loc[idx, "extraction_method"] = "SHEET"
            if t.skipped:
                continue
            col_profiles += column_profiles(t)
            m = map_columns(t, s, model, ctx)
            mappings += m.rows
            codes += [
                {
                    "doc_id": r["doc_id"],
                    "sheet": r["sheet"],
                    "col_idx": r["col_idx"],
                    "code": c,
                    "detail": r["header_raw"],
                }
                for r in m.rows
                for c in r["codes"].split(";")
                if c
            ]
            res = process_sheet(t, m, s, ctx, ent_cfg)
            mentions += res.mentions
            ex_ids += res.excluded_ids
            ex_ents += res.excluded_ents
    mentions.sort(
        key=lambda r: (
            r["doc_id"],
            r["source_sheet"] or "",
            r["source_row"],
            ROLE_ORDER[r["person_role"]],
            r["_local"],
        )
    )
    start = len(df) + 1
    for i, r in enumerate(mentions):
        r["mention_id"] = f"M{start + i:05d}"
    now = datetime.now(UTC).isoformat(timespec="seconds")
    for r in mentions:
        rel = r.pop("_related", None)
        r["related_mention_id"] = rel["mention_id"] if rel else None
        r["_repair_codes"] = ";".join(dict.fromkeys(r.pop("_codes")))
        r.pop("_local", None)
        r["processed_at"] = now
        r["employee_id_present"] = bool(r.get("_raw_employee_id"))
        r["health_group_number_present"] = bool(r.get("_raw_group_number"))
        r["diagnosis_present"] = bool(r.get("_raw_diagnosis"))
    out = pd.DataFrame(mentions)
    ctx.tables["file_profile"] = pd.DataFrame(profiles)
    ctx.tables["column_profile"] = pd.DataFrame(col_profiles)
    ctx.tables["column_mapping"] = pd.DataFrame(mappings)
    ctx.tables["sheet_codes"] = pd.DataFrame(codes)
    for name, rows in (("excluded_identifiers", ex_ids), ("excluded_entities", ex_ents)):
        prev = ctx.tables.get(name)
        new = pd.DataFrame(rows)
        ctx.tables[name] = (
            new if prev is None or prev.empty else pd.concat([prev, new], ignore_index=True)
        )
    summary = {
        "sheet_files": len(files),
        "sheets": len(profiles),
        "sheets_skipped": sum(p["skipped"] for p in profiles),
        "mentions": len(out),
        "columns_mapped": len(mappings),
        "model": "ML+rules" if model else "rules only",
        "excluded_identifiers": len(ex_ids),
        "excluded_entities": len(ex_ents),
    }
    ctx.tables["sheet_summary"] = summary
    logger.info("sheet_track: %s", summary)
    if df.empty:
        return out
    return pd.concat([df, out], ignore_index=True)
