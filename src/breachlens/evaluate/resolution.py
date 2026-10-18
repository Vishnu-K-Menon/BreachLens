"""M5 evaluation: matching, address status, notification (against ground truth).

Run:  python -m breachlens.evaluate.resolution --config config/pipeline.yaml \\
          [--input data/raw/corpus_holdout/docs --truth data/raw/corpus_holdout/truth]

Runs the pipeline in memory (offline: Census results come from the cache) and prints:
pairwise precision/recall, planted matching cases, shared-address pairs, gray-zone
pairs, the address-status confusion against `expected_address_status` (ADR-050), the
notification list against `gt_people`, and the minor/guardian notes. Names are shown
as initials only.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd

from breachlens.evaluate.extraction import read_truth_csv
from breachlens.evaluate.validation import _s, match

STATUSES = ["VERIFIED", "CORRECTED", "UNVERIFIED", "INVALID", "NOT_CHECKED"]


def initials(r: pd.Series) -> str:
    return f"{_s(r.get('first_name'))[:1]}. {_s(r.get('last_name'))[:1]}." if r is not None else "?"


def evaluate(mentions: pd.DataFrame, tables: dict[str, Any], truth: Path) -> dict[str, Any]:
    gt = read_truth_csv(truth / "gt_mentions.csv")
    gt = gt[(gt["entity_type"] == "PERSON") & (gt["duplicate_of_row"] == "")]
    m = match(gt, mentions)
    tp_of = {e["mention_id"]: gt.loc[i, "true_person_id"] for i, e in m.items() if e is not None}
    pid_of = dict(zip(mentions["mention_id"], mentions["person_id"], strict=True))
    ids = sorted(tp_of)
    true_pairs = {(a, b) for a, b in combinations(ids, 2) if tp_of[a] == tp_of[b]}
    pred_pairs = {(a, b) for a, b in combinations(ids, 2) if pid_of[a] == pid_of[b]}
    tp = len(true_pairs & pred_pairs)
    pairwise = {
        "true_pairs": len(true_pairs),
        "predicted_pairs": len(pred_pairs),
        "correct": tp,
        "precision": round(tp / len(pred_pairs), 4) if pred_pairs else 1.0,
        "recall": round(tp / len(true_pairs), 4) if true_pairs else 1.0,
    }
    clusters_of = defaultdict(set)
    for mid, t in tp_of.items():
        clusters_of[t].add(pid_of[mid])
    persons_of = defaultdict(set)
    for mid, t in tp_of.items():
        persons_of[pid_of[mid]].add(t)
    people = tables["people"].set_index("person_id")

    def one(t: str) -> bool:
        return len(clusters_of[t]) == 1

    # planted matching cases
    gtp = read_truth_csv(truth / "gt_people.csv").set_index("true_person_id")
    cases = []
    twins = sorted(
        {
            t
            for i in gt.index
            if "P18" in gt.loc[i, "planted_case"]
            for t in [gt.loc[i, "true_person_id"]]
        }
    )
    hh = gtp.loc[twins[0], "household"] if twins else None
    pair = (
        sorted(gtp[(gtp["household"] == hh) & (gtp["last"] == gtp.loc[twins[0], "last"])].index)
        if hh
        else []
    )
    if len(pair) >= 2:
        merged = bool(clusters_of[pair[0]] & clusters_of[pair[1]])
        cases.append(
            {
                "case": "P18 twins not merged",
                "ok": not merged,
                "detail": f"{pair[0]} vs {pair[1]}: "
                f"{sorted(clusters_of[pair[0]])} / {sorted(clusters_of[pair[1]])}",
            }
        )
    for case, what in (
        ("P17", "mover merged, newer address kept"),
        ("P05", "nickname (Bob/Robert) row merged"),
        ("P08", "one-letter surname variant row merged"),
        ("P24", "4+ sources -> one record"),
    ):
        ts = sorted(
            {gt.loc[i, "true_person_id"] for i in gt.index if case in gt.loc[i, "planted_case"]}
        )
        for t in ts:
            ok = one(t)
            n = sum(1 for x in tp_of.values() if x == t)
            detail = f"{t}: {len(clusters_of[t])} cluster(s), {n} mentions"
            if case in ("P05", "P08"):  # the variant row must join the person's main cluster
                main = Counter(pid_of[mid] for mid, x in tp_of.items() if x == t).most_common(1)[0][
                    0
                ]
                tagged = [
                    e["mention_id"]
                    for i, e in m.items()
                    if e is not None
                    and case in gt.loc[i, "planted_case"]
                    and gt.loc[i, "true_person_id"] == t
                ]
                ok = all(pid_of[x] == main for x in tagged)
                rest = sorted({pid_of[mid] for mid, x in tp_of.items() if x == t} - {main})
                detail += f"; variant row in main cluster {main}: {ok}; other clusters {rest}"
            if case == "P17" and ok:
                p = people.loc[next(iter(clusters_of[t]))]
                want = (gtp.loc[t, "city"], gtp.loc[t, "zip5"])
                ok = ok and (_s(p["city"]), _s(p["zip5"])) == want
                detail += f"; survivor {p['city']} {p['zip5']} (truth {want[0]} {want[1]})"
            cases.append({"case": f"{case} {what}", "ok": ok, "detail": detail})
    p41 = sorted(
        {gt.loc[i, "true_person_id"] for i in gt.index if "P41" in gt.loc[i, "planted_case"]}
    )
    tagged41: dict[str, set[str]] = defaultdict(set)  # W-2 + payroll rows share one person_id
    for i, e in m.items():
        if e is not None and "P41" in gt.loc[i, "planted_case"]:
            tagged41[gt.loc[i, "true_person_id"]].add(pid_of[e["mention_id"]])
    p41_ok = [t for t in p41 if len(tagged41[t]) == 1]
    cases.append(
        {
            "case": "P41 payroll CSV + W-2 -> one person_id",
            "ok": len(p41_ok) == len(p41),
            "detail": f"{len(p41_ok)}/{len(p41)} people: W-2 and payroll rows share one person_id",
        }
    )
    # shared addresses
    sh = read_truth_csv(truth / "gt_shared_addresses.csv")
    shared_merged = [
        (a, b)
        for a, b in zip(sh["true_person_id_a"], sh["true_person_id_b"], strict=True)
        if clusters_of[a] & clusters_of[b]
    ]
    # gray zone
    pf = tables["pair_features"]
    gray = pf[(pf["decision"] == "REVIEW") & ~pf["same_person_id"]]
    by_id = mentions.set_index("mention_id")
    gray_rows = []
    cl_a, cl_b = gray["mention_a"].map(pid_of), gray["mention_b"].map(pid_of)
    seen: set[tuple[str, str]] = set()
    order = gray.sort_values(["score", "mention_a", "mention_b"], ascending=[False, True, True])
    for _, g in order.iterrows():  # one row per cluster pair, its best-scoring pair shown
        ca, cb = sorted((pid_of[g["mention_a"]], pid_of[g["mention_b"]]))
        if (ca, cb) in seen:
            continue
        seen.add((ca, cb))
        n_pairs = int((((cl_a == ca) & (cl_b == cb)) | ((cl_a == cb) & (cl_b == ca))).sum())
        a, b = by_id.loc[g["mention_a"]], by_id.loc[g["mention_b"]]
        same = tp_of.get(g["mention_a"]) == tp_of.get(g["mention_b"])
        feats = {
            k: g[k]
            for k in ("f_first_jw", "f_last_jw", "f_dob", "f_zip_eq", "f_addr_tsr")
            if pd.notna(g[k])
        }
        gray_rows.append(
            {
                "clusters": f"{ca} / {cb}",
                "pairs": n_pairs,
                "a": g["mention_a"],
                "b": g["mention_b"],
                "names": f"{initials(a)} / {initials(b)}",
                "files": f"{a['source_file']} / {b['source_file']}",
                "score": g["score"],
                "guard": g["guard_fired"],
                "truth_same": same,
                "features": feats,
            }
        )
    # address status
    conf = Counter()
    for i, e in m.items():
        exp = gt.loc[i, "expected_address_status"]
        if exp and e is not None:
            conf[(exp, _s(e.get("address_status")) or "NONE")] += 1
    agree = sum(n for (x, y), n in conf.items() if x == y)
    total = sum(conf.values())
    manifest = json.loads((truth / "manifest.json").read_text(encoding="utf-8"))[
        "expected_address_status"
    ]
    got_people = Counter(_s(s) or "NONE" for s in people["address_status"])
    # notification
    nl = tables["notification_list"].set_index("person_id")
    exp_notify = {t for t in gtp.index if gtp.loc[t, "notify_required"] == "1"}
    got_notify_truth = defaultdict(int)
    fp_clusters = []
    for pidx, r in nl.iterrows():
        if not r["notify_required"]:
            continue
        ts = persons_of.get(pidx, set())
        if not ts:
            continue
        t = Counter(
            tp_of[mid] for mid, p in pid_of.items() if p == pidx and mid in tp_of
        ).most_common(1)[0][0]
        got_notify_truth[t] += 1
        if t not in exp_notify:
            fp_clusters.append((pidx, t))
    tpn = len(exp_notify & set(got_notify_truth))
    fn = sorted(exp_notify - set(got_notify_truth))
    dup = {t: n for t, n in got_notify_truth.items() if n > 1}
    by_state_exp = Counter(gtp.loc[t, "state"] for t in exp_notify)
    by_state_got = Counter(_s(r["jurisdiction"]) for _, r in nl.iterrows() if r["notify_required"])
    minors = nl[nl["notify_note"].fillna("").str.contains("parent/guardian")]
    minor_rows = [
        {
            "person_id": p,
            "jurisdiction": r["jurisdiction"],
            "notify_required": r["notify_required"],
            "note": r["notify_note"],
        }
        for p, r in minors.iterrows()
    ]
    review_exp = int((gtp["card_review"] == "1").sum())
    return {
        "pairwise": pairwise,
        "cases": cases,
        "shared": {"pairs": len(sh), "merged": shared_merged},
        "gray": gray_rows,
        "gray_pairs": len(gray),
        "address": {
            "confusion": conf,
            "agree": agree,
            "total": total,
            "manifest_mentions": manifest["mentions"],
            "manifest_people": manifest["people"],
            "people": dict(got_people),
        },
        "notify": {
            "expected": len(exp_notify),
            "listed": int(nl["notify_required"].sum()),
            "tp": tpn,
            "fn": fn,
            "fp": fp_clusters,
            "duplicates": dup,
            "by_state_exp": by_state_exp,
            "by_state_got": by_state_got,
            "minors": minor_rows,
            "needs_review": int((nl["notify_status"] == "NEEDS_REVIEW").sum()),
            "card_review_truth": review_exp,
        },
        "people": {
            "predicted": len(people),
            "truth": len(gtp),
            "split_truth_people": sum(1 for t in clusters_of if len(clusters_of[t]) > 1),
        },
    }


def render(r: dict[str, Any]) -> str:
    p, pe = r["pairwise"], r["people"]
    L = [
        "## Matching",
        "",
        f"Pairwise precision {p['precision']} ({p['correct']}/{p['predicted_pairs']}), "
        f"recall {p['recall']} ({p['correct']}/{p['true_pairs']}).",
        f"People: {pe['predicted']} predicted vs {pe['truth']} truth; "
        f"{pe['split_truth_people']} truth people split.",
        "",
        "| case | ok | detail |",
        "|---|---|---|",
    ]
    L += [f"| {c['case']} | {'yes' if c['ok'] else 'NO'} | {c['detail']} |" for c in r["cases"]]
    sh = r["shared"]
    L += [
        "",
        f"Shared-address pairs merged: {len(sh['merged'])}/{sh['pairs']} {sh['merged'] or ''}",
        "",
        f"### Gray zone: {r['gray_pairs']} REVIEW pairs in {len(r['gray'])} cluster pairs",
        "",
        "| clusters | pairs | a | b | names | files | score | guard | truth same | features |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for g in r["gray"]:
        L.append(
            f"| {g['clusters']} | {g['pairs']} | {g['a']} | {g['b']} | {g['names']} | "
            f"{g['files']} | {g['score']} | {g['guard'] or ''} | {g['truth_same']} | "
            f"{g['features']} |"
        )
    a = r["address"]
    share = a["agree"] / max(a["total"], 1)
    L += [
        "",
        f"## Address status vs expected (ADR-050): {a['agree']}/{a['total']} = {share:.3f}",
        "",
        "| expected / got | " + " | ".join(STATUSES) + " |",
        "|---|" + "---|" * len(STATUSES),
    ]
    for x in STATUSES[:4]:
        cells = " | ".join(str(a["confusion"].get((x, y), 0)) for y in STATUSES)
        L.append(f"| {x} | {cells} |")
    L += [
        "",
        f"Manifest mentions {a['manifest_mentions']}",
        f"People: expected {a['manifest_people']}, got {a['people']}",
    ]
    n = r["notify"]
    L += [
        "",
        f"## Notification: listed {n['listed']} vs truth {n['expected']}",
        "",
        f"True people notified {n['tp']}; missed {len(n['fn'])} {n['fn']}; "
        f"extra {len(n['fp'])} {n['fp']}; duplicate letters {n['duplicates']}.",
        f"needs_review {n['needs_review']} (truth card_review {n['card_review_truth']})",
        "",
        "| state | truth | listed |",
        "|---|---|---|",
    ]
    for st in sorted(set(n["by_state_exp"]) | set(n["by_state_got"])):
        L.append(f"| {st} | {n['by_state_exp'].get(st, 0)} | {n['by_state_got'].get(st, 0)} |")
    L += ["", f"### Minors ({len(n['minors'])})", ""]
    L += [
        f"- {x['person_id']} {x['jurisdiction']} notify={x['notify_required']}: {x['note']}"
        for x in n["minors"]
    ]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", type=Path, default=Path("config/pipeline.yaml"))
    ap.add_argument("--truth", type=Path, default=Path("data/raw/corpus_v1/truth"))
    ap.add_argument("--input", type=Path, default=None)
    args = ap.parse_args()
    from breachlens.pipeline import load_context, run_pipeline

    ctx = load_context(args.config, input_dir=args.input.resolve() if args.input else None)
    mentions = run_pipeline(ctx)
    print(render(evaluate(mentions, ctx.tables, args.truth)))


if __name__ == "__main__":
    main()
