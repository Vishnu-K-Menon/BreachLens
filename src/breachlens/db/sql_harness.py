"""`breachlens sql run`: run the hand-written queries in `sql/queries/*.sql` (ADR-067).

- Read-only connection with `enable_external_access=false`: queries cannot write,
  attach databases or read/write files.
- One `SELECT`/`WITH` statement per file. A file that has only comments (the question)
  is reported EMPTY and skipped.
- A query fails if any result column ends in `_key` (HMAC keys never leave the database).
- Results go to `data/output/sql/<name>.csv` through the guarded writer, so the leak
  guard runs on them too.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import duckdb

from breachlens.privacy.leak_guard import LeakError
from breachlens.privacy.writer import GuardedWriter

OK, EMPTY, FAILED = "OK", "EMPTY", "FAILED"


@dataclass(frozen=True)
class QueryResult:
    name: str
    status: str
    rows: int | None = None
    detail: str = ""
    output: Path | None = None


def connect_read_only(db: Path) -> duckdb.DuckDBPyConnection:
    if not db.is_file():
        raise FileNotFoundError(f"{db} not found; run `breachlens db build` first")
    return duckdb.connect(str(db), read_only=True, config={"enable_external_access": False})


def strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines()).strip()


def check_sql(sql: str) -> str | None:
    """Reason a query is not allowed, or None."""
    body = sql.strip().rstrip(";").strip()
    if ";" in body:
        return "only one statement per file"
    if not re.match(r"^(select|with)\b", body, re.I):
        return "only SELECT / WITH queries are allowed"
    return None


def run_query(con: duckdb.DuckDBPyConnection, path: Path, writer: GuardedWriter) -> QueryResult:
    name = path.stem
    sql = strip_comments(path.read_text(encoding="utf-8"))
    if not sql:
        return QueryResult(name, EMPTY, detail="question only, no SQL yet")
    if reason := check_sql(sql):
        return QueryResult(name, FAILED, detail=reason)
    try:
        rel = con.execute(sql)
    except duckdb.Error as exc:
        return QueryResult(name, FAILED, detail=f"{type(exc).__name__}: {str(exc).splitlines()[0]}")
    keys = [d[0] for d in rel.description or [] if str(d[0]).lower().endswith("_key")]
    if keys:
        return QueryResult(name, FAILED, detail=f"selects key column(s): {', '.join(keys)}")
    df = rel.fetchdf()
    try:
        out = writer.write_csv(df, f"{name}.csv")
    except LeakError as exc:
        return QueryResult(name, FAILED, detail=f"leak guard: {len(exc.findings)} finding(s)")
    return QueryResult(name, OK, rows=len(df), output=out)


def run_all(db: Path, queries: Path, writer: GuardedWriter) -> list[QueryResult]:
    con = connect_read_only(db)
    try:
        return [run_query(con, p, writer) for p in sorted(queries.glob("*.sql"))]
    finally:
        con.close()
