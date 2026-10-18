"""Column mapping: header-alias rules (baseline) + ML classifier, combined by the
ADR-034 decision table (SPREADSHEET_TRACK.md §4).

| rules | ML                          | decision    | outcome                               |
|-------|-----------------------------|-------------|---------------------------------------|
| label | same label                  | AGREE       | accept (+ AGREE_LOW_PROBA if p < 0.60) |
| none  | p >= 0.70                   | ML_ONLY     | accept                                |
| none  | p < 0.70                    | REVIEW      | COL_MAPPING_LOW_CONF                  |
| label | other label, p >= 0.80      | ML_OVERRIDE | accept; COL_MAPPING_ML_OVERRIDE       |
| label | other label, p < 0.80       | REVIEW      | COL_MAPPING_LOW_CONF (rule label kept)|
| label | unavailable                 | RULE_ONLY   | accept                                |
| none  | unavailable                 | REVIEW      | COL_MAPPING_LOW_CONF, final OTHER     |
| label | OTHER (any p)               | RULE_ONLY   | accept the rule label (ADR-056)       |

A column that looks sensitive (>= 50% SSN-shaped or Luhn-valid values) but ends up OTHER
gets COL_UNMAPPED_SENSITIVE.
"""

from __future__ import annotations

from dataclasses import dataclass

from breachlens.sheets.features import normalize_header
from breachlens.sheets.settings import AliasCfg, MappingThresholds

AGREE, ML_ONLY, ML_OVERRIDE, RULE_ONLY, REVIEW = (
    "AGREE",
    "ML_ONLY",
    "ML_OVERRIDE",
    "RULE_ONLY",
    "REVIEW",
)


def rule_label(header: str, aliases: AliasCfg) -> str | None:
    """Exact alias match on the normalized header, then the first `contains` keyword."""
    h = normalize_header(header)
    if not h:
        return None
    for label, names in aliases.exact.items():
        if h in {normalize_header(n) for n in names}:
            return label
    words = f" {h} "
    for key, label in aliases.contains:
        if f" {normalize_header(key)} " in words or (len(key) > 4 and normalize_header(key) in h):
            return label
    return None


@dataclass(frozen=True)
class Decision:
    final_label: str
    decision: str
    codes: tuple[str, ...]


def decide(rule: str | None, ml: str | None, proba: float | None, t: MappingThresholds) -> Decision:
    if ml is None or proba is None:
        if rule is not None:
            return Decision(rule, RULE_ONLY, ())
        return Decision("OTHER", REVIEW, ("COL_MAPPING_LOW_CONF",))
    if rule is not None and rule == ml:
        codes = ("COL_MAPPING_AGREE_LOW_PROBA",) if proba < t.agree_low_proba else ()
        return Decision(rule, AGREE, codes)
    if rule is not None and ml == "OTHER":
        # ADR-056: OTHER means "no recognized type"; it never overrides a concrete rule label.
        return Decision(rule, RULE_ONLY, ())
    if rule is None:
        if proba >= t.ml_only_min:
            return Decision(ml, ML_ONLY, ())
        return Decision(ml, REVIEW, ("COL_MAPPING_LOW_CONF",))
    if proba >= t.override_min:
        return Decision(ml, ML_OVERRIDE, ("COL_MAPPING_ML_OVERRIDE",))
    return Decision(rule, REVIEW, ("COL_MAPPING_LOW_CONF",))


def unmapped_sensitive(final_label: str, features: dict[str, float]) -> bool:
    return final_label == "OTHER" and (
        features.get("ssn_valid", 0) >= 0.5 or features.get("luhn_valid", 0) >= 0.5
    )
