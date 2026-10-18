"""Column-type classifier: training, honest evaluation, model card (ML_MODELS.md §C).

Models compared:
- R     header-alias rules only (`config/header_aliases.yaml`)
- V     value features only, HistGradientBoostingClassifier
- H+V   value features + header char 3-5-gram TF-IDF, as LogisticRegression (scaled,
        class_weight="balanced") and as HistGradientBoostingClassifier; the better one
        by validation macro-F1 is kept, then sigmoid-calibrated (the mapping decision
        uses probability thresholds).

Evaluation:
- validation: GroupKFold(5) on the column corpus, grouped by header alias, so test
  headers are aliases the model never saw
- hard test set: (a) the uninformative-header columns, scored out-of-fold, and (b) the
  8 corpus spreadsheets (`truth/gt_columns.csv`), read through the real reader/layout
  path and never used for training

Outputs (models/): column_classifier.joblib (git-ignored, regenerable), model_card.md,
column_classifier_metrics.json, confusion_matrix.png, reliability.png.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, f1_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from breachlens.ml.common import SEED, macro_f1, reliability
from breachlens.sheets.features import (
    FEATURE_NAMES,
    Lexicons,
    column_features,
    default_lexicons,
    normalize_header,
)
from breachlens.sheets.mapping import rule_label
from breachlens.sheets.settings import AliasCfg, SheetSettings

logger = logging.getLogger(__name__)
MODEL_VERSION = "column-classifier-1"


@dataclass
class ColumnSet:
    X: pd.DataFrame  # FEATURE_NAMES + "header"
    y: list[str]
    groups: list[str]
    kind: list[str]  # ALIAS / UNINFORMATIVE / CORPUS
    raw_headers: list[str]


def _frame(rows: list[dict[str, float]], headers: list[str]) -> pd.DataFrame:
    df = pd.DataFrame(rows).reindex(columns=FEATURE_NAMES).fillna(0.0)
    df["header"] = [normalize_header(h) for h in headers]
    return df


def load_column_corpus(column_dir: Path, as_of: date, lex: Lexicons) -> ColumnSet:
    with (column_dir / "labels.csv").open(encoding="utf-8") as fh:
        fh.readline()
        labels = list(csv.DictReader(fh))
    by_table: dict[str, list[dict[str, str]]] = {}
    for r in labels:
        by_table.setdefault(r["table_id"], []).append(r)
    feats, headers, y, groups, kinds = [], [], [], [], []
    for tid in sorted(by_table):
        with (column_dir / "tables" / f"{tid}.csv").open(encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        body = rows[1:]
        meta = by_table[tid]
        for r in meta:
            j = int(r["col_idx"]) - 1
            col = [row[j] if j < len(row) and row[j] != "" else None for row in body]
            feats.append(
                column_features(r["header_raw"], col, j / max(len(meta) - 1, 1), as_of, lex)
            )
            headers.append(r["header_raw"])
            y.append(r["true_label"])
            groups.append(r["alias_group"])
            kinds.append(r["header_kind"])
    return ColumnSet(_frame(feats, headers), y, groups, kinds, headers)


def load_corpus_sheets(
    docs_dir: Path, truth_dir: Path, s: SheetSettings, as_of: date, lex: Lexicons
) -> ColumnSet:
    """The 8 corpus spreadsheets through the real reader + layout path (hard test set b)."""
    from breachlens.ingest.doc_ids import assign_doc_ids, relative_files
    from breachlens.ingest.inventory import KINDS
    from breachlens.sheets.layout import fix_layout
    from breachlens.sheets.reader import read_file

    with (truth_dir / "gt_columns.csv").open(encoding="utf-8") as fh:
        fh.readline()
        gt = {
            (r["doc_file"], r["sheet"], int(r["col_idx"])): r["true_label"]
            for r in csv.DictReader(fh)
        }
    ids = assign_doc_ids(relative_files(docs_dir))
    feats, headers, y, groups = [], [], [], []
    for rel in sorted({k[0] for k in gt}):
        kind = KINDS[Path(rel).suffix.lower()]
        for sheet in read_file(docs_dir / rel, ids[rel], rel, kind, s.sheets.reader):
            t = fix_layout(sheet, s.sheets.layout)
            if t.skipped:
                continue
            for j, h in enumerate(t.headers):
                key = (rel, sheet.sheet, j + 1)
                if key not in gt:
                    continue
                col = [vals[j] for _, vals in t.rows]
                feats.append(column_features(h, col, j / max(len(t.headers) - 1, 1), as_of, lex))
                headers.append(h)
                y.append(gt[key])
                groups.append(f"CORPUS:{rel}")
    return ColumnSet(_frame(feats, headers), y, groups, ["CORPUS"] * len(y), headers)


def make_models() -> dict[str, Pipeline]:
    tfidf = lambda: TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), max_features=300)  # noqa: E731
    hgb = lambda: HistGradientBoostingClassifier(max_iter=150, learning_rate=0.1, random_state=SEED)  # noqa: E731
    return {
        "V_hgb": Pipeline(
            [("cols", ColumnTransformer([("num", "passthrough", FEATURE_NAMES)])), ("clf", hgb())]
        ),
        "HV_lr": Pipeline(
            [
                (
                    "cols",
                    ColumnTransformer(
                        [("num", StandardScaler(), FEATURE_NAMES), ("hdr", tfidf(), "header")]
                    ),
                ),
                (
                    "clf",
                    LogisticRegression(
                        max_iter=3000, class_weight="balanced", C=2.0, random_state=SEED
                    ),
                ),
            ]
        ),
        "HV_hgb": Pipeline(
            [
                (
                    "cols",
                    ColumnTransformer(
                        [("num", "passthrough", FEATURE_NAMES), ("hdr", tfidf(), "header")],
                        sparse_threshold=0.0,
                    ),
                ),
                ("clf", hgb()),
            ]
        ),
    }


def rules_predict(headers: list[str], aliases: AliasCfg) -> list[str]:
    return [rule_label(h, aliases) or "OTHER" for h in headers]


def oof_predictions(
    model: Pipeline, data: ColumnSet, n_splits: int = 5
) -> tuple[np.ndarray, np.ndarray]:
    """Out-of-fold labels and top-class probabilities (GroupKFold by alias group)."""
    from sklearn.base import clone

    pred = np.empty(len(data.y), dtype=object)
    conf = np.zeros(len(data.y))
    y = np.array(data.y)
    for train, test in GroupKFold(n_splits=n_splits).split(data.X, y, data.groups):
        m = clone(model).fit(data.X.iloc[train], y[train])
        proba = m.predict_proba(data.X.iloc[test])
        pred[test] = m.classes_[proba.argmax(axis=1)]
        conf[test] = proba.max(axis=1)
    return pred, conf


@dataclass
class ColumnClassifier:
    """What gets saved: the calibrated pipeline plus metadata (no raw values)."""

    pipeline: Any
    labels: list[str]
    model_name: str
    version: str = MODEL_VERSION

    def predict(
        self, header: str, values: list, col_pos: float, as_of: date, lex: Lexicons
    ) -> tuple[str, float]:
        X = _frame([column_features(header, values, col_pos, as_of, lex)], [header])
        proba = self.pipeline.predict_proba(X)[0]
        i = int(proba.argmax())
        return str(self.pipeline.classes_[i]), float(proba[i])


def per_label_importance(
    model: Pipeline, data: ColumnSet, top: int = 3
) -> dict[str, list[tuple[str, float]]]:
    """Permutation importance per label on one held-out fold: drop in that label's F1
    when one feature (or the whole header) is shuffled."""
    from sklearn.base import clone

    y = np.array(data.y)
    train, test = next(GroupKFold(n_splits=5).split(data.X, y, data.groups))
    m = clone(model).fit(data.X.iloc[train], y[train])
    Xt, yt = data.X.iloc[test].reset_index(drop=True), y[test]
    labels = sorted(set(yt))
    base = f1_score(yt, m.predict(Xt), labels=labels, average=None, zero_division=0)
    rng = np.random.default_rng(SEED)
    drops: dict[str, list[tuple[str, float]]] = {lab: [] for lab in labels}
    for feat in [*FEATURE_NAMES, "header"]:
        Xp = Xt.copy()
        Xp[feat] = rng.permutation(Xp[feat].to_numpy())
        f = f1_score(yt, m.predict(Xp), labels=labels, average=None, zero_division=0)
        for lab, b, a in zip(labels, base, f, strict=True):
            drops[lab].append((feat, round(float(b - a), 4)))
    return {lab: sorted(v, key=lambda x: -x[1])[:top] for lab, v in drops.items()}


def _plot_confusion(y_true: list[str], y_pred: list[str], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = sorted(set(y_true) | set(y_pred))
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    fig, ax = plt.subplots(figsize=(11, 10))
    ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(labels)), labels, rotation=90, fontsize=7)
    ax.set_yticks(range(len(labels)), labels, fontsize=7)
    for i in range(len(labels)):
        for j in range(len(labels)):
            if cm[i, j]:
                ax.text(
                    j,
                    i,
                    cm[i, j],
                    ha="center",
                    va="center",
                    fontsize=6,
                    color="white" if cm[i, j] > cm.max() / 2 else "black",
                )
    ax.set_xlabel("predicted")
    ax.set_ylabel("true")
    ax.set_title("Column classifier (H+V) on the hard test set - SYNTHETIC DATA")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def _plot_reliability(curves: dict[str, list[dict]], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], "--", color="grey", label="perfect")
    for name, rows in curves.items():
        ax.plot([r["confidence"] for r in rows], [r["accuracy"] for r in rows], "o-", label=name)
    ax.set_xlabel("ml_proba (top class)")
    ax.set_ylabel("accuracy")
    for x in (0.6, 0.7, 0.8):
        ax.axvline(x, color="lightgrey", lw=0.8)
    ax.legend(fontsize=7)
    ax.set_title("Reliability (decision thresholds 0.60/0.70/0.80)")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def train(
    column_dir: Path,
    sheet_sets: dict[str, Path],
    out_dir: Path,
    settings: SheetSettings,
    as_of: date,
) -> dict[str, Any]:
    """Train and evaluate. `sheet_sets` maps a name to a corpus dir whose spreadsheets are
    scored as hard test data, e.g. {"dev_corpus_v1": ..., "test_holdout": ...}."""
    lex = default_lexicons(settings.org_suffixes)
    data = load_column_corpus(column_dir, as_of, lex)
    sets = {
        name: load_corpus_sheets(p / "docs", p / "truth", settings, as_of, lex)
        for name, p in sheet_sets.items()
    }
    logger.info(
        "column corpus: %d columns; sheet sets: %s",
        len(data.y),
        {k: len(v.y) for k, v in sets.items()},
    )
    y = np.array(data.y)
    uninf = np.array([k == "UNINFORMATIVE" for k in data.kind])
    ya = list(y[uninf])
    rules_all = rules_predict(data.raw_headers, settings.aliases)

    models = make_models()
    oof: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    validation = {"R": macro_f1(data.y, rules_all)}
    for name, model in models.items():
        oof[name] = oof_predictions(model, data)
        validation[name] = macro_f1(data.y, list(oof[name][0]))
        logger.info("validation macro-F1 %s = %.4f", name, validation[name])
    best = max(("HV_lr", "HV_hgb"), key=lambda n: validation[n])

    final = CalibratedClassifierCV(
        models[best],
        method="sigmoid",
        cv=list(GroupKFold(n_splits=3).split(data.X, y, data.groups)),
    ).fit(data.X, y)
    raw_v = models["V_hgb"].fit(data.X, y)

    preds: dict[str, dict[str, list[str]]] = {}
    confs: dict[str, np.ndarray] = {}
    for name, cs in sets.items():
        preds[name] = {
            "R": rules_predict(cs.raw_headers, settings.aliases),
            "V_hgb": list(raw_v.predict(cs.X)),
            "HV": list(final.predict(cs.X)),
        }
        confs[name] = final.predict_proba(cs.X).max(axis=1)
    oof_uninf = {
        "R": list(np.array(rules_all)[uninf]),
        "V_hgb": list(oof["V_hgb"][0][uninf]),
        "HV": list(oof[best][0][uninf]),
    }

    hard: dict[str, dict[str, float]] = {}
    for model_key in ("R", "V_hgb", "HV"):
        row: dict[str, float] = {
            "uninformative_headers_oof": round(macro_f1(ya, oof_uninf[model_key]), 4)
        }
        for name, cs in sets.items():
            p = preds[name][model_key]
            row[f"sheets_{name}"] = round(macro_f1(cs.y, p), 4)
            row[f"accuracy_{name}"] = round(float(np.mean(np.array(p) == np.array(cs.y))), 4)
            row[f"combined_{name}"] = round(macro_f1(ya + cs.y, oof_uninf[model_key] + p), 4)
        hard[
            "R"
            if model_key == "R"
            else ("V_hgb" if model_key == "V_hgb" else f"HV ({best}, calibrated)")
        ] = row

    test_name = list(sets)[-1]
    combined_true = ya + sets[test_name].y
    combined_pred = oof_uninf["HV"] + preds[test_name]["HV"]
    labels = sorted(set(combined_true))
    per_label = dict(
        zip(
            labels,
            f1_score(combined_true, combined_pred, labels=labels, average=None, zero_division=0)
            .round(4)
            .tolist(),
            strict=True,
        )
    )
    rel_oof, ece_oof = reliability(oof[best][1], oof[best][0] == y)
    rel_sets = {
        name: reliability(confs[name], np.array(preds[name]["HV"]) == np.array(cs.y))
        for name, cs in sets.items()
    }
    importance = per_label_importance(models[best], data)

    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        ColumnClassifier(final, sorted(set(data.y)), best), out_dir / "column_classifier.joblib"
    )
    _plot_confusion(combined_true, combined_pred, out_dir / "confusion_matrix.png")
    curves = {f"{best} OOF (uncalibrated), ECE {ece_oof}": rel_oof}
    curves |= {f"calibrated, {name}, ECE {rel_sets[name][1]}": rel_sets[name][0] for name in sets}
    _plot_reliability(curves, out_dir / "reliability.png")
    predictions = {
        name: [
            {"header": h, "true": t, "rules": r, "ml": p, "ml_proba": round(float(c), 3)}
            for h, t, r, p, c in zip(
                cs.raw_headers, cs.y, preds[name]["R"], preds[name]["HV"], confs[name], strict=True
            )
        ]
        for name, cs in sets.items()
    }
    metrics = {
        "model_version": MODEL_VERSION,
        "chosen_model": best,
        "data": {
            "train_columns": len(data.y),
            "uninformative_columns": int(uninf.sum()),
            "sheet_columns": {k: len(v.y) for k, v in sets.items()},
            "labels": len(set(data.y)),
        },
        "validation_macro_f1": {k: round(v, 4) for k, v in validation.items()},
        "hard_test_macro_f1": hard,
        "per_label_f1": {"set": f"uninformative OOF + {test_name}", "f1": per_label},
        "calibration": {
            "ece_oof_uncalibrated": ece_oof,
            **{f"ece_{name}_calibrated": rel_sets[name][1] for name in sets},
            "reliability_oof": rel_oof,
            **{f"reliability_{name}": rel_sets[name][0] for name in sets},
        },
        "top_features_per_label": dict(importance),
        "sheet_predictions": predictions,
    }
    (out_dir / "column_classifier_metrics.json").write_text(
        json.dumps(metrics, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "model_card.md").write_text(model_card(metrics, list(sets)), encoding="utf-8")
    return metrics


def model_card(m: dict[str, Any], set_names: list[str]) -> str:
    v, h = m["validation_macro_f1"], m["hard_test_macro_f1"]
    hv = next(k for k in h if k.startswith("HV"))
    cols = [
        "uninformative_headers_oof",
        *[f"sheets_{n}" for n in set_names],
        *[f"combined_{n}" for n in set_names],
    ]
    sets_md = ", ".join(f"`{n}`" for n in set_names)
    lines = [
        "# Model card: column-type classifier (SYNTHETIC DATA)",
        "",
        f"Version `{m['model_version']}`, chosen model `{m['chosen_model']}` (sigmoid-calibrated).",
        "",
        "## Task and data",
        "Predict the semantic label of a spreadsheet column (34 labels, "
        "SPREADSHEET_TRACK.md §4) from its header and values. Training data: the synthetic "
        f"column corpus ({m['data']['train_columns']} columns, "
        "`breachlens.synth.column_corpus`). No real data; no raw values are stored in the "
        "model (value features are aggregate rates; the header TF-IDF vocabulary holds "
        "header n-grams only).",
        "",
        "## Features",
        "Value shape, pattern hit rates (SSN, ZIP, phone, email, dates, Luhn, ABA, state "
        "codes, sci-notation, masks, ID shapes), dictionary rates (first names, surnames, "
        "cities, org suffixes), value statistics and column position; plus header character "
        "3-5-gram TF-IDF (300 features).",
        "",
        "## Evaluation sets",
        "- validation: GroupKFold(5) on the column corpus, grouped by header alias "
        "(unseen aliases)",
        "- uninformative headers (`Column7`, `ID`, blank …): scored out-of-fold",
        f"- spreadsheet sets: {sets_md}, read through the real reader/layout path. "
        "`dev_corpus_v1` was used to diagnose the training-data shift (ADR-055); "
        "`test_holdout` (seed 43) was never inspected before scoring.",
        "",
        "## Results (macro-F1)",
        "",
        "| model | validation | " + " | ".join(cols) + " |",
        "|---|---|" + "---|" * len(cols),
    ]
    for key, label in (
        ("R", "R (header rules)"),
        ("V_hgb", "V (values only, HGB)"),
        (hv, f"H+V ({m['chosen_model']})"),
    ):
        vk = m["chosen_model"] if key == hv else key
        lines.append(f"| {label} | {v[vk]} | " + " | ".join(str(h[key][c]) for c in cols) + " |")
    other = "HV_hgb" if m["chosen_model"] == "HV_lr" else "HV_lr"
    cal = m["calibration"]
    ece_sets = ", ".join(f"{n} {cal[f'ece_{n}_calibrated']}" for n in set_names)
    lines += [
        "",
        f"Validation macro-F1 of the other H+V candidate ({other}): {v[other]}.",
        "",
        "## Calibration",
        f"ECE out-of-fold (uncalibrated) {cal['ece_oof_uncalibrated']}; after sigmoid "
        f"calibration: {ece_sets}. See `reliability.png`; the mapping decision uses "
        "thresholds 0.60 / 0.70 / 0.80 (ADR-034).",
        "",
        "## Limitations",
        "- Synthetic headers and values: dictionary features match the generator's name "
        "lists, which flatters name/city labels. Real exports will be harder.",
        "- All spreadsheet sets come from the same generator family as the training corpus, "
        "and the 8 corpus spreadsheets keep their header templates across seeds: the "
        "holdout tests new values under known layouts. The header-blind test is the "
        "uninformative-header set.",
        "- 34 fixed labels; anything else is OTHER.",
        "",
        "Files: `confusion_matrix.png`, `reliability.png`, `column_classifier_metrics.json` "
        "(per-label F1, top permutation features per label, per-column predictions).",
    ]
    return "\n".join(lines) + "\n"


def load_model(path: Path) -> ColumnClassifier | None:
    if not path.is_file():
        return None
    return joblib.load(path)
