"""Command-line interface (`python -m breachlens …` or `breachlens …`).

Commands that belong to later milestones are stubs that exit with code 1 and name the
milestone that implements them.
"""

from __future__ import annotations

import logging
import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated, NoReturn

import typer

logger = logging.getLogger("breachlens")
_HANDLER_NAME = "breachlens-cli"

app = typer.Typer(
    name="breachlens",
    help="BreachLens: breached documents and spreadsheets to a validated notification list.",
    no_args_is_help=True,
    add_completion=False,
)


class EvalTarget(StrEnum):
    pipeline = "pipeline"
    ask = "ask"


class ModelName(StrEnum):
    column_classifier = "column-classifier"
    match_model = "match-model"
    doctype = "doctype"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


def _configure_logging(level: LogLevel) -> None:
    """(Re)attach one stderr handler to the `breachlens` logger for this invocation."""
    for handler in list(logger.handlers):
        if handler.get_name() == _HANDLER_NAME:
            logger.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(level.value)


def _not_implemented(command: str, milestone: str) -> NoReturn:
    typer.echo(f"'{command}' is not implemented yet (planned for {milestone}).", err=True)
    raise typer.Exit(code=1)


@app.callback()
def main(
    log_level: Annotated[LogLevel, typer.Option("--log-level", help="Log level.")] = LogLevel.INFO,
) -> None:
    """BreachLens pipeline commands."""
    _configure_logging(log_level)


@app.command()
def generate(
    seed: Annotated[int, typer.Option(help="Random seed for the synthetic corpus.")] = 42,
    out: Annotated[Path, typer.Option(help="Output directory.")] = Path("data/raw/corpus_v1"),
    preview: Annotated[
        Path | None, typer.Option(help="Only write review previews to this directory.")
    ] = None,
    root: Annotated[Path, typer.Option(help="Project root (holds config/ and data/).")] = Path("."),
    corpus_only: Annotated[
        bool, typer.Option(help="Only docs/ + truth/ (keep the column corpus and scale file).")
    ] = False,
) -> None:
    """Generate the synthetic corpus and ground truth."""
    from dotenv import load_dotenv

    load_dotenv(root / ".env", override=False)  # tool locations such as SOFFICE_PATH
    if preview is not None:
        from breachlens.synth.preview import build_previews

        files = build_previews(root.resolve(), preview.resolve(), seed)
        typer.echo(f"wrote {len(files)} preview files to {preview}")
        return
    from breachlens.synth.generate import generate_corpus
    from breachlens.synth.settings import load_synth_settings

    settings = load_synth_settings(root / "config", seed)
    result = generate_corpus(settings, root.resolve(), out.resolve(), corpus_only=corpus_only)
    counts = result.truth.manifest["counts"]
    typer.echo(
        f"corpus {settings.config.version} (seed {seed}) -> {out}: {counts['files']} files, "
        f"{counts['people']} people, {counts['person_mentions']} person mentions, "
        f"all 44 planted cases covered"
    )


@app.command()
def run(
    config: Annotated[Path, typer.Option(help="Pipeline config file.")] = Path(
        "config/pipeline.yaml"
    ),
    input_dir: Annotated[
        Path | None, typer.Option("--input", help="Input directory (overrides the config).")
    ] = None,
    online: Annotated[
        bool,
        typer.Option(
            "--online",
            help="Allow the Census batch geocoder (addresses only) to fill the cache. "
            "Default: offline, cached Census results only (ADR-063).",
        ),
    ] = False,
) -> None:
    """Run the pipeline end to end."""
    from breachlens.config import ConfigError
    from breachlens.pipeline import enabled_stages, load_context, run_pipeline

    try:
        ctx = load_context(config, input_dir=input_dir)
    except ConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if online:
        ctx.offline = False  # the Census batch client is the only network client
    logger.info("run %s: offline=%s, input=%s", ctx.run_id, ctx.offline, ctx.paths.input_dir)
    stages = enabled_stages(ctx.config)
    mentions = run_pipeline(ctx)
    typer.echo(
        f"run {ctx.run_id} finished: {len(stages)} stage(s) executed, {len(mentions)} mentions."
    )
    labels = {
        "pdf_summary": "pdf_track",
        "sheet_summary": "sheet_track",
        "address_summary": "address",
        "resolve_summary": "resolve",
        "notify_summary": "notify",
    }
    for name, label in labels.items():
        if summary := ctx.tables.get(name):
            typer.echo(f"{label}: " + ", ".join(f"{k}={v}" for k, v in summary.items()))
    if "qc_status" in mentions:
        typer.echo(
            "qc_status: "
            + ", ".join(f"{k}={v}" for k, v in mentions["qc_status"].value_counts().items())
        )
    if ctx.config.privacy.write_outputs and ctx.config.stages.privacy:
        from breachlens.pipeline import write_outputs

        written = write_outputs(ctx, mentions)
        typer.echo(f"leak guard: 0 findings; wrote {len(written)} file(s) to {ctx.paths.run_dir}")
        for p in written:
            typer.echo(f"  {p.name}")


@app.command()
def evaluate(
    target: Annotated[EvalTarget, typer.Argument(help="What to evaluate.")] = EvalTarget.pipeline,
    run: Annotated[str, typer.Option("--run", help="Run id, or 'latest'.")] = "latest",
    truth: Annotated[
        Path | None, typer.Option(help="Ground-truth directory (pipeline target).")
    ] = None,
) -> None:
    """Evaluate a pipeline run against ground truth, or the Ask assistant."""
    if target is EvalTarget.ask:
        _not_implemented("evaluate ask", "M8")
    _not_implemented("evaluate", "M7")


@app.command()
def train(
    model: Annotated[ModelName, typer.Argument(help="Model to train.")],
    config: Annotated[Path, typer.Option(help="Pipeline config file.")] = Path(
        "config/pipeline.yaml"
    ),
    column_corpus: Annotated[Path, typer.Option(help="Column-classifier training corpus.")] = Path(
        "data/raw/column_corpus"
    ),
    corpus: Annotated[
        Path, typer.Option(help="Dev corpus: its spreadsheets are scored as the dev set.")
    ] = Path("data/raw/corpus_v1"),
    holdout: Annotated[
        Path, typer.Option(help="Held-out corpus: its spreadsheets are the test set.")
    ] = Path("data/raw/corpus_holdout"),
    out: Annotated[Path, typer.Option(help="Model output directory.")] = Path("models"),
) -> None:
    """Train a model (column-classifier; match-model and doctype are optional)."""
    if model is not ModelName.column_classifier:
        _not_implemented(f"train {model.value}", "the optional items after M8")
    from breachlens.config import load_config, project_root_for
    from breachlens.ml.column_classifier import train as train_columns
    from breachlens.sheets.settings import load_sheet_settings

    for needed in (column_corpus / "labels.csv", corpus / "truth"):
        if not needed.exists():
            typer.echo(f"error: {needed} not found; run `breachlens generate` first", err=True)
            raise typer.Exit(code=2)
    cfg = load_config(config)
    settings = load_sheet_settings(project_root_for(config) / "config")
    sets = {"dev_corpus_v1": corpus}
    if (holdout / "truth").is_dir():
        sets["test_holdout"] = holdout
    m = train_columns(column_corpus, sets, out, settings, cfg.as_of_date)
    last = list(sets)[-1]
    typer.echo(
        f"chosen {m['chosen_model']}; macro-F1 on {last} spreadsheets: "
        + ", ".join(f"{k} {v[f'sheets_{last}']}" for k, v in m["hard_test_macro_f1"].items())
    )


@app.command("apply-review")
def apply_review(
    decisions: Annotated[Path, typer.Option(help="Review decisions CSV or edited workbook.")],
) -> None:
    """Import review decisions and re-run the downstream stages."""
    _not_implemented("apply-review", "M6")


@app.command()
def ask(
    question: Annotated[str, typer.Argument(help="Question in plain English.")],
    explain: Annotated[
        bool, typer.Option(help="Also summarize the result (local Ollama only).")
    ] = False,
) -> None:
    """Ask BreachLens: local-LLM text-to-SQL over the results database."""
    _not_implemented("ask", "M8")


@app.command("scale-test")
def scale_test(
    config: Annotated[Path, typer.Option(help="Pipeline config file.")] = Path(
        "config/pipeline.yaml"
    ),
    input_file: Annotated[
        Path, typer.Option("--input", help="The 50k-row claims file (ADR-051).")
    ] = Path("data/raw/scale/large_claims.csv"),
) -> None:
    """Time each stage on the 50k-row claims file and write scale_report.json."""
    if not input_file.is_file():
        typer.echo(f"error: {input_file} not found; run `breachlens generate` first", err=True)
        raise typer.Exit(code=2)
    from breachlens.evaluate.scale import main as scale_main

    report, path = scale_main(config, input_file)
    for s in report["stages"]:
        typer.echo(
            f"  {s['stage']:12s} {s['seconds']:8.2f}s  {s['rows_per_sec'] or 0:>10,.0f} rows/s"
            f"  peak {s['peak_mb']} MB"
        )
    typer.echo(
        f"{report['rows']} rows in {report['total_seconds']}s "
        f"({report['rows_per_sec_end_to_end']:,.0f} rows/s end to end) -> {path}"
    )


@app.command()
def report(
    run: Annotated[str, typer.Option("--run", help="Run id, or 'latest'.")] = "latest",
) -> None:
    """Write the Excel review workbook and metrics report for a run."""
    _not_implemented("report", "M7")


db_app = typer.Typer(help="DuckDB system of record (M6, ADR-067).", no_args_is_help=True)
sql_app = typer.Typer(
    help="Run the hand-written queries in sql/queries/ (M6).", no_args_is_help=True
)
app.add_typer(db_app, name="db")
app.add_typer(sql_app, name="sql")
DEFAULT_DB = Path("data/output/breachlens.duckdb")


@db_app.command("build")
def db_build(
    config: Annotated[Path, typer.Option(help="Pipeline config file.")] = Path(
        "config/pipeline.yaml"
    ),
    run: Annotated[
        str, typer.Option("--run", help="Run id under data/output/, or 'latest'.")
    ] = "latest",
    db: Annotated[Path, typer.Option("--db", help="Database file.")] = DEFAULT_DB,
) -> None:
    """Load one run's outputs into DuckDB; the leak guard scans it before it is saved."""
    from breachlens.config import load_config, project_root_for
    from breachlens.db.load import build_database, find_run
    from breachlens.privacy.leak_guard import LeakError, LeakGuard

    cfg = load_config(config)
    root = project_root_for(config)
    out = (
        cfg.paths.output_dir if cfg.paths.output_dir.is_absolute() else root / cfg.paths.output_dir
    )
    try:
        run_dir = find_run(out, run)
        res = build_database(
            run_dir, db if db.is_absolute() else root / db, root, LeakGuard(cfg.privacy.leak_guard)
        )
    except FileNotFoundError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except LeakError as exc:
        typer.echo(f"error: {exc}; nothing was saved", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"built {res['db']} from {res['source_dir']} (run {res['run_id']})")
    for name, n in res["tables"].items():
        typer.echo(f"  {name:18s} {n:>7,d} rows")
    typer.echo(f"  views: {', '.join(res['views'])}")
    typer.echo(f"leak guard: {len(res['scanned'])} tables/views scanned, 0 findings")


@sql_app.command("run")
def sql_run(
    config: Annotated[Path, typer.Option(help="Pipeline config file.")] = Path(
        "config/pipeline.yaml"
    ),
    db: Annotated[Path, typer.Option("--db", help="Database file.")] = DEFAULT_DB,
    queries: Annotated[Path, typer.Option(help="Folder with *.sql queries.")] = Path("sql/queries"),
) -> None:
    """Run every sql/queries/*.sql read-only; save results to data/output/sql/."""
    from breachlens.config import load_config, project_root_for
    from breachlens.db.sql_harness import FAILED, run_all
    from breachlens.privacy.leak_guard import LeakGuard
    from breachlens.privacy.writer import GuardedWriter

    cfg = load_config(config)
    root = project_root_for(config)
    out = (
        cfg.paths.output_dir if cfg.paths.output_dir.is_absolute() else root / cfg.paths.output_dir
    )
    writer = GuardedWriter(LeakGuard(cfg.privacy.leak_guard), out / "sql")
    try:
        results = run_all(
            db if db.is_absolute() else root / db,
            queries if queries.is_absolute() else root / queries,
            writer,
        )
    except FileNotFoundError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    for r in results:
        rows = "" if r.rows is None else f"{r.rows} rows -> {r.output}"
        typer.echo(f"  {r.name:24s} {r.status:7s} {rows}{r.detail}")
    failed = [r for r in results if r.status == FAILED]
    typer.echo(
        f"{len(results)} queries: {len(results) - len(failed)} ok/empty, {len(failed)} failed"
    )
    if failed:
        raise typer.Exit(code=1)
