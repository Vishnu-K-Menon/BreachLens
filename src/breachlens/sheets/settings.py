"""Typed loading of `config/sheets.yaml`, `config/header_aliases.yaml` and the spreadsheet
keys of `config/rules.yaml`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReaderCfg(_Strict):
    csv_sniff_bytes: int
    csv_delimiters: list[str]
    comment_prefix: str
    encodings: list[str]
    large_file_rows: int


class LayoutCfg(_Strict):
    header_scan_rows: int
    header_min_string_share: float
    header_max_numeric_share: float
    data_like_rows: int
    total_row_pattern: str
    min_data_rows: int
    min_columns: int


class RepairCfg(_Strict):
    excel_errors: list[str]
    premasked_pattern: str
    sci_notation_pattern: str
    excel_serial_range: tuple[int, int]
    long_id_labels: list[str]
    date_formats: list[str]


class ReshapeCfg(_Strict):
    wide_group_pattern: str


class FreetextCfg(_Strict):
    ssn: str
    card: str
    mrn: str


class RoleRule(_Strict):
    labels: list[str]
    role: str


class SheetsCfg(_Strict):
    reader: ReaderCfg
    layout: LayoutCfg
    repair: RepairCfg
    reshape: ReshapeCfg
    freetext: FreetextCfg
    roles: list[RoleRule]
    default_role: str
    guardian_header_words: list[str]
    insurer_header_words: list[str]


class AliasCfg(_Strict):
    exact: dict[str, list[str]]
    contains: list[tuple[str, str]]


class MappingThresholds(_Strict):
    agree_low_proba: float
    ml_only_min: float
    override_min: float


@dataclass(frozen=True)
class SheetSettings:
    sheets: SheetsCfg
    aliases: AliasCfg
    thresholds: MappingThresholds
    zip_leading_zero_states: frozenset[str]
    org_suffixes: tuple[str, ...]


def _yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_sheet_settings(config_dir: Path) -> SheetSettings:
    rules = _yaml(config_dir / "rules.yaml")
    ents = _yaml(config_dir / "entities.yaml")
    return SheetSettings(
        sheets=SheetsCfg.model_validate(_yaml(config_dir / "sheets.yaml")),
        aliases=AliasCfg.model_validate(_yaml(config_dir / "header_aliases.yaml")),
        thresholds=MappingThresholds.model_validate(rules["column_mapping"]),
        zip_leading_zero_states=frozenset(rules["zip_leading_zero_states"]),
        org_suffixes=tuple(ents["org_suffixes"]),
    )
