"""Stable document ids (ADR-047): `D0001`… by sorted POSIX relative path under the input
directory. The generator (ground truth) and the M2 inventory use this one rule.

Hidden files and folders (names starting with ".", e.g. `.ipynb_checkpoints`) are not
documents and are skipped, so tools opening the corpus cannot shift the ids."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


def relative_files(root: Path) -> list[str]:
    """Sorted POSIX paths of all non-hidden files under `root`, relative to it."""
    out = []
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if p.is_file() and not any(part.startswith(".") for part in rel.parts):
            out.append(rel.as_posix())
    return sorted(out)


def assign_doc_ids(paths: Iterable[str]) -> dict[str, str]:
    """Map each relative path to `D0001`, `D0002`, … in sorted order."""
    return {path: f"D{i:04d}" for i, path in enumerate(sorted(set(paths)), start=1)}
