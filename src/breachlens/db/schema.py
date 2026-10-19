"""DuckDB schema for the system of record (DATABASE_AND_ASK.md, ADR-067).

Column types follow the column names, so the database matches whatever the run wrote:

- BOOLEAN: `*_present`, `*_exposed`, `is_minor`, `ferpa_flag`, `needs_review`,
  `notify_required`, `same_person_id`
- BIGINT: counts and positions
- DOUBLE: `f_*` features, scores, confidences, probabilities
- DATE: `dob`, `doc_date`; TIMESTAMP (UTC): `processed_at`, `ts`, `built_at`
- VARCHAR: everything else, including ZIPs and IDs (leading zeros kept) and
  `elements_exposed` (a display list)

Identifiers exist only as `*_present` / `*_masked` / `*_valid` / `*_key`. The printed text
columns below are left out of the database.
"""

from __future__ import annotations

SCHEMA_VERSION = "1.1"

# table -> source file in the run folder; review_items is derived (db/load.py)
SOURCES = {
    "people": "people.csv",
    "mentions": "mentions.csv",
    "notification_list": "notification_list.csv",
    "pair_features": "pair_features.csv",
}
PRIMARY_KEYS = {
    "people": ("run_id", "person_id"),
    "mentions": ("run_id", "mention_id"),
    "notification_list": ("run_id", "person_id"),
    "pair_features": ("run_id", "mention_a", "mention_b"),
    "review_items": ("run_id", "item_id"),
    "audit_log": ("run_id", "event_id"),
}
FOREIGN_KEYS = {"mentions": ("(run_id, person_id)", "people (run_id, person_id)")}
# Printed text, kept out of the system of record (ADR-067).
EXCLUDED_COLUMNS = {"raw_name", "raw_address", "source_snippet"}

BOOL_COLUMNS = {"is_minor", "ferpa_flag", "needs_review", "notify_required", "same_person_id"}
INT_COLUMNS = {
    "page",
    "source_row",
    "age_at_run",
    "mention_count",
    "col_idx",
    "affected_rows",
    "rows",
}
FLOAT_COLUMNS = {"score", "cluster_confidence", "ml_proba"}
DATE_COLUMNS = {"dob", "doc_date"}
TIMESTAMP_COLUMNS = {"processed_at", "ts", "built_at"}


TEXT_COLUMNS = {"elements_exposed"}  # display list ("SSN; MEDICAL INFO"), not a flag


def sql_type(column: str) -> str:
    if column in TEXT_COLUMNS:
        return "VARCHAR"
    if column in BOOL_COLUMNS or column.endswith(("_present", "_exposed")):
        return "BOOLEAN"
    if column in INT_COLUMNS:
        return "BIGINT"
    if column in FLOAT_COLUMNS or column.startswith("f_"):
        return "DOUBLE"
    if column in DATE_COLUMNS:
        return "DATE"
    if column in TIMESTAMP_COLUMNS:
        return "TIMESTAMP"
    return "VARCHAR"
