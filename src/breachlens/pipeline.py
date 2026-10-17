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
from breachlens.config import load_config, load_salt, project_root_for
from breachlens.context import Context, Paths, new_run_id

logger = logging.getLogger(__name__)

Stage = Callable[[pd.DataFrame, Context], pd.DataFrame]

# (name, stage) pairs in execution order. Empty in M0; each milestone registers its stages.
STAGES: list[tuple[str, Stage]] = []


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
    )


def run_pipeline(ctx: Context, stages: list[tuple[str, Stage]] | None = None) -> pd.DataFrame:
    """Run `stages` (default: `STAGES`) in order, starting from an empty DataFrame."""
    df = pd.DataFrame()
    for name, stage in STAGES if stages is None else stages:
        logger.info("stage %s: start (%d rows in)", name, len(df))
        df = stage(df, ctx)
        logger.info("stage %s: done (%d rows out)", name, len(df))
    return df
