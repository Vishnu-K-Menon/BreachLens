"""Column features for the column-type classifier (ML_MODELS.md §C).

Computed per column on up to 500 evenly spaced non-null values. All features are
aggregate rates and statistics; no raw value is kept (PRIVACY.md §10). The header is
returned normalized for the TF-IDF part of the model.

Groups: shape (lengths, character classes), pattern hit rates (SSN, ZIP, phone, email,
dates, Luhn, ABA, state codes, sci-notation, masks, ID shapes), dictionary rates (first
names, surnames, cities, org suffixes), value statistics (distinct ratio, nulls, numeric
moments, plausible birth years) and context (column position).
"""

from __future__ import annotations

import contextlib
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache

from breachlens.sheets.reader import Cell, as_text
from breachlens.synth.identifiers import aba_valid, luhn_valid, ssn_valid_shape

MAX_VALUES = 500
_RX = {
    "ssn_shape": r"^\d{3}-?\d{2}-?\d{4}$",
    "zip5": r"^\d{5}$",
    "zip4": r"^\d{4}$",
    "zip9": r"^\d{5}-\d{4}$",
    "email": r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$",
    "date_iso": r"^\d{4}-\d{2}-\d{2}",
    "date_us": r"^\d{1,2}/\d{1,2}/\d{2,4}$",
    "date_text": r"^\d{1,2} [A-Za-z]{3} \d{4}$",
    "sci": r"^\d(\.\d+)?E\+?\d+$|^\d{12,}\.0$",
    "masked": r"^[Xx*#]{2,}",
    "member_like": r"^[A-Z]{3}\d{9}$",
    "student_like": r"^S\d{7}$",
    "icd_like": r"^[A-Z]\d{2}(\.\d{1,4})?$",
    "ein_like": r"^\d{2}-\d{7}$",
    "passport_like": r"^[A-Z]\d{8}$",
    "dl_like": r"^[A-Z]\d{7,14}$",
    "money": r"^-?\d{1,7}[.,]\d{2}$",
    "csz": r"^[A-Za-z .'-]+, [A-Z]{2} \d{5}(-\d{4})?$",
    "comma_name": r"^[A-Za-zÀ-ÿ'\- ]+, [A-Za-zÀ-ÿ]",
    "street_like": r"^\d{1,6} [A-Za-z0-9 .'-]+$",
    "digits5": r"^\d{5}$",
    "digits6": r"^\d{6}$",
    "digits8": r"^\d{8}$",
    "digits9": r"^\d{9}$",
    "digits10": r"^\d{10}$",
    "alnum_prefix": r"^[A-Z]{1,3}\d+$",
    "phone_fmt": r"^(\+1)?\(?\d{3}\)?[ -.]?\d{3}[ -.]?\d{4}$",
    "suffix_token": r"^(JR|SR|II|III|IV|V|JR\.|SR\.|JUNIOR)$",
    "short_alpha": r"^[A-Za-z]{1,2}\.?$",
}
_COMPILED = {
    k: re.compile(v, re.I if k in {"email", "suffix_token"} else 0) for k, v in _RX.items()
}
_DATE_FMTS = ["%m/%d/%Y", "%Y-%m-%d", "%d %b %Y", "%m/%d/%y"]
STATE_CODES = frozenset(
    [
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
        "DC",
        "PR",
        "VI",
        "GU",
    ]
)


@dataclass(frozen=True)
class Lexicons:
    first_names: frozenset[str]
    last_names: frozenset[str]
    cities: frozenset[str]
    org_suffixes: frozenset[str]


@lru_cache(maxsize=1)
def default_lexicons(
    org_suffixes: tuple[str, ...] = ("INC", "LLC", "CORP", "CO", "LTD", "GROUP"),
) -> Lexicons:
    import zipcodes
    from faker.providers.person.en_US import Provider

    return Lexicons(
        first_names=frozenset(n.upper() for n in Provider.first_names),
        last_names=frozenset(n.upper() for n in Provider.last_names),
        cities=frozenset(z["city"].upper() for z in zipcodes.filter_by()),
        org_suffixes=frozenset(org_suffixes),
    )


def normalize_header(h: str) -> str:
    return " ".join(re.sub(r"[_\W]+", " ", str(h or "").lower()).split())


def _sample(values: list[Cell]) -> list[str]:
    texts = [as_text(v).strip() for v in values]
    texts = [t for t in texts if t]
    if len(texts) <= MAX_VALUES:
        return texts
    step = len(texts) / MAX_VALUES
    return [texts[int(i * step)] for i in range(MAX_VALUES)]


def _parse_date(s: str) -> date | None:
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(s[:10] if fmt == "%Y-%m-%d" else s, fmt).date()
        except ValueError:
            continue
    return None


def _rate(vals: list[str], pred: Callable[[str], bool]) -> float:
    return sum(1 for v in vals if pred(v)) / len(vals) if vals else 0.0


def column_features(
    header: str, values: list[Cell], col_pos: float, as_of: date, lex: Lexicons
) -> dict[str, float]:
    """Numeric features for one column (see module docstring)."""
    n_all = len(values)
    vals = _sample(values)
    f: dict[str, float] = {
        "null_frac": 1 - (len(vals) / n_all) if n_all else 1.0,
        "col_pos": col_pos,
    }
    if not vals:
        return f | {k: 0.0 for k in FEATURE_NAMES if k not in f}
    lens = [len(v) for v in vals]
    mean = sum(lens) / len(lens)
    chars = "".join(vals)
    letters = [c for c in chars if c.isalpha()]
    f |= {
        "len_mean": mean,
        "len_std": math.sqrt(sum((x - mean) ** 2 for x in lens) / len(lens)),
        "digit_frac": sum(c.isdigit() for c in chars) / len(chars),
        "alpha_frac": len(letters) / len(chars),
        "upper_frac": (sum(c.isupper() for c in letters) / len(letters)) if letters else 0.0,
        "space_frac": chars.count(" ") / len(chars),
        "tokens_mean": sum(len(v.split()) for v in vals) / len(vals),
        "has_dash": _rate(vals, lambda v: "-" in v),
        "has_slash": _rate(vals, lambda v: "/" in v),
        "has_at": _rate(vals, lambda v: "@" in v),
        "has_dot": _rate(vals, lambda v: "." in v),
        "has_comma": _rate(vals, lambda v: "," in v),
        "all_digit": _rate(vals, str.isdigit),
        "letter_digit_mix": _rate(
            vals, lambda v: any(c.isdigit() for c in v) and any(c.isalpha() for c in v)
        ),
        "distinct_ratio": len(set(vals)) / len(vals),
    }
    for k, rx in _COMPILED.items():
        f[f"rx_{k}"] = _rate(vals, lambda v, rx=rx: bool(rx.search(v)))
    digits = [re.sub(r"\D", "", v) for v in vals]
    f["ssn_valid"] = _rate(
        vals,
        lambda v: bool(_COMPILED["ssn_shape"].match(v)) and ssn_valid_shape(re.sub(r"\D", "", v)),
    )
    f["luhn_valid"] = _rate(digits, lambda d: 13 <= len(d) <= 19 and luhn_valid(d))
    f["aba_valid"] = _rate(digits, lambda d: len(d) == 9 and aba_valid(d))
    f["phone_digits"] = _rate(
        digits, lambda d: len(d) == 10 or (len(d) == 11 and d.startswith("1"))
    )
    f["state_code"] = _rate(vals, lambda v: v.upper() in STATE_CODES)
    up = [v.upper() for v in vals]
    first_tok = [u.replace(",", " ").split()[0] if u.split() else "" for u in up]
    last_tok = [u.replace(",", " ").split()[-1] if u.split() else "" for u in up]
    f["first_name_rate"] = _rate(first_tok, lambda t: t in lex.first_names)
    f["last_name_rate"] = _rate(last_tok, lambda t: t in lex.last_names)
    f["any_name_token"] = _rate(
        up,
        lambda u: any(
            t in lex.first_names or t in lex.last_names for t in u.replace(",", " ").split()
        ),
    )
    f["city_rate"] = _rate(up, lambda u: u in lex.cities)
    f["org_suffix_rate"] = _rate(last_tok, lambda t: t.strip(".") in lex.org_suffixes)
    nums = []
    for v in vals:
        with contextlib.suppress(ValueError):
            nums.append(float(v.replace(",", "")))
    f["numeric_frac"] = len(nums) / len(vals)
    if nums:
        logs = [math.log10(abs(x) + 1) for x in nums]
        lm = sum(logs) / len(logs)
        f["num_log_mean"] = lm
        f["num_log_std"] = math.sqrt(sum((x - lm) ** 2 for x in logs) / len(logs))
        f["serial_range"] = sum(1 for x in nums if 1 <= x <= 60000 and x.is_integer()) / len(vals)
    else:
        f["num_log_mean"] = f["num_log_std"] = f["serial_range"] = 0.0
    dates = [d for d in (_parse_date(v) for v in vals) if d is not None]
    f["date_rate"] = len(dates) / len(vals)
    if dates:
        ages = [(as_of - d).days / 365.25 for d in dates]
        am = sum(ages) / len(ages)
        f["date_age_mean"] = am
        f["date_age_std"] = math.sqrt(sum((a - am) ** 2 for a in ages) / len(ages))
        f["birth_plausible"] = sum(1 for a in ages if 0 <= a <= 120) / len(vals)
    else:
        f["date_age_mean"] = f["date_age_std"] = f["birth_plausible"] = 0.0
    return f


FEATURE_NAMES = (
    [
        "null_frac",
        "col_pos",
        "len_mean",
        "len_std",
        "digit_frac",
        "alpha_frac",
        "upper_frac",
        "space_frac",
        "tokens_mean",
        "has_dash",
        "has_slash",
        "has_at",
        "has_dot",
        "has_comma",
        "all_digit",
        "letter_digit_mix",
        "distinct_ratio",
    ]
    + [f"rx_{k}" for k in _RX]
    + [
        "ssn_valid",
        "luhn_valid",
        "aba_valid",
        "phone_digits",
        "state_code",
        "first_name_rate",
        "last_name_rate",
        "any_name_token",
        "city_rate",
        "org_suffix_rate",
        "numeric_frac",
        "num_log_mean",
        "num_log_std",
        "serial_range",
        "date_rate",
        "date_age_mean",
        "date_age_std",
        "birth_plausible",
    ]
)
