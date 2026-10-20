"""DuckDB build and SQL harness (M6, ADR-067) on a tiny hand-built run folder."""

from pathlib import Path

import duckdb
import pytest
from run_fixture import RUN, write_run

from breachlens.config import LeakGuardConfig
from breachlens.db.load import build_database, find_run
from breachlens.db.sql_harness import EMPTY, FAILED, OK, connect_read_only, run_all
from breachlens.privacy.leak_guard import LeakError, LeakGuard
from breachlens.privacy.writer import GuardedWriter

ROOT = Path(__file__).resolve().parents[2]
GUARD = LeakGuard(LeakGuardConfig())


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
    # ';' inside a string literal is not a second statement (sql/queries/q5 uses it)
    (q / "q8_literal.sql").write_text(
        "WITH c AS (SELECT unnest(string_split('A;B', ';')) AS code) SELECT code FROM c;",
        encoding="utf-8",
    )
    (q / "q9_two.sql").write_text("SELECT ';' AS s; SELECT 2", encoding="utf-8")
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
    assert res["q8_literal"].status == OK and res["q8_literal"].rows == 2
    assert res["q9_two"].status == FAILED and "one statement" in res["q9_two"].detail
    assert sorted(p.name for p in (tmp_path / "sql").iterdir()) == ["q1_ok.csv", "q8_literal.csv"]


def test_repo_query_files_hold_only_the_question():
    files = sorted((ROOT / "sql" / "queries").glob("*.sql"))
    assert [f.stem for f in files] == [
        "q1_notify_by_state",
        "q2_notify_status",
        "q3_address_status",
        "q4_minors",
        "q5_top_reason_codes",
    ]
