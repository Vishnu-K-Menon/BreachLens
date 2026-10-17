from dataclasses import replace
from pathlib import Path

from breachlens.synth import identifiers as ids
from breachlens.synth.scale import COLUMNS, flat_records, write_large_claims
from breachlens.synth.settings import load_synth_settings

ROOT = Path(__file__).resolve().parents[2]


def test_flat_records_are_deterministic_and_valid():
    s = load_synth_settings(ROOT / "config")
    a, b = flat_records(200, s), flat_records(200, s)
    assert a == b and len(a) == 200 and list(a[0]) == COLUMNS
    assert all(ids.ssn_valid_shape(r["ssn"]) and r["ssn"] not in s.known_invalid_ssns for r in a)
    assert flat_records(50, s, seed=1) != flat_records(50, s, seed=2)


def test_write_large_claims(tmp_path):
    s = load_synth_settings(ROOT / "config")
    small = replace(
        s,
        config=s.config.model_copy(
            update={"scale": s.config.scale.model_copy(update={"large_claims_rows": 100})}
        ),
    )
    info = write_large_claims(small, tmp_path / "large_claims.csv")
    lines = (tmp_path / "large_claims.csv").read_text(encoding="utf-8").splitlines()
    assert (
        lines[0].startswith("# SYNTHETIC - NOT REAL") and len(lines) == 102 and info["rows"] == 100
    )
