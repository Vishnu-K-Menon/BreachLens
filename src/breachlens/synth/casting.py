"""Deterministic casting: which people appear in which PDF, with which planted cases.

Spreadsheet casting lives with each sheet renderer (it is a property of the export),
while PDFs are cast here because several planted cases span document types.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from breachlens.synth.people import BASE, DEPENDENT, STUDENT, Org, Person, Population
from breachlens.synth.settings import SynthSettings

WAGE_STATEMENT = "WAGE_STATEMENT"
HEALTH_CLAIM = "HEALTH_CLAIM"
NEW_HIRE_ID = "NEW_HIRE_ID"
EOB_LETTER = "EOB_LETTER"
FILE_STEM = {
    WAGE_STATEMENT: "wage_statement",
    HEALTH_CLAIM: "health_claim",
    NEW_HIRE_ID: "new_hire_id",
    EOB_LETTER: "eob_letter",
}


@dataclass
class PdfPlan:
    doc_file: str
    doc_type: str
    variant: str
    doc_date: date
    primary: Person
    secondary: Person | Org | None = None
    planted: set[str] = field(default_factory=set)  # applies to the primary mention
    secondary_planted: set[str] = field(default_factory=set)
    scan: bool = False
    extra: dict[str, str] = field(default_factory=dict)


def _fill(chosen: list[Person], pool: list[Person], n: int, rng: random.Random) -> list[Person]:
    used = {p.pid for p in chosen}
    rest = [p for p in pool if p.pid not in used]
    return chosen + rng.sample(rest, n - len(chosen))


def cast_pdfs(pop: Population, settings: SynthSettings) -> list[PdfPlan]:
    cfg = settings.config
    rng = random.Random(cfg.seed + 101)
    counts = cfg.pdf.counts
    base = pop.by_cast(BASE)
    role = pop.role
    employer = next(o for o in pop.orgs.values() if o.role == "employer")
    plans: list[PdfPlan] = []

    def add(doc_type: str, i: int, d: date, primary: Person, **kw: object) -> PdfPlan:
        plan = PdfPlan(
            doc_file=f"pdf/{FILE_STEM[doc_type]}_{i + 1:02d}.pdf",
            doc_type=doc_type,
            variant="AB"[i % 2],
            doc_date=d,
            primary=primary,
            **kw,  # type: ignore[arg-type]
        )
        plans.append(plan)
        return plan

    # WAGE_STATEMENT: P17 (2024 W-2 with the old address), P05, P02, P24, P06, P18 + random.
    special = {
        "mover": {"P17"},
        "nickname": {"P05"},
        "suffix_jr": {"P02"},
        "star": {"P24"},
        "surname_0": {"P06"},
        "twin_a": {"P18"},
    }
    w2 = _fill([role(k) for k in special], base, counts[WAGE_STATEMENT], rng)
    for i, p in enumerate(w2):
        tags = next((v for k, v in special.items() if pop.roles[k] == p.pid), set())
        year = 2024 if p.pid == pop.roles["mover"] else 2025
        add(
            WAGE_STATEMENT,
            i,
            date(year, 12, 31),
            p,
            planted=set(tags) | {"P19", "P41"},
            extra={"tax_year": str(year)},
        )

    # HEALTH_CLAIM: P22, P10, P11, P24, student + guardian, spouse + subscriber, P21, random.
    def service_day() -> date:
        return date(2026, 1, 5) + timedelta(days=rng.randint(0, 250))

    minor = role("minor_dependent")
    student = next(p for p in pop.by_cast(STUDENT) if p.age_on(pop.as_of_date) < 18)
    spouse = next(p for p in pop.by_cast(DEPENDENT) if p.relationship == "SPOUSE")
    claims: list[tuple[Person, Person | Org | None, set[str], set[str]]] = [
        (minor, pop.people[minor.subscriber], {"P22"}, set()),
        (role("city_typo"), None, {"P10"}, set()),
        (role("zip_short"), None, {"P11"}, set()),
        (role("star"), None, {"P24"}, set()),
        (student, pop.people[student.guardian], set(), set()),
        (spouse, pop.people[spouse.subscriber], set(), set()),
    ]
    taken = {c[0].pid for c in claims}
    rest = [p for p in base if p.pid not in taken]
    org_patient, plain = rng.sample(rest, 2)
    claims.append((org_patient, employer, set(), {"P21"}))
    claims.append((plain, None, set(), set()))
    for i, (patient, insured, tags, sec_tags) in enumerate(claims[: counts[HEALTH_CLAIM]]):
        # Variant A (even) prints "LAST, FIRST" (P04); variant B prints 2-digit years (P12).
        tags = set(tags) | {"P20"} | ({"P04"} if i % 2 == 0 else {"P12"})
        extra = {"city_printed": cfg.planted.city_typo.printed} if "P10" in tags else {}
        add(
            HEALTH_CLAIM,
            i,
            service_day(),
            patient,
            secondary=insured,
            planted=tags,
            secondary_planted=sec_tags,
            extra=extra,
        )

    # NEW_HIRE_ID: P15, P16, P07, P24, passport document, accented name.
    hires = [
        ("bad_dl", {"P15"}),
        ("dl_no_state", {"P16"}),
        ("apostrophe", {"P07"}),
        ("star", {"P24"}),
        ("passport_hire", set()),
        ("accented_0", set()),
    ]
    for i, (k, tags) in enumerate(hires[: counts[NEW_HIRE_ID]]):
        p = role(k)
        add(
            NEW_HIRE_ID,
            i,
            p.hire_date or pop.as_of_date,
            p,
            planted=set(tags),
            extra={"document": "PASSPORT" if k == "passport_hire" else "DL"},
        )

    # EOB_LETTER: P01 (DR, REV), P24, P06, P02 (III) + random.
    eob_special = [
        ("title_DR", {"P01"}),
        ("title_REV", {"P01"}),
        ("star", {"P24"}),
        ("surname_1", {"P06"}),
        ("surname_2", {"P06"}),
        ("suffix_iii", {"P02"}),
    ]
    eob = _fill([role(k) for k, _ in eob_special], base, counts[EOB_LETTER], rng)
    for i, p in enumerate(eob):
        tags = next((t for k, t in eob_special if pop.roles[k] == p.pid), set())
        letter = date(2026, 2, 1) + timedelta(days=rng.randint(0, 220))
        service = letter - timedelta(days=rng.randint(14, 45))
        add(EOB_LETTER, i, letter, p, planted=set(tags), extra={"service": service.isoformat()})

    n_scan = round(cfg.pdf.scan.fraction * len(plans))
    for i in sorted(rng.sample(range(len(plans)), n_scan)):
        plans[i].scan = True
    return plans
