"""DuckDB build and SQL harness (M6, ADR-067) on a tiny hand-built run folder."""

import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from breachlens.config import LeakGuardConfig
from breachlens.db.load import build_database, find_run
from breachlens.db.sql_harness import EMPTY, FAILED, OK, connect_read_only, run_all
from breachlens.privacy.leak_guard import LeakError, LeakGuard
from breachlens.privacy.writer import GuardedWriter

ROOT = Path(__file__).resolve().parents[2]
GUARD = LeakGuard(LeakGuardConfig())
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


@pytest.fixture
def db(tmp_path):
    run_dir = write_run(tmp_path)
    path = tmp_path / "output" / "breachlens.duckdb"
    res = build_database(run_dir, path, ROOT, GUARD)
    return path, res


def test_build_tables_views_and_schema_version(db):
    path, res = db
    assert res["tables"] == {
        "people": 2,
        "mentions": 2,
        "notification_list": 2,
        "pair_features": 1,
        "review_items": 4,
        "audit_log": 1,
    }
    assert set(res["views"]) == {"v_notify_by_state", "v_review_queue", "v_address_status"}
    c = connect_read_only(path)
    assert c.execute("SELECT schema_version, run_id FROM schema_version").fetchall() == [
        ("1.1", RUN)
    ]
    assert c.execute(
        "SELECT sum(to_notify), sum(minors), sum(ferpa_flagged) FROM v_notify_by_state"
    ).fetchone() == (1, 1, 1)
    assert c.execute("SELECT address_status, people FROM v_address_status").fetchall() == [
        ("VERIFIED", 2)
    ]


def test_types_and_no_raw_columns(db):
    c = connect_read_only(db[0])
    zip5, dob, minor, conf = c.execute(
        "SELECT zip5, typeof(dob), typeof(is_minor), typeof(cluster_confidence) "
        "FROM people WHERE person_id='P0001'"
    ).fetchone()
    assert (zip5, dob, minor, conf) == ("02134", "DATE", "BOOLEAN", "DOUBLE")
    cols = {
        r[0]
        for r in c.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='mentions'"
        ).fetchall()
    }
    assert (
        "raw_name" not in cols
        and "raw_address" not in cols
        and not any(x.startswith("_") for x in cols)
    )
    assert {"ssn_masked", "ssn_valid", "ssn_present", "ssn_key", "run_id"} <= cols


def test_review_items_group_column_warnings_once(db):
    c = connect_read_only(db[0])
    items = c.execute(
        "SELECT item_type, header, codes, affected_rows, status FROM review_items ORDER BY item_id"
    ).fetchall()
    assert ("COLUMN", "ID", "COL_MAPPING_LOW_CONF", 1, "OPEN") in items
    assert ("COLUMN", "Insurer", "COL_MAPPING_ML_OVERRIDE", 1, "RESOLVED") in items
    mentions = [i for i in items if i[0] == "MENTION"]
    assert [m[2] for m in mentions] == ["SSN_AREA_INVALID"]  # M00001 only had a column code + INFO
    assert (
        c.execute("SELECT count(*) FROM v_review_queue WHERE item_type = 'COLUMN'").fetchone()[0]
        == 1
    )


def test_leak_guard_aborts_and_saves_nothing(tmp_path):
    run_dir = write_run(tmp_path, people_note="Call SSN 123-45-6789")
    path = tmp_path / "output" / "breachlens.duckdb"
    with pytest.raises(LeakError):
        build_database(run_dir, path, ROOT, GUARD)
    assert not path.exists() and not list(path.parent.glob("*.tmp"))


def test_read_only_connection_blocks_writes_and_files(db):
    c = connect_read_only(db[0])
    for q in (
        "CREATE TABLE x (a INT)",
        "INSERT INTO people (run_id, person_id) VALUES ('r', 'p')",
        "DELETE FROM people",
        "COPY people TO 'out.csv'",
        "SELECT * FROM read_csv('README.md')",
    ):
        with pytest.raises(duckdb.Error):
            c.execute(q)


def test_find_run_picks_the_newest_with_people(tmp_path):
    write_run(tmp_path)
    (tmp_path / "output" / "R20991231-000000-ffff").mkdir()  # a scale run: no people.csv
    assert find_run(tmp_path / "output").name == RUN
    with pytest.raises(FileNotFoundError):
        find_run(tmp_path / "output", "R00000000-000000-0000")


def test_sql_harness(db, tmp_path):
    q = tmp_path / "queries"
    q.mkdir()
    (q / "q1_ok.sql").write_text(
        "-- question\nSELECT jurisdiction, to_notify FROM v_notify_by_state;\n", encoding="utf-8"
    )
    (q / "q2_empty.sql").write_text("-- Q2: a question only\n", encoding="utf-8")
    (q / "q3_key.sql").write_text("SELECT person_id, ssn_key FROM mentions", encoding="utf-8")
    (q / "q4_star.sql").write_text("SELECT * FROM mentions", encoding="utf-8")
    (q / "q5_write.sql").write_text("DELETE FROM people", encoding="utf-8")
    (q / "q6_two.sql").write_text("SELECT 1; SELECT 2", encoding="utf-8")
    (q / "q7_bad.sql").write_text("SELECT nope FROM people", encoding="utf-8")
    w = GuardedWriter(GUARD, tmp_path / "sql")
    res = {r.name: r for r in run_all(db[0], q, w)}
    assert (
        res["q1_ok"].status == OK
        and res["q1_ok"].rows == 1
        and (tmp_path / "sql" / "q1_ok.csv").is_file()
    )
    assert res["q2_empty"].status == EMPTY
    for name in ("q3_key", "q4_star"):
        assert res[name].status == FAILED and "key column" in res[name].detail
    assert (
        res["q5_write"].status == FAILED
        and res["q6_two"].status == FAILED
        and res["q7_bad"].status == FAILED
    )
    assert sorted(p.name for p in (tmp_path / "sql").iterdir()) == ["q1_ok.csv"]


def test_repo_query_files_hold_only_the_question():
    files = sorted((ROOT / "sql" / "queries").glob("*.sql"))
    assert [f.stem for f in files] == [
        "q1_notify_by_state",
        "q2_notify_status",
        "q3_address_status",
        "q4_minors",
        "q5_top_reason_codes",
    ]
