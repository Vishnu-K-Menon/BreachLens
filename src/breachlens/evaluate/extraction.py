"""PDF-track extraction metrics against ground truth (M2 acceptance evidence).

Run:  python -m breachlens.evaluate.extraction --config config/pipeline.yaml \
          --truth data/raw/corpus_v1/truth

Extracted mentions are matched to ground-truth mentions by (doc_id, person_role).
Recall per field = correct / ground-truth mentions that have the field, split by
extraction method (TEXT layer vs OCR). Also: doc-type and doc_date accuracy, exclusion
recall/precision by kind, duplicate skipping (P25) and the worst failures with causes.
Output is printed only; identifiers are masked to their last 4 characters.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

FIELDS = [
    "name",
    "dob",
    "ssn_present",
    "ssn_value",
    "line1",
    "city",
    "state",
    "zip5",
    "member_id",
    "dl",
    "dl_state",
    "passport",
    "diagnosis",
    "procedure",
    "date_of_service",
    "phone",
    "email",
]
AC_FIELDS = ["name", "dob", "ssn_present"]
# which extractor field explains a failure
DIAG_FIELD = {
    "name": ["raw_name", "_last", "_first"],
    "dob": ["dob"],
    "ssn_present": ["_raw_ssn"],
    "ssn_value": ["_raw_ssn"],
    "line1": ["raw_address", "raw_name"],
    "city": ["raw_address"],
    "state": ["raw_address"],
    "zip5": ["raw_address"],
    "member_id": ["_raw_member_id"],
    "dl": ["_raw_dl"],
    "dl_state": ["dl_state"],
    "passport": ["_raw_passport"],
    "diagnosis": ["_raw_diagnosis"],
    "procedure": ["_raw_procedure"],
    "date_of_service": ["date_of_service"],
    "phone": ["phone"],
    "email": ["email"],
}
CSZ = re.compile(r"^(.*?),\s*([A-Z]{2})\s+(\d{4,5})(?:-\d{4})?$")


def read_truth_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, skiprows=1, dtype=str, keep_default_na=False)


def name_tokens(s: str) -> list[str]:
    s = s.upper().replace("' ", "'")
    return re.sub(r"[^A-Z0-9'\- ]", " ", s).split()


def _contains(tokens: list[str], phrase: str) -> bool:
    want = name_tokens(phrase)
    return bool(want) and all(w in tokens for w in want)


def mask(v: str) -> str:
    v = str(v or "")
    return ("*" * max(len(v) - 4, 0) + v[-4:]) if v else "∅"


def split_address(raw: str) -> tuple[str, str, str, str]:
    lines = [ln.strip() for ln in str(raw or "").split("\n") if ln.strip()]
    if not lines:
        return "", "", "", ""
    m = CSZ.match(lines[-1]) if len(lines) > 1 else None
    city, state, zip5 = (m.group(1), m.group(2), m.group(3)) if m else ("", "", "")
    return " ".join(lines[0].upper().split()), city.upper().strip(), state, zip5


def field_checks(gt: pd.Series, ex: pd.Series | None) -> dict[str, tuple[bool, str, str]]:
    """field -> (correct, expected, got) for every field present in ground truth."""
    e = lambda k: "" if ex is None or pd.isna(ex.get(k)) else str(ex.get(k))  # noqa: E731
    out: dict[str, tuple[bool, str, str]] = {}
    line1, city, state, zip5 = split_address(e("raw_address"))
    if gt["exp_first"] or gt["exp_last"]:
        toks = name_tokens(e("raw_name"))
        ok = _contains(toks, gt["exp_first"]) and _contains(toks, gt["exp_last"])
        out["name"] = (ok, f"{gt['exp_first'][:1]}. {gt['exp_last']}", " ".join(toks))
    if gt["exp_dob"]:
        out["dob"] = (e("dob") == gt["exp_dob"], gt["exp_dob"], e("dob"))
    if gt["has_ssn"] == "1":
        out["ssn_present"] = (
            bool(e("_raw_ssn")),
            "present",
            "present" if e("_raw_ssn") else "missing",
        )
        out["ssn_value"] = (e("_raw_ssn") == gt["ssn"], mask(gt["ssn"]), mask(e("_raw_ssn")))
    if gt["exp_line1"]:
        want = " ".join(f"{gt['exp_line1']} {gt['exp_line2']}".split())
        out["line1"] = (line1 == want, want, line1)
        out["city"] = (city == gt["exp_city"], gt["exp_city"], city)
        out["state"] = (state == gt["exp_state"], gt["exp_state"], state)
        out["zip5"] = (zip5 == gt["exp_zip5"], gt["exp_zip5"], zip5)
    simple = {
        "member_id": "_raw_member_id",
        "dl": "_raw_dl",
        "dl_state": "dl_state",
        "passport": "_raw_passport",
        "procedure": "_raw_procedure",
        "date_of_service": "_raw_date_of_service",
        "phone": "phone",
        "email": "email",
    }
    for f, col in simple.items():
        if gt[f]:
            show = mask if f in {"member_id", "dl", "passport"} else (lambda x: x)
            out[f] = (e(col) == gt[f], show(gt[f]), show(e(col)))
    if gt["diagnosis"]:
        got = e("_raw_diagnosis").split(";")
        out["diagnosis"] = (gt["diagnosis"] in got, gt["diagnosis"], e("_raw_diagnosis"))
    return out


@dataclass
class Report:
    recall: pd.DataFrame
    doc_type: dict[str, Any]
    doc_date: dict[str, Any]
    exclusions: pd.DataFrame
    duplicates: dict[str, Any]
    worst: list[dict[str, Any]]
    mentions: dict[str, int]


def evaluate(mentions: pd.DataFrame, tables: dict[str, Any], truth_dir: Path) -> Report:
    import json

    gt = read_truth_csv(truth_dir / "gt_mentions.csv")
    gt = gt[(gt["source_type"] == "PDF") & (gt["entity_type"] == "PERSON")]
    manifest = json.loads((truth_dir / "manifest.json").read_text(encoding="utf-8"))
    inv = tables["inventory"].set_index("doc_id")
    diags = tables.get(
        "pdf_diagnostics", pd.DataFrame(columns=["doc_id", "role", "field", "status"])
    )
    ex = mentions[mentions["source_type"] == "PDF"].set_index(["doc_id", "person_role"])
    rows, worst = [], []
    for _, g in gt.iterrows():
        key = (g["doc_id"], g["person_role"])
        e = ex.loc[key] if key in ex.index else None
        method = inv.loc[g["doc_id"], "extraction_method"]
        checks = field_checks(g, e)
        failed = []
        for f, (ok, want, got) in checks.items():
            rows.append({"field": f, "method": method, "ok": ok})
            if not ok:
                d = diags[
                    (diags["doc_id"] == g["doc_id"])
                    & (diags["role"].isin([g["person_role"], "INSURED"]))
                    & (diags["field"].isin(DIAG_FIELD[f]))
                ]
                status = (
                    "MENTION_MISSING"
                    if e is None
                    else (",".join(sorted(set(d["status"]) - {"OK"})) or "VALUE_MISMATCH")
                )
                failed.append({"field": f, "cause": status, "expected": want, "got": got})
        if failed:
            worst.append(
                {
                    "doc_id": g["doc_id"],
                    "doc_file": g["doc_file"],
                    "role": g["person_role"],
                    "method": method,
                    "planted": g["planted_case"],
                    "failed": failed,
                }
            )
    df = pd.DataFrame(rows)
    recall = (
        df.groupby(["field", "method"])["ok"]
        .agg(["sum", "count"])
        .reset_index()
        .assign(recall=lambda d: (d["sum"] / d["count"]).round(4))
    )
    recall["order"] = recall["field"].map(FIELDS.index)
    recall = recall.sort_values(["order", "method"]).drop(columns="order")

    files = {
        f["doc_id"]: f
        for f in manifest["files_detail"]
        if f["file_kind"] == "PDF" and not f["duplicate_of"]
    }
    dt = [
        (d, inv.loc[d, "doc_type"] == f["doc_type"], inv.loc[d, "extraction_method"])
        for d, f in files.items()
    ]
    dd = [
        (
            d,
            (inv.loc[d, "doc_date"] or "") == (f["doc_date"] or ""),
            inv.loc[d, "extraction_method"],
        )
        for d, f in files.items()
    ]

    def acc(items: list[tuple[str, bool, str]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for m in ("TEXT", "OCR"):
            sub = [ok for _, ok, mm in items if mm == m]
            out[m] = f"{sum(sub)}/{len(sub)}"
        out["wrong"] = [d for d, ok, _ in items if not ok]
        return out

    gx = read_truth_csv(truth_dir / "gt_excluded.csv")
    gx = gx[gx["doc_file"].str.startswith("pdf/")]
    digits = lambda s: re.sub(r"\D", "", str(s))  # noqa: E731
    want = {
        (r.doc_id, r.kind, digits(r.value) if r.kind != "ORG" else r.value.upper())
        for r in gx.itertuples()
    }
    got: set[tuple[str, str, str]] = set()
    xi, xe = tables.get("excluded_identifiers"), tables.get("excluded_entities")
    if xi is not None and not xi.empty:
        got |= {
            (d, k, digits(v))
            for d, k, v in zip(xi["doc_id"], xi["kind"], xi["_raw_value"], strict=True)
        }
    if xe is not None and not xe.empty:
        got |= {
            (d, "ORG", str(v).upper())
            for d, v in zip(xe["doc_id"], xe["value_masked"], strict=True)
        }
    for doc_id, kind, value in sorted(want - got):  # missed exclusions are failures too
        worst.append(
            {
                "doc_id": doc_id,
                "doc_file": gx.loc[gx["doc_id"] == doc_id, "doc_file"].iloc[0],
                "role": "EXCLUSION",
                "method": inv.loc[doc_id, "extraction_method"],
                "planted": "",
                "failed": [
                    {"field": kind, "cause": "NOT_EXCLUDED", "expected": mask(value), "got": "∅"}
                ],
            }
        )
    exc_rows = []
    for kind in sorted({k for _, k, _ in want | got}):
        w = {x for x in want if x[1] == kind}
        g2 = {x for x in got if x[1] == kind}
        exc_rows.append(
            {
                "kind": kind,
                "expected": len(w),
                "found": len(g2),
                "correct": len(w & g2),
                "recall": round(len(w & g2) / len(w), 4) if w else None,
                "precision": round(len(w & g2) / len(g2), 4) if g2 else None,
            }
        )
    dups = {d: v for d, v in manifest["duplicate_files"].items()}
    dup_ids = [f["doc_id"] for f in manifest["files_detail"] if f["duplicate_of"]]
    duplicates = {
        "duplicate_files": len(dups),
        "flagged": int(inv.loc[dup_ids, "is_exact_duplicate"].sum()) if dup_ids else 0,
        "mentions_from_duplicates": int(mentions["doc_id"].isin(dup_ids).sum()),
    }
    gt_keys = set(zip(gt["doc_id"], gt["person_role"], strict=True))
    ex_keys = set(ex.index)
    worst.sort(key=lambda w: (-len(w["failed"]), w["doc_id"]))
    return Report(
        recall=recall,
        doc_type=acc(dt),
        doc_date=acc(dd),
        exclusions=pd.DataFrame(exc_rows),
        duplicates=duplicates,
        worst=worst[:5],
        mentions={
            "ground_truth": len(gt_keys),
            "extracted": len(ex_keys),
            "matched": len(gt_keys & ex_keys),
            "missing": len(gt_keys - ex_keys),
            "extra": len(ex_keys - gt_keys),
        },
    )


def _md_table(df: pd.DataFrame) -> str:
    head = "| " + " | ".join(df.columns) + " |"
    sep = "|" + "---|" * len(df.columns)
    body = [
        "| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |"
        for row in df.itertuples(index=False)
    ]
    return "\n".join([head, sep, *body])


def render(report: Report) -> str:
    piv = report.recall.pivot(index="field", columns="method", values=["sum", "count", "recall"])
    lines = [
        "## PDF extraction recall by field (TEXT layer vs OCR)",
        "",
        "| field | TEXT | OCR |",
        "|---|---|---|",
    ]
    for f in [f for f in FIELDS if f in piv.index]:
        cells = []
        for m in ("TEXT", "OCR"):
            try:
                s, c, r = (
                    int(piv.loc[f, ("sum", m)]),
                    int(piv.loc[f, ("count", m)]),
                    piv.loc[f, ("recall", m)],
                )
                cells.append(f"{r:.3f} ({s}/{c})")
            except (KeyError, ValueError):
                cells.append("-")
        star = " **(AC)**" if f in AC_FIELDS else ""
        lines.append(f"| {f}{star} | {cells[0]} | {cells[1]} |")
    lines += [
        "",
        f"Mentions: {report.mentions}",
        f"Doc type accuracy: {report.doc_type}",
        f"doc_date accuracy: {report.doc_date}",
        f"Duplicates: {report.duplicates}",
        "",
        "## Exclusions (EIN / NPI / provider TIN / ORG)",
        "",
        _md_table(report.exclusions),
        "",
        "## Worst failures (top 5 mentions by failed fields)",
        "",
    ]
    for i, w in enumerate(report.worst, start=1):
        planted = w["planted"] or "-"
        lines.append(
            f"{i}. {w['doc_id']} `{w['doc_file']}` {w['role']} ({w['method']}, planted {planted})"
        )
        for f in w["failed"]:
            lines.append(
                f"   - {f['field']}: {f['cause']} (expected `{f['expected']}`, got `{f['got']}`)"
            )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--config", type=Path, default=Path("config/pipeline.yaml"))
    parser.add_argument("--truth", type=Path, default=Path("data/raw/corpus_v1/truth"))
    parser.add_argument("--input", type=Path, default=None, help="Input docs (overrides config).")
    args = parser.parse_args()
    from breachlens.extract.pdf_track import stage_pdf_track
    from breachlens.pipeline import load_context

    ctx = load_context(args.config, input_dir=args.input.resolve() if args.input else None)
    mentions = stage_pdf_track(pd.DataFrame(), ctx)
    print(render(evaluate(mentions, ctx.tables, args.truth)))


if __name__ == "__main__":
    main()
