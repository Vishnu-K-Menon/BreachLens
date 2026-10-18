"""M4 evaluation: planted validation cases, rule precision, normalized fields.

Run:  python -m breachlens.evaluate.validation --config config/pipeline.yaml \\
          [--input data/raw/corpus_holdout/docs --truth data/raw/corpus_holdout/truth]

Runs the pipeline in memory (nothing is written) and compares the privacy-stage output
with ground truth. Mentions are matched by (doc_id, page, role, order) for PDFs and
(doc_id, sheet, row, role, order) for spreadsheets. Prints masked values only.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd

from breachlens.evaluate.extraction import read_truth_csv

NORMALIZED = {
    "title": ("exp_title", "name_title"),
    "first": ("exp_first", "first_name"),
    "middle_initial": ("exp_middle_initial", "middle_initial"),
    "last": ("exp_last", "last_name"),
    "suffix": ("exp_suffix", "name_suffix"),
    "line1": ("exp_line1", "address_line1"),
    "line2": ("exp_line2", "address_line2"),
    "city": ("exp_city", "city"),
    "state": ("exp_state", "state"),
    "zip5": ("exp_zip5", "zip5"),
    "dob": ("exp_dob", "dob"),
}
# planted-code rules -> the cases where they are expected to fire
RULE_CASES = {
    "NAME_TITLE_REMOVED": {"P01"},
    "NAME_SUFFIX_INVALID": {"P03"},
    "NAME_PUNCT_FIXED": {"P07"},
    "NAME_WHITESPACE": {"P26"},
    "ADDR_LINE2_SPLIT": {"P09"},
    "ADDR_ZIP_CITY_MISMATCH": {"P10"},
    "ADDR_ZIP_FORMAT": {"P11"},
    "DOB_TWO_DIGIT_YEAR": {"P12", "P32"},
    "SSN_AREA_INVALID": {"P13"},
    "SSN_GROUP_INVALID": {"P13"},
    "SSN_SERIAL_INVALID": {"P13"},
    "SSN_FORMAT": {"P13"},
    "CARD_LUHN_FAIL": {"P14"},
    "DL_FORMAT_STATE": {"P15"},
    "DL_STATE_MISSING": {"P16"},
    "PERSON_NO_QUALIFYING_ELEMENT": {"P23"},
    "XL_SSN_ZERO_PADDED": {"P44"},
    "XL_ERROR_VALUE": {"P43"},
    "FREE_TEXT_PII_FOUND": {"P38"},
    "PREMASKED_VALUE": {"P34"},
    "XL_NUMBER_PRECISION_LOST": {"P33"},
    "XL_ZIP_LEADING_ZERO_RESTORED": {"P31"},
}

QUALIFYING_FLAGS = (
    "has_ssn",
    "has_dl",
    "has_state_id",
    "has_passport",
    "has_dob",
    "has_bank_account",
    "has_card",
    "has_mrn",
    "has_health_member_id",
    "has_student_id",
)
PRESENCE = {
    "has_ssn": "ssn_present",
    "has_dl": "dl_present",
    "has_passport": "passport_present",
    "has_bank_account": "bank_account_present",
    "has_routing": "routing_number_present",
    "has_card": "card_present",
    "has_mrn": "mrn_present",
    "has_health_member_id": "health_member_id_present",
    "has_health_group_number": "health_group_number_present",
    "has_diagnosis": "diagnosis_present",
    "has_procedure": "procedure_present",
    "has_date_of_service": "date_of_service_present",
    "has_student_id": "student_id_present",
    "has_employee_id": "employee_id_present",
}
# Rules whose correct firings are known from truth values, not only from case tags.
TRUTH_EXPECTED: dict[str, Callable[[pd.Series], bool]] = {
    "ADDR_LINE2_SPLIT": lambda g: bool(g["exp_line2"]),
    "PERSON_NO_QUALIFYING_ELEMENT": lambda g: not any(g[c] == "1" for c in QUALIFYING_FLAGS),
}


def _s(v: Any) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


def codes_of(e: pd.Series | None) -> set[str]:
    return set(_s(None if e is None else e.get("qc_reasons")).split(";")) - {""}


def match(gt: pd.DataFrame, ex: pd.DataFrame) -> dict[int, pd.Series | None]:
    """gt row index -> extracted mention (or None)."""

    def key(r: pd.Series, page: str, sheet: str, row: str, role: str) -> tuple:
        if r["source_type"] == "PDF":
            return (r["doc_id"], "PDF", _s(r[role]))
        return (r["doc_id"], _s(r[sheet]), int(float(r[row])), _s(r[role]))

    ex_keys: dict[tuple, list[pd.Series]] = defaultdict(list)
    for _, r in ex.iterrows():
        ex_keys[key(r, "page", "source_sheet", "source_row", "person_role")].append(r)
    seen: Counter = Counter()
    out: dict[int, pd.Series | None] = {}
    for i, r in gt.iterrows():
        k = key(r, "page", "sheet", "row", "person_role")
        lst = ex_keys.get(k, [])
        out[i] = lst[seen[k]] if seen[k] < len(lst) else None
        seen[k] += 1
    return out


def evaluate(
    mentions: pd.DataFrame, tables: dict[str, Any], audit: list[Any], truth: Path
) -> dict[str, Any]:
    gt = read_truth_csv(truth / "gt_mentions.csv")
    gt = gt[(gt["entity_type"] == "PERSON") & (gt["duplicate_of_row"] == "")]
    m = match(gt, mentions)
    cases = gt["planted_case"].str.split(";")
    by_key = {}
    for i, e in m.items():
        if e is not None:
            by_key[e["mention_id"]] = i
    suggestions = {
        (ev.item_id, ev.code): json.loads(ev.detail_json or "{}").get("suggestion")
        for ev in audit
        if ev.event_type == "RULE_FIRED"
    }

    def tagged(case: str) -> list[tuple[pd.Series, pd.Series | None]]:
        return [(gt.loc[i], m[i]) for i in gt.index if case in cases[i]]

    def eq(e: pd.Series, col: str, want: str) -> bool:
        return _s(e.get(col)).upper() == want.upper()

    preds: dict[str, tuple[str, Callable[[pd.Series, pd.Series], bool]]] = {
        "P01": (
            "title moved to name_title",
            lambda g, e: (
                eq(e, "name_title", g["exp_title"]) and "NAME_TITLE_REMOVED" in codes_of(e)
            ),
        ),
        "P02": ("suffix variants normalized", lambda g, e: eq(e, "name_suffix", g["exp_suffix"])),
        "P03": (
            "suffix typo -> NAME_SUFFIX_INVALID, suggest JR",
            lambda g, e: (
                "NAME_SUFFIX_INVALID" in codes_of(e)
                and suggestions.get((e["mention_id"], "NAME_SUFFIX_INVALID")) == "JR"
            ),
        ),
        "P04": (
            "LAST, FIRST M parsed",
            lambda g, e: (
                eq(e, "first_name", g["exp_first"])
                and eq(e, "last_name", g["exp_last"])
                and eq(e, "middle_initial", g["exp_middle_initial"])
            ),
        ),
        "P06": ("hyphen/particle surnames intact", lambda g, e: eq(e, "last_name", g["exp_last"])),
        "P07": (
            "apostrophe spacing fixed",
            lambda g, e: eq(e, "last_name", g["exp_last"]) and "NAME_PUNCT_FIXED" in codes_of(e),
        ),
        "P09": (
            "unit -> line 2, formatted",
            lambda g, e: (
                eq(e, "address_line1", g["exp_line1"]) and eq(e, "address_line2", g["exp_line2"])
            ),
        ),
        "P10": (
            "ZIP-city mismatch + suggestion",
            lambda g, e: (
                "ADDR_ZIP_CITY_MISMATCH" in codes_of(e) and bool(_s(e.get("address_suggestion")))
            ),
        ),
        "P11": (
            "ZIP missing a digit -> ADDR_ZIP_FORMAT",
            lambda g, e: "ADDR_ZIP_FORMAT" in codes_of(e) and e.get("address_status") == "INVALID",
        ),
        "P12": (
            "two-digit-year DOB flagged, pivoted",
            lambda g, e: "DOB_TWO_DIGIT_YEAR" in codes_of(e) and eq(e, "dob", g["exp_dob"]),
        ),
        "P13": (
            "invalid SSN -> SSN_* ERROR",
            lambda g, e: (
                any(c.startswith("SSN_") for c in codes_of(e))
                and _s(e.get("ssn_valid")).startswith("SSN_")
            ),
        ),
        "P14": (
            "card failing Luhn",
            lambda g, e: (
                "CARD_LUHN_FAIL" in codes_of(e) and e.get("card_valid") == "CARD_LUHN_FAIL"
            ),
        ),
        "P15": ("license not matching state format", lambda g, e: "DL_FORMAT_STATE" in codes_of(e)),
        "P16": (
            "license without state",
            lambda g, e: "DL_STATE_MISSING" in codes_of(e) and e.get("qc_status") == "FAIL",
        ),
        "P22": (
            "minor -> is_minor",
            lambda g, e: _s(e.get("is_minor")) == "True" or e.get("is_minor") is True,
        ),
        "P23": (
            "name only -> PERSON_NO_QUALIFYING_ELEMENT",
            lambda g, e: "PERSON_NO_QUALIFYING_ELEMENT" in codes_of(e),
        ),
        "P26": (
            "leading/trailing spaces trimmed",
            lambda g, e: (
                "NAME_WHITESPACE" in codes_of(e)
                and eq(e, "first_name", g["exp_first"])
                and eq(e, "last_name", g["exp_last"])
            ),
        ),
        "P29": (
            "hidden rows -> SHEET_HIDDEN_ROWS",
            lambda g, e: "SHEET_HIDDEN_ROWS" in codes_of(e),
        ),
        "P31": (
            "ZIP zero restored",
            lambda g, e: (
                "XL_ZIP_LEADING_ZERO_RESTORED" in codes_of(e) and eq(e, "zip5", g["exp_zip5"])
            ),
        ),
        "P32": ("DOB serials / mixed formats", lambda g, e: eq(e, "dob", g["exp_dob"])),
        "P33": (
            "precision-lost card -> ERROR",
            lambda g, e: (
                e.get("card_valid") == "XL_NUMBER_PRECISION_LOST" and e.get("qc_status") == "FAIL"
            ),
        ),
        "P34": (
            "pre-masked -> PREMASKED_VALUE",
            lambda g, e: (
                "PREMASKED_VALUE" in codes_of(e)
                and "PREMASKED_VALUE" in {e.get("ssn_valid"), e.get("card_valid")}
            ),
        ),
        "P37": (
            "dependents linked",
            lambda g, e: g["person_role"] != "DEPENDENT" or bool(_s(e.get("related_mention_id"))),
        ),
        "P38": ("notes PII flagged + counted", lambda g, e: "FREE_TEXT_PII_FOUND" in codes_of(e)),
        "P40": (
            "student record -> FERPA_RECORD",
            lambda g, e: g["person_role"] != "STUDENT" or "FERPA_RECORD" in codes_of(e),
        ),
        "P42": ("duplicate row flagged", lambda g, e: "ROW_DUPLICATE_IN_FILE" in codes_of(e)),
        "P43": ("#N/A -> XL_ERROR_VALUE", lambda g, e: "XL_ERROR_VALUE" in codes_of(e)),
        "P44": (
            "8-digit SSN padded -> XL_SSN_ZERO_PADDED",
            lambda g, e: (
                "XL_SSN_ZERO_PADDED" in codes_of(e) and e.get("ssn_valid") == "XL_SSN_ZERO_PADDED"
            ),
        ),
    }
    planted = []
    for case, (what, pred) in preds.items():
        items = tagged(case)
        if case == "P42":  # the duplicate row itself is dropped; its original carries the code
            items = [(g, e) for g, e in items if e is not None]
        ok = sum(1 for g, e in items if e is not None and pred(g, e))
        planted.append({"case": case, "what": what, "caught": ok, "tagged": len(items)})

    # doc-level and exclusion cases
    dc = tables.get("doc_codes", pd.DataFrame(columns=["doc_id", "code"]))
    inv = tables["inventory"].set_index("path")
    for case, path, code, what in (
        (
            "P27",
            "sheets/hr_roster.xlsx",
            "SHEET_HEADER_OFFSET",
            "title rows -> SHEET_HEADER_OFFSET",
        ),
        (
            "P28",
            "sheets/hr_roster.xlsx",
            "SHEET_MERGED_HEADER",
            "merged header -> SHEET_MERGED_HEADER",
        ),
        (
            "P30",
            "sheets/hr_roster.xlsx",
            "SHEET_TOTAL_ROW_DROPPED",
            "total row -> SHEET_TOTAL_ROW_DROPPED",
        ),
        (
            "P35",
            "sheets/payroll_export.csv",
            "CSV_ENCODING_DETECTED",
            "Latin-1 CSV -> CSV_ENCODING_DETECTED",
        ),
    ):
        hit = bool(((dc["doc_id"] == inv.loc[path, "doc_id"]) & (dc["code"] == code)).any())
        planted.append({"case": case, "what": what, "caught": int(hit), "tagged": 1})
    gx = read_truth_csv(truth / "gt_excluded.csv")
    xi, xe = tables.get("excluded_identifiers"), tables.get("excluded_entities")
    for case, kinds, code, what in (
        ("P19", {"EIN"}, "EIN_EXCLUDED", "EIN near the SSN -> EIN_EXCLUDED"),
        ("P20", {"NPI", "PROVIDER_TIN"}, None, "provider NPI/TIN -> NPI/EIN_EXCLUDED"),
        ("P21", {"ORG"}, "NAME_ORG_LIKE", "org in a name field -> NAME_ORG_LIKE"),
    ):
        want = gx[gx["planted_case"].str.contains(case) & gx["kind"].isin(kinds)]
        table = xe if kinds == {"ORG"} else xi
        got = 0
        for _, w in want.iterrows():
            t = table[(table["doc_id"] == w["doc_id"]) & (table["kind"] == w["kind"])]
            if kinds == {"ORG"}:
                t = t[t["value_masked"].str.upper() == w["value"].upper()]
            else:
                t = t[t["value_masked"].str[-4:] == re.sub(r"\D", "", w["value"])[-4:]]
            exp_code = code or ("NPI_EXCLUDED" if w["kind"] == "NPI" else "EIN_EXCLUDED")
            got += int(t["reason"].str.startswith(exp_code).any())
        planted.append({"case": case, "what": what, "caught": got, "tagged": len(want)})
    vendor = inv.loc["sheets/vendor_list.xlsx", "doc_id"]
    n_vendor = int((mentions["doc_id"] == vendor).sum())
    planted.append(
        {
            "case": "P39",
            "what": "vendor file: 0 person mentions",
            "caught": int(n_vendor == 0),
            "tagged": 1,
        }
    )
    p41 = defaultdict(set)
    for g, e in tagged("P41"):
        if e is not None:
            p41[g["true_person_id"]].add(_s(e.get("ssn_key")))
    p41_ok = sum(1 for keys in p41.values() if len(keys) == 1 and "" not in keys)
    planted.append(
        {
            "case": "P41",
            "what": "payroll CSV + W-2: same ssn_key (merge is M5)",
            "caught": p41_ok,
            "tagged": len(p41),
        }
    )
    planted.sort(key=lambda p: int(p["case"][1:]))

    # rule precision: firings outside the planted rows
    precision = []
    ex_cases = {e["mention_id"]: set(cases[i]) for i, e in m.items() if e is not None}
    for code, expected in RULE_CASES.items():
        fired = [
            mid
            for mid, c in zip(mentions["mention_id"], mentions["qc_reasons"].map(_s), strict=True)
            if code in c.split(";")
        ]
        outside = [
            mid
            for mid in fired
            if not (ex_cases.get(mid, set()) & expected)
            and not (
                code in TRUTH_EXPECTED
                and mid in by_key
                and TRUTH_EXPECTED[code](gt.loc[by_key[mid]])
            )
        ]
        precision.append(
            {"code": code, "fired": len(fired), "outside_planted": len(outside), "ids": outside[:5]}
        )

    # normalized fields
    norm = []
    for src in ("PDF", "SPREADSHEET"):
        for f, (gcol, ecol) in NORMALIZED.items():
            rows = [
                (gt.loc[i], e)
                for i, e in m.items()
                if gt.loc[i, "source_type"] == src and gt.loc[i, gcol]
            ]
            ok = sum(1 for g, e in rows if e is not None and eq(e, ecol, g[gcol]))
            norm.append({"track": src, "field": f, "ok": ok, "n": len(rows)})
    presence = []
    for flag, col in PRESENCE.items():
        rows = [(gt.loc[i], e) for i, e in m.items() if e is not None]
        agree = sum(1 for g, e in rows if (g[flag] == "1") == (_s(e.get(col)) == "True"))
        exp = sum(1 for g, _ in rows if g[flag] == "1")
        got = sum(1 for _, e in rows if _s(e.get(col)) == "True")
        presence.append(
            {
                "element": flag.removeprefix("has_"),
                "agree": agree,
                "n": len(rows),
                "truth": exp,
                "flagged": got,
            }
        )
    freq = Counter(c for r in mentions["qc_reasons"].map(_s) for c in r.split(";") if c)
    return {
        "planted": planted,
        "precision": precision,
        "normalized": norm,
        "freq": freq,
        "presence": presence,
        "qc": mentions["qc_status"].value_counts().to_dict(),
        "matched": sum(e is not None for e in m.values()),
        "gt": len(m),
    }


def render(r: dict[str, Any]) -> str:
    lines = [
        f"Mentions matched: {r['matched']}/{r['gt']}. qc_status: {r['qc']}",
        "",
        "## Planted validation cases",
        "",
        "| case | expected outcome | caught |",
        "|---|---|---|",
    ]
    for p in r["planted"]:
        mark = "" if p["caught"] == p["tagged"] else " **MISSED**"
        lines.append(f"| {p['case']} | {p['what']} | {p['caught']}/{p['tagged']}{mark} |")
    caught = sum(p["caught"] for p in r["planted"])
    tagged = sum(p["tagged"] for p in r["planted"])
    lines += [
        "",
        f"Planted-case recall: {caught}/{tagged} = {caught / tagged:.3f}",
        "",
        "## Rule precision (firings the truth does not expect)",
        "",
        "| code | fired | unexpected |",
        "|---|---|---|",
    ]
    lines += [
        f"| {p['code']} | {p['fired']} | {p['outside_planted']} {p['ids'] or ''} |"
        for p in r["precision"]
    ]
    lines += [
        "",
        "## Normalized fields vs exp_*",
        "",
        "| track | field | accuracy |",
        "|---|---|---|",
    ]
    lines += [
        f"| {n['track']} | {n['field']} | {n['ok']}/{n['n']} |" for n in r["normalized"] if n["n"]
    ]
    lines += [
        "",
        "## Element presence (`*_present`) vs truth `has_*`",
        "",
        "| element | agree | truth | flagged |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {p['element']} | {p['agree']}/{p['n']} | {p['truth']} | {p['flagged']} |"
        for p in r["presence"]
    ]
    lines += ["", "## Reason-code frequency", ""] + [
        f"- {c}: {n}" for c, n in r["freq"].most_common()
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", type=Path, default=Path("config/pipeline.yaml"))
    ap.add_argument("--truth", type=Path, default=Path("data/raw/corpus_v1/truth"))
    ap.add_argument("--input", type=Path, default=None)
    args = ap.parse_args()
    from breachlens.pipeline import load_context, run_pipeline

    ctx = load_context(args.config, input_dir=args.input.resolve() if args.input else None)
    mentions = run_pipeline(ctx)
    print(render(evaluate(mentions, ctx.tables, ctx.audit.events, args.truth)))


if __name__ == "__main__":
    main()
