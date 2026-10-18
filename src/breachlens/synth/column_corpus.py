"""Training corpus for the column-type classifier (ML_MODELS.md §C).

About 400 random tables (5-25 columns, 20-500 rows) with about 6,000 labelled columns,
written to `data/raw/column_corpus/`:
- `tables/T0001.csv` …  one CSV per table (UTF-8, every value a string, blanks = null)
- `labels.csv`          table_id, col_idx, header_raw, true_label, alias_group,
                        header_kind (ALIAS / UNINFORMATIVE), n_rows, null_pct

Header noise: an alias from `config/column_corpus_aliases.yaml`, then random case,
underscores, abbreviation, a typo or a prefix; about 15% of columns get an uninformative
header (`Column7`, `ID`, `Field_3`, blank). Value noise: 5-40% nulls, mixed formats,
masking and Excel damage (lost zeros, date serials, scientific notation). Confusables
on purpose: 9-digit employee IDs vs SSNs, MRN vs member ID, 5-digit employee IDs vs ZIP,
hire dates (OTHER) vs DOB, phone vs account numbers.
"""

from __future__ import annotations

import csv
import hashlib
import random
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml
import zipcodes
from faker import Faker

from breachlens.synth import identifiers as ids
from breachlens.synth.settings import SynthSettings

UNINFORMATIVE = [
    "Column{n}",
    "ID",
    "Field_{n}",
    "",
    "Col{n}",
    "Data",
    "Value",
    "X{n}",
    "Unnamed: {n}",
]
ABBREV = {
    "Number": "No",
    "Address": "Addr",
    "Date": "Dt",
    "Name": "Nm",
    "Account": "Acct",
    "Phone": "Ph",
}
STATES = ["CA", "NY", "TX", "FL", "PA", "VA", "NJ", "MA", "IL", "OH", "GA", "WA"]
POOL_SIZE = 800
SCHOOL_KINDS = ["Elementary", "Middle School", "High School", "Academy"]
# label weights for picking table columns (identity-heavy, like real breach exports)
WEIGHTS = {
    "OTHER": 6,
    "FULL_NAME": 3,
    "FIRST_NAME": 3,
    "LAST_NAME": 3,
    "ADDRESS_LINE1": 3,
    "CITY": 3,
    "STATE": 3,
    "ZIP": 3,
    "PHONE": 3,
    "EMAIL": 2,
    "DOB": 3,
    "SSN": 3,
}


def _excel_serial(d: date) -> str:
    return str((d - date(1899, 12, 30)).days)


class _Values:
    """Per-label value pools (clean values) plus per-column formatting with noise."""

    def __init__(self, settings: SynthSettings, rng: random.Random, fake: Faker) -> None:
        self.s, self.r, self.f = settings, rng, fake
        self.ref = settings.config.as_of_date
        zips = [
            z
            for z in zipcodes.filter_by()
            if z.get("zip_code_type") == "STANDARD" and z["state"] in STATES
        ]
        self.zips = sorted(zips, key=lambda z: z["zip_code"])

    def date_between(self, lo_years: int, hi_years: int) -> date:
        return self.ref - timedelta(days=self.r.randint(lo_years * 365, hi_years * 365))

    def raw(self, label: str) -> Callable[[], Any]:
        r, f, cfg = self.r, self.f, self.s.config
        z = lambda: r.choice(self.zips)  # noqa: E731
        gens: dict[str, Callable[[], Any]] = {
            "FULL_NAME": f.name,
            "FIRST_NAME": f.first_name,
            "MIDDLE_NAME": f.first_name,
            "LAST_NAME": f.last_name,
            "SUFFIX": lambda: r.choice(["JR", "SR", "II", "III", "Jr.", "IV"]),
            "ADDRESS_FULL": lambda: f.address().replace("\n", ", "),
            "ADDRESS_LINE1": lambda: f"{r.randint(1, 9999)} {f.street_name()}",
            "ADDRESS_LINE2": lambda: (
                r.choice(["Apt", "Unit", "Ste", "#"]) + f" {r.randint(1, 40)}{r.choice('ABCD')}"
            ),
            "CITY": lambda: z()["city"].title(),
            "STATE": lambda: r.choice(STATES),
            "ZIP": lambda: z()["zip_code"],
            "CITY_STATE_ZIP": lambda: (
                lambda q: f"{q['city'].title()}, {q['state']} {q['zip_code']}"
            )(z()),
            "PHONE": lambda: ids.phone(r, ["212", "415", "512", "305", "617", "973"]),
            "EMAIL": lambda: f"{f.user_name()}@{r.choice(cfg.email_domains)}",
            "DOB": lambda: self.date_between(1, 95),
            "SSN": lambda: ids.ssn(r, self.s.known_invalid_ssns, leading_zero=r.random() < 0.08),
            "DL_NUMBER": lambda: ids.drivers_license(
                r, r.choice(list(self.s.dl_formats)), self.s.dl_formats
            ),
            "DL_STATE": lambda: r.choice(list(self.s.dl_formats)),
            "PASSPORT": lambda: ids.passport(r),
            "BANK_ACCOUNT": lambda: ids.bank_account(r),
            "ROUTING": lambda: ids.routing_number(r),
            "CARD": lambda: ids.card_number(r, cfg.card_iins),
            "MRN": lambda: ids.mrn(r),
            "MEMBER_ID": lambda: ids.member_id(r),
            "GROUP_NUMBER": lambda: ids.group_number(r),
            "DIAGNOSIS": lambda: ids.diagnosis_code(r),
            "STUDENT_ID": lambda: ids.student_id(r),
            "SCHOOL": lambda: f"{f.last_name()} {r.choice(SCHOOL_KINDS)}",
            "GUARDIAN_NAME": f.name,
            "EMPLOYEE_ID": lambda: ids.employee_id(r),
            "ORG_NAME": lambda: (
                f"{f.last_name()} {r.choice(['LLC', 'Inc', 'Corp', 'Group', 'Partners'])}"
            ),
            "EIN": lambda: ids.ein(r),
            "FREE_TEXT": lambda: f.sentence(nb_words=r.randint(4, 14)),
            "OTHER": lambda: None,  # chosen per column (see other_column)
        }
        return gens[label]

    def other_column(self, n: int) -> list[str]:
        """OTHER columns: hire dates (DOB confusable), amounts, departments, statuses…"""
        r = self.r
        kind = r.choice(["hire_date", "amount", "department", "status", "plan", "order_no", "flag"])
        make: dict[str, Callable[[], str]] = {
            "hire_date": lambda: self.date_between(0, 30).strftime(
                r.choice(["%m/%d/%Y", "%Y-%m-%d"])
            ),
            "amount": lambda: f"{r.uniform(5, 9000):.2f}",
            "department": lambda: r.choice(
                ["Sales", "Ops", "Finance", "HR", "IT", "Legal", "Fleet"]
            ),
            "status": lambda: r.choice(["Active", "Inactive", "Pending", "Closed"]),
            "plan": lambda: r.choice(["PPO", "HMO", "HDHP", "EPO"]),
            "order_no": lambda: f"ORD-{r.randint(100000, 999999)}",
            "flag": lambda: r.choice(["Y", "N"]),
        }
        return [make[kind]() for _ in range(n)]

    def column(self, label: str, pool: list[Any], n: int) -> list[str]:
        """Sample n values from the pool and format them with one dominant column style."""
        r = self.r
        if label == "OTHER":
            return self.other_column(n)
        vals = [r.choice(pool) for _ in range(n)]
        style = r.random()
        out: list[str] = []
        for v in vals:
            mixed = r.random() < 0.12  # a few cells in another format
            s = style if not mixed else r.random()
            out.append(self.fmt(label, v, s))
        return out

    def fmt(self, label: str, v: Any, s: float) -> str:
        r = self.r
        if label == "DOB":
            d: date = v
            if s < 0.35:
                return d.strftime("%m/%d/%Y")
            if s < 0.55:
                return d.isoformat()
            if s < 0.70:
                return _excel_serial(d)  # Excel serial
            if s < 0.85:
                return f"{d.day} {d.strftime('%b')} {d.year}"
            return d.strftime("%m/%d/%y")
        if label == "SSN":
            if s < 0.45:
                return f"{v[:3]}-{v[3:5]}-{v[5:]}"
            if s < 0.75:
                return v
            if s < 0.88:
                return str(int(v))  # numeric: leading zeros lost
            return f"XXX-XX-{v[5:]}"  # pre-masked
        if label == "ZIP":
            if s < 0.6:
                return v
            if s < 0.85:
                return str(int(v))  # lost leading zero
            return f"{v}-{r.randint(1000, 9999)}"
        if label == "PHONE":
            digits = v[2:]
            if s < 0.3:
                return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
            if s < 0.6:
                return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
            if s < 0.8:
                return digits
            return v
        if label == "CARD":
            if s < 0.45:
                return v
            if s < 0.6:
                return " ".join(v[i : i + 4] for i in range(0, 16, 4))
            if s < 0.75:
                return f"{int(v[:15]) * 10:.5E}"  # sci-notation damage, e.g. 4.11111E+15
            if s < 0.85:
                return f"{int(v[:15]) * 10}.0"
            return f"XXXX-XXXX-XXXX-{v[-4:]}"
        if label == "EMPLOYEE_ID":
            if s < 0.5:
                return v
            if s < 0.75:
                return ids.digits(r, 9)  # 9 digits, no dashes: SSN confusable
            if s < 0.9:
                return v[:5]  # 5 digits: ZIP confusable
            return f"E{v}"
        if label == "MRN":
            return v if s < 0.7 else f"MRN{v}"
        if label == "MEMBER_ID":
            return v if s < 0.7 else v[3:]  # digits only: MRN confusable
        if label == "BANK_ACCOUNT" and s > 0.8:
            return v[:10]  # 10 digits: phone confusable
        if label in {"FIRST_NAME", "LAST_NAME", "FULL_NAME", "CITY"}:
            return v.upper() if s < 0.4 else v
        return str(v)


def _noisy_header(alias: str, rng: random.Random) -> str:
    h = alias
    for k, v in ABBREV.items():
        if k in h and rng.random() < 0.25:
            h = h.replace(k, v)
    roll = rng.random()
    if roll < 0.2:
        h = h.upper()
    elif roll < 0.4:
        h = h.lower()
    if rng.random() < 0.25:
        h = h.replace(" ", "_")
    if rng.random() < 0.08 and len(h) > 4:  # typo: drop one character
        i = rng.randrange(1, len(h) - 1)
        h = h[:i] + h[i + 1 :]
    if rng.random() < 0.08:
        h = rng.choice(["emp_", "cust_", "pt_", "mbr_"]) + h
    return h


def build_column_corpus(
    settings: SynthSettings, aliases_path: Path, out_dir: Path
) -> dict[str, Any]:
    cc = settings.config.column_corpus
    rng = random.Random(settings.config.seed + 707)
    fake = Faker("en_US")
    fake.seed_instance(settings.config.seed + 707)
    aliases: dict[str, list[str]] = yaml.safe_load(aliases_path.read_text(encoding="utf-8"))
    values = _Values(settings, rng, fake)
    pools = {
        lab: [values.raw(lab)() for _ in range(POOL_SIZE)] for lab in aliases if lab != "OTHER"
    }
    labels = list(aliases)
    weights = [WEIGHTS.get(lab, 1) for lab in labels]
    tables_dir = out_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    for old in tables_dir.glob("*.csv"):
        old.unlink()
    label_rows: list[dict[str, Any]] = []
    for t in range(1, cc.tables + 1):
        tid = f"T{t:04d}"
        n_cols = rng.randint(cc.min_cols, cc.max_cols)
        n_rows = rng.randint(cc.min_rows, cc.max_rows)
        cols: list[tuple[str, list[str], str, str, str]] = []
        for c in range(1, n_cols + 1):
            lab = rng.choices(labels, weights)[0]
            if rng.random() < cc.uninformative_header_rate:
                header = rng.choice(UNINFORMATIVE).format(n=c)
                group, kind = f"UNINFORMATIVE:{tid}", "UNINFORMATIVE"
            else:
                k = rng.randrange(len(aliases[lab]))
                header = _noisy_header(aliases[lab][k], rng)
                group, kind = f"{lab}:{k}", "ALIAS"
            col = values.column(lab, pools.get(lab, []), n_rows)
            null_rate = rng.uniform(0.05, 0.40)
            col = ["" if rng.random() < null_rate else v for v in col]
            cols.append((header, col, lab, group, kind))
        with (tables_dir / f"{tid}.csv").open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow([h for h, *_ in cols])
            for i in range(n_rows):
                w.writerow([col[i] for _, col, *_ in cols])
        for c, (header, col, lab, group, kind) in enumerate(cols, start=1):
            label_rows.append(
                {
                    "table_id": tid,
                    "col_idx": c,
                    "header_raw": header,
                    "true_label": lab,
                    "alias_group": group,
                    "header_kind": kind,
                    "n_rows": n_rows,
                    "null_pct": round(sum(1 for v in col if v == "") / n_rows, 4),
                }
            )
    labels_path = out_dir / "labels.csv"
    with labels_path.open("w", encoding="utf-8", newline="") as fh:
        fh.write("# SYNTHETIC - NOT REAL: column-classifier training labels\n")
        w = csv.DictWriter(fh, fieldnames=list(label_rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(label_rows)
    digest = hashlib.sha256()
    for p in sorted(tables_dir.glob("*.csv")):
        digest.update(p.read_bytes())
    return {
        "tables": cc.tables,
        "columns": len(label_rows),
        "uninformative_columns": sum(1 for r in label_rows if r["header_kind"] == "UNINFORMATIVE"),
        "labels": len({r["true_label"] for r in label_rows}),
        "alias_groups": len({r["alias_group"] for r in label_rows if r["header_kind"] == "ALIAS"}),
        "labels_sha256": hashlib.sha256(labels_path.read_bytes()).hexdigest(),
        "tables_sha256": digest.hexdigest(),
    }
