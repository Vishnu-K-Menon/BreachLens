"""Ground truth for the synthetic corpus (SYNTHETIC_DATA.md §Ground truth, ADR-047/049/050).

Writes to `truth/`:
- `gt_mentions.csv`  one row per expected mention (raw synthetic values allowed here only)
- `gt_people.csv`    one row per true person: canonical fields, exposure, notification
- `gt_columns.csv`   true semantic label of every corpus spreadsheet column
- `gt_excluded.csv`  EIN / NPI / provider TIN / ORG values the pipeline must exclude
- `gt_shared_addresses.csv` unrelated people sharing a pool address (must not merge)
- `manifest.json`    counts, hashes, planted-case coverage, expected address statuses

Every CSV starts with `# SYNTHETIC GROUND TRUTH - NOT REAL PEOPLE`. Nothing here depends
on the wall clock, so the same seed gives byte-identical files.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import xlrd

from breachlens import __version__
from breachlens.ingest.doc_ids import assign_doc_ids, relative_files
from breachlens.synth.people import (
    BASE,
    EXTRA,
    EXTRA_GUARDIAN,
    Address,
    Person,
    Population,
    shared_address_pairs,
)
from breachlens.synth.records import Mention, Rendered
from breachlens.synth.settings import SynthSettings

HEADER_COMMENT = "# SYNTHETIC GROUND TRUTH - NOT REAL PEOPLE"
PLANTED_CASES = [f"P{i:02d}" for i in range(1, 45)]
ROLE_ORDER = [
    "EMPLOYEE",
    "NEW_HIRE",
    "PATIENT",
    "INSURED",
    "SUBSCRIBER",
    "DEPENDENT",
    "CUSTOMER",
    "MEMBER",
    "STUDENT",
    "GUARDIAN",
]

# element -> display name (DATA_SCHEMA.md §Element display names), in display order
ELEMENTS: list[tuple[str, str]] = [
    ("ssn", "SSN"),
    ("dl", "DRIVER LICENSE"),
    ("state_id", "STATE ID"),
    ("passport", "PASSPORT"),
    ("bank_account", "FINANCIAL ACCOUNT"),
    ("card", "PAYMENT CARD"),
    ("mrn", "MEDICAL INFO"),
    ("diagnosis", "MEDICAL INFO"),
    ("procedure", "MEDICAL INFO"),
    ("date_of_service", "MEDICAL INFO"),
    ("health_member_id", "HEALTH INSURANCE INFO"),
    ("health_group_number", "HEALTH INSURANCE INFO"),
    ("dob", "DATE OF BIRTH"),
    ("student_id", "STUDENT RECORD"),
]
FLAGS = [e for e, _ in ELEMENTS] + ["routing", "employee_id"]
VALUE_FIELDS = [
    "ssn",
    "dl",
    "dl_state",
    "passport",
    "bank_account",
    "routing",
    "card",
    "card_status",
    "mrn",
    "member_id",
    "group_number",
    "insurer",
    "diagnosis",
    "procedure",
    "date_of_service",
    "employee_id",
    "student_id",
    "school",
    "phone",
    "email",
    "relationship",
    "notes_pii",
    "duplicate_of_row",
]
MENTION_COLUMNS = (
    [
        "mention_ref",
        "doc_id",
        "doc_file",
        "source_type",
        "page",
        "sheet",
        "row",
        "person_role",
        "entity_type",
        "true_person_id",
        "related_ref",
        "doc_date",
        "exp_title",
        "exp_first",
        "exp_middle_initial",
        "exp_last",
        "exp_suffix",
        "exp_line1",
        "exp_line2",
        "exp_city",
        "exp_state",
        "exp_zip5",
        "exp_dob",
    ]
    + VALUE_FIELDS
    + [f"has_{f}" for f in FLAGS]
    + ["address_source", "expected_address_status", "printed_name", "planted_case"]
)

POOL, FAKE = "POOL", "FAKE_STREET"


def _flags(f: dict[str, str]) -> dict[str, bool]:
    return {
        "ssn": bool(f.get("ssn")) or f.get("notes_pii") == "SSN",
        "dl": bool(f.get("dl")),
        "state_id": False,
        "passport": bool(f.get("passport")),
        "bank_account": bool(f.get("bank_account")),
        "card": bool(f.get("card")) or f.get("card_status") in {"PRECISION_LOST", "PREMASKED"},
        "mrn": bool(f.get("mrn")) or f.get("notes_pii") == "MRN",
        "diagnosis": bool(f.get("diagnosis")),
        "procedure": bool(f.get("procedure")),
        "date_of_service": bool(f.get("date_of_service")),
        "health_member_id": bool(f.get("member_id")),
        "health_group_number": bool(f.get("group_number")),
        "dob": bool(f.get("dob")),
        "student_id": bool(f.get("student_id")),
        "routing": bool(f.get("routing")),
        "employee_id": bool(f.get("employee_id")),
    }


def _address_of(m: Mention) -> Address | None:
    """Which canonical address the mention printed (current or the P17 old one)."""
    p = m.person
    if p is None or not m.fields.get("line1"):
        return None
    if p.old_address is not None and m.fields["line1"] == p.old_address.line1.upper():
        return p.old_address
    return p.address


def address_source(a: Address | None) -> str:
    return "" if a is None else (POOL if a.pool_id else FAKE)


def expected_status(m: Mention) -> str:
    """Expected address_status with the Census stage online (VALIDATION_RULES.md mapping).

    Verified pool buildings -> VERIFIED; fake streets with a real city+ZIP -> UNVERIFIED;
    P10 city typo with the right ZIP -> CORRECTED; P11 ZIP missing a digit -> INVALID.
    Offline runs report NOT_CHECKED instead.
    """
    a = _address_of(m)
    if a is None:
        return ""
    if "P11" in m.planted:
        return "INVALID"
    if "P10" in m.planted:
        return "CORRECTED"
    return "VERIFIED" if a.pool_id else "UNVERIFIED"


def person_status(p: Person) -> str:
    return "VERIFIED" if p.address.pool_id else "UNVERIFIED"


def content_hash_xls(path: Path) -> str:
    """sha256 over every sheet's cell types and values (LibreOffice .xls bytes vary)."""
    book = xlrd.open_workbook(path)
    cells = [
        [sh.name, [[(c.ctype, c.value) for c in sh.row(r)] for r in range(sh.nrows)]]
        for sh in book.sheets()
    ]
    return hashlib.sha256(json.dumps(cells, ensure_ascii=True).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(HEADER_COMMENT + "\n")
        w = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n", extrasaction="raise")
        w.writeheader()
        for row in rows:
            w.writerow({k: _cell(row.get(k)) for k in columns})


def _cell(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    return str(v)


@dataclass
class TruthSummary:
    mentions: list[dict[str, Any]]
    people: list[dict[str, Any]]
    people_columns: list[str]
    columns: list[dict[str, Any]]
    excluded: list[dict[str, Any]]
    shared_addresses: list[dict[str, Any]]
    manifest: dict[str, Any]


def build_truth(
    pop: Population,
    settings: SynthSettings,
    rendered: Rendered,
    docs_dir: Path,
    extra_stats: dict[str, Any],
) -> TruthSummary:
    cfg = settings.config
    doc_ids = assign_doc_ids(relative_files(docs_dir))
    docs = {d.doc_file: d for d in rendered.docs}
    if set(docs) != set(doc_ids):
        raise AssertionError(f"rendered docs and files differ: {sorted(set(docs) ^ set(doc_ids))}")

    def sort_key(m: Mention) -> tuple:
        return (
            doc_ids[m.doc_file],
            m.page or 0,
            m.sheet or "",
            m.row or 0,
            ROLE_ORDER.index(m.role),
            m.person.pid if m.person else "",
        )

    mentions = sorted(rendered.mentions, key=sort_key)
    for i, m in enumerate(mentions, start=1):
        m.ref = f"GM{i:05d}"

    # ---- gt_mentions ----------------------------------------------------------------
    m_rows: list[dict[str, Any]] = []
    for m in mentions:
        f, doc = m.fields, docs[m.doc_file]
        row: dict[str, Any] = {
            "mention_ref": m.ref,
            "doc_id": doc_ids[m.doc_file],
            "doc_file": m.doc_file,
            "source_type": m.source_type,
            "page": m.page,
            "sheet": m.sheet,
            "row": m.row,
            "person_role": m.role,
            "entity_type": m.entity_type,
            "true_person_id": m.person.pid if m.person else "",
            "related_ref": m.related.ref if m.related else "",
            "doc_date": doc.doc_date.isoformat() if doc.doc_date else "",
            "printed_name": m.printed.get("name", ""),
            "planted_case": ";".join(sorted(m.planted)),
            "address_source": address_source(_address_of(m)),
            "expected_address_status": expected_status(m),
        }
        for k in [
            "title",
            "first",
            "middle_initial",
            "last",
            "suffix",
            "line1",
            "line2",
            "city",
            "state",
            "zip5",
            "dob",
        ]:
            row[f"exp_{k}"] = f.get(k, "") if m.person else ""
        for k in VALUE_FIELDS:
            row[k] = f.get(k, "")
        for k, v in _flags(f).items():
            row[f"has_{k}"] = v if m.person else False
        m_rows.append(row)

    # ---- gt_people ------------------------------------------------------------------
    by_person: dict[str, list[Mention]] = {}
    for m in mentions:
        if m.person is not None:
            by_person.setdefault(m.person.pid, []).append(m)
    missing = sorted(set(pop.people) - set(by_person))
    if missing:
        raise AssertionError(f"people without any mention: {missing}")
    juris = settings.jurisdictions
    p_rows: list[dict[str, Any]] = []
    for pid in sorted(by_person):
        p, ms = pop.people[pid], by_person[pid]
        exposed = {e: any(_flags(m.fields)[e] for m in ms) for e in FLAGS}
        # Demo assumption: a bank account counts as covered only with a routing number in the
        # same mention (VALIDATION_RULES.md §jurisdictions).
        bank_covered = any(
            _flags(m.fields)["bank_account"] and _flags(m.fields)["routing"] for m in ms
        )
        j = p.state if p.state in juris else "default"
        covered = set(juris[j].covered_elements)
        hits = {e for e in covered if exposed.get(e)}
        if "bank_account" in hits and not bank_covered:
            hits.discard("bank_account")
        # ADR-052: a card is present in every case, but only some exposures trigger notice
        # (pre-masked values are treated as redacted) or send the person to review.
        card_rule = settings.element_rules.card
        card_statuses = {
            m.fields.get("card_status") or "TEXT" for m in ms if _flags(m.fields)["card"]
        }
        card_triggers = any(card_rule.triggers(s) for s in card_statuses)
        card_review = bool(card_statuses & set(card_rule.review_on))
        if "card" in hits and not card_triggers:
            hits.discard("card")
        names = list(dict.fromkeys(label for e, label in ELEMENTS if exposed[e]))
        planted = set().union(*(m.planted for m in ms))
        a = p.address
        p_rows.append(
            {
                "true_person_id": pid,
                "cast": p.cast,
                "household": p.household,
                "title": p.title.upper(),
                "first": p.first.upper(),
                "middle_initial": p.middle[:1].upper(),
                "last": p.last.upper(),
                "suffix": p.suffix,
                "line1": a.line1,
                "line2": a.line2,
                "city": a.city,
                "state": a.state,
                "zip5": a.zip5,
                "dob": p.dob.isoformat(),
                "is_minor": p.age_on(cfg.as_of_date) < 18,
                "jurisdiction": p.state,
                "jurisdiction_rules": j,
                **{f"{e}_exposed": exposed[e] for e in FLAGS},
                "elements_exposed": "; ".join(names),
                "card_triggers": card_triggers,
                "card_review": card_review,
                "notify_required": bool(hits),
                "notify_elements": ";".join(sorted(hits)),
                "ferpa_flag": exposed["student_id"],
                "address_source": address_source(a),
                "expected_address_status": person_status(p),
                "n_mentions": len(ms),
                "source_docs": ";".join(sorted({doc_ids[m.doc_file] for m in ms})),
                "source_types": ";".join(sorted({m.source_type for m in ms})),
                "planted_case": ";".join(sorted(planted)),
            }
        )
    person_cols = list(p_rows[0])

    # ---- gt_columns / gt_excluded / gt_shared_addresses -----------------------------
    c_rows = [
        {
            "doc_id": doc_ids[d.doc_file],
            "doc_file": d.doc_file,
            "sheet": sheet,
            "col_idx": idx,
            "header_raw": header,
            "true_label": label,
        }
        for d in sorted(rendered.docs, key=lambda d: doc_ids[d.doc_file])
        for sheet, idx, header, label in d.columns
    ]
    e_rows = sorted(
        (
            {
                "doc_id": doc_ids[e.doc_file],
                "doc_file": e.doc_file,
                "page": e.page,
                "sheet": e.sheet,
                "row": e.row,
                "kind": e.kind,
                "value": e.value,
                "planted_case": ";".join(sorted(e.planted)),
            }
            for e in rendered.exclusions
        ),
        key=lambda r: (r["doc_id"], r["page"] or 0, r["row"] or 0, r["kind"], r["value"]),
    )
    s_rows = [
        {
            "address": key,
            "true_person_id_a": a,
            "true_person_id_b": b,
            "household_a": ha,
            "household_b": hb,
        }
        for key, a, b, ha, hb in shared_address_pairs(pop)
    ]

    # ---- coverage, overlap, address mix ---------------------------------------------
    coverage: dict[str, list[str]] = {c: [] for c in PLANTED_CASES}
    for m in mentions:
        for c in m.planted:
            coverage[c].append(m.ref)
    for d in rendered.docs:
        for c in d.planted:
            coverage[c].append(d.doc_file)
    for e in rendered.exclusions:
        for c in e.planted:
            coverage[c].append(f"exclusion:{e.doc_file}")
    not_covered = [c for c, refs in coverage.items() if not refs]
    if not_covered:
        raise AssertionError(f"planted cases missing: {not_covered}")

    pdf_people = {m.person.pid for m in mentions if m.person and m.source_type == "PDF"}
    sheet_files: dict[str, set[str]] = {}
    for m in mentions:
        if m.person and m.source_type == "SPREADSHEET":
            sheet_files.setdefault(m.person.pid, set()).add(m.doc_file)
    both = sorted(pdf_people & set(sheet_files))
    two_sheets = sorted(pid for pid, files in sheet_files.items() if len(files) >= 2)
    if len(both) < 12 or len(two_sheets) < 5:
        raise AssertionError(
            f"overlap too small: pdf+sheet={len(both)}, 2+ sheets={len(two_sheets)}"
        )

    def mix(people: list[Person]) -> dict[str, int]:
        c = Counter(address_source(p.address) for p in people)
        return {POOL: c.get(POOL, 0), FAKE: c.get(FAKE, 0)}

    groups: dict[str, list[Person]] = {
        "base": [p for p in pop.people.values() if p.cast == BASE],
        "extras": [p for p in pop.people.values() if p.cast in {EXTRA, EXTRA_GUARDIAN}],
        "household_members": [
            p for p in pop.people.values() if p.cast not in {BASE, EXTRA, EXTRA_GUARDIAN}
        ],
    }
    person_status_by_group = {
        g: dict(sorted(Counter(person_status(p) for p in ps).items())) for g, ps in groups.items()
    }
    mention_status = Counter(
        r["expected_address_status"] for r in m_rows if r["expected_address_status"]
    )
    group_of = {p.pid: g for g, ps in groups.items() for p in ps}
    mention_status_by_cast: dict[str, Counter[str]] = {g: Counter() for g in groups}
    for r, m in zip(m_rows, mentions, strict=True):
        if r["expected_address_status"] and m.person:
            mention_status_by_cast[group_of[m.person.pid]][r["expected_address_status"]] += 1

    # ---- manifest -------------------------------------------------------------------
    files = []
    for path, did in sorted(doc_ids.items(), key=lambda kv: kv[1]):
        d = docs[path]
        full = docs_dir / path
        entry: dict[str, Any] = {
            "doc_id": did,
            "doc_file": path,
            "file_kind": d.file_kind,
            "doc_type": d.doc_type,
            "doc_date": d.doc_date.isoformat() if d.doc_date else None,
            "scanned": d.scanned,
            "duplicate_of": d.duplicate_of or None,
            "bytes": full.stat().st_size,
        }
        if d.file_kind == "XLS":
            entry |= {
                "hash_kind": "cell_content_sha256",
                "hash": content_hash_xls(full),
                "hash_note": "LibreOffice-written .xls bytes differ between runs; the hash covers "
                "every sheet's cell types and values instead.",
            }
        else:
            entry |= {"hash_kind": "file_sha256", "hash": sha256_file(full)}
        files.append(entry)
    persons = [m for m in mentions if m.person]
    manifest: dict[str, Any] = {
        "notice": "SYNTHETIC - NOT REAL. Every person, document and identifier is generated.",
        "version": cfg.version,
        "generator_version": __version__,
        "seed": cfg.seed,
        "as_of_date": cfg.as_of_date.isoformat(),
        "counts": {
            "people": len(pop.people),
            "people_by_cast": dict(sorted(Counter(p.cast for p in pop.people.values()).items())),
            "organizations": len(pop.orgs),
            "files": len(files),
            "pdf_by_type": dict(
                sorted(
                    Counter(
                        d.doc_type
                        for d in docs.values()
                        if d.file_kind == "PDF" and not d.duplicate_of
                    ).items()
                )
            ),
            "pdf_scanned": sum(1 for d in docs.values() if d.scanned and not d.duplicate_of),
            "pdf_exact_duplicates": sum(1 for d in docs.values() if d.duplicate_of),
            "spreadsheets": sum(1 for d in docs.values() if d.file_kind in {"XLSX", "XLS", "CSV"}),
            "mentions": len(mentions),
            "person_mentions": len(persons),
            "person_mentions_by_file": dict(sorted(Counter(m.doc_file for m in persons).items())),
            "org_mentions": len(mentions) - len(persons),
            "exclusions_by_kind": dict(
                sorted(Counter(e.kind for e in rendered.exclusions).items())
            ),
            "unrelated_shared_address_pairs": len(s_rows),
            "notify_required": sum(1 for r in p_rows if r["notify_required"]),
            "card_review": sum(1 for r in p_rows if r["card_review"]),
            "ferpa_flagged": sum(1 for r in p_rows if r["ferpa_flag"]),
            "minors": sum(1 for r in p_rows if r["is_minor"]),
        },
        "overlap": {
            "people_in_pdf_and_sheet": len(both),
            "people_in_two_or_more_sheets": len(two_sheets),
        },
        "scanned_docs": sorted(
            d.doc_file for d in docs.values() if d.scanned and not d.duplicate_of
        ),
        "duplicate_files": {d.doc_file: d.duplicate_of for d in docs.values() if d.duplicate_of},
        "address_mix": {g: mix(ps) for g, ps in groups.items()},
        "expected_address_status": {
            "assumes": "Census stage online; offline runs report NOT_CHECKED for every address",
            "rule": "pool building -> VERIFIED, fake street with real city+ZIP -> UNVERIFIED, "
            "P10 city typo -> CORRECTED, P11 short ZIP -> INVALID (ADR-050)",
            "people": dict(sorted(Counter(r["expected_address_status"] for r in p_rows).items())),
            "people_by_group": person_status_by_group,
            "mentions": dict(sorted(mention_status.items())),
            "mentions_by_group": {
                g: dict(sorted(c.items())) for g, c in mention_status_by_cast.items()
            },
        },
        "planted_case_coverage": {
            c: {"count": len(refs), "refs": refs[:10]} for c, refs in coverage.items()
        },
        "files_detail": files,
        **extra_stats,
    }
    return TruthSummary(m_rows, p_rows, person_cols, c_rows, e_rows, s_rows, manifest)


def write_truth(summary: TruthSummary, truth_dir: Path) -> list[Path]:
    s = summary
    truth_dir.mkdir(parents=True, exist_ok=True)
    out = {
        "gt_mentions.csv": (MENTION_COLUMNS, s.mentions),
        "gt_people.csv": (s.people_columns, s.people),
        "gt_columns.csv": (
            ["doc_id", "doc_file", "sheet", "col_idx", "header_raw", "true_label"],
            s.columns,
        ),
        "gt_excluded.csv": (
            ["doc_id", "doc_file", "page", "sheet", "row", "kind", "value", "planted_case"],
            s.excluded,
        ),
        "gt_shared_addresses.csv": (
            ["address", "true_person_id_a", "true_person_id_b", "household_a", "household_b"],
            s.shared_addresses,
        ),
    }
    paths = []
    for name, (cols, rows) in out.items():
        _write_csv(truth_dir / name, cols, rows)
        paths.append(truth_dir / name)
    mpath = truth_dir / "manifest.json"
    mpath.write_text(
        json.dumps(s.manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return [*paths, mpath]
