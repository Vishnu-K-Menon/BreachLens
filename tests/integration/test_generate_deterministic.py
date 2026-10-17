"""Full corpus generation on a reduced config (fewer column-corpus tables, a small scale
file, low-dpi scans): run twice and require byte-identical ground truth, plus the M1
acceptance checks on the result."""

import csv
import json
from dataclasses import replace
from pathlib import Path

import pytest

from breachlens.synth.generate import generate_corpus
from breachlens.synth.ground_truth import PLANTED_CASES
from breachlens.synth.settings import load_synth_settings

ROOT = Path(__file__).resolve().parents[2]


def _reduced():
    s = load_synth_settings(ROOT / "config")
    c = s.config
    cfg = c.model_copy(
        update={
            "column_corpus": c.column_corpus.model_copy(update={"tables": 6, "max_rows": 40}),
            "scale": c.scale.model_copy(update={"large_claims_rows": 100}),
            "pdf": c.pdf.model_copy(update={"scan": c.pdf.scan.model_copy(update={"dpi": 72})}),
        }
    )
    return replace(s, config=cfg)


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    s = _reduced()
    out = []
    for tag in ("a", "b"):
        root = tmp_path_factory.mktemp(tag)
        out.append(generate_corpus(s, ROOT, root / "raw" / "corpus_v1"))
    return out


pytestmark = pytest.mark.libreoffice


def test_truth_is_byte_identical(runs):
    a, b = (r.out_dir / "truth" for r in runs)
    names = sorted(p.name for p in a.iterdir())
    assert names == sorted(p.name for p in b.iterdir())
    assert names == [
        "gt_columns.csv",
        "gt_excluded.csv",
        "gt_mentions.csv",
        "gt_people.csv",
        "gt_shared_addresses.csv",
        "manifest.json",
    ]
    for name in names:
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


def test_planted_cases_and_counts(runs):
    m = json.loads((runs[0].out_dir / "truth" / "manifest.json").read_text(encoding="utf-8"))
    assert all(m["planted_case_coverage"][c]["count"] >= 1 for c in PLANTED_CASES)
    counts = m["counts"]
    assert counts["pdf_by_type"] == {
        "EOB_LETTER": 8,
        "HEALTH_CLAIM": 8,
        "NEW_HIRE_ID": 6,
        "WAGE_STATEMENT": 8,
    }
    assert counts["pdf_scanned"] == 9 and counts["pdf_exact_duplicates"] == 1
    assert counts["spreadsheets"] == 8
    assert "sheets/vendor_list.xlsx" not in counts["person_mentions_by_file"]
    assert m["overlap"]["people_in_pdf_and_sheet"] >= 12
    assert m["overlap"]["people_in_two_or_more_sheets"] >= 5
    xls = next(f for f in m["files_detail"] if f["file_kind"] == "XLS")
    assert xls["hash_kind"] == "cell_content_sha256"
    assert set(m["expected_address_status"]["people_by_group"]) == {
        "base",
        "extras",
        "household_members",
    }


def test_truth_files_start_with_the_notice(runs):
    truth = runs[0].out_dir / "truth"
    for p in truth.glob("gt_*.csv"):
        assert p.read_text(encoding="utf-8").startswith(
            "# SYNTHETIC GROUND TRUTH - NOT REAL PEOPLE\n"
        )


def test_layout_keeps_truth_and_training_data_out_of_docs(runs):
    out = runs[0].out_dir
    docs = sorted(
        p.relative_to(out / "docs").as_posix() for p in (out / "docs").rglob("*") if p.is_file()
    )
    assert all(d.startswith(("pdf/", "sheets/")) for d in docs) and len(docs) == 39
    assert (out.parent / "column_corpus" / "labels.csv").is_file()
    assert (out.parent / "scale" / "large_claims.csv").is_file()


def test_gt_columns_cover_the_8_corpus_spreadsheets(runs):
    with (runs[0].out_dir / "truth" / "gt_columns.csv").open(encoding="utf-8") as fh:
        fh.readline()
        files = {r["doc_file"] for r in csv.DictReader(fh)}
    assert len(files) == 8 and all(f.startswith("sheets/") for f in files)
