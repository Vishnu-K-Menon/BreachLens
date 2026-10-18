from datetime import date
from pathlib import Path

import pytest

from breachlens.extract.templates import (
    LABEL_NOT_FOUND,
    NO_VALUE,
    OK,
    PATTERN_MISS,
    Extractor,
    FieldSpec,
    Page,
    Template,
    extract,
    label_regex,
    load_templates,
    parse_date,
    repair_digits,
    repair_shape,
)
from breachlens.ingest.tokens import Token

ROOT = Path(__file__).resolve().parents[2]
AS_OF = date(2026, 10, 1)


def T(text, x0, top, size=10.0, conf=1.0):
    return Token(text, x0, top, x0 + 6 * len(text), top + size, conf)


def words(line_text, x0, top, size=10.0, gap=6.0):
    out, x = [], x0
    for w in line_text.split():
        out.append(T(w, x, top, size))
        x += 6 * len(w) + gap
    return out


@pytest.mark.parametrize(
    ("label", "line", "hit"),
    [
        ("Employee's name", "e Employee's name JOAN", True),
        ("Employee's name", "e Employee'sname JOAN", True),  # OCR dropped the space
        ("Employee's name", "c Employer's name, address", False),
        ("PATIENT NAME", "PATIENT NAMES", False),
    ],
)
def test_label_regex_whole_words_space_tolerant(label, line, hit):
    assert bool(label_regex(FieldSpec(label=label)).search(line)) is hit


@pytest.mark.parametrize(
    ("value", "shape", "out"),
    [
        ("SVY09743953S", "LLLDDDDDDDDD", "SVY097439535"),
        ("2O0.00", "L*", "ZO0.00"),
        ("R51.9", "L*", "R51.9"),
    ],
)
def test_repair_shape(value, shape, out):
    assert repair_shape(value, shape) == out


def test_repair_digits_maps_lookalikes_and_drops_stray_marks():
    assert repair_digits("O1 26 2S") == "01 26 25"
    assert repair_digits("52~-0013389") == "52-0013389"


@pytest.mark.parametrize(
    ("text", "fmt", "iso"),
    [
        ("12/08/65", "%m/%d/%y", "1965-12-08"),
        ("03/04/26", "%m/%d/%y", "2026-03-04"),
        ("03/04/27", "%m/%d/%y", "1927-03-04"),
        ("04 30 2018", "%m %d %Y", "2018-04-30"),
    ],
)
def test_parse_date_pivots_on_as_of(text, fmt, iso):
    assert parse_date(text, [fmt], AS_OF).isoformat() == iso


def test_parse_date_failure_is_none():
    assert parse_date("13/45/90", ["%m/%d/%y"], AS_OF) is None


def _template(**persons) -> Template:
    return Template.model_validate(
        {"doc_type": "X", "layout": "A", "keywords": [{"text": "x"}], "persons": persons}
    )


def test_right_value_stops_at_the_next_label():
    toks = words("2. PATIENT'S NAME CARNEY, MICHELLE E", 44, 113) + words(
        "3. BIRTH DATE 04 30 2018", 404, 113
    )
    t = _template(
        PATIENT={
            "fields": {
                "raw_name": {"label": "2. PATIENT'S NAME"},
                "dob": {
                    "label": "3. BIRTH DATE",
                    "charset": "digits",
                    "parse": "date",
                    "pattern": r"\d{2} \d{2} \d{4}",
                    "formats": ["%m %d %Y"],
                },
            }
        }
    )
    ex = extract(t, toks, ocr=False, as_of=AS_OF)
    assert ex.persons["PATIENT"]["raw_name"] == "CARNEY, MICHELLE E"
    assert ex.persons["PATIENT"]["dob"] == "2018-04-30"
    assert ex.persons["PATIENT"]["_raw_dob"] == "04 30 2018"


def test_below_value_stays_in_its_column_and_skips_box_labels():
    toks = (
        words("HOME ADDRESS", 44, 248, 7.5)
        + words("FEDERAL TAX WITHHELD", 374, 256, 7.5)
        + words("2461 BRYANT TERRACE", 46, 261)
        + words("11,996.54", 377, 273)
        + words("GREENFIELD, CA 93927", 46, 273)
    )
    t = Template.model_validate(
        {
            "doc_type": "X",
            "layout": "B",
            "keywords": [{"text": "x"}],
            "boundaries": ["FEDERAL TAX WITHHELD"],
            "persons": {
                "P": {
                    "fields": {
                        "raw_name": {"label": "HOME ADDRESS", "direction": "below"},
                        "raw_address": {"label": "HOME ADDRESS", "direction": "below", "lines": 2},
                    }
                }
            },
        }
    )
    ex = extract(t, toks, ocr=False, as_of=AS_OF)
    assert ex.persons["P"]["raw_address"] == "2461 BRYANT TERRACE\nGREENFIELD, CA 93927"


def test_statuses_label_missing_no_value_pattern_miss():
    toks = words("SSN", 44, 85, 7.5) + words("MEMBER ID ABC", 44, 120)
    page = Page(toks, ocr=False)
    t = _template(P={"fields": {}})
    ex = Extractor(t, page, AS_OF)
    assert ex.value(FieldSpec(label="PASSPORT"))[2] == LABEL_NOT_FOUND
    ex = Extractor(
        _template(P={"fields": {"a": {"label": "SSN", "direction": "below"}}}), page, AS_OF
    )
    assert ex.value(FieldSpec(label="SSN", direction="below", max_distance=10))[2] == NO_VALUE
    ex = Extractor(_template(P={"fields": {"a": {"label": "MEMBER ID"}}}), page, AS_OF)
    assert ex.value(FieldSpec(label="MEMBER ID", pattern=r"\d{9}"))[2] == PATTERN_MISS
    assert ex.value(FieldSpec(label="MEMBER ID"))[2] == OK


def test_same_insured_merges_ids_into_patient_and_compose_name():
    toks = (
        words("PATIENT NAME", 44, 110, 7.5)
        + words("LEE K HERNANDEZ", 46, 123)
        + words("SUBSCRIBER NAME", 44, 147, 7.5)
        + words("SAME", 46, 160)
        + words("MEMBER ID", 300, 147, 7.5)
        + words("SVY097439533", 302, 160)
    )
    t = _template(
        PATIENT={"fields": {"raw_name": {"label": "PATIENT NAME", "direction": "below"}}},
        INSURED={
            "merge_into_if_absent": "PATIENT",
            "fields": {
                "raw_name": {"label": "SUBSCRIBER NAME", "direction": "below"},
                "_raw_member_id": {"label": "MEMBER ID", "direction": "below"},
            },
        },
    )
    ex = extract(t, toks, ocr=False, as_of=AS_OF)
    assert set(ex.persons) == {"PATIENT"}
    assert ex.persons["PATIENT"]["_raw_member_id"] == "SVY097439533"
    t2 = _template(
        H={
            "compose_name": "{_last}, {_first} {_middle}",
            "fields": {
                "_last": {"label": "LAST NAME", "direction": "below"},
                "_first": {"label": "FIRST NAME", "direction": "below"},
            },
        }
    )
    toks2 = (
        words("LAST NAME", 44, 85, 7.5)
        + words("FIRST NAME", 264, 85, 7.5)
        + words("FOWLER", 46, 97)
        + words("EDWIN", 266, 97)
    )
    assert extract(t2, toks2, ocr=False, as_of=AS_OF).persons["H"]["raw_name"] == "FOWLER, EDWIN"


def test_block_after_anchor_reads_a_letter_address():
    toks = (
        words("July 1, 2026", 40, 123)
        + words("DR. KERRY M SMITH", 40, 154)
        + words("2600 FRESNO ST", 40, 168)
        + words("FRESNO, CA 93721", 40, 182)
        + words("RE: Explanation", 40, 222)
    )
    t = _template(
        PATIENT={
            "block_name_address": {
                "direction": "block",
                "lines": 4,
                "max_distance": 8,
                "inline": r"^July \d{1,2}, \d{4}$",
            }
        }
    )
    p = extract(t, toks, ocr=False, as_of=AS_OF).persons["PATIENT"]
    assert (
        p["raw_name"] == "DR. KERRY M SMITH"
        and p["raw_address"] == "2600 FRESNO ST\nFRESNO, CA 93721"
    )


def test_repo_templates_load():
    names = {t.name for t in load_templates(ROOT / "config" / "doc_templates")}
    assert names == {
        f"{d}_{v}"
        for d in ["WAGE_STATEMENT", "HEALTH_CLAIM", "NEW_HIRE_ID", "EOB_LETTER"]
        for v in "AB"
    }
