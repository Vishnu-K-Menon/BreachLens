from pathlib import Path

import pandas as pd

from breachlens.context import RUN_ID_PATTERN, Context
from breachlens.pipeline import STAGES, enabled_stages, load_context, run_pipeline


def test_load_context_builds_everything(project, salt_env):
    ctx = load_context(project / "config" / "pipeline.yaml")
    assert RUN_ID_PATTERN.match(ctx.run_id)
    assert ctx.salt == salt_env.encode("utf-8")
    assert ctx.offline is True
    assert ctx.paths.root == project.resolve()
    assert ctx.audit.run_id == ctx.run_id


def test_load_context_input_override(project, salt_env, tmp_path):
    other = tmp_path / "other_input"
    ctx = load_context(project / "config" / "pipeline.yaml", input_dir=other)
    assert ctx.paths.input_dir == other.resolve()


def test_load_context_reads_salt_from_project_env_file(project, monkeypatch):
    monkeypatch.delenv("BREACHLENS_SALT", raising=False)
    (project / ".env").write_text("BREACHLENS_SALT=" + "s" * 40 + "\n", encoding="utf-8")
    ctx = load_context(project / "config" / "pipeline.yaml")
    assert ctx.salt == b"s" * 40


def test_run_pipeline_with_no_stages_returns_empty_frame(project, salt_env):
    ctx = load_context(project / "config" / "pipeline.yaml")
    assert run_pipeline(ctx, stages=[]).empty


def test_stages_are_registered_and_toggleable(project, salt_env):
    ctx = load_context(project / "config" / "pipeline.yaml")
    assert [name for name, _, _ in STAGES] == ["pdf_track", "sheet_track"]
    assert [name for name, _ in enabled_stages(ctx.config)] == ["pdf_track", "sheet_track"]
    off = ctx.config.model_copy(
        update={
            "stages": ctx.config.stages.model_copy(
                update={"pdf_track": False, "sheet_track": False}
            )
        }
    )
    assert enabled_stages(off) == []


def test_track_stages_without_input_dir_are_no_ops(project, salt_env):
    ctx = load_context(project / "config" / "pipeline.yaml")
    assert run_pipeline(ctx).empty
    assert ctx.tables["pdf_summary"] == {"pdf_files": 0}
    assert ctx.tables["sheet_summary"] == {"sheet_files": 0}


def test_run_pipeline_runs_stages_in_order(project, salt_env):
    ctx = load_context(project / "config" / "pipeline.yaml")

    def add_rows(df: pd.DataFrame, ctx: Context) -> pd.DataFrame:
        return pd.DataFrame({"step": ["a", "b"]})

    def tag(df: pd.DataFrame, ctx: Context) -> pd.DataFrame:
        return df.assign(run_id=ctx.run_id)

    out = run_pipeline(ctx, stages=[("add_rows", add_rows), ("tag", tag)])
    assert list(out["step"]) == ["a", "b"]
    assert set(out["run_id"]) == {ctx.run_id}


def test_load_context_does_not_create_output_dirs(project, salt_env):
    load_context(project / "config" / "pipeline.yaml")
    assert not (Path(project) / "data").exists()
