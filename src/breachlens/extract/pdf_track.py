"""PDF track stage: inventory -> text layer or OCR -> doc type -> template extraction ->
identifier / entity disambiguation -> `mentions` rows (source_type=PDF).

Everything stays in memory (ADR-044); raw identifiers live only in `_raw_*` columns.
Side tables go to `ctx.tables` (ADR-054): `inventory`, `excluded_identifiers`,
`excluded_entities`, `pdf_diagnostics`, `pdf_summary`.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from breachlens.classify.doctype import UNKNOWN, classify
from breachlens.context import Context
from breachlens.extract import identifiers as idmod
from breachlens.extract.entity_type import ORG, classify_entity, load_entity_config
from breachlens.extract.templates import extract as run_template
from breachlens.extract.templates import load_templates
from breachlens.ingest.inventory import build_inventory
from breachlens.ingest.ocr import TesseractMissingError, ocr_tokens, tesseract_cmd
from breachlens.ingest.text_extract import extract_tokens
from breachlens.ingest.tokens import group_lines

logger = logging.getLogger(__name__)

ROLE_ORDER = ["EMPLOYEE", "NEW_HIRE", "PATIENT", "INSURED"]
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
    "raw_name",
    "name_order_detected",
    "raw_address",
    "dob",
    "_raw_dob",
    "_raw_ssn",
    "_raw_dl",
    "dl_state",
    "_raw_passport",
    "passport_country",
    "_raw_member_id",
    "_raw_group_number",
    "health_group_number_present",
    "_raw_diagnosis",
    "diagnosis_present",
    "_raw_procedure",
    "procedure_present",
    "_raw_date_of_service",
    "date_of_service_present",
    "insurer_name",
    "employer_name",
    "phone",
    "email",
    "field_confidence",
    "extraction_method",
    "run_id",
    "processed_at",
]
SIMPLE = [
    "raw_name",
    "name_order_detected",
    "raw_address",
    "dob",
    "_raw_dob",
    "_raw_ssn",
    "_raw_dl",
    "dl_state",
    "_raw_passport",
    "_raw_member_id",
    "_raw_group_number",
    "_raw_diagnosis",
    "_raw_procedure",
    "insurer_name",
    "employer_name",
    "phone",
    "email",
]


def _mention_row(
    doc: pd.Series,
    doc_type: str,
    doc_date: str | None,
    role: str,
    vals: dict[str, str],
    confs: dict[str, float],
    method: str,
    ctx: Context,
    now: str,
) -> dict[str, Any]:
    row: dict[str, Any] = {c: None for c in MENTION_COLUMNS}
    row.update({k: vals.get(k) for k in SIMPLE})
    dos = vals.get("date_of_service")
    row.update(
        {
            "source_type": "PDF",
            "doc_id": doc["doc_id"],
            "page": 1,
            "source_file": doc["path"],
            "doc_type": doc_type,
            "doc_date": doc_date,
            "person_role": role,
            "entity_type": "PERSON",
            "passport_country": "US" if vals.get("_raw_passport") else None,
            "health_group_number_present": bool(vals.get("_raw_group_number")),
            "diagnosis_present": bool(vals.get("_raw_diagnosis")),
            "procedure_present": bool(vals.get("_raw_procedure")),
            "_raw_date_of_service": dos,
            "date_of_service_present": bool(dos),
            "field_confidence": json.dumps(
                {k: confs[k] for k in sorted(confs) if not k.startswith("_")}
                | {k.lstrip("_"): confs[k] for k in sorted(confs) if k.startswith("_")}
            ),
            "extraction_method": method,
            "run_id": ctx.run_id,
            "processed_at": now,
        }
    )
    return row


def stage_pdf_track(df: pd.DataFrame, ctx: Context) -> pd.DataFrame:
    """Input: mentions so far (any track). Output: the same plus PDF mentions."""
    cfg = ctx.config
    input_dir = ctx.paths.input_dir
    if not input_dir.is_dir():
        logger.warning("pdf_track: input directory %s does not exist; nothing to do", input_dir)
        ctx.tables["pdf_summary"] = {"pdf_files": 0}
        return df
    inventory = ctx.tables.get("inventory")
    if inventory is None:
        inventory = build_inventory(input_dir)
        ctx.tables["inventory"] = inventory
    pdfs = inventory[inventory["file_kind"] == "PDF"]
    if pdfs.empty:
        ctx.tables["pdf_summary"] = {"pdf_files": 0}
        return df
    templates = load_templates(ctx.paths.config_dir / "doc_templates")
    id_cfg = idmod.load_identifier_config(ctx.paths.config_dir / "identifiers.yaml")
    ent_cfg = load_entity_config(ctx.paths.config_dir / "entities.yaml")
    have_tesseract = tesseract_cmd() is not None
    now = datetime.now(UTC).isoformat(timespec="seconds")
    rows: list[dict[str, Any]] = []
    excluded_ids: list[dict[str, Any]] = []
    excluded_ents: list[dict[str, Any]] = []
    diags: list[dict[str, Any]] = []
    counts = {
        "pdf_files": len(pdfs),
        "text": 0,
        "ocr": 0,
        "duplicates_skipped": 0,
        "ocr_skipped": 0,
    }
    for idx, doc in pdfs.iterrows():
        if doc["is_exact_duplicate"]:  # P25: never double-count an identical file
            counts["duplicates_skipped"] += 1
            inventory.loc[idx, "extraction_method"] = "SKIPPED_DUPLICATE"
            continue
        t0 = time.perf_counter()
        path = input_dir / doc["path"]
        ocr = not bool(doc["has_text_layer"])
        if ocr and not have_tesseract:
            logger.warning("%s: image-only PDF but Tesseract is missing; skipped", doc["doc_id"])
            counts["ocr_skipped"] += 1
            inventory.loc[idx, "extraction_method"] = "SKIPPED_NO_OCR"
            continue
        try:
            tokens = (
                ocr_tokens(
                    path,
                    dpi=cfg.ocr.dpi,
                    lang=cfg.ocr.lang,
                    psm=cfg.ocr.psm,
                    binarize_threshold=cfg.ocr.binarize_threshold,
                    remove_lines_min_px=cfg.ocr.remove_lines_min_px,
                    min_conf=cfg.ocr.min_conf,
                    min_height_pt=cfg.ocr.min_height_pt,
                )
                if ocr
                else extract_tokens(path, cfg.text_layer.max_font_size)
            )
        except TesseractMissingError:
            counts["ocr_skipped"] += 1
            continue
        method = "OCR" if ocr else "TEXT"
        counts[method.lower()] += 1
        page1 = [t for t in tokens if t.page == 1]
        result = classify(templates, " ".join(t.text for t in page1), ocr, cfg.doctype.min_score)
        inventory.loc[idx, ["doc_type", "doc_type_score", "extraction_method"]] = [
            result.doc_type,
            result.score,
            method,
        ]
        if ocr:
            inventory.loc[idx, "mean_ocr_conf"] = round(
                sum(t.conf for t in tokens) / max(len(tokens), 1), 4
            )
        if result.template is None:
            logger.warning("%s: doc type %s (score %.2f)", doc["doc_id"], UNKNOWN, result.score)
            inventory.loc[idx, "processing_ms"] = int((time.perf_counter() - t0) * 1000)
            continue
        ex = run_template(result.template, page1, ocr, ctx.as_of_date)
        inventory.loc[idx, "doc_date"] = ex.doc_date
        found = idmod.dedupe(
            [idmod.FoundId(k, v, "template", c) for k, v, c in ex.identifiers]
            + idmod.scan(group_lines(page1), id_cfg)
        )
        business_digits = {"".join(ch for ch in f.value if ch.isdigit()) for f in found}
        for f in found:
            excluded_ids.append(
                {
                    "doc_id": doc["doc_id"],
                    "page": 1,
                    "kind": f.kind,
                    "_raw_value": f.value,
                    "value_masked": None,
                    "reason": f.reason,
                }
            )
        role_rows: dict[str, dict[str, Any]] = {}
        for role in sorted(
            ex.persons, key=lambda r: ROLE_ORDER.index(r) if r in ROLE_ORDER else 99
        ):
            vals = dict(ex.persons[role])
            kind, reason = classify_entity(vals.get("raw_name", ""), ent_cfg)
            if kind == ORG:  # P21: organization in a person field
                excluded_ents.append(
                    {
                        "doc_id": doc["doc_id"],
                        "page": 1,
                        "kind": ORG,
                        "value_masked": vals.get("raw_name"),
                        "reason": f"{role}:{reason}",
                    }
                )
                continue
            ssn = vals.get("_raw_ssn")
            if ssn and idmod.is_itin(ssn, id_cfg):  # ADR-035: ITIN before SSN validity
                excluded_ids.append(
                    {
                        "doc_id": doc["doc_id"],
                        "page": 1,
                        "kind": "ITIN",
                        "_raw_value": ssn,
                        "value_masked": None,
                        "reason": "ITIN_DETECTED",
                    }
                )
                vals.pop("_raw_ssn")
            elif ssn and ssn in business_digits:  # the "SSN" is really a business id
                vals.pop("_raw_ssn")
            role_rows[role] = _mention_row(
                doc,
                result.doc_type,
                ex.doc_date,
                role,
                vals,
                ex.confidence.get(role, {}),
                method,
                ctx,
                now,
            )
        rows += role_rows.values()
        for role, field_name, status in ex.diagnostics:
            diags.append(
                {
                    "doc_id": doc["doc_id"],
                    "template": result.template.name,
                    "role": role,
                    "field": field_name,
                    "status": status,
                    "method": method,
                }
            )
        inventory.loc[idx, "processing_ms"] = int((time.perf_counter() - t0) * 1000)

    out = pd.DataFrame(rows, columns=MENTION_COLUMNS)
    out = out.sort_values(["doc_id", "page", "person_role"], kind="stable").reset_index(drop=True)
    start = len(df) + 1
    out["mention_id"] = [f"M{i:05d}" for i in range(start, start + len(out))]
    # dependent / child patient -> insured on the same claim
    for _doc_id, grp in out.groupby("doc_id"):
        ids = dict(zip(grp["person_role"], grp["mention_id"], strict=True))
        if "PATIENT" in ids and "INSURED" in ids:
            out.loc[out["mention_id"] == ids["PATIENT"], "related_mention_id"] = ids["INSURED"]
    ctx.tables["excluded_identifiers"] = pd.DataFrame(excluded_ids)
    ctx.tables["excluded_entities"] = pd.DataFrame(excluded_ents)
    ctx.tables["pdf_diagnostics"] = pd.DataFrame(diags)
    counts |= {
        "mentions": len(out),
        "excluded_identifiers": len(excluded_ids),
        "excluded_entities": len(excluded_ents),
    }
    ctx.tables["pdf_summary"] = counts
    logger.info("pdf_track: %s", counts)
    return pd.concat([df, out], ignore_index=True) if not df.empty else out
