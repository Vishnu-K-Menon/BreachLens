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
    reference_date: date
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


@dataclass(frozen=True)
class SynthSettings:
    config: SynthConfig
    dl_formats: dict[str, list[str]]
    jurisdictions: dict[str, Jurisdiction]
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
    """Load all generator settings; `seed` overrides the config seed."""
    cfg = SynthConfig.model_validate(_yaml(config_dir / "synth.yaml"))
    if seed is not None:
        cfg = cfg.model_copy(update={"seed": seed})
    rules = _yaml(config_dir / "rules.yaml")
    juris = {
        k: Jurisdiction.model_validate(v)
        for k, v in _yaml(config_dir / "jurisdictions.yaml").items()
    }
    dl = {k: list(v) for k, v in _yaml(config_dir / "dl_formats.yaml").items()}
    missing = sorted(set(cfg.base_people_per_state) - set(dl))
    if missing:
        raise ValueError(f"dl_formats.yaml has no format for: {missing}")
    return SynthSettings(
        config=cfg,
        dl_formats=dl,
        jurisdictions=juris,
        known_invalid_ssns=frozenset(rules["known_invalid_ssns"]),
        valid_suffixes=tuple(rules["valid_suffixes"]),
        titles=tuple(rules["titles"]),
    )
