"""What the renderers report back: one `Mention` per person per document location,
exclusions (EIN/NPI/TIN/ORG), and one `DocRecord` per file. Ground truth is built
from these, so every value in it is exactly what was rendered.

`Mention.fields` holds the *expected normalized* values (uppercase, digits-only IDs,
ISO dates). `Mention.printed` holds the raw rendered strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from breachlens.synth.people import Address, Org, Person

SUFFIX_PRINT = {"JR": "Jr.", "SR": "Sr.", "II": "II", "III": "III"}


@dataclass
class Mention:
    doc_file: str
    source_type: str
    role: str
    person: Person | None
    org: Org | None = None
    entity_type: str = "PERSON"
    page: int | None = None
    sheet: str | None = None
    row: int | None = None
    fields: dict[str, str] = field(default_factory=dict)
    printed: dict[str, str] = field(default_factory=dict)
    planted: set[str] = field(default_factory=set)
    related: Mention | None = None
    ref: str = ""


@dataclass
class Exclusion:
    doc_file: str
    kind: str
    value: str
    page: int | None = None
    sheet: str | None = None
    row: int | None = None
    planted: set[str] = field(default_factory=set)


@dataclass
class DocRecord:
    doc_file: str
    file_kind: str
    doc_type: str
    doc_date: date | None
    scanned: bool = False
    duplicate_of: str = ""
    planted: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)
    # (sheet, col_idx 1-based, header_raw after layout fix, true label) for gt_columns.csv
    columns: list[tuple[str, int, str, str]] = field(default_factory=list)
    # free-text description of each mess, for the preview summary
    messes: list[str] = field(default_factory=list)


@dataclass
class Rendered:
    mentions: list[Mention] = field(default_factory=list)
    exclusions: list[Exclusion] = field(default_factory=list)
    docs: list[DocRecord] = field(default_factory=list)

    def extend(self, other: Rendered) -> None:
        self.mentions += other.mentions
        self.exclusions += other.exclusions
        self.docs += other.docs


# ---- formatting helpers -------------------------------------------------------------
def up(s: str) -> str:
    return " ".join(s.upper().split())


def middle_initial(p: Person) -> str:
    return p.middle[:1].upper()


def name_fields(
    p: Person,
    *,
    first: str | None = None,
    last: str | None = None,
    suffix: str | None = None,
    with_title: bool = False,
    with_middle: bool = True,
) -> dict[str, str]:
    """Expected normalized name parts for a mention (optionally overriding first/last)."""
    return {
        "title": up(p.title) if with_title else "",
        "first": up(first if first is not None else p.first),
        "middle_initial": middle_initial(p) if with_middle else "",
        "last": up(last if last is not None else p.last),
        "suffix": up(suffix if suffix is not None else p.suffix),
    }


def first_last(n: dict[str, str], suffix_text: str | None = None, title: bool = True) -> str:
    parts = [
        n["title"] + "." if title and n["title"] else "",
        n["first"],
        n["middle_initial"],
        n["last"],
    ]
    sfx = suffix_text if suffix_text is not None else n["suffix"]
    return " ".join(x for x in [*parts, sfx] if x)


def last_comma_first(n: dict[str, str], suffix_text: str | None = None) -> str:
    sfx = suffix_text if suffix_text is not None else n["suffix"]
    head = " ".join(x for x in [n["last"], sfx] if x)
    tail = " ".join(x for x in [n["first"], n["middle_initial"]] if x)
    return f"{head}, {tail}"


def address_fields(
    a: Address, *, city: str | None = None, zip5: str | None = None
) -> dict[str, str]:
    return {
        "line1": up(a.line1),
        "line2": up(a.line2),
        "city": up(city if city is not None else a.city),
        "state": a.state,
        "zip5": zip5 if zip5 is not None else a.zip5,
    }


def address_lines(f: dict[str, str], unit_inline: str | None = None) -> tuple[str, str]:
    """(street line, 'CITY, ST ZIP') as printed; `unit_inline` puts the unit on line 1."""
    street = f["line1"]
    if f["line2"]:
        street = f"{street} {unit_inline if unit_inline is not None else f['line2']}"
    return street, f"{f['city']}, {f['state']} {f['zip5']}"


def fmt_ssn(ssn: str, sep: str = "-") -> str:
    return f"{ssn[:3]}{sep}{ssn[3:5]}{sep}{ssn[5:]}"


def mdy(d: date, two_digit_year: bool = False, sep: str = "/") -> str:
    y = f"{d.year % 100:02d}" if two_digit_year else f"{d.year}"
    return f"{d.month:02d}{sep}{d.day:02d}{sep}{y}"
