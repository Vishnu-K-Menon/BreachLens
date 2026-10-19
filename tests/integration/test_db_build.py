"""M6 acceptance on the generated corpus run: the database builds from the written run
folder, the views return the expected totals, and the leak guard finds nothing."""

from pathlib import Path

import pytest

from breachlens.db.load import build_database, scan_database
from breachlens.db.sql_harness import connect_read_only
from breachlens.privacy.leak_guard import LeakGuard

ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.libreoffice, pytest.mark.tesseract]


@pytest.fixture(scope="module")
def db(generated_run, tmp_path_factory):
    ctx, _, _, _ = generated_run
    path = tmp_path_factory.mktemp("db") / "breachlens.duckdb"
    res = build_database(ctx.paths.run_dir, path, ROOT, LeakGuard(ctx.config.privacy.leak_guard))
    return ctx, path, res


def test_views_return_the_expected_totals(db):
    _, path, res = db
    c = connect_read_only(path)
    assert c.execute("SELECT sum(to_notify) FROM v_notify_by_state").fetchone()[0] == 155
    n = c.execute("SELECT count(*) FROM notification_list WHERE notify_required").fetchone()[0]
    assert (
        n == 155
        and res["tables"]["people"]
        == c.execute("SELECT sum(people) FROM v_notify_by_state").fetchone()[0]
    )
    cols = c.execute(
        "SELECT count(*), min(affected_rows) FROM v_review_queue WHERE item_type = 'COLUMN'"
    ).fetchone()
    assert cols[0] >= 1 and cols[1] > 0
    assert (
        c.execute("SELECT sum(people) FROM v_address_status").fetchone()[0]
        == res["tables"]["people"]
    )


def test_leak_guard_finds_nothing_in_the_database(db):
    ctx, path, res = db
    assert res["findings"] == 0
    names, findings = scan_database(
        connect_read_only(path), LeakGuard(ctx.config.privacy.leak_guard)
    )
    assert findings == [] and {"people", "mentions", "v_review_queue"} <= set(names)
