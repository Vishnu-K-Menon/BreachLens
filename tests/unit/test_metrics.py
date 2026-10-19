"""Field precision/recall counting of evaluate/metrics.py (M7) on hand-made cases."""

import pandas as pd

from breachlens.evaluate.metrics import count_fields, micro, render


def checks(gt, ex):
    """Toy checker: fields present in the truth row, correct when the values match."""
    out = {}
    for f in ("dob", "zip5"):
        if gt.get(f):
            got = "" if ex is None else (ex.get(f) or "")
            out[f] = (got == gt[f], gt[f], got)
    return out


COLS = {"dob": "dob", "zip5": "zip5"}


def test_tp_fp_fn_counting():
    s = pd.Series
    pairs = [
        ("T", s({"dob": "1980-01-01", "zip5": "02134"}), s({"dob": "1980-01-01", "zip5": "02134"})),
        ("T", s({"dob": "1980-01-01", "zip5": ""}), s({"dob": "1980-02-01", "zip5": "10001"})),
        ("T", s({"dob": "1990-05-05", "zip5": "07102"}), None),  # missed mention
        ("T", None, s({"dob": "2000-01-01", "zip5": ""})),  # extracted, not in truth
    ]
    f = count_fields(pairs, checks, COLS).set_index("field")
    # dob: TP 1; wrong value = FN + FP; missed = FN; spurious mention = FP
    assert f.loc["dob", ["tp", "fp", "fn"]].tolist() == [1, 2, 2]
    # zip5: TP 1; a value where the truth has none = FP; missed = FN
    assert f.loc["zip5", ["tp", "fp", "fn"]].tolist() == [1, 1, 1]
    assert f.loc["dob", "precision"] == round(1 / 3, 4) and f.loc["dob", "recall"] == round(
        1 / 3, 4
    )
    m = micro(f.reset_index())
    assert m["T"]["tp"] == 2 and m["T"]["fp"] == 3 and m["T"]["fn"] == 3


def test_render_shows_both_corpora_side_by_side():
    corpus = {
        "mentions": 10,
        "people": 5,
        "collapse_ratio": 2.0,
        "notification": {
            "listed": 3,
            "truth": 3,
            "missed": 0,
            "extra": 0,
            "by_state_truth": {"MA": 3},
            "by_state_listed": {"MA": 3},
        },
        "matching": {
            "precision": 1.0,
            "recall": 0.9,
            "f1": 0.947,
            "shared_address_merged": 0,
            "shared_address_pairs": 4,
            "cases": [{"case": "P18 twins not merged", "ok": True}],
        },
        "address": {
            "agree": 9,
            "total": 10,
            "accuracy": 0.9,
            "confusion": {"VERIFIED->VERIFIED": 9},
        },
        "planted_validation": {"caught": 4, "tagged": 4},
        "planted_spreadsheet": {"handled": 2, "total": 2},
        "column_mapping": {k: {"accuracy": 1.0, "macro_f1": 1.0} for k in ("rules", "ml", "final")},
        "throughput": {
            "total_seconds": 1.5,
            "stages": [{"stage": "pdf_track", "seconds": 1.5, "rows": 10}],
        },
        "fields": [],
        "fields_by_track": {"SPREADSHEET": {"precision": 1.0, "recall": 1.0, "f1": 1.0}},
    }
    text = render(
        {"generated_at": "t", "corpora": {"dev": corpus, "holdout": corpus}, "scale": None}
    )
    assert "| metric | dev | holdout |" in text
    assert (
        "| notification list vs truth | 3/3 (missed 0, extra 0) | 3/3 (missed 0, extra 0) |" in text
    )
    assert "| P18 twins not merged | yes | yes |" in text
