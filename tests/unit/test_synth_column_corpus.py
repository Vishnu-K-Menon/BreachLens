import csv
from dataclasses import replace
from pathlib import Path

import pytest

from breachlens.synth.column_corpus import build_column_corpus
from breachlens.synth.settings import load_synth_settings

ROOT = Path(__file__).resolve().parents[2]
ALIASES = ROOT / "config" / "column_corpus_aliases.yaml"


@pytest.fixture(scope="module")
def small():
    s = load_synth_settings(ROOT / "config")
    cc = s.config.column_corpus.model_copy(update={"tables": 12, "max_rows": 60})
    return replace(s, config=s.config.model_copy(update={"column_corpus": cc}))


def _labels(out: Path) -> list[dict[str, str]]:
    with (out / "labels.csv").open(encoding="utf-8") as fh:
        assert fh.readline().startswith("# SYNTHETIC - NOT REAL")
        return list(csv.DictReader(fh))


def test_corpus_shape_and_labels(small, tmp_path):
    stats = build_column_corpus(small, ALIASES, tmp_path)
    rows = _labels(tmp_path)
    assert stats["tables"] == 12 and len(list((tmp_path / "tables").glob("*.csv"))) == 12
    assert stats["columns"] == len(rows)
    for r in rows:
        assert (r["header_kind"] == "UNINFORMATIVE") == r["alias_group"].startswith(
            "UNINFORMATIVE:"
        )
        assert 0.0 <= float(r["null_pct"]) <= 0.96  # complete, partly empty and sparse columns
    with (tmp_path / "tables" / "T0001.csv").open(encoding="utf-8") as fh:
        table = list(csv.reader(fh))
    n_cols = sum(1 for r in rows if r["table_id"] == "T0001")
    assert len(table[0]) == n_cols and len(table) - 1 == int(rows[0]["n_rows"])


def test_corpus_is_deterministic(small, tmp_path):
    a = build_column_corpus(small, ALIASES, tmp_path / "a")
    b = build_column_corpus(small, ALIASES, tmp_path / "b")
    assert a == b
