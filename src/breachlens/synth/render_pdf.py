"""Render the synthetic PDFs (reportlab): 4 document types × 2 layout variants.

The layouts are original and generic, "in the style of" common forms; no official
artwork is reproduced. Every page carries a diagonal `SYNTHETIC - NOT REAL` watermark.
Variant A places single-line values to the right of their label; variant B places them
below the label. `invariant=1` keeps the output byte-identical for the same input.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from breachlens.synth import casting as C
from breachlens.synth.casting import PdfPlan
from breachlens.synth.people import Org, Person, Population
from breachlens.synth.records import (
    SUFFIX_PRINT,
    DocRecord,
    Exclusion,
    Mention,
    Rendered,
    address_fields,
    address_lines,
    first_last,
    fmt_ssn,
    last_comma_first,
    mdy,
    name_fields,
    up,
)

WATERMARK = "SYNTHETIC - NOT REAL"
PAGE_W, PAGE_H = letter
LABEL_FONT, VALUE_FONT = "Helvetica", "Courier"


class Form:
    """A one-page form canvas with label/value boxes."""

    def __init__(self, path: Path, doc_type: str, variant: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.c = canvas.Canvas(str(path), pagesize=letter, invariant=1)
        self.c.setAuthor("BreachLens synthetic generator")
        self.c.setTitle(f"{WATERMARK} - {doc_type}")
        self.c.setSubject(WATERMARK)
        self.variant = variant
        self._watermark()

    def _watermark(self) -> None:
        c = self.c
        c.saveState()
        c.setFillColorRGB(0.86, 0.86, 0.86)
        c.setFont("Helvetica-Bold", 54)
        c.translate(PAGE_W / 2, PAGE_H / 2)
        c.rotate(35)
        c.drawCentredString(0, 0, WATERMARK)
        c.restoreState()
        c.setFont("Helvetica", 7)
        c.drawString(40, 24, f"{WATERMARK} - generated test document, contains no real data.")

    def header(self, title: str, subtitle: str = "") -> None:
        self.c.setFont("Helvetica-Bold", 14)
        self.c.drawString(40, PAGE_H - 50, title)
        if subtitle:
            self.c.setFont("Helvetica", 8.5)
            self.c.drawString(40, PAGE_H - 63, subtitle)

    def box(
        self, x: float, top: float, w: float, h: float, label: str, value: str | list[str]
    ) -> None:
        """Draw a box at (x, top) going down; single values honor the variant direction."""
        c = self.c
        y = PAGE_H - top - h
        c.setLineWidth(0.6)
        c.rect(x, y, w, h)
        c.setFont(LABEL_FONT, 7.5)
        c.drawString(x + 4, y + h - 11, label)
        lines = value if isinstance(value, list) else [value]
        c.setFont(VALUE_FONT, 10)
        if self.variant == "A" and len(lines) == 1:
            lx = x + 4 + c.stringWidth(label, LABEL_FONT, 7.5) + 10
            c.drawString(lx, y + h - 11, lines[0])
        else:
            for i, line in enumerate(lines):
                c.drawString(x + 6, y + h - 25 - 12 * i, line)

    def text(
        self, x: float, top: float, lines: list[str], size: float = 10, font: str = VALUE_FONT
    ) -> None:
        self.c.setFont(font, size)
        for i, line in enumerate(lines):
            self.c.drawString(x, PAGE_H - top - i * (size + 4), line)

    def save(self) -> None:
        self.c.showPage()
        self.c.save()


def _money(rng: random.Random, lo: int, hi: int) -> str:
    return f"{rng.randint(lo, hi):,}.{rng.randint(0, 99):02d}"


def _org_lines(o: Org) -> list[str]:
    street, csz = address_lines(address_fields(o.address))
    return [o.name, street, csz]


def _mention(plan: PdfPlan, role: str, p: Person | None, **kw: object) -> Mention:
    return Mention(doc_file=plan.doc_file, source_type="PDF", role=role, person=p, page=1, **kw)  # type: ignore[arg-type]


# ---- WAGE_STATEMENT ---------------------------------------------------------------------
def render_wage_statement(
    plan: PdfPlan, pop: Population, path: Path, rng: random.Random
) -> Rendered:
    p, v = plan.primary, plan.variant
    employer = next(o for o in pop.orgs.values() if o.role == "employer")
    payer = next(o for o in pop.orgs.values() if o.role == "payer")
    n = name_fields(p)
    addr = p.old_address if "P17" in plan.planted and p.old_address else p.address
    a = address_fields(addr)
    # P02: the suffix is printed in its dotted form ("Jr.") on this document.
    sfx_text = SUFFIX_PRINT[n["suffix"]] if "P02" in plan.planted and n["suffix"] else None
    street, csz = address_lines(a)
    addr_lines = [street, csz]
    wages, tax = _money(rng, 38000, 140000), _money(rng, 3000, 25000)
    year = plan.extra["tax_year"]
    f = Form(path, plan.doc_type, v)
    tags = set(plan.planted)
    if v == "A":
        name = first_last(n, sfx_text, title=False)
        ssn = fmt_ssn(p.ssn)
        f.header(
            "WAGE AND TAX STATEMENT",
            f"Tax year {year}  -  Copy B, for the employee's records (synthetic form)",
        )
        f.box(40, 80, 270, 34, "a  Employee's social security number", ssn)
        f.box(310, 80, 262, 34, "b  Employer identification number (EIN)", employer.ein)
        f.box(40, 114, 270, 74, "c  Employer's name, address and ZIP code", _org_lines(employer))
        f.box(310, 114, 262, 37, "1  Wages, tips, other compensation", wages)
        f.box(310, 151, 262, 37, "2  Federal income tax withheld", tax)
        f.box(40, 188, 532, 34, "e  Employee's name", name)
        f.box(40, 222, 532, 60, "f  Employee's address and ZIP code", addr_lines)
        f.box(40, 282, 120, 34, "15  State", a["state"])
        f.box(160, 282, 200, 34, "16  State wages", wages)
        f.box(360, 282, 212, 34, "d  Control number", f"CN{rng.randint(100000, 999999)}")
    else:
        tags.add("P04")
        name = last_comma_first(n, sfx_text)
        ssn = fmt_ssn(p.ssn, " ")
        f.header(
            f"EMPLOYEE EARNINGS SUMMARY - TAX YEAR {year}", "Wage statement, W-2 style (synthetic)"
        )
        f.box(40, 80, 330, 44, "EMPLOYEE (LAST, FIRST M)", name)
        f.box(370, 80, 202, 44, "SOCIAL SECURITY NO.", ssn)
        f.box(370, 124, 202, 44, "EMPLOYER EIN", employer.ein)
        f.box(40, 124, 330, 74, "EMPLOYER", _org_lines(employer))
        f.box(370, 168, 202, 44, "PAYROLL AGENT EIN", payer.ein)
        f.box(40, 198, 330, 44, "PAYROLL AGENT", payer.name)
        f.box(40, 242, 330, 64, "HOME ADDRESS", addr_lines)
        f.box(370, 212, 202, 44, "GROSS WAGES", wages)
        f.box(370, 256, 202, 50, "FEDERAL TAX WITHHELD", tax)
        f.box(40, 306, 120, 44, "STATE", a["state"])
    f.save()
    m = _mention(plan, "EMPLOYEE", p, planted=tags)
    m.fields = {**n, **a, "ssn": p.ssn, "employer": employer.name}
    m.printed = {"name": name, "address": " / ".join(addr_lines), "ssn": ssn}
    exc = [Exclusion(plan.doc_file, "EIN", employer.ein, page=1, planted={"P19"})]
    if v == "B":
        exc.append(Exclusion(plan.doc_file, "EIN", payer.ein, page=1, planted={"P19"}))
    doc = DocRecord(plan.doc_file, "PDF", plan.doc_type, plan.doc_date, scanned=plan.scan)
    return Rendered([m], exc, [doc])


# ---- HEALTH_CLAIM -----------------------------------------------------------------------
def render_health_claim(plan: PdfPlan, pop: Population, path: Path, rng: random.Random) -> Rendered:
    p, v, ins = plan.primary, plan.variant, plan.secondary
    clinic = next(o for o in pop.orgs.values() if o.role == "clinic")
    insurer = next(o for o in pop.orgs.values() if o.role == "insurer")
    n = name_fields(p)
    # P10: city typo with the correct ZIP; P11: ZIP missing its last digit.
    a = address_fields(
        p.address,
        city=plan.extra.get("city_printed"),
        zip5=p.address.zip5[:4] if "P11" in plan.planted else None,
    )
    street, csz = address_lines(a)
    holder = ins if isinstance(ins, Person) else p
    member, group = holder.member_id, holder.group_number
    rel = {"CHILD": "Child", "SPOUSE": "Spouse"}.get(
        p.relationship, "Self" if ins is None else "Other"
    )
    if isinstance(ins, Person) and ins.pid == p.guardian:
        rel = "Child"
    dx = [p.diagnosis, rng.choice(["I10", "Z00.00", "R51.9"])]
    cpt = rng.choice(["99213", "99214", "99203"])
    if v == "A":
        pname = last_comma_first(n)
        dob = mdy(p.dob, sep=" ")
        dos = mdy(plan.doc_date, two_digit_year=True, sep=" ")
    else:
        pname = first_last(n, title=False)
        dob = mdy(p.dob, two_digit_year=True)
        dos = mdy(plan.doc_date)
    if ins is None:
        iname, iaddr = "SAME", ["SAME"]
    elif isinstance(ins, Org):
        iname, iaddr = ins.name, _org_lines(ins)[1:]
    else:
        ni = name_fields(ins)
        iname = last_comma_first(ni) if v == "A" else first_last(ni, title=False)
        iaddr = list(address_lines(address_fields(ins.address)))
    f = Form(path, plan.doc_type, v)
    L = {  # label text per variant
        "A": [
            "1a. INSURED'S I.D. NUMBER",
            "2. PATIENT'S NAME (Last, First, Middle Initial)",
            "3. PATIENT'S BIRTH DATE",
            "4. INSURED'S NAME (Last, First, Middle Initial)",
            "5. PATIENT'S ADDRESS",
            "6. PATIENT RELATIONSHIP TO INSURED",
            "7. INSURED'S ADDRESS",
            "11. INSURED'S POLICY GROUP NUMBER",
            "11c. INSURANCE PLAN NAME",
            "21. DIAGNOSIS CODES",
            "24A. DATE OF SERVICE",
            "24D. PROCEDURE CODE",
            "24J. RENDERING PROVIDER NPI",
            "25. FEDERAL TAX I.D. NUMBER",
            "33. BILLING PROVIDER INFO",
        ],
        "B": [
            "MEMBER ID",
            "PATIENT NAME",
            "PATIENT DOB",
            "SUBSCRIBER NAME",
            "PATIENT ADDRESS",
            "RELATIONSHIP",
            "SUBSCRIBER ADDRESS",
            "GROUP #",
            "PLAN",
            "DX CODES",
            "SERVICE DATE",
            "CPT",
            "PROVIDER NPI",
            "PROVIDER TIN",
            "BILLING PROVIDER",
        ],
    }[v]
    f.header(
        "HEALTH INSURANCE CLAIM" if v == "A" else "PROFESSIONAL SERVICES CLAIM",
        f"Payer: {insurer.name}  -  professional claim style (synthetic)",
    )
    f.box(40, 80, 532, 30, L[0], member)
    f.box(40, 110, 360, 36, L[1], pname)
    f.box(400, 110, 172, 36, L[2], dob)
    f.box(40, 146, 532, 30, L[3], iname)
    f.box(40, 176, 266, 60, L[4], [street, csz])
    f.box(306, 176, 266, 60, L[6], iaddr)
    f.box(40, 236, 200, 30, L[5], rel)
    f.box(240, 236, 332, 30, L[7], group)
    f.box(40, 266, 532, 30, L[8], insurer.name)
    f.box(40, 296, 532, 30, L[9], "   ".join(dx))
    f.box(40, 326, 180, 36, L[10], dos)
    f.box(220, 326, 140, 36, L[11], cpt)
    f.box(360, 326, 212, 36, L[12], clinic.npi)
    f.box(40, 362, 266, 36, L[13], clinic.ein)
    f.box(40, 398, 532, 74, L[14], [*_org_lines(clinic), f"NPI {clinic.npi}"])
    f.save()
    tags = set(plan.planted)
    m = _mention(plan, "PATIENT", p, planted=tags)
    m.fields = {
        **n,
        **a,
        "dob": p.dob.isoformat(),
        "diagnosis": dx[0],
        "procedure": cpt,
        "date_of_service": plan.doc_date.isoformat(),
        "insurer": insurer.name,
    }
    if ins is None:
        m.fields |= {"member_id": member, "group_number": group}
    m.printed = {"name": pname, "address": f"{street} / {csz}", "dob": dob}
    out = Rendered(
        [m], [], [DocRecord(plan.doc_file, "PDF", plan.doc_type, plan.doc_date, scanned=plan.scan)]
    )
    if isinstance(ins, Person):
        mi = _mention(plan, "INSURED", ins, planted=set(plan.secondary_planted), related=None)
        mi.fields = {
            **name_fields(ins),
            **address_fields(ins.address),
            "member_id": member,
            "group_number": group,
            "insurer": insurer.name,
        }
        mi.printed = {"name": iname, "address": " / ".join(iaddr)}
        m.related = mi
        out.mentions.append(mi)
    elif isinstance(ins, Org):
        out.exclusions.append(Exclusion(plan.doc_file, "ORG", ins.name, page=1, planted={"P21"}))
        mo = _mention(plan, "INSURED", None, org=ins, entity_type="ORG", planted={"P21"})
        mo.printed = {"name": iname}
        out.mentions.append(mo)
    out.exclusions += [
        Exclusion(plan.doc_file, "NPI", clinic.npi, page=1, planted={"P20"}),
        Exclusion(plan.doc_file, "PROVIDER_TIN", clinic.ein, page=1, planted={"P20"}),
    ]
    return out


# ---- NEW_HIRE_ID ------------------------------------------------------------------------
def render_new_hire(plan: PdfPlan, pop: Population, path: Path, rng: random.Random) -> Rendered:
    p, v = plan.primary, plan.variant
    employer = next(o for o in pop.orgs.values() if o.role == "employer")
    n = name_fields(p)
    printed_last = n["last"].replace("'", "' ") if "P07" in plan.planted else n["last"]
    a = address_fields(p.address)
    street, csz = address_lines(a)
    use_passport = plan.extra["document"] == "PASSPORT"
    f = Form(path, plan.doc_type, v)
    f.header(
        "NEW HIRE IDENTITY VERIFICATION WORKSHEET"
        if v == "A"
        else "EMPLOYEE ONBOARDING - IDENTITY RECORD",
        f"Employer: {employer.name}  -  internal worksheet (synthetic)",
    )
    if v == "A":
        name = f"{printed_last}, {n['first']}" + (
            f", {n['middle_initial']}" if n["middle_initial"] else ""
        )
        f.box(40, 80, 532, 34, "Legal name (Last, First, Middle)", name)
        f.box(40, 114, 266, 34, "Date of birth", mdy(p.dob))
        f.box(306, 114, 266, 34, "Social Security number", fmt_ssn(p.ssn))
        f.box(40, 148, 532, 60, "Home address", [street, csz])
        f.box(40, 208, 266, 34, "Telephone", p.phone)
        f.box(306, 208, 266, 34, "Email", p.email)
        f.box(40, 242, 266, 34, "Date of hire", mdy(plan.doc_date))
    else:
        name = " ".join(x for x in [n["first"], n["middle_initial"], printed_last] if x)
        f.box(40, 80, 220, 40, "LAST NAME", printed_last)
        f.box(260, 80, 200, 40, "FIRST NAME", n["first"])
        f.box(460, 80, 112, 40, "MIDDLE INITIAL", n["middle_initial"])
        f.box(40, 120, 266, 40, "DATE OF BIRTH", mdy(p.dob))
        f.box(306, 120, 266, 40, "SSN", fmt_ssn(p.ssn))
        f.box(40, 160, 532, 60, "HOME ADDRESS", [street, csz])
        f.box(40, 220, 266, 40, "PHONE", p.phone)
        f.box(306, 220, 266, 40, "HIRE DATE", mdy(plan.doc_date))
    top = 290
    f.text(40, top, ["Section 2 - Identity document presented"], size=10, font="Helvetica-Bold")
    if use_passport:
        doc_fields = {"passport": p.passport}
        f.box(40, top + 10, 200, 40, "Document type", "U.S. PASSPORT")
        f.box(240, top + 10, 200, 40, "Passport number", p.passport)
        f.box(440, top + 10, 132, 40, "Issuing country", "USA")
    else:
        dl_state = "" if "P16" in plan.planted else p.dl_state
        doc_fields = {"dl": p.dl, "dl_state": dl_state}
        f.box(40, top + 10, 200, 40, "Document type", "DRIVER LICENSE")
        f.box(240, top + 10, 200, 40, "License number", p.dl)
        f.box(440, top + 10, 132, 40, "Issuing state", dl_state)
    f.text(40, top + 80, ["Reviewed by: Human Resources Department"], size=8, font="Helvetica")
    f.save()
    m = _mention(plan, "NEW_HIRE", p, planted=set(plan.planted))
    m.fields = {**n, **a, "dob": p.dob.isoformat(), "ssn": p.ssn, "phone": p.phone, **doc_fields}
    if v == "A":
        m.fields["email"] = p.email
    m.printed = {"name": name, "address": f"{street} / {csz}"}
    return Rendered(
        [m], [], [DocRecord(plan.doc_file, "PDF", plan.doc_type, plan.doc_date, scanned=plan.scan)]
    )


# ---- EOB_LETTER -------------------------------------------------------------------------
def _long_date(d: date) -> str:
    return d.strftime("%B ") + f"{d.day}, {d.year}"


def render_eob(plan: PdfPlan, pop: Population, path: Path, rng: random.Random) -> Rendered:
    p, v = plan.primary, plan.variant
    insurer = next(o for o in pop.orgs.values() if o.role == "insurer")
    clinic = next(o for o in pop.orgs.values() if o.role == "clinic")
    n = name_fields(p, with_title=True)
    sfx_text = SUFFIX_PRINT.get(n["suffix"], n["suffix"]) if n["suffix"] else ""
    a = address_fields(p.address)
    street, csz = address_lines(a)
    service = date.fromisoformat(plan.extra["service"])
    cpt = rng.choice(["99213", "99214", "93000", "80053"])
    billed = _money(rng, 120, 900)
    name = first_last(n, sfx_text)
    greet = f"{n['title'].title()}. {p.last}" if n["title"] else f"{p.first} {p.last}"
    claim_no = f"CLM-{rng.randint(1000000, 9999999)}"
    f = Form(path, plan.doc_type, v)
    f.text(
        40,
        50,
        [insurer.name, *_org_lines(insurer)[1:], f"Member services: {insurer.phone}"],
        9,
        "Helvetica",
    )
    f.text(40, 130, [_long_date(plan.doc_date)], 10, "Helvetica")
    f.text(40, 160, [name, street, csz], 10.5)
    if v == "A":
        f.text(
            40,
            230,
            [
                "RE: Explanation of Benefits - this is not a bill",
                f"Member ID: {p.member_id}",
                f"Claim number: {claim_no}",
            ],
            10,
            "Helvetica-Bold",
        )
        body = [
            f"Dear {greet},",
            "",
            f"We have processed a claim for services you received on {mdy(service)} from",
            f"{clinic.name}. The service was billed under procedure code {cpt}.",
            f"The provider billed ${billed}. Your plan paid its share and the remaining",
            "balance, if any, is shown on your provider's statement.",
            "",
            f"Patient: {name}    Member ID: {p.member_id}",
            "",
            "If you have questions, call Member Services at the number above.",
            "",
            "Sincerely,",
            "Claims Department",
        ]
        f.text(40, 290, body, 10, "Helvetica")
    else:
        f.text(
            40, 230, ["EXPLANATION OF BENEFITS (EOB)", f"Claim {claim_no}"], 11, "Helvetica-Bold"
        )
        f.text(
            40,
            270,
            [f"Dear {greet}, here is a summary of a recent claim processed under your plan."],
            10,
            "Helvetica",
        )
        rows = [
            ("Patient name", name),
            ("Member ID", p.member_id),
            ("Date of service", mdy(service)),
            ("Provider", clinic.name),
            ("Procedure", cpt),
            ("Amount billed", f"${billed}"),
        ]
        for i, (label, value) in enumerate(rows):
            f.box(40, 300 + i * 28, 532, 28, label, value)
        f.text(
            40,
            480,
            ["This is not a bill. Keep this notice for your records.", "Claims Department"],
            9,
            "Helvetica",
        )
    f.save()
    m = _mention(plan, "PATIENT", p, planted=set(plan.planted))
    m.fields = {
        **n,
        **a,
        "member_id": p.member_id,
        "procedure": cpt,
        "date_of_service": service.isoformat(),
        "insurer": insurer.name,
    }
    m.printed = {"name": name, "address": f"{street} / {csz}"}
    return Rendered(
        [m], [], [DocRecord(plan.doc_file, "PDF", plan.doc_type, plan.doc_date, scanned=plan.scan)]
    )


RENDERERS: dict[str, Callable[[PdfPlan, Population, Path, random.Random], Rendered]] = {
    C.WAGE_STATEMENT: render_wage_statement,
    C.HEALTH_CLAIM: render_health_claim,
    C.NEW_HIRE_ID: render_new_hire,
    C.EOB_LETTER: render_eob,
}


def render_pdf(plan: PdfPlan, pop: Population, docs_dir: Path, seed: int) -> Rendered:
    rng = random.Random(f"{seed}:{plan.doc_file}")
    return RENDERERS[plan.doc_type](plan, pop, docs_dir / plan.doc_file, rng)


__all__ = ["RENDERERS", "WATERMARK", "render_pdf", "up"]
