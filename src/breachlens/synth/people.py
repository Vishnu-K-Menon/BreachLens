"""Synthetic population: base cast, dependents, students, background extras, organizations.

The base cast (40 people across 8 states) appears in several documents. Dependents and
students attach to base households. "Extras" are background people who appear in exactly
one spreadsheet. Planted roles (P05, P06, P08, P17, P18, …) are fixed here so that the
document casting can place them.

Addresses: 80% of base households get a verified public-building address from
`data/reference/address_pool.csv`; the rest get a fake street with a real city + ZIP from
`zipcodes` (expected UNVERIFIED). At most `max_unrelated_households_per_address`
unrelated households share one pool address (ADR-049).
"""

from __future__ import annotations

import csv
import random
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import zipcodes
from faker import Faker

from breachlens.synth import identifiers as ids
from breachlens.synth.settings import SynthSettings

BASE = "BASE"
DEPENDENT = "DEPENDENT"
STUDENT = "STUDENT"
EXTRA = "EXTRA"
EXTRA_GUARDIAN = "EXTRA_GUARDIAN"


@dataclass(frozen=True)
class Address:
    line1: str
    line2: str
    city: str
    state: str
    zip5: str
    pool_id: str | None = None

    def key(self) -> str:
        return f"{self.line1}|{self.city}|{self.state}|{self.zip5}"


@dataclass
class Org:
    org_id: str
    role: str
    name: str
    ein: str
    address: Address
    npi: str = ""
    phone: str = ""


@dataclass
class Person:
    pid: str
    cast: str
    household: str
    first: str
    last: str
    dob: date
    ssn: str
    address: Address
    title: str = ""
    middle: str = ""
    suffix: str = ""
    sex: str = "F"
    dl: str = ""
    dl_state: str = ""
    passport: str = ""
    phone: str = ""
    email: str = ""
    bank_account: str = ""
    routing: str = ""
    card: str = ""
    mrn: str = ""
    member_id: str = ""
    group_number: str = ""
    diagnosis: str = ""
    employee_id: str = ""
    student_id: str = ""
    school: str = ""
    hire_date: date | None = None
    old_address: Address | None = None
    subscriber: str = ""
    relationship: str = ""
    guardian: str = ""
    home_sheet: str = ""
    roles: set[str] = field(default_factory=set)

    @property
    def state(self) -> str:
        return self.address.state

    def age_on(self, day: date) -> int:
        years = day.year - self.dob.year
        return years - ((day.month, day.day) < (self.dob.month, self.dob.day))


@dataclass
class Population:
    people: dict[str, Person]
    orgs: dict[str, Org]
    roles: dict[str, str]  # planted role -> pid
    pool_households: dict[str, list[str]]  # pool_id -> household ids
    as_of_date: date

    def by_cast(self, cast: str) -> list[Person]:
        return [p for p in self.people.values() if p.cast == cast]

    def household_members(self, household: str) -> list[Person]:
        return [p for p in self.people.values() if p.household == household]

    def role(self, name: str) -> Person:
        return self.people[self.roles[name]]


def read_pool(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def ascii_fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


class _Builder:
    def __init__(self, settings: SynthSettings, pool: list[dict[str, str]]) -> None:
        self.s = settings
        self.cfg = settings.config
        self.rng = random.Random(self.cfg.seed)
        self.fake = Faker("en_US")
        self.fake.seed_instance(self.cfg.seed)
        self.people: dict[str, Person] = {}
        self.orgs: dict[str, Org] = {}
        self.roles: dict[str, str] = {}
        self.pool_by_state: dict[str, list[dict[str, str]]] = {}
        for row in pool:
            self.pool_by_state.setdefault(row["state"], []).append(row)
        self.pool_households: dict[str, list[str]] = {}
        self._hh = 0
        self._zip_cache: dict[str, list[dict]] = {}

    # ---- helpers -------------------------------------------------------------------
    def new_pid(self) -> str:
        return f"T{len(self.people) + 1:04d}"

    def new_household(self) -> str:
        self._hh += 1
        return f"H{self._hh:04d}"

    def dob_for_age(self, lo: int, hi: int) -> date:
        ref = self.cfg.as_of_date
        age = self.rng.randint(lo, hi)
        return ref - timedelta(days=age * 365 + self.rng.randint(30, 330))

    def fake_address(self, state: str) -> Address:
        if state not in self._zip_cache:
            rows = [
                z
                for z in zipcodes.filter_by(state=state)
                if z.get("zip_code_type") == "STANDARD" and z.get("active", True)
            ]
            self._zip_cache[state] = sorted(rows, key=lambda z: z["zip_code"])
        z = self.rng.choice(self._zip_cache[state])
        street = f"{self.rng.randint(10, 9899)} {self.fake.street_name()}".upper()
        return Address(street, "", z["city"].upper(), state, z["zip_code"], None)

    @staticmethod
    def pool_address(row: dict[str, str]) -> Address:
        return Address(row["line1"], "", row["city"], row["state"], row["zip5"], row["pool_id"])

    def pool_capacity(self, pool_id: str) -> int:
        cap = self.cfg.max_unrelated_households_per_address
        return cap - len(self.pool_households.get(pool_id, []))

    def claim_pool(self, row: dict[str, str], household: str) -> Address:
        holders = self.pool_households.setdefault(row["pool_id"], [])
        if household not in holders:
            if len(holders) >= self.cfg.max_unrelated_households_per_address:
                raise AssertionError(f"pool address {row['pool_id']} is full")
            holders.append(household)
        return self.pool_address(row)

    def least_used_pool(self, state: str, exclude: set[str] = frozenset()) -> dict[str, str] | None:
        rows = [r for r in self.pool_by_state.get(state, []) if r["pool_id"] not in exclude]
        rows = [r for r in rows if self.pool_capacity(r["pool_id"]) > 0]
        if not rows:
            return None
        fewest = min(len(self.pool_households.get(r["pool_id"], [])) for r in rows)
        return self.rng.choice(
            [r for r in rows if len(self.pool_households.get(r["pool_id"], [])) == fewest]
        )

    def email(self, first: str, last: str) -> str:
        user = ascii_fold(f"{first}.{last}").lower().replace(" ", "").replace("'", "")
        return f"{user}{self.rng.randint(1, 99)}@{self.rng.choice(self.cfg.email_domains)}"

    def adult_ids(self, p: Person) -> None:
        r, rates = self.rng, self.cfg.rates
        p.dl, p.dl_state = ids.drivers_license(r, p.state, self.s.dl_formats), p.state
        if r.random() < rates.passport:
            p.passport = ids.passport(r)
        if r.random() < rates.bank:
            p.bank_account, p.routing = ids.bank_account(r), ids.routing_number(r)
        if r.random() < rates.card:
            p.card = ids.card_number(r, self.cfg.card_iins)
        p.phone = ids.phone(r, self.cfg.area_codes[p.state])
        p.email = self.email(p.first, p.last)

    def health_ids(self, p: Person, group_number: str) -> None:
        p.mrn = ids.mrn(self.rng)
        p.member_id = ids.member_id(self.rng)
        p.group_number = group_number
        p.diagnosis = ids.diagnosis_code(self.rng)

    def make_person(
        self,
        cast: str,
        household: str,
        address: Address,
        age: tuple[int, int],
        last: str | None = None,
    ) -> Person:
        r = self.rng
        sex = r.choice("FM")
        first = self.fake.first_name_female() if sex == "F" else self.fake.first_name_male()
        p = Person(
            pid=self.new_pid(),
            cast=cast,
            household=household,
            first=first,
            last=last or self.fake.last_name(),
            dob=self.dob_for_age(*age),
            ssn=ids.ssn(r, self.s.known_invalid_ssns),
            address=address,
            sex=sex,
        )
        if r.random() < self.cfg.rates.middle:
            p.middle = self.fake.first_name()
        adult = p.age_on(self.cfg.as_of_date) >= 18
        if adult and r.random() < self.cfg.rates.title:
            p.title = r.choice(["MS", "MRS", "DR"] if sex == "F" else ["MR", "DR"])
        if adult and sex == "M" and r.random() < self.cfg.rates.suffix:
            p.suffix = r.choice(["JR", "SR", "II", "III"])
        self.people[p.pid] = p
        return p

    # ---- build steps ------------------------------------------------------------------
    def build_orgs(self) -> None:
        o = self.cfg.organizations
        roles = [
            ("employer", o.employer),
            ("payer", o.payer),
            ("clinic", o.clinic),
            ("insurer", o.insurer),
            ("school_district", o.school_district),
            ("university", o.university),
            ("bank", o.bank),
            ("vendor", o.vendor),
        ]
        states = list(self.cfg.base_people_per_state)
        for i, (role, name) in enumerate(roles, start=1):
            state = states[i % len(states)]
            org = Org(f"O{i:02d}", role, name.upper(), ids.ein(self.rng), self.fake_address(state))
            org.phone = ids.phone(self.rng, self.cfg.area_codes[state])
            if role == "clinic":
                org.npi = ids.npi(self.rng)
            self.orgs[org.org_id] = org
        n_more = self.cfg.n_vendor_rows - len(self.orgs)
        suffixes = ["LLC", "INC", "CORP", "CO", "LLP", "GROUP INC"]
        for j in range(n_more):
            state = self.rng.choice(states)
            base = self.fake.company().replace(",", "").replace(" and ", " & ")
            base = (
                base.rsplit(" ", 1)[0]
                if base.split()[-1] in {"LLC", "Inc", "PLC", "Ltd", "Group"}
                else base
            )
            name = f"{base} {self.rng.choice(suffixes)}".upper()
            org = Org(
                f"V{j + 1:02d}", "vendor_extra", name, ids.ein(self.rng), self.fake_address(state)
            )
            org.phone = ids.phone(self.rng, self.cfg.area_codes[state])
            self.orgs[org.org_id] = org

    def org(self, role: str) -> Org:
        return next(o for o in self.orgs.values() if o.role == role)

    def build_base(self) -> list[Person]:
        ref = self.cfg.as_of_date
        employer_group = ids.group_number(self.rng)
        base: list[Person] = []
        for state, n in self.cfg.base_people_per_state.items():
            for _ in range(n):
                hh = self.new_household()
                p = self.make_person(BASE, hh, Address("", "", "", state, ""), (23, 72))
                p.employee_id = ids.employee_id(self.rng)
                p.hire_date = ref - timedelta(days=self.rng.randint(60, 4000))
                base.append(p)
        for p in base:
            self.adult_ids(p)
            self.health_ids(p, employer_group)
        return base

    def plant_roles(self, base: list[Person]) -> None:
        r, pl = self.rng, self.cfg.planted
        by_state: dict[str, list[Person]] = {}
        for p in base:
            by_state.setdefault(p.state, []).append(p)
        used: set[str] = set()

        def take(name: str, pool: list[Person], **want: str) -> Person:
            cands = [
                p
                for p in pool
                if p.pid not in used and all(getattr(p, k) == v for k, v in want.items())
            ]
            if not cands:
                cands = [p for p in pool if p.pid not in used]
            p = r.choice(cands)
            used.add(p.pid)
            self.roles[name] = p.pid
            p.roles.add(name)
            return p

        big = [p for p in base if p.state not in {"NJ", "MA"}]
        # P18 twins: two PA people, same last name + household, DOBs one day apart.
        twin_a, twin_b = take("twin_a", by_state["PA"]), take("twin_b", by_state["PA"])
        twin_b.last, twin_b.household = twin_a.last, twin_a.household
        twin_b.dob = twin_a.dob + timedelta(days=1)
        twin_b.title = twin_b.suffix = ""
        twin_b.email = self.email(twin_b.first, twin_b.last)
        # P05 nickname, P06 surnames, P07 apostrophe, P08 one-letter variant.
        robert = take("nickname", big, sex="M")
        robert.first, robert.sex = pl.nickname.canonical, "M"
        if not robert.card:
            robert.card = ids.card_number(r, self.cfg.card_iins)
        for i, surname in enumerate(pl.surnames):
            take(f"surname_{i}", big).last = surname
        take("apostrophe", big).last = pl.apostrophe_surname
        take("variant_surname", big).last = pl.variant_surname.canonical
        for i, (first, last) in enumerate(pl.accented):
            p = take(f"accented_{i}", big)
            p.first, p.last = first, last
        # P01 titles.
        for t in pl.titles:
            take(f"title_{t}", big).title = t
        # P02/P03 suffixes.
        take("suffix_jr", big, sex="M").suffix = "JR"
        take("suffix_iii", big, sex="M").suffix = "III"
        for name in ("suffix_jr", "suffix_iii"):
            self.people[self.roles[name]].sex = "M"
        # P44 SSN with a leading zero (stored as an 8-digit number in payroll).
        take("leading_zero_ssn", big).ssn = ids.ssn(r, self.s.known_invalid_ssns, leading_zero=True)
        # P15 / P16 license problems (new-hire PDFs). P15: canonical DL breaks the state format.
        bad = take("bad_dl", [p for p in big if p.state == "CA"] or big)
        bad.dl = ids.digits(r, 8) if bad.state == "CA" else "X" + ids.digits(r, 3)
        take("dl_no_state", big)
        take("passport_hire", big).passport = ids.passport(r)
        # P10 city typo (Sacramento pool address), P11 ZIP missing a digit (TX).
        take("city_typo", by_state["CA"])
        take("zip_short", by_state["TX"])
        take("mover", big)  # P17
        take("star", big)  # P24
        take("subscriber_minor", big)  # P22 parent
        for p in base:
            p.email = self.email(p.first, p.last)

    def add_dependents(self, base: list[Person]) -> None:
        r = self.rng
        cands = [p for p in base if not p.roles & {"twin_a", "twin_b"}]
        subs = [self.role("subscriber_minor")] + r.sample(
            [p for p in cands if p.pid != self.roles["subscriber_minor"]], 4
        )
        plan = [
            ("CHILD", (3, 11)),
            ("CHILD", (6, 15)),
            ("SPOUSE", (25, 60)),
            ("CHILD", (8, 17)),
            ("CHILD", (19, 23)),
            ("SPOUSE", (30, 65)),
            ("CHILD", (1, 9)),
            ("CHILD", (10, 16)),
            ("CHILD", (12, 17)),
            ("CHILD", (18, 22)),
        ]
        for i, (rel, age) in enumerate(plan[: self.cfg.n_dependents]):
            sub = subs[i % len(subs)]
            last = sub.last if rel == "CHILD" or r.random() < 0.7 else None
            d = self.make_person(DEPENDENT, sub.household, sub.address, age, last=last)
            d.subscriber, d.relationship = sub.pid, rel
            d.title = d.suffix = "" if rel == "CHILD" else d.title
            if d.age_on(self.cfg.as_of_date) >= 18:
                self.adult_ids(d)
            self.health_ids(d, sub.group_number)
            if i == 0:
                d.roles.add("minor_dependent")
                self.roles["minor_dependent"] = d.pid

    def role(self, name: str) -> Person:
        return self.people[self.roles[name]]

    def add_students(self, base: list[Person]) -> None:
        r = self.rng
        busy = {self.roles[k] for k in ("twin_a", "twin_b", "mover")}
        guardians = r.sample([p for p in base if p.pid not in busy], self.cfg.n_students)
        district, uni = self.org("school_district"), self.org("university")
        for i, g in enumerate(guardians):
            minor = i < 5
            s = self.make_person(
                STUDENT, g.household, g.address, (12, 17) if minor else (18, 21), last=g.last
            )
            s.title = s.suffix = ""
            s.guardian = g.pid
            s.student_id = ids.student_id(r)
            s.school = (district if minor else uni).name
            if not minor:
                self.adult_ids(s)
            self.health_ids(s, g.group_number)

    def assign_addresses(self) -> None:
        """Pool or fake address per household (base cast), honoring the reuse cap."""
        heads: dict[str, Person] = {}
        for p in self.people.values():
            if p.cast == BASE and p.household not in heads:
                heads[p.household] = p
        by_state: dict[str, list[str]] = {}
        for hh, p in heads.items():
            by_state.setdefault(p.state, []).append(hh)
        hh_addr: dict[str, Address] = {}
        typo_hh = self.role("city_typo").household
        sac = next(
            r for r in self.pool_by_state["CA"] if r["city"] == self.cfg.planted.city_typo.city
        )
        hh_addr[typo_hh] = self.claim_pool(sac, typo_hh)
        for state, all_hhs in by_state.items():
            hhs = [h for h in all_hhs if h not in hh_addr]
            already = len(all_hhs) - len(hhs)  # the P10 household is pre-assigned
            k = round(self.cfg.pool_share * len(all_hhs)) - already
            self.rng.shuffle(hhs)
            for i, hh in enumerate(hhs):
                row = self.least_used_pool(state) if i < k else None
                hh_addr[hh] = self.claim_pool(row, hh) if row else self.fake_address(state)
        # P09: three households get a unit (APT 6F / UPPER / LOWER).
        unit_hh = self.rng.sample(sorted(h for h in hh_addr if h != typo_hh), 3)
        for hh, unit in zip(unit_hh, ["APT 6F", "UPPER", "LOWER"], strict=True):
            a = hh_addr[hh]
            hh_addr[hh] = Address(a.line1, unit, a.city, a.state, a.zip5, a.pool_id)
            self.roles[f"unit_{unit.split()[0].lower()}"] = heads[hh].pid
        for p in self.people.values():
            if p.household in hh_addr:
                p.address = hh_addr[p.household]
        # P17 mover: old address in the same state (pool if capacity, else fake).
        mover = self.role("mover")
        row = self.least_used_pool(mover.state, exclude={mover.address.pool_id or ""})
        mover.old_address = (
            self.claim_pool(row, mover.household) if row else self.fake_address(mover.state)
        )
        for p in self.people.values():  # phones follow the final state
            if p.phone:
                p.phone = ids.phone(self.rng, self.cfg.area_codes[p.state])

    def add_extras(self) -> None:
        r, cfg = self.rng, self.cfg
        states = list(cfg.base_people_per_state)
        weights = list(cfg.base_people_per_state.values())
        group = ids.group_number(r)
        for sheet, n in cfg.sheets.extras.items():
            for i in range(n):
                state = r.choices(states, weights)[0]
                hh = self.new_household()
                row = self.least_used_pool(state) if r.random() < cfg.extras_pool_share else None
                addr = self.claim_pool(row, hh) if row else self.fake_address(state)
                student = sheet == "student_roster.xlsx"
                p = self.make_person(EXTRA, hh, addr, (12, 17) if student else (20, 80))
                p.home_sheet = sheet
                p.phone = ids.phone(r, cfg.area_codes[state])
                if student:
                    p.title = p.suffix = ""
                    p.student_id = ids.student_id(r)
                    p.school = self.org("school_district").name
                    g = self.make_person(EXTRA_GUARDIAN, hh, addr, (32, 60), last=p.last)
                    g.home_sheet, p.guardian = sheet, g.pid
                    g.phone = ids.phone(r, cfg.area_codes[state])
                    if i == 0:
                        self.roles["guardian_only"] = g.pid
                else:
                    self.adult_ids(p)
                    self.health_ids(p, group)
                if sheet in {"hr_roster.xlsx"}:
                    p.employee_id = ids.employee_id(r)
                    p.hire_date = cfg.as_of_date - timedelta(days=r.randint(60, 3000))
                if sheet == "customer_cards.xlsx" and not p.card:
                    p.card = ids.card_number(r, cfg.card_iins)
        # P13 invalid SSNs on two singletons (hr_roster: area 666, legacy: group 00).
        hr = [p for p in self.people.values() if p.home_sheet == "hr_roster.xlsx"]
        lg = [p for p in self.people.values() if p.home_sheet == "legacy_export.xls"]
        a, b = r.choice(hr), r.choice(lg)
        a.ssn = "666" + a.ssn[3:]
        b.ssn = b.ssn[:3] + "00" + b.ssn[5:]
        self.roles["ssn_area_666"], self.roles["ssn_group_00"] = a.pid, b.pid
        # P14 Luhn failure on one customer extra.
        c = r.choice([p for p in self.people.values() if p.home_sheet == "customer_cards.xlsx"])
        c.card = ids.break_luhn(c.card)
        self.roles["luhn_fail"] = c.pid


def build_population(settings: SynthSettings, pool: list[dict[str, str]]) -> Population:
    b = _Builder(settings, pool)
    b.build_orgs()
    base = b.build_base()
    b.plant_roles(base)
    b.add_dependents(base)
    b.add_students(base)
    b.assign_addresses()
    b.add_extras()
    return Population(
        people=b.people,
        orgs=b.orgs,
        roles=b.roles,
        pool_households=b.pool_households,
        as_of_date=settings.config.as_of_date,
    )


def check_reuse_cap(pop: Population, cap: int) -> None:
    """ADR-049: at most `cap` unrelated households per pool address."""
    holders: dict[str, set[str]] = {}
    for p in pop.people.values():
        for a in (p.address, p.old_address):
            if a is not None and a.pool_id:
                holders.setdefault(a.pool_id, set()).add(p.household)
    over = {k: sorted(v) for k, v in holders.items() if len(v) > cap}
    if over:
        raise AssertionError(f"address reuse cap exceeded: {over}")


def shared_address_pairs(pop: Population) -> list[tuple[str, str, str, str, str]]:
    """(address, pid_a, pid_b, household_a, household_b) for unrelated people at one address."""
    at: dict[str, list[Person]] = {}
    for p in pop.people.values():
        for a in (p.address, p.old_address):
            if a is not None and a.pool_id:
                at.setdefault(a.key(), []).append(p)
    pairs = []
    for key in sorted(at):
        ps = sorted({p.pid: p for p in at[key]}.values(), key=lambda p: p.pid)
        for i, a in enumerate(ps):
            for b in ps[i + 1 :]:
                if a.household != b.household:
                    pairs.append((key, a.pid, b.pid, a.household, b.household))
    return pairs
