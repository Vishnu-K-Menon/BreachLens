from datetime import date
from pathlib import Path

import pytest

from breachlens.config import (
    SALT_ENV_VAR,
    ConfigError,
    PipelineConfig,
    load_config,
    load_salt,
    project_root_for,
)

ROOT = Path(__file__).resolve().parents[2]


def test_repo_pipeline_config_is_valid():
    config = load_config(ROOT / "config" / "pipeline.yaml")
    assert isinstance(config, PipelineConfig)
    assert config.offline is True
    assert config.seed == 42
    assert config.paths.input_dir == Path("data/raw/corpus_v1/docs")


def test_minimal_config_uses_defaults(tmp_path):
    path = tmp_path / "pipeline.yaml"
    path.write_text("as_of_date: 2026-10-01\n", encoding="utf-8")
    assert load_config(path) == PipelineConfig(as_of_date=date(2026, 10, 1))


def test_as_of_date_is_required(tmp_path):
    path = tmp_path / "pipeline.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ConfigError, match="as_of_date"):
        load_config(path)


def test_repo_config_as_of_date():
    assert load_config(ROOT / "config" / "pipeline.yaml").as_of_date == date(2026, 10, 1)


@pytest.mark.parametrize(
    "text",
    [
        "bogus: 1\n",
        "paths:\n  input_dirr: data\n",
        "stages:\n  teleport: true\n",
        "offline: maybe\n",
    ],
)
def test_invalid_config_is_rejected(tmp_path, text):
    path = tmp_path / "pipeline.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_non_mapping_config_is_rejected(tmp_path):
    path = tmp_path / "pipeline.yaml"
    path.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="mapping"):
        load_config(path)


def test_missing_config_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.yaml")


def test_project_root_is_parent_of_config_dir(tmp_path):
    assert project_root_for(tmp_path / "config" / "pipeline.yaml") == tmp_path.resolve()


def test_salt_from_environment(salt_env):
    assert load_salt() == salt_env.encode("utf-8")


def test_salt_from_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv(SALT_ENV_VAR, raising=False)
    salt = "x" * 40
    (tmp_path / ".env").write_text(f"{SALT_ENV_VAR}={salt}\n", encoding="utf-8")
    assert load_salt(tmp_path / ".env") == salt.encode("utf-8")


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("", "not set"),
        ("change-me-to-a-random-32+-char-string", "placeholder"),
        ("short-salt", "at least 32"),
    ],
)
def test_bad_salt_is_rejected_without_echoing_it(monkeypatch, tmp_path, value, message):
    monkeypatch.setenv(SALT_ENV_VAR, value)
    with pytest.raises(ConfigError, match=message) as excinfo:
        load_salt(tmp_path / ".env")
    if value:
        assert value not in str(excinfo.value)
