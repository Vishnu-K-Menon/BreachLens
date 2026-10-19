"""`breachlens db build`: load one run's outputs into DuckDB (ADR-067).

The database is rebuilt from a single run folder (`data/output/<run_id>/`). Every table
keeps `run_id` and composite primary keys (ADR-030), so appending runs later stays
possible. The build goes to a temp file, and every table and view is read back
through the leak guard. Only if there are no findings is the temp file moved to
`data/output/breachlens.duckdb`.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from breachlens.db.schema import (
    EXCLUDED_COLUMNS,
    FOREIGN_KEYS,
    PRIMARY_KEYS,
    SCHEMA_VERSION,
    SOURCES,
    sql_type,
)
from breachlens.privacy.leak_guard import Finding, LeakError, LeakGuard
from breachlens.validate.engine import COLUMN_WARN
from breachlens.validate.settings import load_validation_settings

SEVERITY_ORDER = {"ERROR": 0, "WARN": 1, "INFO": 2}
TABLE_ORDER = [
    "people",
    "mentions",
    "notification_list",
    "pair_features",
    "review_items",
    "audit_log",
]


def find_run(output_dir: Path, run: str = "latest") -> Path:
    """A run folder with M5 outputs; `latest` = the newest one that has people.csv."""
    if run != "latest":
        p = output_dir / run
        if not (p / "people.csv").is_file():
            raise FileNotFoundError(f"{p} has no people.csv (run the pipeline first)")
        return p
    runs = sorted(p for p in output_dir.glob("R*") if (p / "people.csv").is_file())
    if not runs:
        raise FileNotFoundError(
            f"no run with people.csv under {output_dir}; run `breachlens run` first"
        )
    return runs[-1]


def read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    keep = [c for c in df.columns if c not in EXCLUDED_COLUMNS and not str(c).startswith("_")]
    return df[keep].replace("", None)


def read_audit(run_dir: Path) -> pd.DataFrame:
    files = sorted(run_dir.glob("audit_*.jsonl"))
    cols = [
        "event_id",
        "run_id",
        "ts",
        "stage",
        "event_type",
        "item_id",
        "field",
        "code",
        "old_value_masked",
        "new_value_masked",
        "detail_json",
    ]
    rows = [
        json.loads(line)
        for f in files
        for line in f.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return pd.DataFrame(rows, columns=cols).astype(object).where(lambda d: d.notna(), None)


def _codes(v: Any) -> list[str]:
    return [c for c in str(v).split(";") if c] if v else []


def review_items(
    mentions: pd.DataFrame,
    mapping: pd.DataFrame,
    pairs: pd.DataFrame,
    severity: dict[str, str],
    run_id: str,
) -> pd.DataFrame:
    """One row per review item (ADR-062): a column-level warning once per column (with
    `affected_rows`), a mention's own row-level WARN/ERROR codes, a gray-zone pair."""
    rows: list[dict[str, Any]] = []
    for _, c in mapping.iterrows():
        codes = [x for x in _codes(c.get("codes")) if x in COLUMN_WARN]
        if not codes:
            continue
        rows.append(
            {
                "item_id": f"COL:{c['doc_id']}:{c.get('sheet') or ''}:{c['col_idx']}",
                "item_type": "COLUMN",
                "doc_id": c["doc_id"],
                "sheet": c.get("sheet"),
                "header": c.get("header_raw"),
                "mention_id": None,
                "person_id": None,
                "codes": ";".join(codes),
                "severity": "WARN",
                "affected_rows": int(c.get("affected_rows") or 0),
                "status": "RESOLVED" if c.get("reviewed_label") else "OPEN",
            }
        )
    for _, m in mentions.iterrows():
        own = [
            x
            for x in _codes(m.get("qc_reasons"))
            if x not in COLUMN_WARN and severity.get(x) in ("WARN", "ERROR")
        ]
        if not own:
            continue
        sev = min((severity[x] for x in own), key=SEVERITY_ORDER.__getitem__)
        rows.append(
            {
                "item_id": f"MEN:{m['mention_id']}",
                "item_type": "MENTION",
                "doc_id": m["doc_id"],
                "sheet": m.get("source_sheet"),
                "header": None,
                "mention_id": m["mention_id"],
                "person_id": m.get("person_id"),
                "codes": ";".join(own),
                "severity": sev,
                "affected_rows": 1,
                "status": "OPEN",
            }
        )
    gray = pairs[(pairs["decision"] == "REVIEW") & (pairs["same_person_id"].astype(str) != "True")]
    pid = dict(zip(mentions["mention_id"], mentions["person_id"], strict=True))
    for _, p in gray.iterrows():
        code = (
            "DOB_CONFLICT_IN_CLUSTER"
            if p.get("guard_fired") == "DOB_CONFLICT" and p.get("pass") == "A"
            else "DUPLICATE_CANDIDATE"
        )
        rows.append(
            {
                "item_id": f"PAIR:{p['mention_a']}~{p['mention_b']}",
                "item_type": "PAIR",
                "doc_id": None,
                "sheet": None,
                "header": None,
                "mention_id": p["mention_a"],
                "person_id": f"{pid.get(p['mention_a'])}~{pid.get(p['mention_b'])}",
                "codes": code,
                "severity": "WARN",
                "affected_rows": 2,
                "status": "OPEN",
            }
        )
    cols = [
        "item_id",
        "item_type",
        "doc_id",
        "sheet",
        "header",
        "mention_id",
        "person_id",
        "codes",
        "severity",
        "affected_rows",
        "status",
    ]
    out = pd.DataFrame(rows, columns=cols)
    out.insert(1, "run_id", run_id)
    return out


def _create(con: duckdb.DuckDBPyConnection, name: str, df: pd.DataFrame) -> None:
    for c in df.columns:  # timestamps are stored as UTC TIMESTAMP
        if sql_type(c) == "TIMESTAMP":
            df[c] = df[c].map(lambda v: str(v).replace("+00:00", "") if v is not None else None)
    cols = ", ".join(f'"{c}" {sql_type(c)}' for c in df.columns)
    keys = f", PRIMARY KEY ({', '.join(PRIMARY_KEYS[name])})" if name in PRIMARY_KEYS else ""
    fk = (
        f", FOREIGN KEY {FOREIGN_KEYS[name][0]} REFERENCES {FOREIGN_KEYS[name][1]}"
        if name in FOREIGN_KEYS
        else ""
    )
    con.execute(f"CREATE TABLE {name} ({cols}{keys}{fk})")
    con.register("src_df", df.astype(object).where(df.notna(), None))
    select = ", ".join(f'CAST("{c}" AS {sql_type(c)})' for c in df.columns)
    con.execute(f"INSERT INTO {name} SELECT {select} FROM src_df")
    con.unregister("src_df")


def scan_database(
    con: duckdb.DuckDBPyConnection, guard: LeakGuard
) -> tuple[list[str], list[Finding]]:
    names = [
        r[0]
        for r in con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()
    ]
    findings: list[Finding] = []
    for n in names:
        findings += guard.scan_frame(con.execute(f'SELECT * FROM "{n}"').fetchdf(), n)
    return names, findings


def build_database(run_dir: Path, db_path: Path, root: Path, guard: LeakGuard) -> dict[str, Any]:
    s = load_validation_settings(root / "config")
    tables = {name: read_csv(run_dir / f) for name, f in SOURCES.items()}
    run_id = (
        str(tables["mentions"]["run_id"].dropna().iloc[0])
        if "run_id" in tables["mentions"]
        else run_dir.name
    )
    for df in tables.values():
        if "run_id" not in df:
            df.insert(0, "run_id", run_id)
    mapping = (
        read_csv(run_dir / "column_mapping.csv")
        if (run_dir / "column_mapping.csv").is_file()
        else pd.DataFrame(
            columns=[
                "doc_id",
                "sheet",
                "col_idx",
                "header_raw",
                "codes",
                "reviewed_label",
                "affected_rows",
            ]
        )
    )
    tables["review_items"] = review_items(
        tables["mentions"], mapping, tables["pair_features"], s.severity, run_id
    )
    tables["audit_log"] = read_audit(run_dir)
    tables["audit_log"]["run_id"] = tables["audit_log"]["run_id"].fillna(run_id)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_name(db_path.name + ".tmp")
    for p in (tmp, tmp.with_name(tmp.name + ".wal")):
        p.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    try:
        for name in TABLE_ORDER:
            _create(con, name, tables[name].copy())
        counts = {
            n: int(con.execute(f"SELECT count(*) FROM {n}").fetchone()[0]) for n in TABLE_ORDER
        }
        con.execute(
            "CREATE TABLE schema_version (schema_version VARCHAR, run_id VARCHAR, "
            "built_at TIMESTAMP, source_dir VARCHAR, table_rows VARCHAR)"
        )
        src = run_dir.relative_to(root).as_posix() if run_dir.is_relative_to(root) else run_dir.name
        con.execute(
            "INSERT INTO schema_version VALUES (?, ?, ?, ?, ?)",
            [
                SCHEMA_VERSION,
                run_id,
                datetime.now(UTC).replace(tzinfo=None),
                src,
                json.dumps(counts),
            ],
        )
        views = []
        for f in sorted((root / "sql" / "views").glob("v_*.sql")):
            con.execute(f.read_text(encoding="utf-8"))
            views.append(f.stem)
        names, findings = scan_database(con, guard)
    finally:
        con.close()
    if findings:
        tmp.unlink(missing_ok=True)
        raise LeakError(findings)
    os.replace(tmp, db_path)
    return {
        "db": db_path,
        "run_id": run_id,
        "source_dir": src,
        "tables": counts,
        "views": views,
        "scanned": names,
        "findings": 0,
    }
