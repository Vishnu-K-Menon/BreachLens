import os
import subprocess
import sys

import pytest
from typer.testing import CliRunner

from breachlens.cli import app

COMMANDS = [
    "generate",
    "run",
    "evaluate",
    "train",
    "apply-review",
    "ask",
    "scale-test",
    "report",
]

runner = CliRunner()


def test_help_lists_all_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in COMMANDS:
        assert command in result.output


def test_python_m_breachlens_help_lists_all_commands():
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "COLUMNS": "120"}
    proc = subprocess.run(
        [sys.executable, "-m", "breachlens", "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    for command in COMMANDS:
        assert command in proc.stdout


def test_run_succeeds_with_valid_config(project, salt_env):
    result = runner.invoke(app, ["run", "--config", str(project / "config" / "pipeline.yaml")])
    assert result.exit_code == 0, result.output
    assert "finished" in result.output


def test_run_without_salt_fails_cleanly(project, monkeypatch):
    monkeypatch.delenv("BREACHLENS_SALT", raising=False)
    result = runner.invoke(app, ["run", "--config", str(project / "config" / "pipeline.yaml")])
    assert result.exit_code == 2
    assert "BREACHLENS_SALT" in result.output


def test_run_with_missing_config_fails_cleanly(tmp_path, salt_env):
    result = runner.invoke(app, ["run", "--config", str(tmp_path / "config" / "nope.yaml")])
    assert result.exit_code == 2
    assert "not found" in result.output


@pytest.mark.parametrize(
    ("args", "milestone"),
    [
        (["evaluate"], "M7"),
        (["evaluate", "ask"], "M8"),
        (["train", "match-model"], "after M8"),
        (["apply-review", "--decisions", "decisions.csv"], "M6"),
        (["ask", "How many people must be notified?"], "M8"),
        (["report", "--run", "latest"], "M7"),
    ],
)
def test_stub_commands_exit_nonzero_and_name_milestone(args, milestone):
    result = runner.invoke(app, args)
    assert result.exit_code == 1
    assert "not implemented" in result.output
    assert milestone in result.output


def test_scale_test_needs_the_input_file(tmp_path):
    result = runner.invoke(app, ["scale-test", "--input", str(tmp_path / "none.csv")])
    assert result.exit_code == 2
    assert "not found" in result.output


def test_train_column_classifier_needs_the_corpus(tmp_path):
    result = runner.invoke(
        app, ["train", "column-classifier", "--column-corpus", str(tmp_path / "none")]
    )
    assert result.exit_code == 2
    assert "not found" in result.output


def test_evaluate_rejects_unknown_target():
    result = runner.invoke(app, ["evaluate", "bogus"])
    assert result.exit_code == 2
