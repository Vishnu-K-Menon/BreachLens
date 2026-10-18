"""Validation settings: `config/rules.yaml` (rule catalogue + scalars),
`dl_formats.yaml`, `address_abbrev.yaml`, `identifiers.yaml` (ITIN ranges)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from breachlens.extract.identifiers import IdentifierConfig, load_identifier_config

SEVERITIES = ("ERROR", "WARN", "INFO")


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    severity: str
    stage: str
    scope: str
    milestone: str = "M4"


class RulesConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    ocr_conf_threshold: float
    qualifying_elements: tuple[str, ...]
    valid_suffixes: tuple[str, ...]
    suffix_variants: dict[str, str]
    titles: tuple[str, ...]
    name_particles: tuple[str, ...]
    max_age_years: int
    minor_age_years: int
    known_invalid_ssns: frozenset[str]
    zip_leading_zero_states: frozenset[str]
    zip_city_suggest_min_similarity: float
    rules: tuple[Rule, ...]


class AddressAbbrev(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    states: frozenset[str]
    unit_designators: dict[str, str]  # printed -> standard (APARTMENT -> APT)
    standalone_units: frozenset[str]  # units without a number (UPPER, LOWER, REAR...)
    po_box_pattern: str


@dataclass(frozen=True)
class ValidationSettings:
    rules: RulesConfig
    dl_formats: dict[str, tuple[str, ...]]
    address: AddressAbbrev
    identifiers: IdentifierConfig

    @cached_property
    def severity(self) -> dict[str, str]:
        return {r.id: r.severity for r in self.rules.rules}

    @cached_property
    def dl_regex(self) -> dict[str, list[re.Pattern]]:
        return {st: [re.compile(p) for p in pats] for st, pats in self.dl_formats.items()}

    def m4_codes(self) -> list[str]:
        return [r.id for r in self.rules.rules if r.milestone == "M4"]


def _yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_validation_settings(config_dir: Path) -> ValidationSettings:
    rules = RulesConfig.model_validate(_yaml(config_dir / "rules.yaml"))
    ids = [r.id for r in rules.rules]
    dupes = {i for i in ids if ids.count(i) > 1}
    bad = [r.id for r in rules.rules if r.severity not in SEVERITIES]
    if dupes or bad:
        raise ValueError(f"rules.yaml: duplicate ids {sorted(dupes)}, bad severities {bad}")
    return ValidationSettings(
        rules=rules,
        dl_formats={k: tuple(v) for k, v in _yaml(config_dir / "dl_formats.yaml").items()},
        address=AddressAbbrev.model_validate(_yaml(config_dir / "address_abbrev.yaml")),
        identifiers=load_identifier_config(config_dir / "identifiers.yaml"),
    )
