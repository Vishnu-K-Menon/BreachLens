"""Typed loading of the generator's config files.

Reads `config/synth.yaml`, `config/dl_formats.yaml`, `config/jurisdictions.yaml` and the
scalar keys of `config/rules.yaml` (titles, suffixes, known-invalid SSNs).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from breachlens.config import load_config


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Rates(_Strict):
    title: float
    middle: float
    suffix: float
    passport: float
    bank: float
    card: float


class VariantName(_Strict):
    canonical: str
    printed: str


class CityTypo(_Strict):
    city: str
    printed: str


class Planted(_Strict):
    surnames: list[str]
    apostrophe_surname: str
    variant_surname: VariantName
    nickname: VariantName
    accented: list[tuple[str, str]]
    titles: list[str]
    city_typo: CityTypo


class Organizations(_Strict):
    employer: str
    payer: str
    clinic: str
    insurer: str
    school_district: str
    university: str
    bank: str
    vendor: str


class ScanSettings(_Strict):
    fraction: float
    dpi: int
    noise_sigma: float
    max_rotation_deg: float
    blur_radius: float
    jpeg_quality: int


class PdfSettings(_Strict):
    counts: dict[str, int]
    scan: ScanSettings


class SheetSettings(_Strict):
    export_dates: dict[str, date]
    extras: dict[str, int]
    payroll_pay_dates: list[date]


class ColumnCorpusSettings(_Strict):
    tables: int
    min_cols: int
    max_cols: int
    min_rows: int
    max_rows: int
    uninformative_header_rate: float


class ScaleSettings(_Strict):
    n: int
    large_claims_rows: int


class SynthConfig(_Strict):
    version: str
    seed: int
    as_of_date: date
    base_people_per_state: dict[str, int]
    n_dependents: int
    n_students: int
    pool_share: float
    max_unrelated_households_per_address: int
    extras_pool_share: float
    rates: Rates
    area_codes: dict[str, list[str]]
    email_domains: list[str]
    card_iins: list[str]
    planted: Planted
    organizations: Organizations
    n_vendor_rows: int
    pdf: PdfSettings
    sheets: SheetSettings
    column_corpus: ColumnCorpusSettings
    scale: ScaleSettings


class Jurisdiction(_Strict):
    covered_elements: list[str]
    verified: bool
    citation: str | None = None


class CardRule(_Strict):
    """ADR-052: which card exposures trigger notice and review (illustrative)."""

    premasked_triggers: bool
    precision_lost_triggers: bool
    invalid_triggers: bool
    review_on: list[str]

    def triggers(self, status: str) -> bool:
        return {
            "PREMASKED": self.premasked_triggers,
            "PRECISION_LOST": self.precision_lost_triggers,
            "LUHN_FAIL": self.invalid_triggers,
        }.get(status, True)


class ElementRules(_Strict):
    card: CardRule


@dataclass(frozen=True)
class SynthSettings:
    config: SynthConfig
    dl_formats: dict[str, list[str]]
    jurisdictions: dict[str, Jurisdiction]
    element_rules: ElementRules
    known_invalid_ssns: frozenset[str]
    valid_suffixes: tuple[str, ...]
    titles: tuple[str, ...]


def _yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def load_synth_settings(config_dir: Path, seed: int | None = None) -> SynthSettings:
    """Load all generator settings; `seed` overrides the config seed.

    `as_of_date` comes from `pipeline.yaml` only (ADR-053), never from `synth.yaml`.
    """
    raw = _yaml(config_dir / "synth.yaml")
    if "as_of_date" in raw:
        raise ValueError("as_of_date belongs in pipeline.yaml (ADR-053), not synth.yaml")
    raw["as_of_date"] = load_config(config_dir / "pipeline.yaml").as_of_date
    cfg = SynthConfig.model_validate(raw)
    if seed is not None:
        cfg = cfg.model_copy(update={"seed": seed})
    rules = _yaml(config_dir / "rules.yaml")
    juris_raw = _yaml(config_dir / "jurisdictions.yaml")
    element_rules = ElementRules.model_validate(juris_raw.pop("element_rules"))
    juris = {k: Jurisdiction.model_validate(v) for k, v in juris_raw.items()}
    dl = {k: list(v) for k, v in _yaml(config_dir / "dl_formats.yaml").items()}
    missing = sorted(set(cfg.base_people_per_state) - set(dl))
    if missing:
        raise ValueError(f"dl_formats.yaml has no format for: {missing}")
    return SynthSettings(
        config=cfg,
        dl_formats=dl,
        jurisdictions=juris,
        element_rules=element_rules,
        known_invalid_ssns=frozenset(rules["known_invalid_ssns"]),
        valid_suffixes=tuple(rules["valid_suffixes"]),
        titles=tuple(rules["titles"]),
    )
