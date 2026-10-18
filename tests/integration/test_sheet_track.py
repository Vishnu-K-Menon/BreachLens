"""M3 acceptance on a freshly generated corpus: a small column classifier is trained in a
temp dir, then the spreadsheet track runs on the corpus. Every planted spreadsheet case
P27-P44 is handled or flagged; the vendor file yields 0 person mentions (P39); ML beats
the header rules on uninformative headers."""

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from breachlens.evaluate.sheets import evaluate
from breachlens.ml.column_classifier import train
from breachlens.pipeline import load_context
from breachlens.sheets.settings import load_sheet_settings
from breachlens.sheets.sheet_track import stage_sheet_track
from breachlens.synth.generate import generate_corpus
from breachlens.synth.settings import load_synth_settings

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.libreoffice  # legacy_export.xls is converted with LibreOffice


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    s = load_synth_settings(ROOT / "config")
    c = s.config
    cfg = c.model_copy(
        update={
            "column_corpus": c.column_corpus.model_copy(update={"tables": 80, "max_rows": 60}),
            "scale": c.scale.model_copy(update={"large_claims_rows": 50}),
        }
    )
    base = tmp_path_factory.mktemp("m3")
    out = base / "raw" / "corpus_v1"
    generate_corpus(replace(s, config=cfg), ROOT, out)
    mp = pytest.MonkeyPatch()
    mp.setenv("BREACHLENS_SALT", "integration-test-salt-0123456789abcdef")
    ctx = load_context(ROOT / "config" / "pipeline.yaml", input_dir=out / "docs")
    mp.undo()
    settings = load_sheet_settings(ROOT / "config")
    metrics = train(
        out.parent / "column_corpus", {"dev": out}, base / "models", settings, ctx.as_of_date
    )
    ctx.paths = replace(ctx.paths, models_dir=base / "models")
    mentions = stage_sheet_track(pd.DataFrame(), ctx)
    return mentions, ctx, evaluate(mentions, ctx.tables, out / "truth"), metrics


def test_every_planted_case_is_handled_or_flagged(run):
    _, ctx, report, _ = run
    by_case = {p["case"]: p for p in report["planted"]}
    assert sorted(by_case) == [f"P{n}" for n in range(27, 45)]
    for case, p in by_case.items():
        if case == "P36":  # a small model may be unsure: then the column must go to review
            cm = ctx.tables["column_mapping"]
            cols = cm[cm["header_raw"].isin(["ID", "Column7"])]
            ok = (cols["final_label"].tolist() == ["SSN", "DOB"]) or cols["codes"].str.contains(
                "COL_MAPPING_LOW_CONF"
            ).all()
            assert ok, cols[["header_raw", "final_label", "decision", "codes"]]
            continue
        assert p["handled"] == "yes", p


def test_vendor_file_has_no_person_mentions(run):
    mentions, ctx, report, _ = run
    inv = ctx.tables["inventory"].set_index("path")
    assert not (mentions["doc_id"] == inv.loc["sheets/vendor_list.xlsx", "doc_id"]).any()
    assert report["exclusions"]["EIN"]["correct"] == report["exclusions"]["EIN"]["expected"] > 0
    assert report["exclusions"]["ORG"]["correct"] == report["exclusions"]["ORG"]["expected"] > 0


def test_field_recall_and_provenance(run):
    mentions, ctx, report, _ = run
    rec = report["recall"]["recall"]
    for field in ("name", "ssn_present", "zip5"):
        assert rec[field] >= 0.95, field
    # A small model may leave Column7 (P36) in review: only then may its DOBs be missing.
    cm = ctx.tables["column_mapping"]
    col7 = cm[cm["header_raw"] == "Column7"].iloc[0]
    for f in report["failures"]:
        assert f["file"] == "sheets/legacy_export.xls" and f["field"] == "dob", f
        assert col7["decision"] == "REVIEW" and "COL_MAPPING_LOW_CONF" in col7["codes"]
    assert set(mentions["source_type"]) == {"SPREADSHEET"}
    assert mentions["source_file"].notna().all() and mentions["source_row"].notna().all()
    deps = mentions[mentions["person_role"].isin(["DEPENDENT", "GUARDIAN"])]
    assert not deps.empty and deps["related_mention_id"].notna().all()


def test_ml_beats_rules_on_uninformative_headers(run):
    *_, metrics = run
    hard = metrics["hard_test_macro_f1"]
    hv = next(k for k in hard if k.startswith("HV"))
    assert hard[hv]["uninformative_headers_oof"] > hard["R"]["uninformative_headers_oof"]
