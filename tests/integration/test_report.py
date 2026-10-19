"""M7 acceptance on the generated corpus run: database -> workbook -> LibreOffice
recalculation. The recalculated Summary equals Python (155 to notify), no formula
errors, and the leak guard finds nothing in the run folder including the workbook."""

from pathlib import Path

import pytest

from breachlens.db.load import build_database
from breachlens.privacy.leak_guard import LeakGuard, scan_dir
from breachlens.report.excel_writer import load_report_data, write_workbook
from breachlens.report.recalc import check, recalculate
from breachlens.validate.settings import load_validation_settings

ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.libreoffice, pytest.mark.tesseract]


def test_workbook_recalculates_to_the_python_counts(generated_run, tmp_path):
    ctx, _, _, _ = generated_run
    guard = LeakGuard(ctx.config.privacy.leak_guard)
    db = tmp_path / "breachlens.duckdb"
    build_database(ctx.paths.run_dir, db, ROOT, guard)
    d = load_report_data(db, ROOT, ctx.as_of_date)
    path = write_workbook(
        d, ctx.paths.run_dir, guard, load_validation_settings(ROOT / "config").severity
    )
    res = check(recalculate(path, tmp_path / "recalc"), d)
    assert res.errors == [] and res.mismatches == []
    got = {(s, i): e for s, i, e, _ in res.summary}
    assert got[("KPI", "People to notify")] == 155
    assert sum(v for (s, _), v in got.items() if s == "To notify by state") == 155
    assert res.status_rows == len(d.notify) and res.status_disagree == 0
    cols = d.review[d.review["item_type"] == "COLUMN"]
    assert cols["item_id"].is_unique and (cols["affected_rows"] > 0).all()
    files, findings = scan_dir(ctx.paths.run_dir, guard)
    assert path in files and findings == []
