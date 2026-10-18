"""Guarded writers (ADR-058): the only way BreachLens writes tables, the audit trail or
run metadata. Each write is scanned by the leak guard first; on any finding nothing is
written and `LeakError` is raised.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from breachlens.privacy.leak_guard import LeakError, LeakGuard


class GuardedWriter:
    def __init__(self, guard: LeakGuard, out_dir: Path) -> None:
        self.guard = guard
        self.out_dir = out_dir
        self.written: list[Path] = []

    def _path(self, name: str) -> Path:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        return self.out_dir / name

    def write_csv(self, df: pd.DataFrame, name: str) -> Path:
        self.guard.check_frame(df, name)
        p = self._path(name)
        df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")
        self.written.append(p)
        return p

    def write_jsonl(self, records: list[dict[str, Any]], name: str) -> Path:
        if findings := self.guard.scan_records(records, name):
            raise LeakError(findings)
        p = self._path(name)
        with p.open("w", encoding="utf-8", newline="\n") as fh:
            for r in records:
                fh.write(json.dumps(r, sort_keys=True, default=str) + "\n")
        self.written.append(p)
        return p

    def write_json(self, obj: dict[str, Any], name: str) -> Path:
        text = json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n"
        if findings := self.guard.scan_text(text, name):
            raise LeakError(findings)
        p = self._path(name)
        p.write_text(text, encoding="utf-8", newline="\n")
        self.written.append(p)
        return p
