from datetime import UTC, datetime
from pathlib import Path

import pytest

from breachlens.audit.log import AuditLogger
from breachlens.config import PathsConfig, PipelineConfig
from breachlens.context import RUN_ID_PATTERN, SCHEMA_VERSION, Context, Paths, new_run_id


def test_new_run_id_format():
    run_id = new_run_id(datetime(2026, 10, 17, 15, 30, 0, tzinfo=UTC), suffix="ab12")
    assert run_id == "R20261017-153000-ab12"


def test_new_run_id_random_suffix_matches_pattern():
    assert RUN_ID_PATTERN.match(new_run_id())


@pytest.mark.parametrize("suffix", ["AB12", "abc", "ab123", "zz12"])
def test_new_run_id_rejects_bad_suffix(suffix):
    with pytest.raises(ValueError):
        new_run_id(suffix=suffix)


def test_paths_resolve_relative_to_root(tmp_path):
    paths = Paths.from_config(PipelineConfig(), tmp_path, "R20261017-153000-ab12")
    assert paths.input_dir == (tmp_path / "data/raw/corpus_v1/docs").resolve()
    assert paths.output_dir == (tmp_path / "data/output").resolve()
    assert paths.run_dir == paths.output_dir / "R20261017-153000-ab12"
    assert paths.config_dir == tmp_path / "config"


def test_paths_keep_absolute_dirs(tmp_path):
    absolute = (tmp_path / "elsewhere").resolve()
    config = PipelineConfig(paths=PathsConfig(input_dir=absolute))
    paths = Paths.from_config(config, tmp_path / "root", "R20261017-153000-ab12")
    assert paths.input_dir == absolute


def test_paths_construction_creates_nothing(tmp_path):
    Paths.from_config(PipelineConfig(), tmp_path, "R20261017-153000-ab12")
    assert list(tmp_path.iterdir()) == []


def test_context_repr_hides_salt(tmp_path):
    run_id = "R20261017-153000-ab12"
    ctx = Context(
        config=PipelineConfig(),
        run_id=run_id,
        paths=Paths.from_config(PipelineConfig(), Path(tmp_path), run_id),
        audit=AuditLogger(run_id=run_id),
        salt=b"super-secret-salt-value-0123456789",
        offline=True,
    )
    assert "super-secret" not in repr(ctx)
    assert ctx.schema_version == SCHEMA_VERSION == "1.1"
