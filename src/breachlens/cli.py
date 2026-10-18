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
    result = generate_corpus(settings, root.resolve(), out.resolve())
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
) -> None:
    """Run the pipeline end to end."""
    from breachlens.config import ConfigError
    from breachlens.pipeline import enabled_stages, load_context, run_pipeline

    try:
        ctx = load_context(config, input_dir=input_dir)
    except ConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    logger.info("run %s: offline=%s, input=%s", ctx.run_id, ctx.offline, ctx.paths.input_dir)
    stages = enabled_stages(ctx.config)
    mentions = run_pipeline(ctx)
    typer.echo(
        f"run {ctx.run_id} finished: {len(stages)} stage(s) executed, {len(mentions)} mentions."
    )
    summary = ctx.tables.get("pdf_summary")
    if summary:
        typer.echo("pdf_track: " + ", ".join(f"{k}={v}" for k, v in summary.items()))


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
) -> None:
    """Train a model (column-classifier; match-model and doctype are optional)."""
    if model is ModelName.column_classifier:
        _not_implemented("train column-classifier", "M3")
    _not_implemented(f"train {model.value}", "the optional items after M8")


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
    n: Annotated[int, typer.Option("--n", help="Number of generated records.")] = 10_000,
) -> None:
    """Time each stage on generated records and write scale_report.json."""
    _not_implemented("scale-test", "M5")


@app.command()
def report(
    run: Annotated[str, typer.Option("--run", help="Run id, or 'latest'.")] = "latest",
) -> None:
    """Write the Excel review workbook and metrics report for a run."""
    _not_implemented("report", "M7")
