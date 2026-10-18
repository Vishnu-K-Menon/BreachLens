"""Pipeline wiring: build a `Context` and run the registered stages in order.

Every stage is a pure function `run(df, ctx) -> df`, so it can also be wrapped as a
KNIME Python Script node (see ARCHITECTURE.md §KNIME integration).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from breachlens.audit.log import AuditLogger
from breachlens.config import PipelineConfig, load_config, load_salt, project_root_for
from breachlens.context import Context, Paths, new_run_id

logger = logging.getLogger(__name__)

Stage = Callable[[pd.DataFrame, Context], pd.DataFrame]


def _pdf_track(df: pd.DataFrame, ctx: Context) -> pd.DataFrame:
    from breachlens.extract.pdf_track import stage_pdf_track

    return stage_pdf_track(df, ctx)


# (name, StagesConfig toggle, stage) in execution order; each milestone adds its stages.
STAGES: list[tuple[str, str, Stage]] = [
    ("pdf_track", "pdf_track", _pdf_track),
]


def enabled_stages(config: PipelineConfig) -> list[tuple[str, Stage]]:
    return [(name, fn) for name, toggle, fn in STAGES if getattr(config.stages, toggle)]


def load_context(
    config_path: str | Path,
    *,
    input_dir: Path | None = None,
    run_id: str | None = None,
) -> Context:
    """Load config + salt and build the run context. `input_dir` overrides the config."""
    config_path = Path(config_path)
    config = load_config(config_path)
    if input_dir is not None:
        config = config.model_copy(
            update={"paths": config.paths.model_copy(update={"input_dir": input_dir})}
        )
    root = project_root_for(config_path)
    salt = load_salt(root / ".env")
    run_id = run_id or new_run_id()
    return Context(
        config=config,
        run_id=run_id,
        paths=Paths.from_config(config, root, run_id),
        audit=AuditLogger(run_id=run_id),
        salt=salt,
        offline=config.offline,
        as_of_date=config.as_of_date,
    )


def run_pipeline(ctx: Context, stages: list[tuple[str, Stage]] | None = None) -> pd.DataFrame:
    """Run `stages` (default: the enabled `STAGES`) in order, from an empty DataFrame."""
    df = pd.DataFrame()
    for name, stage in enabled_stages(ctx.config) if stages is None else stages:
        logger.info("stage %s: start (%d rows in)", name, len(df))
        df = stage(df, ctx)
        logger.info("stage %s: done (%d rows out)", name, len(df))
    return df
