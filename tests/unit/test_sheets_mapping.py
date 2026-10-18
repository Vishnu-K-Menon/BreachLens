from pathlib import Path

import pytest

from breachlens.sheets.mapping import decide, rule_label, unmapped_sensitive
from breachlens.sheets.settings import load_sheet_settings

ROOT = Path(__file__).resolve().parents[2]
S = load_sheet_settings(ROOT / "config")
T = S.thresholds


@pytest.mark.parametrize(
    ("header", "label"),
    [
        ("SSN", "SSN"),
        ("SS#", "SSN"),
        ("Employee SSN", "SSN"),
        ("Date of Birth", "DOB"),
        ("Zip", "ZIP"),
        ("Column7", None),
        ("ID", None),
        ("", None),
    ],
)
def test_rule_labels(header, label):
    assert rule_label(header, S.aliases) == label


@pytest.mark.parametrize(
    ("rule", "ml", "p", "final", "decision", "codes"),
    [
        ("SSN", "SSN", 0.95, "SSN", "AGREE", ()),
        ("SSN", "SSN", 0.40, "SSN", "AGREE", ("COL_MAPPING_AGREE_LOW_PROBA",)),
        (None, "DOB", 0.75, "DOB", "ML_ONLY", ()),
        (None, "DOB", 0.65, "DOB", "REVIEW", ("COL_MAPPING_LOW_CONF",)),
        ("PHONE", "SSN", 0.85, "SSN", "ML_OVERRIDE", ("COL_MAPPING_ML_OVERRIDE",)),
        ("PHONE", "SSN", 0.75, "PHONE", "REVIEW", ("COL_MAPPING_LOW_CONF",)),
        ("DOB", None, None, "DOB", "RULE_ONLY", ()),
        (None, None, None, "OTHER", "REVIEW", ("COL_MAPPING_LOW_CONF",)),
        ("DOB", "OTHER", 0.97, "DOB", "RULE_ONLY", ()),  # ADR-056
    ],
)
def test_decision_table(rule, ml, p, final, decision, codes):
    d = decide(rule, ml, p, T)
    assert (d.final_label, d.decision, d.codes) == (final, decision, codes)


def test_thresholds_come_from_config():
    assert (T.agree_low_proba, T.ml_only_min, T.override_min) == (0.60, 0.70, 0.80)


def test_unmapped_sensitive():
    assert unmapped_sensitive("OTHER", {"ssn_valid": 0.8})
    assert unmapped_sensitive("OTHER", {"luhn_valid": 0.5})
    assert not unmapped_sensitive("SSN", {"ssn_valid": 1.0})
    assert not unmapped_sensitive("OTHER", {"ssn_valid": 0.1})
