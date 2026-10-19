"""A tiny hand-built run folder (M6/M7 tests): people, mentions, notification list,
pair features, column mapping and an audit file, all synthetic."""

import json
from pathlib import Path

import pandas as pd

RUN = "R20261019-120000-ab12"


def write_run(base: Path, people_note: str = "Notify parent/guardian (P0001)") -> Path:
    d = base / "output" / RUN
    d.mkdir(parents=True)
    people = pd.DataFrame(
        [
            {
                "person_id": "P0001",
                "first_name": "ANN",
                "last_name": "LEE",
                "state": "MA",
                "zip5": "02134",
                "dob": "1980-01-02",
                "is_minor": "False",
                "ssn_exposed": "True",
                "elements_exposed": "SSN",
                "address_status": "VERIFIED",
                "cluster_confidence": "1.0",
                "needs_review": "False",
                "notify_required": "True",
                "ferpa_flag": "False",
            },
            {
                "person_id": "P0002",
                "first_name": "BO",
                "last_name": "LEE",
                "state": "MA",
                "zip5": "02134",
                "dob": "2015-05-05",
                "is_minor": "True",
                "ssn_exposed": "False",
                "elements_exposed": "",
                "address_status": "VERIFIED",
                "cluster_confidence": "1.0",
                "needs_review": "True",
                "notify_required": "False",
                "ferpa_flag": "True",
            },
        ]
    )
    people.to_csv(d / "people.csv", index=False)
    pd.DataFrame(
        [
            {
                "mention_id": "M00001",
                "source_type": "SPREADSHEET",
                "doc_id": "D0001",
                "source_sheet": "S",
                "source_row": "2",
                "raw_name": "Ann Lee",
                "raw_address": "1 MAIN ST",
                "first_name": "ANN",
                "zip5": "02134",
                "ssn_present": "True",
                "ssn_masked": "***-**-6789",
                "ssn_valid": "PASS",
                "ssn_key": "0123456789abcdef",
                "qc_status": "REVIEW",
                "qc_reasons": "COL_MAPPING_LOW_CONF;DOB_MINOR",
                "person_id": "P0001",
                "run_id": RUN,
                "processed_at": "2026-10-19T12:00:00+00:00",
                "address_status": "VERIFIED",
            },
            {
                "mention_id": "M00002",
                "source_type": "PDF",
                "doc_id": "D0002",
                "source_sheet": "",
                "source_row": "",
                "raw_name": "Bo Lee",
                "raw_address": "",
                "first_name": "BO",
                "zip5": "02134",
                "ssn_present": "False",
                "ssn_masked": "",
                "ssn_valid": "",
                "ssn_key": "",
                "qc_status": "FAIL",
                "qc_reasons": "SSN_AREA_INVALID",
                "person_id": "P0002",
                "run_id": RUN,
                "processed_at": "2026-10-19T12:00:00+00:00",
                "address_status": "VERIFIED",
            },
        ]
    ).to_csv(d / "mentions.csv", index=False)
    pd.DataFrame(
        [
            {
                "person_id": "P0001",
                "jurisdiction": "MA",
                "notify_required": "True",
                "notify_note": "",
                "ferpa_flag": "False",
                "notify_status": "READY",
                "address_status": "VERIFIED",
            },
            {
                "person_id": "P0002",
                "jurisdiction": "MA",
                "notify_required": "False",
                "notify_note": people_note,
                "ferpa_flag": "True",
                "notify_status": "NOT_REQUIRED",
                "address_status": "VERIFIED",
            },
        ]
    ).to_csv(d / "notification_list.csv", index=False)
    pd.DataFrame(
        [
            {
                "mention_a": "M00001",
                "mention_b": "M00002",
                "f_first_jw": "0.5",
                "score": "0.8",
                "pass": "C",
                "decision": "REVIEW",
                "guard_fired": "",
                "same_person_id": "False",
            }
        ]
    ).to_csv(d / "pair_features.csv", index=False)
    pd.DataFrame(
        [
            {
                "doc_id": "D0001",
                "sheet": "S",
                "col_idx": "3",
                "header_raw": "ID",
                "codes": "COL_MAPPING_LOW_CONF",
                "reviewed_label": "",
                "affected_rows": "1",
            },
            {
                "doc_id": "D0001",
                "sheet": "S",
                "col_idx": "4",
                "header_raw": "Insurer",
                "codes": "COL_MAPPING_ML_OVERRIDE",
                "reviewed_label": "INSURER",
                "affected_rows": "1",
            },
            {
                "doc_id": "D0001",
                "sheet": "S",
                "col_idx": "5",
                "header_raw": "Name",
                "codes": "",
                "reviewed_label": "",
                "affected_rows": "0",
            },
        ]
    ).to_csv(d / "column_mapping.csv", index=False)
    (d / f"audit_{RUN}.jsonl").write_text(
        json.dumps(
            {
                "event_id": "E000001",
                "run_id": RUN,
                "ts": "2026-10-19T12:00:00+00:00",
                "stage": "validate",
                "event_type": "RULE_FIRED",
                "item_id": "M00002",
                "code": "SSN_AREA_INVALID",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return d
