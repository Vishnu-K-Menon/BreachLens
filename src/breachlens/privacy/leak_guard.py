"""Leak guard: scan every DataFrame and string before it is written (PRIVACY.md §4).

Fails on (ADR-027):
- SSN-like `\\b\\d{3}([- ]?)\\d{2}\\1\\d{4}\\b` in every string column that isn't exempt
- card-like `\\b\\d{13,19}\\b` in every string column that isn't exempt
- account-like `\\b\\d{9,17}\\b` only in `account_scan_columns` and `*_masked`
- any `_raw_` (or other `_`-prefixed transient) column

Exempt: `exempt_columns` (numeric/meta, timestamps, zip4, phone) and every `*_key`.
Findings name the table, column, row and pattern, never the value.

Run as a file scanner:  python -m breachlens.privacy.leak_guard data/output/<run_id>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from breachlens.config import LeakGuardConfig


@dataclass(frozen=True)
class Finding:
    where: str  # table or file
    column: str | None
    row: int | None
    pattern: str  # ssn / card / account / raw_column


class LeakError(RuntimeError):
    def __init__(self, findings: list[Finding]) -> None:
        self.findings = findings
        head = "; ".join(f"{f.where}.{f.column} row {f.row}: {f.pattern}" for f in findings[:5])
        super().__init__(f"leak guard: {len(findings)} finding(s): {head}")


class LeakGuard:
    def __init__(self, cfg: LeakGuardConfig) -> None:
        self.cfg = cfg
        self.ssn = re.compile(cfg.ssn_pattern)
        self.card = re.compile(cfg.card_pattern)
        self.account = re.compile(cfg.account_pattern)

    def _exempt(self, col: str) -> bool:
        return col in self.cfg.exempt_columns or col.endswith("_key")

    def _account_col(self, col: str) -> bool:
        return col in self.cfg.account_scan_columns or col.endswith("_masked")

    def scan_text(
        self,
        s: str,
        where: str,
        column: str | None = None,
        row: int | None = None,
        account: bool = False,
    ) -> list[Finding]:
        out = []
        if self.ssn.search(s):
            out.append(Finding(where, column, row, "ssn"))
        if self.card.search(s):
            out.append(Finding(where, column, row, "card"))
        if account and self.account.search(s):
            out.append(Finding(where, column, row, "account"))
        return out

    def scan_frame(self, df: pd.DataFrame, table: str) -> list[Finding]:
        findings: list[Finding] = []
        for col in df.columns:
            name = str(col)
            if name.startswith("_"):
                findings.append(Finding(table, name, None, "raw_column"))
                continue
            if self._exempt(name):
                continue
            s = df[col]
            if not (pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)):
                continue
            account = self._account_col(name)
            for i, v in zip(range(len(s)), s.tolist(), strict=True):
                if isinstance(v, str) and v:
                    findings += self.scan_text(v, table, name, i, account)
        return findings

    def check_frame(self, df: pd.DataFrame, table: str) -> None:
        if findings := self.scan_frame(df, table):
            raise LeakError(findings)

    def scan_records(self, records: list[dict], where: str) -> list[Finding]:
        return self.scan_frame(pd.DataFrame(records), where) if records else []

    def scan_file(self, path: Path) -> list[Finding]:
        """Column-aware scan of a written CSV / JSONL / workbook; plain scan of other text
        files. Binary files (the DuckDB database, scanned at build time) are skipped."""
        name = path.name
        if path.suffix in {".xlsx", ".xlsm"}:
            from breachlens.report.excel_writer import scan_workbook

            return scan_workbook(path, self)
        if path.suffix in {".duckdb", ".bin", ".png"}:
            return []
        if path.suffix == ".csv":
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            return self.scan_frame(df, name)
        if path.suffix == ".jsonl":
            lines = path.read_text(encoding="utf-8").splitlines()
            return self.scan_records([json.loads(x) for x in lines if x.strip()], name)
        text = path.read_text(encoding="utf-8")
        return self.scan_text(text, name, account=False)


def scan_dir(root: Path, guard: LeakGuard) -> tuple[list[Path], list[Finding]]:
    files = sorted(p for p in root.rglob("*") if p.is_file())
    findings: list[Finding] = []
    for p in files:
        findings += guard.scan_file(p)
    return files, findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scan written outputs for leaked identifiers.")
    ap.add_argument("dir", type=Path)
    ap.add_argument("--config", type=Path, default=Path("config/pipeline.yaml"))
    args = ap.parse_args(argv)
    from breachlens.config import load_config

    guard = LeakGuard(load_config(args.config).privacy.leak_guard)
    files, findings = scan_dir(args.dir, guard)
    for p in files:
        n = sum(1 for f in findings if f.where == p.name)
        rel = p.relative_to(args.dir).as_posix()
        print(f"  {rel:40s} {p.stat().st_size:>9,d} bytes  {n} finding(s)")
    print(f"leak guard: {len(files)} file(s) scanned, {len(findings)} finding(s)")
    for f in findings[:20]:
        print(f"  FINDING {f.where}.{f.column} row {f.row}: {f.pattern}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
