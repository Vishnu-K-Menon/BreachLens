"""Leak guard (PRIVACY.md §4, ADR-027, ADR-058).

Unit part: the patterns and their column scope, and the writer refusing to write.
Integration part: generate a corpus (both tracks: text PDFs, scans, all 8
spreadsheets), run the whole pipeline with writes, scan every output file and assert
that no raw identifier from ground truth appears in any output byte.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest

from breachlens.config import LeakGuardConfig
from breachlens.evaluate.extraction import read_truth_csv
from breachlens.privacy.leak_guard import LeakError, LeakGuard, scan_dir
from breachlens.privacy.writer import GuardedWriter

ROOT = Path(__file__).resolve().parents[1]
G = LeakGuard(LeakGuardConfig())


def patterns(df: pd.DataFrame) -> set[str]:
    return {f.pattern for f in G.scan_frame(df, "t")}


@pytest.mark.parametrize(
    "value", ["123-45-6789", "123 45 6789", "123456789", "SSN 123-45-6789 on file"]
)
def test_ssn_like_values_fail(value):
    assert patterns(pd.DataFrame({"note": [value]})) == {"ssn"}


@pytest.mark.parametrize(
    "value", ["02134-1234", "12345-6789", "R20261017-153000-ab12", "***-**-6789", "1234-56-789"]
)
def test_zip4_run_id_and_masks_pass(value):
    assert patterns(pd.DataFrame({"note": [value]})) == set()


def test_card_like_fails_everywhere_not_exempt():
    assert patterns(pd.DataFrame({"city": ["4111111111111111"]})) == {"card"}


def test_account_like_only_in_listed_columns():
    assert patterns(pd.DataFrame({"raw_name": ["ACCT 12345678901"]})) == {"account"}
    assert patterns(pd.DataFrame({"card_masked": ["12345678901"]})) == {"account"}
    assert patterns(pd.DataFrame({"doc_type": ["12345678901"]})) == set()


def test_raw_columns_fail_even_when_empty():
    assert patterns(pd.DataFrame({"_raw_ssn": [None]})) == {"raw_column"}
    assert patterns(pd.DataFrame({"_repair_codes": [""]})) == {"raw_column"}


def test_exempt_columns_and_keys_pass():
    df = pd.DataFrame(
        {
            "phone": ["+12125550123"],
            "zip4": ["1234"],
            "ssn_key": ["1234567890123456"],
            "processed_at": ["2026-10-17T15:30:00123456789"],
            "bytes": [123456789],
        }
    )
    assert patterns(df) == set()


def test_numeric_columns_are_not_scanned():
    assert patterns(pd.DataFrame({"source_row": [123456789]})) == set()


def test_findings_never_carry_the_value():
    f = G.scan_frame(pd.DataFrame({"note": ["123-45-6789"]}), "mentions.csv")[0]
    assert "6789" not in repr(f) and (f.where, f.column, f.row) == ("mentions.csv", "note", 0)


def test_writer_refuses_and_writes_nothing(tmp_path):
    w = GuardedWriter(G, tmp_path / "out")
    with pytest.raises(LeakError):
        w.write_csv(pd.DataFrame({"note": ["123-45-6789"]}), "x.csv")
    with pytest.raises(LeakError):
        w.write_jsonl([{"detail_json": "account 1234567890"}], "a.jsonl")
    with pytest.raises(LeakError):
        w.write_json({"x": "4111111111111111"}, "s.json")
    assert not (tmp_path / "out").exists() or not any((tmp_path / "out").iterdir())
    w.write_csv(pd.DataFrame({"ssn_masked": ["***-**-6789"]}), "ok.csv")
    assert [p.name for p in w.written] == ["ok.csv"]


def test_scan_dir_reads_written_files(tmp_path):
    (tmp_path / "m.csv").write_text(
        "raw_name,phone\nJOHN 123-45-6789,+12125550123\n", encoding="utf-8"
    )
    (tmp_path / "a.jsonl").write_text('{"detail_json": "ok"}\n', encoding="utf-8")
    files, findings = scan_dir(tmp_path, G)
    assert len(files) == 2 and [(f.where, f.pattern) for f in findings] == [("m.csv", "ssn")]


# ---- integration: both tracks, every output file -------------------------------------
TRUTH_ID_COLUMNS = [
    "ssn",
    "dl",
    "passport",
    "bank_account",
    "routing",
    "card",
    "mrn",
    "member_id",
    "group_number",
    "employee_id",
    "student_id",
]


@pytest.fixture(scope="module")
def run(generated_run):
    return generated_run


@pytest.mark.libreoffice
@pytest.mark.tesseract
def test_every_output_file_passes_the_guard(run, capsys):
    ctx, mentions, written, _ = run
    files, findings = scan_dir(ctx.paths.run_dir, G)
    with capsys.disabled():
        print(f"\nleak guard scanned {len(files)} files: " + ", ".join(p.name for p in files))
    assert findings == []
    assert {p.name for p in files} >= {
        "mentions.csv",
        "excluded_identifiers.csv",
        "column_mapping.csv",
        "inventory.csv",
        f"audit_{ctx.run_id}.jsonl",
        "run_summary.json",
    }
    assert set(mentions["source_type"]) == {"PDF", "SPREADSHEET"}
    assert set(mentions["extraction_method"]) >= {"TEXT", "OCR", "SHEET"}


@pytest.mark.libreoffice
@pytest.mark.tesseract
def test_no_raw_truth_identifier_reaches_any_output(run):
    ctx, _, written, truth = run
    blob = "\n".join(p.read_text(encoding="utf-8") for p in written)
    digits = re.sub(r"[^\d\n,;|\"]", "", blob)
    gt = read_truth_csv(truth / "gt_mentions.csv")
    gx = read_truth_csv(truth / "gt_excluded.csv")
    values = {v for c in TRUTH_ID_COLUMNS for v in gt[c] if v} | {
        v for v, k in zip(gx["value"], gx["kind"], strict=True) if k != "ORG"
    }
    leaked = [
        c for c in values if c in blob or (len(d := re.sub(r"\D", "", c)) >= 6 and d in digits)
    ]
    assert len(values) > 100 and leaked == []
