from datetime import date, datetime
from pathlib import Path

import pytest

from breachlens.sheets import repair as R
from breachlens.sheets.settings import load_sheet_settings

ROOT = Path(__file__).resolve().parents[2]
S = load_sheet_settings(ROOT / "config")


def ctx(day_first=None) -> R.RepairContext:
    return R.RepairContext(S.sheets.repair, S.zip_leading_zero_states, date(2026, 10, 1), day_first)


@pytest.mark.parametrize(
    ("value", "state", "zip5", "zip4", "codes"),
    [
        (2134, "MA", "02134", None, ["XL_ZIP_LEADING_ZERO_RESTORED"]),
        ("7030-1234", "NJ", "07030", "1234", ["XL_ZIP_LEADING_ZERO_RESTORED"]),
        ("2134", "TX", "2134", None, []),  # not a leading-zero state: left alone
        ("94110", "CA", "94110", None, []),
    ],
)
def test_zip_leading_zero(value, state, zip5, zip4, codes):
    f, z4 = R.repair_zip(value, state, ctx())
    assert (f.value, z4, f.codes) == (zip5, zip4, codes)


@pytest.mark.parametrize(
    ("value", "day_first", "iso", "codes"),
    [
        (32874, None, "1990-01-01", ["XL_DATE_SERIAL_CONVERTED"]),
        ("32874", None, "1990-01-01", ["XL_DATE_SERIAL_CONVERTED"]),
        (datetime(1985, 3, 4), None, "1985-03-04", []),
        ("03/04/1985", None, "1985-03-04", ["DOB_AMBIGUOUS_FORMAT"]),
        ("03/04/1985", True, "1985-04-03", []),
        ("25/12/1990", None, "1990-12-25", []),  # unambiguous day-first
        ("12/25/90", None, "1990-12-25", []),  # 2-digit year pivots on as_of_date
        ("12/25/19", None, "2019-12-25", []),
        ("1985-03-04", None, "1985-03-04", []),
        ("04 Mar 1985", None, "1985-03-04", []),
        ("not a date", None, None, []),
    ],
)
def test_dates(value, day_first, iso, codes):
    f = R.repair_date(value, ctx(day_first))
    assert (f.value, f.codes) == (iso, codes)


def test_column_day_first_votes_on_unambiguous_dates():
    assert R.column_day_first(["25/12/1990", "03/04/1985", "13/01/2000"]) is True
    assert R.column_day_first(["12/25/1990", "03/04/1985"]) is False
    assert R.column_day_first(["03/04/1985", 32874]) is None


@pytest.mark.parametrize(
    ("value", "out", "status", "codes"),
    [
        (12345678, "012345678", "TEXT", ["XL_SSN_ZERO_PADDED"]),
        ("12345678", "012345678", "TEXT", ["XL_SSN_ZERO_PADDED"]),
        ("123-45-6789", "123456789", "TEXT", []),
        ("XXX-XX-6789", "XXX-XX-6789", "PREMASKED", ["PREMASKED_VALUE"]),
    ],
)
def test_ssn(value, out, status, codes):
    f = R.repair_ssn(value, ctx())
    assert (f.value, f.status, f.codes) == (out, status, codes)


@pytest.mark.parametrize(
    ("value", "status", "codes"),
    [
        (4111111111111110, "PRECISION_LOST", ["XL_NUMBER_PRECISION_LOST"]),  # stored as a number
        (4.11111111111111e15, "PRECISION_LOST", ["XL_NUMBER_PRECISION_LOST"]),
        ("4.11111E+15", "PRECISION_LOST", ["XL_NUMBER_PRECISION_LOST"]),
        ("4111 1111 1111 1111", "TEXT", []),
        ("************1111", "PREMASKED", ["PREMASKED_VALUE"]),
        (123456789012, "TEXT", []),  # 12 digits fit in Excel's 15-digit precision
    ],
)
def test_long_ids(value, status, codes):
    f = R.repair_long_id(value, ctx())
    assert (f.status, f.codes) == (status, codes)


def test_text_long_id_is_compacted():
    assert R.repair_long_id("4111-1111-1111-1111", ctx()).value == "4111111111111111"
    assert R.repair_long_id("AB 12-34", ctx()).value == "AB 12-34"  # non-numeric kept as is


def test_excel_errors():
    assert R.is_excel_error("#N/A", S.sheets.repair)
    assert R.is_excel_error(" #ref! ", S.sheets.repair)
    assert not R.is_excel_error("N/A", S.sheets.repair)
    assert not R.is_excel_error(0, S.sheets.repair)


def test_city_state_zip_split():
    assert R.split_city_state_zip("Boston, ma 02134") == ("Boston", "MA", "02134")
    assert R.split_city_state_zip("Austin TX") is None


def test_address_full_split():
    a = R.split_address_full("12 Main St Apt 4, Springfield, IL 62701")
    assert a["line1"] == "12 Main St" and a["line2"] == "Apt 4"
    assert (a["city"], a["state"], a["zip"]) == ("Springfield", "IL", "62701")
