"""Run context shared by every stage (`run(df, ctx) -> df`)."""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from breachlens.audit.log import AuditLogger
from breachlens.config import PipelineConfig

SCHEMA_VERSION = "1.1"

# R<yyyymmdd>-<hhmmss>-<4 hex>, e.g. R20261017-153000-ab12 (ADR-027). The separators keep
# it clear of the leak-guard SSN/card/account patterns.
RUN_ID_PATTERN = re.compile(r"^R\d{8}-\d{6}-[0-9a-f]{4}$")


def new_run_id(now: datetime | None = None, suffix: str | None = None) -> str:
    """Return a new run id from a UTC timestamp and a random 4-hex suffix."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")
    tail = suffix if suffix is not None else secrets.token_hex(2)
    run_id = f"R{stamp}-{tail}"
    if not RUN_ID_PATTERN.match(run_id):
        raise ValueError(f"malformed run id: {run_id!r}")
    return run_id


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else (root / path).resolve()


@dataclass(frozen=True)
class Paths:
    """Absolute directories for one run. Nothing is created on construction."""

    root: Path
    config_dir: Path
    input_dir: Path
    output_dir: Path
    cache_dir: Path
    reference_dir: Path
    run_dir: Path

    @classmethod
    def from_config(cls, config: PipelineConfig, root: Path, run_id: str) -> Paths:
        output_dir = _resolve(root, config.paths.output_dir)
        return cls(
            root=root,
            config_dir=root / "config",
            input_dir=_resolve(root, config.paths.input_dir),
            output_dir=output_dir,
            cache_dir=_resolve(root, config.paths.cache_dir),
            reference_dir=_resolve(root, config.paths.reference_dir),
            run_dir=output_dir / run_id,
        )


@dataclass
class Context:
    """Everything a stage needs besides its input DataFrame. The salt is never shown."""

    config: PipelineConfig
    run_id: str
    paths: Paths
    audit: AuditLogger
    salt: bytes = field(repr=False)
    offline: bool
    as_of_date: date
    schema_version: str = SCHEMA_VERSION
