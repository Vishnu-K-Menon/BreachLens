"""Pipeline metrics against ground truth (M7): `metrics.json` + `METRICS.md`.

Run:  breachlens evaluate pipeline [--input DOCS --truth TRUTH]

The pipeline runs in memory, one timed stage at a time (offline: Census results come
from the cache). Extraction is scored right after `pdf_track` / `sheet_track`, while the
transient raw values still exist; everything else is scored on the final output. By
default corpus_v1 (dev) is evaluated, plus the seed-43 holdout when its truth exists, so
METRICS.md shows tuned and untuned numbers side by side.

Field precision/recall/F1 per track reuse the field checks of `evaluate/extraction.py`
(PDF) and `evaluate/sheets.py` (spreadsheets):
- TP: the field is in the truth and extracted correctly
- FN: the field is in the truth and missing or wrong
- FP: a wrong value, a value where the truth has none, or a field on an extracted
  mention that matches no truth mention

Only counts and rates are written; no values. Outputs go through the guarded writer.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from breachlens.evaluate import extraction, resolution, sheets, validation
from breachlens.evaluate.extraction import read_truth_csv

# field -> mention column whose non-empty value means "the pipeline extracted this field"
PDF_FIELD_COLUMNS = {
    "name": "raw_name",
    "dob": "dob",
    "ssn_present": "_raw_ssn",
    "ssn_value": "_raw_ssn",
    "line1": "raw_address",
    "city": "raw_address",
    "state": "raw_address",
    "zip5": "raw_address",
    "member_id": "_raw_member_id",
    "dl": "_raw_dl",
    "dl_state": "dl_state",
    "passport": "_raw_passport",
    "procedure": "_raw_procedure",
    "date_of_service": "_raw_date_of_service",
    "phone": "phone",
    "email": "email",
    "diagnosis": "_raw_diagnosis",
}
SHEET_FIELD_COLUMNS = {
    "name": "raw_name",
    "dob": "dob",
    "ssn_present": "_raw_ssn",
    "ssn_value": "_raw_ssn",
    "line1": "address_line1",
    "city": "city",
    "state": "state",
    "zip5": "zip5",
    "card": "_raw_card",
    "mrn": "_raw_mrn",
    "member_id": "_raw_member_id",
    "group_number": "_raw_group_number",
    "employee_id": "_raw_employee_id",
    "student_id": "_raw_student_id",
    "bank_account": "_raw_bank_account",
    "routing": "_raw_routing",
    "email": "email",
    "phone": "phone",
}
Checks = Callable[[pd.Series, pd.Series | None], dict[str, tuple[bool, str, str]]]


def _has(ex: pd.Series | None, col: str) -> bool:
    if ex is None:
        return False
    v = ex.get(col)
    return v is not None and not (isinstance(v, float) and pd.isna(v)) and str(v).strip() != ""


def count_fields(
    pairs: list[tuple[str, pd.Series | None, pd.Series | None]],
    checks: Checks,
    field_columns: dict[str, str],
) -> pd.DataFrame:
    """TP/FP/FN per (track, field) over (track, truth, extracted) pairs; either side may be
    None (a missed truth mention, or an extracted mention with no truth)."""
    acc: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
    for track, gt, ex in pairs:
        result = checks(gt, ex) if gt is not None else {}
        for f, (ok, _, _) in result.items():
            c = acc[(track, f)]
            if ok:
                c[0] += 1
            else:
                c[2] += 1
                if _has(ex, field_columns.get(f, f)):
                    c[1] += 1  # a wrong value is also a false positive
        for f, col in field_columns.items():
            if f not in result and _has(ex, col):
                acc[(track, f)][1] += 1
    rows = []
    for (track, f), (tp, fp, fn) in sorted(acc.items()):
        p = tp / (tp + fp) if tp + fp else None
        r = tp / (tp + fn) if tp + fn else None
        f1 = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
        rows.append(
            {
                "track": track,
                "field": f,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": None if p is None else round(p, 4),
                "recall": None if r is None else round(r, 4),
                "f1": None if f1 is None else round(f1, 4),
            }
        )
    return pd.DataFrame(
        rows, columns=["track", "field", "tp", "fp", "fn", "precision", "recall", "f1"]
    )


def pdf_pairs(mentions: pd.DataFrame, tables: dict[str, Any], truth: Path) -> list:
    gt = read_truth_csv(truth / "gt_mentions.csv")
    gt = gt[(gt["source_type"] == "PDF") & (gt["entity_type"] == "PERSON")]
    method = tables["inventory"].set_index("doc_id")["extraction_method"]
    ex = mentions[mentions["source_type"] == "PDF"]
    ex_by = {(r["doc_id"], r["person_role"]): r for _, r in ex.iterrows()}
    out, seen = [], set()
    for _, g in gt.iterrows():
        k = (g["doc_id"], g["person_role"])
        seen.add(k)
        out.append((f"PDF-{method.get(g['doc_id'], '?')}", g, ex_by.get(k)))
    for k, e in ex_by.items():
        if k not in seen:
            out.append((f"PDF-{method.get(k[0], '?')}", None, e))
    return out


def _keyed(df: pd.DataFrame, sheet: str, row: str, role: str) -> dict[tuple, pd.Series]:
    """The spreadsheet match key of `evaluate/sheets.py`: (doc, sheet, row, role, order)."""
    out: dict[tuple, pd.Series] = {}
    counter: dict[tuple, int] = defaultdict(int)
    for _, r in df.iterrows():
        s = r[sheet]
        k = (r["doc_id"], "" if pd.isna(s) else str(s), int(float(r[row])), r[role])
        out[(*k, counter[k])] = r
        counter[k] += 1
    return out


def sheet_pairs(mentions: pd.DataFrame, truth: Path) -> list:
    gt = read_truth_csv(truth / "gt_mentions.csv")
    gt = gt[
        (gt["source_type"] == "SPREADSHEET")
        & (gt["entity_type"] == "PERSON")
        & (gt["duplicate_of_row"] == "")
    ]
    g_map = _keyed(gt, "sheet", "row", "person_role")
    e_map = _keyed(
        mentions[mentions["source_type"] == "SPREADSHEET"],
        "source_sheet",
        "source_row",
        "person_role",
    )
    out = [("SPREADSHEET", g, e_map.get(k)) for k, g in g_map.items()]
    out += [("SPREADSHEET", None, e) for k, e in e_map.items() if k not in g_map]
    return out


def micro(fields: pd.DataFrame) -> dict[str, dict[str, Any]]:
    out = {}
    for track, g in fields.groupby("track"):
        tp, fp, fn = int(g["tp"].sum()), int(g["fp"].sum()), int(g["fn"].sum())
        p = tp / (tp + fp) if tp + fp else 1.0
        r = tp / (tp + fn) if tp + fn else 1.0
        out[str(track)] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
        }
    return out


def evaluate_corpus(
    config: Path, input_dir: Path | None, truth: Path, models_dir: Path | None = None
) -> dict[str, Any]:
    """Run the pipeline in memory on one corpus and score it."""
    from dataclasses import replace

    from breachlens.pipeline import enabled_stages, load_context

    ctx = load_context(config, input_dir=input_dir)
    if models_dir is not None:
        ctx.paths = replace(ctx.paths, models_dir=models_dir)
    df = pd.DataFrame()
    stages, pairs = [], []
    sheet_eval: dict[str, Any] = {}
    pdf_report = None
    for name, stage in enabled_stages(ctx.config):
        t0 = time.perf_counter()
        df = stage(df, ctx)
        sec = time.perf_counter() - t0
        stages.append(
            {
                "stage": name,
                "seconds": round(sec, 2),
                "rows": len(df),
                "rows_per_sec": round(len(df) / sec, 1) if sec > 0 else None,
            }
        )
        if name == "pdf_track":
            pdf_report = extraction.evaluate(df, ctx.tables, truth)
            pairs.append(("pdf", pdf_pairs(df, ctx.tables, truth)))
        elif name == "sheet_track":
            sheet_eval = sheets.evaluate(df, ctx.tables, truth)
            pairs.append(("sheet", sheet_pairs(df, truth)))
    fields = pd.concat(
        [
            count_fields(
                p,
                extraction.field_checks if kind == "pdf" else sheets.checks,
                PDF_FIELD_COLUMNS if kind == "pdf" else SHEET_FIELD_COLUMNS,
            )
            for kind, p in pairs
        ],
        ignore_index=True,
    )
    val = validation.evaluate(df, ctx.tables, ctx.audit.events, truth)
    res = resolution.evaluate(df, ctx.tables, truth)
    manifest = json.loads((truth / "manifest.json").read_text(encoding="utf-8"))
    people = ctx.tables["people"]
    a, n = res["address"], res["notify"]
    planted_sheets = sheet_eval.get("planted", [])
    return {
        "run_id": ctx.run_id,
        "corpus": manifest.get("version"),
        "seed": manifest.get("seed"),
        "as_of_date": str(ctx.as_of_date),
        "mentions": len(df),
        "people": len(people),
        "collapse_ratio": round(len(df) / max(len(people), 1), 2),
        "fields": fields.to_dict("records"),
        "fields_by_track": micro(fields),
        "pdf": {
            "mentions": pdf_report.mentions if pdf_report else {},
            "doc_type": pdf_report.doc_type if pdf_report else {},
        },
        "column_mapping": {k: sheet_eval["mapping"][k] for k in ("rules", "ml", "final")}
        if sheet_eval
        else {},
        "planted_spreadsheet": {
            "handled": sum(bool(p["handled"]) for p in planted_sheets),
            "total": len(planted_sheets),
        },
        "planted_validation": {
            "caught": sum(p["caught"] for p in val["planted"]),
            "tagged": sum(p["tagged"] for p in val["planted"]),
        },
        "qc_status": {str(k): int(v) for k, v in val["qc"].items()},
        "matching": {
            **res["pairwise"],
            "f1": _f1(res["pairwise"]["precision"], res["pairwise"]["recall"]),
            "cases": [{"case": c["case"], "ok": bool(c["ok"])} for c in res["cases"]],
            "shared_address_pairs": res["shared"]["pairs"],
            "shared_address_merged": len(res["shared"]["merged"]),
            "gray_zone_pairs": res["gray_pairs"],
            "people_predicted": res["people"]["predicted"],
            "people_truth": res["people"]["truth"],
        },
        "address": {
            "agree": a["agree"],
            "total": a["total"],
            "accuracy": round(a["agree"] / max(a["total"], 1), 4),
            "expected_distribution": a["manifest_mentions"],
            "confusion": {f"{x}->{y}": int(v) for (x, y), v in sorted(a["confusion"].items())},
        },
        "notification": {
            "listed": n["listed"],
            "truth": n["expected"],
            "true_positive": n["tp"],
            "missed": len(n["fn"]),
            "extra": len(n["fp"]),
            "by_state_truth": n["by_state_exp"],
            "by_state_listed": n["by_state_got"],
            "needs_review": n["needs_review"],
        },
        "throughput": {
            "stages": stages,
            "total_seconds": round(sum(s["seconds"] for s in stages), 2),
        },
    }


def _f1(p: float, r: float) -> float:
    return round(2 * p * r / (p + r), 4) if p + r else 0.0


def latest_scale_report(output_dir: Path) -> dict[str, Any] | None:
    reports = sorted(output_dir.glob("R*/scale_report.json"))
    if not reports:
        return None
    r = json.loads(reports[-1].read_text(encoding="utf-8"))
    return {
        "rows": r.get("rows"),
        "total_seconds": r.get("total_seconds"),
        "rows_per_sec_end_to_end": r.get("rows_per_sec_end_to_end"),
        "source": reports[-1].parent.name,
    }


def classifier_summary(models_dir: Path) -> dict[str, Any]:
    p = models_dir / "column_classifier_metrics.json"
    if not p.is_file():
        return {}
    m = json.loads(p.read_text(encoding="utf-8"))
    chosen = m["chosen_model"]
    return {
        "chosen_model": chosen,
        "hard_test_macro_f1": m["hard_test_macro_f1"].get(chosen, {}),
        "hard_test_macro_f1_rules_only": m["hard_test_macro_f1"].get("R", {}),
    }


# ---- METRICS.md -------------------------------------------------------------------
def _pct(v: Any) -> str:
    return "n/a" if v is None else f"{v:.3f}"


def render(m: dict[str, Any]) -> str:
    sets = m["corpora"]
    names = list(sets)
    head = "| metric | " + " | ".join(names) + " |"
    sep = "|---|" + "---|" * len(names)

    def row(label: str, get: Callable[[dict], Any]) -> str:
        cells = []
        for k in names:
            try:
                cells.append(str(get(sets[k])))
            except (KeyError, TypeError):
                cells.append("n/a")
        return f"| {label} | " + " | ".join(cells) + " |"

    L = [
        "# METRICS.md: BreachLens pipeline metrics (SYNTHETIC DATA)",
        "",
        f"Generated {m['generated_at']} by `breachlens evaluate pipeline` (ADR-068). "
        "corpus_v1 is the dev corpus (tuned on); the seed-43 holdout is untuned.",
        "",
        "## Headline",
        "",
        head,
        sep,
        row("mentions / people", lambda s: f"{s['mentions']} / {s['people']}"),
        row("collapse ratio (mentions per person)", lambda s: s["collapse_ratio"]),
        row(
            "notification list vs truth",
            lambda s: (
                f"{s['notification']['listed']}/{s['notification']['truth']} "
                f"(missed {s['notification']['missed']}, extra {s['notification']['extra']})"
            ),
        ),
        row(
            "matching pairwise P / R / F1",
            lambda s: (
                f"{s['matching']['precision']} / {s['matching']['recall']} / {s['matching']['f1']}"
            ),
        ),
        row(
            "shared-address pairs merged",
            lambda s: (
                f"{s['matching']['shared_address_merged']}/{s['matching']['shared_address_pairs']}"
            ),
        ),
        row(
            "address status vs expected (ADR-050)",
            lambda s: (
                f"{s['address']['agree']}/{s['address']['total']} = {s['address']['accuracy']}"
            ),
        ),
        row(
            "planted validation cases caught",
            lambda s: f"{s['planted_validation']['caught']}/{s['planted_validation']['tagged']}",
        ),
        row(
            "planted spreadsheet cases handled",
            lambda s: f"{s['planted_spreadsheet']['handled']}/{s['planted_spreadsheet']['total']}",
        ),
        row(
            "column mapping final accuracy / macro-F1",
            lambda s: (
                f"{s['column_mapping']['final']['accuracy']} / "
                f"{s['column_mapping']['final']['macro_f1']}"
            ),
        ),
        row("pipeline seconds (in memory)", lambda s: s["throughput"]["total_seconds"]),
    ]
    for track in sorted({t for s in sets.values() for t in s["fields_by_track"]}):
        L.append(
            row(
                f"fields {track} micro P / R / F1",
                lambda s, t=track: (
                    f"{s['fields_by_track'][t]['precision']} / "
                    f"{s['fields_by_track'][t]['recall']} / {s['fields_by_track'][t]['f1']}"
                ),
            )
        )
    L += ["", "## Matching cases", "", head, sep]
    cases = [c["case"] for c in sets[names[0]]["matching"]["cases"]]
    for c in cases:
        L.append(
            row(
                c,
                lambda s, c=c: next(
                    ("yes" if x["ok"] else "NO") for x in s["matching"]["cases"] if x["case"] == c
                ),
            )
        )
    L += ["", "## Notification by state (listed / truth)", "", head, sep]
    states = sorted({st for s in sets.values() for st in s["notification"]["by_state_truth"]})
    for st in states:
        L.append(
            row(
                st,
                lambda s, st=st: (
                    f"{s['notification']['by_state_listed'].get(st, 0)} / "
                    f"{s['notification']['by_state_truth'].get(st, 0)}"
                ),
            )
        )
    for k in names:
        s = sets[k]
        L += [
            "",
            f"## Field precision / recall / F1: {k}",
            "",
            "| track | field | TP | FP | FN | precision | recall | F1 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        L += [
            f"| {f['track']} | {f['field']} | {f['tp']} | {f['fp']} | {f['fn']} | "
            f"{_pct(f['precision'])} | {_pct(f['recall'])} | {_pct(f['f1'])} |"
            for f in s["fields"]
        ]
    cm = m.get("column_classifier") or {}
    if cm:
        L += [
            "",
            "## Column classifier (models/column_classifier_metrics.json)",
            "",
            f"Chosen model `{cm['chosen_model']}`. Macro-F1 on the hard tests:",
            "",
            "| test set | chosen model | rules only |",
            "|---|---|---|",
        ]
        for t, v in cm["hard_test_macro_f1"].items():
            L.append(f"| {t} | {v} | {cm['hard_test_macro_f1_rules_only'].get(t, 'n/a')} |")
        L += ["", head, sep]
        for mapper in ("rules", "ml", "final"):
            L.append(
                row(
                    f"spreadsheet columns, {mapper}: accuracy / macro-F1",
                    lambda s, mp=mapper: (
                        f"{s['column_mapping'][mp]['accuracy']} / "
                        f"{s['column_mapping'][mp]['macro_f1']}"
                    ),
                )
            )
    L += ["", "## Address status: expected -> got (mentions)", ""]
    for k in names:
        conf = sets[k]["address"]["confusion"]
        L.append(f"- {k}: " + ", ".join(f"{x} {v}" for x, v in conf.items()))
    L += ["", "## Throughput", "", "| stage | " + " | ".join(names) + " |", sep]
    for st in [x["stage"] for x in sets[names[0]]["throughput"]["stages"]]:
        L.append(
            row(
                st,
                lambda s, st=st: next(
                    f"{x['seconds']} s ({x['rows']} rows)"
                    for x in s["throughput"]["stages"]
                    if x["stage"] == st
                ),
            )
        )
    sc = m.get("scale")
    if sc:
        L += [
            "",
            f"Scale test (latest `scale_report.json`, {sc['source']}): {sc['rows']:,} rows in "
            f"{sc['total_seconds']} s = {sc['rows_per_sec_end_to_end']:,.0f} rows/s end to end.",
        ]
    return "\n".join(L) + "\n"


def runs_row(m: dict[str, Any]) -> dict[str, Any]:
    first = next(iter(m["corpora"].values()))
    return {
        "generated_at": m["generated_at"],
        "run_id": first["run_id"],
        "corpus": first["corpus"],
        "mentions": first["mentions"],
        "people": first["people"],
        "notified": first["notification"]["listed"],
        "notify_truth": first["notification"]["truth"],
        "pairwise_precision": first["matching"]["precision"],
        "pairwise_recall": first["matching"]["recall"],
        "address_accuracy": first["address"]["accuracy"],
        "planted_caught": first["planted_validation"]["caught"],
        "planted_tagged": first["planted_validation"]["tagged"],
        "seconds": first["throughput"]["total_seconds"],
    }


def main(
    config: Path,
    corpora: dict[str, tuple[Path | None, Path]],
    out_dir: Path,
    models_dir: Path,
    output_dir: Path,
    guard: Any,
) -> tuple[dict[str, Any], list[Path]]:
    from breachlens.privacy.writer import GuardedWriter

    m: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "corpora": {
            name: evaluate_corpus(config, inp, truth, models_dir)
            for name, (inp, truth) in corpora.items()
        },
        "column_classifier": classifier_summary(models_dir),
        "scale": latest_scale_report(output_dir),
    }
    w = GuardedWriter(guard, out_dir)
    paths = [w.write_json(m, "metrics.json")]
    paths.append(w.write_text(render(m), "METRICS.md"))
    runs = out_dir / "runs.csv"
    hist = pd.read_csv(runs, dtype=str) if runs.is_file() else pd.DataFrame()
    hist = pd.concat([hist, pd.DataFrame([runs_row(m)]).astype(str)], ignore_index=True)
    paths.append(w.write_csv(hist, "runs.csv"))
    return m, paths
