"""Human column overrides (config/review_overrides.yaml, ADR-061)."""

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from breachlens.audit.log import AuditLogger
from breachlens.extract.entity_type import load_entity_config
from breachlens.sheets.layout import fix_layout
from breachlens.sheets.reader import read_file
from breachlens.sheets.settings import ReviewOverride, load_overrides, load_sheet_settings
from breachlens.sheets.sheet_track import map_columns, process_sheet
from breachlens.validate.engine import column_codes

ROOT = Path(__file__).resolve().parents[2]
S = load_sheet_settings(ROOT / "config")


def table(tmp_path: Path):
    p = tmp_path / "patients.csv"
    p.write_text(
        "Patient Name,DOB,Insurer\n"
        "Ann Lee,1990-01-01,Mutual Health Plan\n"
        "Bo Diaz,1991-02-02,Acme Insurance\n",
        encoding="utf-8",
    )
    [raw] = read_file(p, "D0001", "sheets/patients.csv", "CSV", S.sheets.reader)
    return fix_layout(raw, S.sheets.layout)


def run(tmp_path, overrides):
    s = S.__class__(**{**S.__dict__, "overrides": tuple(overrides)})
    ctx = SimpleNamespace(
        as_of_date=pd.Timestamp("2026-10-01").date(),
        run_id="R1",
        tables={},
        audit=AuditLogger("R1"),
    )
    t = table(tmp_path)
    m = map_columns(t, s, None, ctx)
    out = process_sheet(t, m, s, ctx, load_entity_config(ROOT / "config" / "entities.yaml"))
    return m, out, ctx


def test_override_sets_reviewed_label_routes_field_and_logs(tmp_path):
    ov = ReviewOverride(
        file="sheets/patients.csv",
        header="insurer",
        reviewed_label="INSURER",
        reviewed_by="tester",
        reviewed_on="2026-10-18",
    )
    m, out, ctx = run(tmp_path, [ov])
    row = next(r for r in m.rows if r["header_raw"] == "Insurer")
    assert (row["reviewed_label"], row["final_label"]) == ("INSURER", "ORG_NAME")
    assert {r["insurer_name"] for r in out.mentions} == {"Mutual Health Plan", "Acme Insurance"}
    [ev] = [e for e in ctx.audit.events if e.event_type == "REVIEW_OVERRIDE_APPLIED"]
    assert (ev.item_id, ev.field, ev.new_value_masked) == ("D0001::3", "Insurer", "INSURER")
    assert ctx.tables["overrides_applied"] == [ov]


def test_no_override_leaves_the_model_decision(tmp_path):
    m, _, ctx = run(tmp_path, [])
    assert all(r["reviewed_label"] is None for r in m.rows)
    assert not ctx.audit.events


def test_override_for_another_file_does_not_apply(tmp_path):
    ov = ReviewOverride(
        file="sheets/other.csv",
        header="Insurer",
        reviewed_label="INSURER",
        reviewed_by="t",
        reviewed_on="2026-10-18",
    )
    m, _, ctx = run(tmp_path, [ov])
    assert (
        all(r["reviewed_label"] is None for r in m.rows) and "overrides_applied" not in ctx.tables
    )


def test_reviewed_columns_do_not_propagate_warnings():
    df = pd.DataFrame(
        [
            {
                "source_type": "SPREADSHEET",
                "doc_id": "D1",
                "source_sheet": "S",
                "person_role": "PATIENT",
                "insurer_name": "ACME",
            }
        ]
    )
    mapping = pd.DataFrame(
        [
            {
                "doc_id": "D1",
                "sheet": "S",
                "header_raw": "Insurer",
                "final_label": "ORG_NAME",
                "codes": "COL_MAPPING_ML_OVERRIDE",
                "reviewed_label": "INSURER",
            }
        ]
    )
    assert column_codes(df, mapping, r"^dep(\d+)_(.+)$") == {}
    mapping["reviewed_label"] = None
    assert column_codes(df, mapping, r"^dep(\d+)_(.+)$") == {0: ["COL_MAPPING_ML_OVERRIDE"]}


def test_unknown_reviewed_label_is_a_config_error(tmp_path):
    for name in ("column_corpus_aliases.yaml",):
        (tmp_path / name).write_text(
            (ROOT / "config" / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    (tmp_path / "review_overrides.yaml").write_text(
        "overrides:\n  - {file: a.csv, header: X, reviewed_label: NOPE,"
        " reviewed_by: t, reviewed_on: '2026-10-18'}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown reviewed_label"):
        load_overrides(tmp_path)


def test_repo_override_file_loads():
    [ov] = S.overrides
    assert (ov.file, ov.header, ov.reviewed_label) == (
        "sheets/patient_list.xlsx",
        "Insurer",
        "INSURER",
    )
