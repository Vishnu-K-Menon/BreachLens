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


class ReviewOverride(_Strict):
    """A human column decision (config/review_overrides.yaml, ADR-061)."""

    file: str  # input-relative path, e.g. sheets/patient_list.xlsx
    sheet: str | None = None  # None = any sheet of the file
    header: str
    reviewed_label: str
    reviewed_by: str
    reviewed_on: str
    note: str = ""

    def matches(self, path: str, sheet: str | None, header: str) -> bool:
        same_sheet = self.sheet is None or (self.sheet or "") == (sheet or "")
        return (
            self.file == path
            and same_sheet
            and self.header.strip().lower() == header.strip().lower()
        )


# Reviewed-only labels (not model labels): reviewed label -> (mapping label, mention field).
REVIEWED_LABELS = {"INSURER": ("ORG_NAME", "insurer_name")}


@dataclass(frozen=True)
class SheetSettings:
    sheets: SheetsCfg
    aliases: AliasCfg
    thresholds: MappingThresholds
    zip_leading_zero_states: frozenset[str]
    org_suffixes: tuple[str, ...]
    overrides: tuple[ReviewOverride, ...] = ()


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
        overrides=load_overrides(config_dir),
    )


def load_overrides(config_dir: Path) -> tuple[ReviewOverride, ...]:
    """Human column decisions. A reviewed label must be a model label or a reviewed-only
    label (REVIEWED_LABELS); anything else is a config error."""
    path = config_dir / "review_overrides.yaml"
    if not path.is_file():
        return ()
    data = _yaml(path) or {}
    out = tuple(ReviewOverride.model_validate(o) for o in data.get("overrides") or [])
    labels = (
        set(_yaml(config_dir / "column_corpus_aliases.yaml")) | {"OTHER"} | set(REVIEWED_LABELS)
    )
    bad = [o.reviewed_label for o in out if o.reviewed_label not in labels]
    if bad:
        raise ValueError(f"review_overrides.yaml: unknown reviewed_label {bad}")
    return out
