"""Stable document ids (ADR-047): `D0001`… by sorted POSIX relative path under the input
directory. The generator (ground truth) and the M2 inventory use this one rule."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


def relative_files(root: Path) -> list[str]:
    """Sorted POSIX paths of all files under `root`, relative to it."""
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def assign_doc_ids(paths: Iterable[str]) -> dict[str, str]:
    """Map each relative path to `D0001`, `D0002`, … in sorted order."""
    return {path: f"D{i:04d}" for i, path in enumerate(sorted(set(paths)), start=1)}
