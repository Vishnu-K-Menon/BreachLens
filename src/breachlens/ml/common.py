"""Shared ML helpers: reproducibility, macro-F1, reliability (calibration) curves."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import f1_score

SEED = 0


def macro_f1(y_true: list[str], y_pred: list[str]) -> float:
    labels = sorted(set(y_true))
    return float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0))


def reliability(conf: np.ndarray, correct: np.ndarray, bins: int = 10) -> tuple[list[dict], float]:
    """Per-bin mean confidence vs accuracy, and the expected calibration error (ECE)."""
    edges = np.linspace(0, 1, bins + 1)
    rows, ece = [], 0.0
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (conf > lo) & (conf <= hi) if lo > 0 else (conf >= lo) & (conf <= hi)
        if not m.any():
            continue
        acc, mc = float(correct[m].mean()), float(conf[m].mean())
        ece += m.sum() / len(conf) * abs(acc - mc)
        rows.append(
            {
                "bin": f"{lo:.1f}-{hi:.1f}",
                "n": int(m.sum()),
                "confidence": round(mc, 4),
                "accuracy": round(acc, 4),
            }
        )
    return rows, round(float(ece), 4)
