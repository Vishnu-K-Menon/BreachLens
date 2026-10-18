"""M2 acceptance on a freshly generated corpus (reduced column corpus / scale file,
full-resolution scans): text-layer recall >= 0.95 for name, DOB and SSN-present; doc
types; duplicate skipping (P25); EIN/NPI/TIN exclusions (P19/P20); ORG in a person
field (P21). OCR results are checked separately (marker `tesseract`)."""

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from breachlens.evaluate.extraction import AC_FIELDS, evaluate
from breachlens.extract.pdf_track import stage_pdf_track
from breachlens.pipeline import load_context
from breachlens.synth.generate import generate_corpus
from breachlens.synth.settings import load_synth_settings

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.libreoffice


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    s = load_synth_settings(ROOT / "config")
    c = s.config
    cfg = c.model_copy(
        update={
            "column_corpus": c.column_corpus.model_copy(update={"tables": 4, "max_rows": 30}),
            "scale": c.scale.model_copy(update={"large_claims_rows": 50}),
        }
    )
    out = tmp_path_factory.mktemp("m2") / "raw" / "corpus_v1"
    generate_corpus(replace(s, config=cfg), ROOT, out)
    mp = pytest.MonkeyPatch()
    mp.setenv("BREACHLENS_SALT", "integration-test-salt-0123456789abcdef")
    ctx = load_context(ROOT / "config" / "pipeline.yaml", input_dir=out / "docs")
    mp.undo()
    mentions = stage_pdf_track(pd.DataFrame(), ctx)
    return mentions, ctx, evaluate(mentions, ctx.tables, out / "truth")


def _recall(report, field, method):
    r = report.recall
    row = r[(r["field"] == field) & (r["method"] == method)]
    return float(row["recall"].iloc[0])


def test_text_layer_recall_meets_the_ac(run):
    _, _, report = run
    for field in AC_FIELDS:
        assert _recall(report, field, "TEXT") >= 0.95, field


def test_doc_types_and_duplicates(run):
    mentions, ctx, report = run
    assert report.doc_type["TEXT"] == "21/21" and report.doc_type["wrong"] == []
    assert report.duplicates == {"duplicate_files": 1, "flagged": 1, "mentions_from_duplicates": 0}
    assert set(mentions["source_type"]) == {"PDF"}
    assert not mentions["person_role"].isna().any()


def test_business_ids_and_orgs_are_excluded(run):
    _, ctx, report = run
    exc = report.exclusions.set_index("kind")
    assert exc.loc["ORG", "correct"] == 1
    for kind in ("EIN", "NPI", "PROVIDER_TIN"):
        assert exc.loc[kind, "precision"] == 1.0, kind
    assert not ctx.tables["excluded_entities"].empty


def test_raw_values_stay_in_transient_columns(run):
    mentions, _, _ = run
    for col in ("ssn", "dl", "passport", "member_id", "ssn_present"):
        assert col not in mentions.columns  # presence/masking columns arrive in M4
    assert {"_raw_ssn", "_raw_member_id"} <= set(mentions.columns)


@pytest.mark.tesseract
def test_scans_are_processed_and_reported(run):
    _, ctx, report = run
    assert ctx.tables["pdf_summary"]["ocr"] == 9
    assert report.doc_type["OCR"] == "9/9"
    for field in AC_FIELDS:
        assert _recall(report, field, "OCR") >= 0.8, field
