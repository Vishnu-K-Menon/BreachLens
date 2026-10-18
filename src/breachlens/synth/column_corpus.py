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

ACCENTED_FIRST = ["José", "Renée", "Zoë", "Chloé", "André", "Inés", "Noël", "Jürgen"]
ACCENTED_LAST = ["Muñoz", "Lefèvre", "Brückner", "Peña", "García", "Núñez", "Müller"]
PARTICLES = ["De La", "Van", "Van der", "De", "Del", "Da", "St."]
ORG_WORDS = [
    "Mutual",
    "Health",
    "Logistics",
    "Supply",
    "Services",
    "Bank",
    "Savings",
    "Clinic",
    "Holdings",
    "Systems",
    "Medical",
    "Family",
    "Insurance",
    "Partners",
]
SCHOOL_SYSTEMS = ["Unified School District", "State University", "Community College"]
SHORT_NOTES = [
    "Follow-up in {n} weeks.",
    "Prefers morning appointments.",
    "Allergy list reviewed.",
    "Requested paper statements.",
    "Left voicemail {d}.",
    "Address updated {d}.",
    "Seen {n} times.",
]
PII_NOTES = ["Verified SSN {v} on file.", "Old MRN {v} merged.", "Called back on {v}."]
DEPARTMENTS = [
    "Sales",
    "Ops",
    "Finance",
    "HR",
    "IT",
    "Legal",
    "Fleet",
    "Customer Service",
    "Field Operations",
    "Accounts Payable",
    "Warehouse",
]
PLANS = ["PPO", "HMO", "HDHP", "EPO", "PPO Standard", "HMO Plus", "HDHP + HSA", "Dental Basic"]
OTHER_KINDS = [
    "hire_date",
    "amount",
    "department",
    "status",
    "plan",
    "order_no",
    "flag",
    "pay_date",
    "count",
]
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
            "FULL_NAME": self.person_name,
            "FIRST_NAME": self.first,
            "MIDDLE_NAME": self.first,
            "LAST_NAME": self.last,
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
            "SCHOOL": self.school,
            "GUARDIAN_NAME": self.person_name,
            "EMPLOYEE_ID": lambda: ids.employee_id(r),
            "ORG_NAME": self.org_name,
            "EIN": lambda: ids.ein(r),
            "FREE_TEXT": self.note,
            "OTHER": lambda: None,  # chosen per column (see other_column)
        }
        return gens[label]

    # ---- realistic text values (names, organizations, schools, notes) ----------------
    def first(self) -> str:
        r = self.r
        if r.random() < 0.04:
            return r.choice(ACCENTED_FIRST)
        name = self.f.first_name()
        return f"  {name} " if r.random() < 0.02 else name

    def last(self) -> str:
        r, f = self.r, self.f
        roll = r.random()
        if roll < 0.05:
            return f"{f.last_name()}-{f.last_name()}"
        if roll < 0.09:
            return f"{r.choice(PARTICLES)} {f.last_name()}"
        if roll < 0.11:
            return r.choice(ACCENTED_LAST)
        if roll < 0.12:
            return "O" + chr(39) + f.last_name()
        return f.last_name()

    def person_name(self) -> tuple[str, str, str, str]:
        """(first, middle, last, suffix); the column style decides how it is printed."""
        r = self.r
        middle = self.f.first_name() if r.random() < 0.6 else ""
        suffix = r.choice(["Jr.", "JR", "Sr.", "II", "III"]) if r.random() < 0.08 else ""
        return self.first().strip(), middle, self.last(), suffix

    def org_name(self) -> str:
        r, f = self.r, self.f
        shape = r.random()
        if shape < 0.35:
            words = [f.last_name()]
        elif shape < 0.70:
            words = [f.last_name(), r.choice(ORG_WORDS)]
        else:
            words = [f.city(), r.choice(ORG_WORDS), r.choice(ORG_WORDS)]
        tail = r.choice(["LLC", "Inc", "Corp", "Group", "Partners", "Co", "Plan", ""])
        return " ".join([*words, tail]).strip()

    def school(self) -> str:
        r, f = self.r, self.f
        if r.random() < 0.6:
            return f"{f.last_name()} {r.choice(SCHOOL_KINDS)}"
        return f"{f.city()} {r.choice(SCHOOL_SYSTEMS)}"

    def note(self) -> str:
        r, f = self.r, self.f
        roll = r.random()
        if roll < 0.35:
            day = f"{r.randint(1, 12):02d}/{r.randint(1, 28):02d}"
            return r.choice(SHORT_NOTES).format(n=r.randint(1, 12), d=day)
        if roll < 0.45:  # PII in prose, as in real comment fields
            value = r.choice(
                [
                    f"{r.randint(100, 899)}-{r.randint(10, 99)}-{r.randint(1000, 9999)}",
                    str(r.randint(10_000_000, 99_999_999)),
                    f"(212) 555-01{r.randint(10, 99)}",
                ]
            )
            return r.choice(PII_NOTES).format(v=value)
        return f.sentence(nb_words=r.randint(4, 14))

    def other_column(self, n: int) -> list[str]:
        """OTHER columns: hire dates (DOB confusable), amounts, departments, statuses…"""
        r = self.r
        kind = r.choice(OTHER_KINDS)
        make: dict[str, Callable[[], str]] = {
            "hire_date": lambda: self.date_between(0, 30).strftime(
                r.choice(["%m/%d/%Y", "%Y-%m-%d"])
            ),
            "amount": lambda: f"{r.uniform(5, 9000):.2f}",
            "department": lambda: r.choice(DEPARTMENTS),
            "status": lambda: r.choice(["Active", "Inactive", "Pending", "Closed"]),
            "plan": lambda: r.choice(PLANS),
            "order_no": lambda: f"ORD-{r.randint(100000, 999999)}",
            "flag": lambda: r.choice(["Y", "N"]),
            "pay_date": lambda: self.date_between(0, 2).strftime(
                r.choice(["%m/%d/%Y", "%Y-%m-%d"])
            ),
            "count": lambda: str(r.randint(0, 40)),
        }
        return [make[kind]() for _ in range(n)]

    def column(self, label: str, pool: list[Any], n: int) -> list[str]:
        """Sample n values from the pool and format them with one dominant column style."""
        r = self.r
        if label == "OTHER":
            return self.other_column(n)
        # Real exports repeat entities (several rows per person) and hold constant columns.
        roll = r.random()
        if roll < 0.04:
            pool = [r.choice(pool)]
        elif roll < 0.30 and n < len(pool):
            pool = r.sample(pool, max(3, int(n * r.uniform(0.3, 0.9))))
        vals = [r.choice(pool) for _ in range(n)]
        style = r.random()
        mix = 0.0 if r.random() < 0.5 else r.uniform(0.03, 0.20)  # half the columns are pure
        out: list[str] = []
        for v in vals:
            s = style if r.random() >= mix else r.random()
            out.append(self.fmt(label, v, s))
        return out

    def fmt(self, label: str, v: Any, s: float) -> str:
        r = self.r
        if label in {"FULL_NAME", "GUARDIAN_NAME"}:
            return _format_name(v, s)
        if label in {"FIRST_NAME", "LAST_NAME", "MIDDLE_NAME", "CITY", "ORG_NAME", "SCHOOL"}:
            return str(v).upper() if s < 0.3 else str(v)
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


def _format_name(v: tuple[str, str, str, str], s: float) -> str:
    """Print (first, middle, last, suffix) in one of the formats real exports use."""
    first, middle, last, suffix = v
    mi = f"{middle[0]}." if middle else ""
    if s < 0.30:
        text = f"{first} {last}"
    elif s < 0.50:
        text = " ".join(x for x in [first, mi, last, suffix] if x)
    elif s < 0.70:
        head = f"{last} {suffix}".strip()
        tail = f"{first} {middle[:1]}".strip()
        text = f"{head}, {tail}"
    elif s < 0.85:
        text = " ".join(x for x in [first, middle, last] if x)
    else:
        text = f"{last}, {first}"
    return text.upper() if (s * 7) % 1 < 0.3 else text


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
            # Real exports have complete, partly empty and sparse columns.
            roll = rng.random()
            if roll < 0.40:
                null_rate = 0.0
            elif roll < 0.85:
                null_rate = rng.uniform(0.01, 0.40)
            else:
                null_rate = rng.uniform(0.50, 0.95)
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
