"""Spreadsheet-track metrics against ground truth (M3 acceptance evidence).

Run:  python -m breachlens.evaluate.sheets --config config/pipeline.yaml \
          [--input data/raw/corpus_holdout/docs --truth data/raw/corpus_holdout/truth]

- field recall for spreadsheet person mentions (matched by doc, sheet, row, role, order)
- column mapping vs `gt_columns.csv`: rules, ML and the final decision (accuracy, macro-F1)
- exclusions (ORG names and EINs) and the vendor file's person mentions (P39)
- one handled/flagged check per planted spreadsheet case P27-P44
Prints only; identifiers are masked to their last 4 characters.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd

from breachlens.evaluate.extraction import mask, name_tokens, read_truth_csv
from breachlens.ml.common import macro_f1

FIELDS = [
    "name",
    "dob",
    "ssn_present",
    "ssn_value",
    "line1",
    "city",
    "state",
    "zip5",
    "card",
    "mrn",
    "member_id",
    "group_number",
    "employee_id",
    "student_id",
    "bank_account",
    "routing",
    "phone",
    "email",
]


def _s(v: Any) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


def _digits(v: Any) -> str:
    return re.sub(r"\D", "", _s(v))


def checks(gt: pd.Series, ex: pd.Series | None) -> dict[str, tuple[bool, str, str]]:
    e = lambda k: "" if ex is None else _s(ex.get(k))  # noqa: E731
    out: dict[str, tuple[bool, str, str]] = {}
    toks = name_tokens(e("raw_name"))
    if gt["exp_first"] or gt["exp_last"]:
        ok = all(w in toks for w in name_tokens(gt["exp_first"]) + name_tokens(gt["exp_last"]))
        out["name"] = (ok, f"{gt['exp_first'][:1]}. {gt['exp_last']}", " ".join(toks))
    if gt["exp_dob"]:
        out["dob"] = (e("dob") == gt["exp_dob"], gt["exp_dob"], e("dob"))
    if gt["ssn"]:
        out["ssn_present"] = (
            bool(e("_raw_ssn")),
            "present",
            "present" if e("_raw_ssn") else "missing",
        )
        out["ssn_value"] = (
            _digits(e("_raw_ssn")) == gt["ssn"],
            mask(gt["ssn"]),
            mask(e("_raw_ssn")),
        )
    if gt["exp_line1"]:
        want = (gt["exp_line1"] + gt["exp_line2"]).replace(" ", "").upper()
        got = (e("address_line1") + e("address_line2")).replace(" ", "").upper()
        out["line1"] = (got == want, gt["exp_line1"], e("address_line1"))
        out["city"] = (e("city").upper() == gt["exp_city"], gt["exp_city"], e("city"))
        out["state"] = (e("state") == gt["exp_state"], gt["exp_state"], e("state"))
        out["zip5"] = (e("zip5") == gt["exp_zip5"], gt["exp_zip5"], e("zip5"))
    if gt["card_status"]:
        status = e("_card_status")
        if gt["card_status"] in {"TEXT", "LUHN_FAIL"}:
            ok = _digits(e("_raw_card")) == gt["card"] and status == "TEXT"
        else:
            ok = status == gt["card_status"]
        out["card"] = (
            ok,
            f"{gt['card_status']} {mask(gt['card'])}",
            f"{status} {mask(e('_raw_card'))}",
        )
    simple = {
        "mrn": "_raw_mrn",
        "member_id": "_raw_member_id",
        "group_number": "_raw_group_number",
        "employee_id": "_raw_employee_id",
        "student_id": "_raw_student_id",
        "bank_account": "_raw_bank_account",
        "routing": "_raw_routing",
        "email": "email",
    }
    for f, col in simple.items():
        if gt[f]:
            out[f] = (e(col).strip() == gt[f], mask(gt[f]), mask(e(col)))
    if gt["phone"]:
        out["phone"] = (
            _digits(e("phone"))[-10:] == _digits(gt["phone"])[-10:],
            mask(gt["phone"]),
            mask(e("phone")),
        )
    return out


def _codes(ex: pd.Series | None) -> set[str]:
    return set(_s(None if ex is None else ex.get("_repair_codes")).split(";")) - {""}


def evaluate(mentions: pd.DataFrame, tables: dict[str, Any], truth_dir: Path) -> dict[str, Any]:
    gt = read_truth_csv(truth_dir / "gt_mentions.csv")
    gt = gt[gt["source_type"] == "SPREADSHEET"].copy()
    ex = mentions[mentions["source_type"] == "SPREADSHEET"].copy()
    ex["source_sheet"] = ex["source_sheet"].fillna("")

    def keyed(df: pd.DataFrame, sheet: str, row: str, role: str) -> dict[tuple, pd.Series]:
        out: dict[tuple, pd.Series] = {}
        counter: dict[tuple, int] = defaultdict(int)
        for _, r in df.iterrows():
            k = (r["doc_id"], _s(r[sheet]), int(float(r[row])), r[role])
            out[(*k, counter[k])] = r
            counter[k] += 1
        return out

    persons = gt[(gt["entity_type"] == "PERSON") & (gt["duplicate_of_row"] == "")]
    g_map = keyed(persons, "sheet", "row", "person_role")
    e_map = keyed(ex, "source_sheet", "source_row", "person_role")
    rows, failures = [], []
    for k, g in g_map.items():
        e = e_map.get(k)
        for f, (ok, want, got) in checks(g, e).items():
            rows.append({"field": f, "ok": ok, "file": g["doc_file"]})
            if not ok:
                failures.append(
                    {
                        "file": g["doc_file"],
                        "row": k[2],
                        "role": k[3],
                        "field": f,
                        "expected": want,
                        "got": got if e is not None else "MENTION_MISSING",
                    }
                )
    recall = (
        pd.DataFrame(rows).groupby("field")["ok"].agg(["sum", "count"]).reindex(FIELDS).dropna()
    )
    recall["recall"] = (recall["sum"] / recall["count"]).round(4)

    # column mapping
    gc = read_truth_csv(truth_dir / "gt_columns.csv")
    cm = tables["column_mapping"].copy()
    cm["sheet"] = cm["sheet"].fillna("")
    gc["col_idx"] = gc["col_idx"].astype(int)
    j = cm.merge(gc, on=["doc_id", "sheet", "col_idx"], how="inner")
    mapping = {}
    for name, col in (("rules", "rule_label"), ("ml", "ml_label"), ("final", "final_label")):
        pred = j[col].fillna("OTHER").tolist()
        mapping[name] = {
            "accuracy": round(float((j[col].fillna("OTHER") == j["true_label"]).mean()), 4),
            "macro_f1": round(macro_f1(j["true_label"].tolist(), pred), 4),
        }
    mapping["decisions"] = j["decision"].value_counts().to_dict()
    mapping["wrong_final"] = j[j["final_label"] != j["true_label"]][
        [
            "doc_file",
            "header_raw_x",
            "true_label",
            "rule_label",
            "ml_label",
            "ml_proba",
            "final_label",
            "decision",
        ]
    ].to_dict("records")

    # exclusions
    gx = read_truth_csv(truth_dir / "gt_excluded.csv")
    gx = gx[gx["doc_file"].str.startswith("sheets/")]
    want = {
        (r["doc_id"], r["kind"], _digits(r["value"]) if r["kind"] == "EIN" else r["value"].upper())
        for _, r in gx.iterrows()
    }
    got: set[tuple[str, str, str]] = set()
    xi, xe = tables.get("excluded_identifiers"), tables.get("excluded_entities")
    sheet_docs = set(ex["doc_id"]) | set(gx["doc_id"])
    if xi is not None and not xi.empty:
        got |= {
            (d, k, _digits(v))
            for d, k, v in zip(xi["doc_id"], xi["kind"], xi["_raw_value"], strict=True)
            if d in sheet_docs
        }
    if xe is not None and not xe.empty:
        got |= {
            (d, "ORG", str(v).upper())
            for d, v in zip(xe["doc_id"], xe["value_masked"], strict=True)
            if d in sheet_docs
        }
    exclusions = {
        kind: {
            "expected": len({x for x in want if x[1] == kind}),
            "correct": len({x for x in want & got if x[1] == kind}),
            "found": len({x for x in got if x[1] == kind}),
        }
        for kind in ("EIN", "ORG")
    }

    planted = planted_cases(gt, g_map, e_map, ex, tables, j)
    return {
        "recall": recall,
        "mapping": mapping,
        "exclusions": exclusions,
        "planted": planted,
        "failures": failures,
        "mentions": {
            "ground_truth": len(g_map),
            "extracted": len(e_map),
            "matched": len(set(g_map) & set(e_map)),
        },
    }


def planted_cases(
    gt: pd.DataFrame, g_map: dict, e_map: dict, ex: pd.DataFrame, tables: dict, j: pd.DataFrame
) -> list[dict]:
    """P27-P44: how each planted spreadsheet case was handled (or flagged)."""
    fp = tables["file_profile"]
    sc = tables["sheet_codes"]
    inv = tables["inventory"].set_index("path")
    did = lambda f: inv.loc[f, "doc_id"]  # noqa: E731

    def sheet_code(f: str, code: str) -> bool:
        return bool(((sc["doc_id"] == did(f)) & (sc["code"] == code)).any())

    def tagged(case: str) -> list[tuple[pd.Series, pd.Series | None]]:
        out = []
        for k, g in g_map.items():
            if case in g["planted_case"].split(";"):
                out.append((g, e_map.get(k)))
        return out

    def all_ok(case: str, pred: Callable[[pd.Series, pd.Series], bool]) -> tuple[bool, str]:
        items = tagged(case)
        good = sum(1 for g, e in items if e is not None and pred(g, e))
        return good == len(items) and bool(items), f"{good}/{len(items)} tagged mentions"

    res = []

    def add(case: str, what: str, ok: bool | str, evidence: str) -> None:
        handled = ok if isinstance(ok, str) else ("yes" if ok else "NO")
        res.append({"case": case, "what": what, "handled": handled, "evidence": evidence})

    hr = "sheets/hr_roster.xlsx"
    p = fp[fp["doc_id"] == did(hr)].iloc[0]
    add(
        "P27",
        "title rows above the header",
        p["header_row"] == 5
        and p["title_rows_dropped"] == 3
        and sheet_code(hr, "SHEET_HEADER_OFFSET"),
        f"header_row={p['header_row']}, title rows dropped={p['title_rows_dropped']}, "
        "SHEET_HEADER_OFFSET",
    )
    joined = j[(j["doc_file"] == hr) & (j["header_raw_x"] == "Employee SSN")]
    add(
        "P28",
        "merged 2-row header",
        not joined.empty and sheet_code(hr, "SHEET_MERGED_HEADER"),
        "headers joined, e.g. 'Employee SSN'; SHEET_MERGED_HEADER",
    )
    ok, ev = all_ok("P29", lambda g, e: "SHEET_HIDDEN_ROWS" in _codes(e))
    add("P29", "hidden rows kept + flagged", ok, f"{ev} extracted with SHEET_HIDDEN_ROWS")
    add(
        "P30",
        "total row dropped",
        p["total_rows_dropped"] == 1 and sheet_code(hr, "SHEET_TOTAL_ROW_DROPPED"),
        f"total rows dropped={p['total_rows_dropped']}",
    )
    ok, ev = all_ok(
        "P31",
        lambda g, e: (
            _s(e.get("zip5")) == g["exp_zip5"] and "XL_ZIP_LEADING_ZERO_RESTORED" in _codes(e)
        ),
    )
    add("P31", "ZIP leading zero restored", ok, f"{ev}: zip5 padded + XL_ZIP_LEADING_ZERO_RESTORED")
    ok, ev = all_ok("P32", lambda g, e: _s(e.get("dob")) == g["exp_dob"])
    serial = sum(
        1 for _, e in tagged("P32") if e is not None and "XL_DATE_SERIAL_CONVERTED" in _codes(e)
    )
    add(
        "P32",
        "DOB serials + mixed formats",
        ok,
        f"{ev} with the right ISO DOB; {serial} serials converted",
    )
    ok, ev = all_ok(
        "P33",
        lambda g, e: (
            "XL_NUMBER_PRECISION_LOST" in _codes(e)
            and _s(e.get("_card_status")) == "PRECISION_LOST"
        ),
    )
    add("P33", "card in sci-notation", ok, f"{ev} flagged XL_NUMBER_PRECISION_LOST")
    ok, ev = all_ok("P34", lambda g, e: "PREMASKED_VALUE" in _codes(e))
    add("P34", "pre-masked values", ok, f"{ev} flagged PREMASKED_VALUE")
    pay = "sheets/payroll_export.csv"
    pp = fp[fp["doc_id"] == did(pay)].iloc[0]
    ss = j[(j["doc_file"] == pay) & (j["header_raw_x"] == "SS#")]
    ok35, ev35 = all_ok(
        "P35",
        lambda g, e: all(
            w in name_tokens(_s(e.get("raw_name"))) for w in name_tokens(g["exp_last"])
        ),
    )
    add(
        "P35",
        "Latin-1, ';' delimiter, 'SS#' header",
        pp["delimiter"] == ";"
        and str(pp["encoding"]).lower() in {"cp1252", "latin-1", "iso-8859-1"}
        and not ss.empty
        and ss["final_label"].iloc[0] == "SSN"
        and ok35,
        f"encoding={pp['encoding']}, delimiter={pp['delimiter']!r}, "
        f"SS# -> {ss['final_label'].iloc[0] if not ss.empty else '?'}; accented names {ev35}",
    )
    leg = j[j["doc_file"] == "sheets/legacy_export.xls"].set_index("header_raw_x")
    want36 = {"ID": "SSN", "Column7": "DOB"}

    def col36(h: str) -> str:
        c = leg.loc[h]
        return (
            f"{h}: rules={c['rule_label']}, ML={c['ml_label']} ({c['ml_proba']}) "
            f"-> {c['final_label']} [{c['decision']}]"
        )

    if all(leg.loc[h, "final_label"] == lab for h, lab in want36.items()):
        p36: bool | str = True
    elif all(
        leg.loc[h, "final_label"] == lab or "COL_MAPPING_LOW_CONF" in _s(leg.loc[h, "codes"])
        for h, lab in want36.items()
    ):
        p36 = "flagged"  # the unsure column goes to column review
    else:
        p36 = False
    add("P36", "'ID' holds SSNs, 'Column7' holds DOBs", p36, "; ".join(map(col36, want36)))
    ok, ev = all_ok(
        "P37", lambda g, e: g["person_role"] != "DEPENDENT" or bool(_s(e.get("related_mention_id")))
    )
    deps = sum(1 for k in e_map if k[3] == "DEPENDENT")
    add(
        "P37",
        "wide dependent columns unpivoted",
        ok,
        f"{ev}; {deps} DEPENDENT mentions linked to subscribers",
    )
    ok, ev = all_ok("P38", lambda g, e: "FREE_TEXT_PII_FOUND" in _codes(e))
    add("P38", "SSN/MRN in notes", ok, f"{ev} flagged FREE_TEXT_PII_FOUND")
    vendor_id = did("sheets/vendor_list.xlsx")
    n_vendor = int((ex["doc_id"] == vendor_id).sum())
    add(
        "P39",
        "vendor file (orgs only)",
        n_vendor == 0,
        f"{n_vendor} person mentions; orgs/EINs excluded",
    )
    ok, ev = all_ok(
        "P40", lambda g, e: g["person_role"] != "GUARDIAN" or bool(_s(e.get("related_mention_id")))
    )
    st = sum(1 for k in e_map if k[3] == "STUDENT")
    add(
        "P40",
        "student + guardian (FERPA)",
        ok and st > 0,
        f"{ev}; {st} STUDENT mentions with student IDs, guardians linked",
    )
    ok, ev = all_ok("P41", lambda g, e: _digits(e.get("_raw_ssn")) == g["ssn"])
    add(
        "P41",
        "same person in payroll CSV and W-2",
        ok,
        f"{ev} carry the exact SSN (merge itself is M5)",
    )
    dup = gt[gt["duplicate_of_row"] != ""]
    dup_ok = all(
        (
            "ROW_DUPLICATE_IN_FILE"
            in _codes(
                e_map.get(
                    (r["doc_id"], r["sheet"], int(r["duplicate_of_row"]), r["person_role"], 0)
                )
            )
            and (r["doc_id"], r["sheet"], int(r["row"]), r["person_role"], 0) not in e_map
        )
        for _, r in dup.iterrows()
    )
    add(
        "P42",
        "duplicate row in a file",
        dup_ok and len(dup) > 0,
        f"{len(dup)} duplicate row(s) kept once, original flagged ROW_DUPLICATE_IN_FILE",
    )
    ok, ev = all_ok("P43", lambda g, e: "XL_ERROR_VALUE" in _codes(e))
    add("P43", "#N/A cells", ok, f"{ev} flagged XL_ERROR_VALUE (cells nulled)")
    ok, ev = all_ok(
        "P44",
        lambda g, e: "XL_SSN_ZERO_PADDED" in _codes(e) and _digits(e.get("_raw_ssn")) == g["ssn"],
    )
    add(
        "P44",
        "SSN stored as 8-digit number",
        ok,
        f"{ev} padded to the true SSN + XL_SSN_ZERO_PADDED",
    )
    return res


def render(r: dict[str, Any]) -> str:
    lines = ["## Spreadsheet extraction recall by field", "", "| field | recall |", "|---|---|"]
    for f, row in r["recall"].iterrows():
        lines.append(f"| {f} | {row['recall']:.3f} ({int(row['sum'])}/{int(row['count'])}) |")
    m = r["mapping"]
    lines += [
        "",
        f"Mentions: {r['mentions']}",
        "",
        "## Column mapping vs gt_columns",
        "",
        "| mapper | accuracy | macro-F1 |",
        "|---|---|---|",
    ]
    for k in ("rules", "ml", "final"):
        lines.append(f"| {k} | {m[k]['accuracy']} | {m[k]['macro_f1']} |")
    lines += ["", f"Decisions: {m['decisions']}", "", "Wrong final labels:"]
    lines += [
        f"- {w['doc_file']} `{w['header_raw_x']}`: true {w['true_label']}, "
        f"rules {w['rule_label']}, "
        f"ML {w['ml_label']} ({w['ml_proba']}) -> {w['final_label']} [{w['decision']}]"
        for w in m["wrong_final"]
    ] or ["- none"]
    lines += [
        "",
        f"Exclusions: {r['exclusions']}",
        "",
        "## Planted spreadsheet cases",
        "",
        "| case | what | handled | evidence |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {p['case']} | {p['what']} | {p['handled']} | {p['evidence']} |" for p in r["planted"]
    ]
    lines += ["", f"## Field failures ({len(r['failures'])})", ""]
    lines += [
        f"- {f['file']} row {f['row']} {f['role']} {f['field']}: "
        f"expected `{f['expected']}`, got `{f['got']}`"
        for f in r["failures"][:25]
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", type=Path, default=Path("config/pipeline.yaml"))
    ap.add_argument("--truth", type=Path, default=Path("data/raw/corpus_v1/truth"))
    ap.add_argument("--input", type=Path, default=None)
    args = ap.parse_args()
    from breachlens.pipeline import load_context
    from breachlens.sheets.sheet_track import stage_sheet_track

    ctx = load_context(args.config, input_dir=args.input.resolve() if args.input else None)
    mentions = stage_sheet_track(pd.DataFrame(), ctx)
    print(render(evaluate(mentions, ctx.tables, args.truth)))


if __name__ == "__main__":
    main()


__all__ = ["checks", "evaluate", "json", "render"]
