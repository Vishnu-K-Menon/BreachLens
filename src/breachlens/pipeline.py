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


def _sheet_track(df: pd.DataFrame, ctx: Context) -> pd.DataFrame:
    from breachlens.sheets.sheet_track import stage_sheet_track

    return stage_sheet_track(df, ctx)


def _normalize(df: pd.DataFrame, ctx: Context) -> pd.DataFrame:
    from breachlens.normalize.stage import stage_normalize

    return stage_normalize(df, ctx)


def stage_validate(df: pd.DataFrame, ctx: Context) -> pd.DataFrame:
    from breachlens.validate.engine import stage_validate as _validate

    return _validate(df, ctx)


def _address(df: pd.DataFrame, ctx: Context) -> pd.DataFrame:
    from breachlens.address.stage import stage_address

    return stage_address(df, ctx)


def _privacy(df: pd.DataFrame, ctx: Context) -> pd.DataFrame:
    from breachlens.privacy.stage import stage_privacy

    return stage_privacy(df, ctx)


def _resolve(df: pd.DataFrame, ctx: Context) -> pd.DataFrame:
    from breachlens.resolve.stage import stage_resolve

    return stage_resolve(df, ctx)


def _notify(df: pd.DataFrame, ctx: Context) -> pd.DataFrame:
    from breachlens.notify.triggers import stage_notify

    return stage_notify(df, ctx)


# (name, StagesConfig toggle, stage) in execution order; each milestone adds its stages.
# Resolution and notification run after privacy, on keys only (never raw values).
STAGES: list[tuple[str, str, Stage]] = [
    ("pdf_track", "pdf_track", _pdf_track),
    ("sheet_track", "sheet_track", _sheet_track),
    ("normalize", "normalize", _normalize),
    ("validate", "validation", stage_validate),
    ("address", "address", _address),
    ("privacy", "privacy", _privacy),
    ("resolve", "resolve", _resolve),
    ("notify", "notify", _notify),
]

# Run tables written to data/output/<run_id>/ (ADR-058), all through the leak guard.
OUTPUT_TABLES = [
    "people",
    "notification_list",
    "pair_features",
    "inventory",
    "excluded_entities",
    "excluded_identifiers",
    "doc_codes",
    "file_profile",
    "column_profile",
    "column_mapping",
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


def write_outputs(ctx: Context, mentions: pd.DataFrame) -> list[Path]:
    """Write the run tables, the audit trail and a counts-only summary through the
    guarded writer. Refused unless the privacy stage ran (no `_` columns may remain)."""
    from breachlens.privacy.leak_guard import LeakError, LeakGuard
    from breachlens.privacy.writer import GuardedWriter

    if not ctx.config.stages.privacy:
        raise RuntimeError("refusing to write outputs: the privacy stage is disabled")
    guard = LeakGuard(ctx.config.privacy.leak_guard)
    tables = {"mentions": mentions}
    tables |= {n: t for n in OUTPUT_TABLES if isinstance(t := ctx.tables.get(n), pd.DataFrame)}
    events = [e.__dict__ | {"ts": e.ts.isoformat(timespec="seconds")} for e in ctx.audit.events]
    findings = [f for n, t in tables.items() for f in guard.scan_frame(t, f"{n}.csv")]
    findings += guard.scan_records(events, f"audit_{ctx.run_id}.jsonl")
    if findings:  # scan everything first: a finding leaves no partial run directory
        raise LeakError(findings)
    w = GuardedWriter(guard, ctx.paths.run_dir)
    for name, t in tables.items():
        w.write_csv(t, f"{name}.csv")
    counts = {name: len(t) for name, t in tables.items()}
    w.write_jsonl(events, f"audit_{ctx.run_id}.jsonl")
    qc = mentions["qc_status"].value_counts().to_dict() if "qc_status" in mentions else {}
    summary = {
        "run_id": ctx.run_id,
        "as_of_date": ctx.as_of_date.isoformat(),
        "rows": counts,
        "audit_events": len(events),
        "qc_status": qc,
        "files": [p.name for p in w.written] + ["run_summary.json"],
    }
    w.write_json(summary, "run_summary.json")
    return w.written
