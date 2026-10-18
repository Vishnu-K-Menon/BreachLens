"""Pipeline configuration and secrets loading.

`config/pipeline.yaml` is validated by `PipelineConfig` (unknown keys are rejected).
Relative paths in the config are resolved against the project root, which is the parent
of the directory holding the config file (`<root>/config/pipeline.yaml`).

The HMAC salt comes from `BREACHLENS_SALT` (environment or `<root>/.env`) and is never
logged or echoed.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, ValidationError

SALT_ENV_VAR = "BREACHLENS_SALT"
SALT_MIN_LENGTH = 32
SALT_PLACEHOLDER_PREFIX = "change-me"


class ConfigError(ValueError):
    """Raised when configuration or secrets are missing or invalid."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PathsConfig(_Strict):
    """Directories used by the pipeline, relative to the project root unless absolute."""

    input_dir: Path = Path("data/raw/corpus_v1/docs")
    output_dir: Path = Path("data/output")
    cache_dir: Path = Path("data/cache")
    reference_dir: Path = Path("data/reference")


class StagesConfig(_Strict):
    """On/off switch per pipeline stage. Stages land milestone by milestone."""

    pdf_track: bool = True
    sheet_track: bool = True
    normalize: bool = True
    validation: bool = True
    address: bool = True
    privacy: bool = True
    resolve: bool = True
    notify: bool = True
    database: bool = True
    workbook: bool = True


class PipelineConfig(_Strict):
    """Top-level shape of `config/pipeline.yaml`.

    `as_of_date` (ADR-053) is the fixed date that ages, minor status, DOB plausibility,
    the 2-digit-year pivot, the generator and the workbook's RunDate all use, so results
    never drift with the wall clock. It is required.
    """

    as_of_date: date
    offline: bool = True
    seed: int = 42
    paths: PathsConfig = PathsConfig()
    stages: StagesConfig = StagesConfig()


def load_config(path: Path) -> PipelineConfig:
    """Read and validate a pipeline config file.

    Raises:
        ConfigError: the file is missing, is not a YAML mapping, or fails validation.
    """
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"config file must contain a YAML mapping: {path}")
    try:
        return PipelineConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid config {path}:\n{exc}") from exc


def project_root_for(config_path: Path) -> Path:
    """Project root for a config file stored at `<root>/config/<name>.yaml`."""
    return config_path.resolve().parent.parent


def load_salt(env_file: Path | None = None) -> bytes:
    """Return the HMAC salt from `BREACHLENS_SALT`.

    `env_file` (if it exists) is loaded first without overriding variables that are
    already set. The value itself never appears in error messages.

    Raises:
        ConfigError: the salt is missing, still the `.env.example` placeholder, or shorter
            than `SALT_MIN_LENGTH` characters.
    """
    if env_file is not None and env_file.is_file():
        load_dotenv(env_file, override=False)
    value = os.environ.get(SALT_ENV_VAR, "").strip()
    if not value:
        raise ConfigError(
            f"{SALT_ENV_VAR} is not set. Copy .env.example to .env and set it to a random "
            f"string of at least {SALT_MIN_LENGTH} characters."
        )
    if value.startswith(SALT_PLACEHOLDER_PREFIX):
        raise ConfigError(f"{SALT_ENV_VAR} is still the .env.example placeholder; replace it.")
    if len(value) < SALT_MIN_LENGTH:
        raise ConfigError(f"{SALT_ENV_VAR} must be at least {SALT_MIN_LENGTH} characters long.")
    return value.encode("utf-8")
