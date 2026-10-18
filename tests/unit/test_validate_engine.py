"""Normalize -> validate -> privacy on hand-built mentions (no corpus needed)."""

import json
from pathlib import Path

import pandas as pd
import pytest

from breachlens.normalize.stage import stage_normalize
from breachlens.pipeline import load_context
from breachlens.privacy.stage import stage_privacy
from breachlens.validate.engine import column_codes, qc_status, stage_validate
from breachlens.validate.settings import load_validation_settings

ROOT = Path(__file__).resolve().parents[2]
V = load_validation_settings(ROOT / "config")


@pytest.fixture
def ctx(salt_env):
    return load_context(ROOT / "config" / "pipeline.yaml")


def mentions() -> pd.DataFrame:
    base = {
        "source_type": "PDF",
        "doc_id": "D0001",
        "page": 1,
        "person_role": "PATIENT",
        "entity_type": "PERSON",
        "extraction_method": "TEXT",
        "name_order_detected": "LAST_COMMA_FIRST",
        "run_id": "R1",
    }
    return pd.DataFrame(
        [
            base
            | {
                "mention_id": "M00001",
                "raw_name": "WALKER, BRYAN M",
                "raw_address": "1201 LEOPARD ST\nCORPUS CHRISTI, TX 7840",
                "dob": "1968-12-10",
                "_raw_dob": "12/10/68",
                "_raw_ssn": "666001234",
            },
            base
            | {
                "mention_id": "M00002",
                "raw_name": "DR. KERRY M SMITH",
                "name_order_detected": "FIRST_LAST",
                "raw_address": "828 I ST\nSACRAMNETO, CA 95814",
                "dob": "2015-01-01",
                "_raw_ssn": "900701234",
                "phone": "(212) 555-0123",
                "email": " Kerry@Example.COM ",
            },
            base
            | {
                "mention_id": "M00003",
                "raw_name": "SHANE HENDERSON",
                "name_order_detected": "FIRST_LAST",
            },
        ]
    )


def run(ctx) -> pd.DataFrame:
    return stage_privacy(stage_validate(stage_normalize(mentions(), ctx), ctx), ctx)


def test_codes_status_and_normalized_fields(ctx):
    out = run(ctx).set_index("mention_id")
    a = out.loc["M00001"]
    assert (a["first_name"], a["middle_initial"], a["last_name"]) == ("BRYAN", "M", "WALKER")
    assert set(a["qc_reasons"].split(";")) >= {
        "ADDR_ZIP_FORMAT",
        "DOB_TWO_DIGIT_YEAR",
        "SSN_AREA_INVALID",
        "SSN_GROUP_INVALID",
    }
    assert (
        a["qc_status"] == "FAIL"
        and a["address_status"] == "INVALID"
        and a["ssn_valid"] == "SSN_AREA_INVALID"
    )
    b = out.loc["M00002"]
    assert b["name_title"] == "DR" and b["is_minor"] and b["age_at_run"] == 11
    assert "ADDR_ZIP_CITY_MISMATCH" in b["qc_reasons"] and "SACRAMENTO" in b["address_suggestion"]
    assert (b["phone"], b["email"]) == ("+12125550123", "kerry@example.com")
    assert not b["ssn_present"]  # the ITIN was routed out
    c = out.loc["M00003"]
    assert c["qc_status"] == "REVIEW" and "PERSON_NO_QUALIFYING_ELEMENT" in c["qc_reasons"]
    assert not [col for col in out.columns if col.startswith("_")]


def test_itin_is_routed_to_excluded_identifiers(ctx):
    run(ctx)
    ex = ctx.tables["excluded_identifiers"]
    assert ex["kind"].tolist() == ["ITIN"] and ex["value_masked"].tolist() == ["*****1234"]
    assert ex["reason"].str.startswith("ITIN_DETECTED").all() and "_raw_value" not in ex


def test_audit_events_carry_codes_not_values(ctx):
    run(ctx)
    ev = [e for e in ctx.audit.events if e.event_type == "RULE_FIRED"]
    assert {e.code for e in ev} >= {"SSN_AREA_INVALID", "ADDR_ZIP_CITY_MISMATCH"}
    city = next(e for e in ev if e.code == "ADDR_ZIP_CITY_MISMATCH")
    assert json.loads(city.detail_json) == {"severity": "WARN", "suggestion": "SACRAMENTO"}
    assert not any("666001234" in (e.detail_json or "") for e in ctx.audit.events)


def test_qc_status_from_config_severities():
    assert qc_status([], V) == "PASS"
    assert qc_status(["DOB_MINOR"], V) == "PASS"
    assert qc_status(["DOB_MINOR", "FREE_TEXT_PII_FOUND"], V) == "REVIEW"
    assert qc_status(["FREE_TEXT_PII_FOUND", "CARD_LUHN_FAIL"], V) == "FAIL"
    with pytest.raises(ValueError, match="not declared"):
        qc_status(["NOT_A_CODE"], V)


def test_column_warn_codes_reach_only_mentions_that_used_the_column():
    df = pd.DataFrame(
        [
            {
                "source_type": "SPREADSHEET",
                "doc_id": "D1",
                "source_sheet": "S",
                "person_role": "PATIENT",
                "insurer_name": "ACME",
            },
            {
                "source_type": "SPREADSHEET",
                "doc_id": "D1",
                "source_sheet": "S",
                "person_role": "PATIENT",
                "insurer_name": None,
            },
            {
                "source_type": "SPREADSHEET",
                "doc_id": "D1",
                "source_sheet": "S",
                "person_role": "DEPENDENT",
                "insurer_name": "ACME",
            },
        ]
    )
    mapping = pd.DataFrame(
        [
            {
                "doc_id": "D1",
                "sheet": "S",
                "header_raw": "Insurer",
                "final_label": "SCHOOL",
                "codes": "COL_MAPPING_ML_OVERRIDE",
            },
            {
                "doc_id": "D1",
                "sheet": "S",
                "header_raw": "Insurer",
                "final_label": "ORG_NAME",
                "codes": "COL_MAPPING_LOW_CONF",
            },
        ]
    )
    df["school_name"] = ["ACME", None, None]
    out = column_codes(df, mapping, r"^(?:dep|dependent|child)\s*_?(\d+)[_ ]+(.+)$")
    assert out == {0: ["COL_MAPPING_ML_OVERRIDE", "COL_MAPPING_LOW_CONF"]}
