"""Shared fixtures and automatic skipping for tests that need external tools.

Markers (see pyproject.toml): `tesseract`, `libreoffice`, `ollama`, `network`. A marked
test is skipped with a clear reason when its dependency is missing. Availability is only
probed when at least one collected test uses the marker.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
TEST_SALT = "test-salt-not-a-secret-0123456789abcdef"

# Pick up only the tool locations from the developer's .env (never the salt).
for _key, _value in dotenv_values(ROOT / ".env").items():
    if _key in {"TESSERACT_CMD", "SOFFICE_PATH", "OLLAMA_HOST"} and _value:
        os.environ.setdefault(_key, _value)


def _env_path_exists(var: str) -> bool:
    value = os.environ.get(var, "").strip()
    return bool(value) and Path(value).is_file()


def _has_tesseract() -> bool:
    return _env_path_exists("TESSERACT_CMD") or shutil.which("tesseract") is not None


def _has_libreoffice() -> bool:
    return _env_path_exists("SOFFICE_PATH") or shutil.which("soffice") is not None


def _has_ollama() -> bool:
    import requests

    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    try:
        return requests.get(f"{host}/api/tags", timeout=1).ok
    except requests.RequestException:
        return False


def _network_enabled() -> bool:
    return os.environ.get("BREACHLENS_TEST_NETWORK") == "1"


_PROBES: dict[str, tuple[Callable[[], bool], str]] = {
    "tesseract": (_has_tesseract, "Tesseract not found (install it or set TESSERACT_CMD)"),
    "libreoffice": (_has_libreoffice, "LibreOffice not found (install it or set SOFFICE_PATH)"),
    "ollama": (_has_ollama, "Ollama server not reachable at OLLAMA_HOST"),
    "network": (_network_enabled, "network tests are opt-in: set BREACHLENS_TEST_NETWORK=1"),
}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    available: dict[str, bool] = {}
    for item in items:
        for marker, (probe, reason) in _PROBES.items():
            if item.get_closest_marker(marker) is None:
                continue
            if marker not in available:
                available[marker] = probe()
            if not available[marker]:
                item.add_marker(pytest.mark.skip(reason=reason))


@pytest.fixture(autouse=True)
def _isolate_salt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test without BREACHLENS_SALT and restore the original afterwards.

    setenv records the original value; delenv then removes it. On teardown monkeypatch
    undoes both, which also discards any value a test loaded from a .env file.
    """
    monkeypatch.setenv("BREACHLENS_SALT", "unset")
    monkeypatch.delenv("BREACHLENS_SALT")


@pytest.fixture
def salt_env(monkeypatch: pytest.MonkeyPatch) -> str:
    """Set a valid test salt in the environment."""
    monkeypatch.setenv("BREACHLENS_SALT", TEST_SALT)
    return TEST_SALT


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A throwaway project root with `config/pipeline.yaml` copied from the repo."""
    (tmp_path / "config").mkdir()
    shutil.copy(ROOT / "config" / "pipeline.yaml", tmp_path / "config" / "pipeline.yaml")
    return tmp_path
