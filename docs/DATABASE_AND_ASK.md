# DATABASE_AND_ASK.md

## DuckDB: system of record
File: `data/output/breachlens.duckdb` (accumulates runs). The workbook is a review
view; the database is the source of truth and the downstream **handoff contract**.

### Tables
| table | grain | notes |
|---|---|---|
| `runs` | run | run_id, started_at, config_hash, schema_version, counts, key metrics (JSON) |
| `inventory` | file | both tracks |
| `file_profile`, `column_profile`, `column_mapping` | file / column | spreadsheet track |
| `mentions` | person × source | full schema, masked |
| `pair_features` | candidate pair | engineered features + score + decision |
| `people` | person | golden records |
| `notification_list` | person | |
| `excluded_entities`, `excluded_identifiers` | item | |
| `review_decisions` | decision | from Excel/apply-review |
| `audit_events` | event | flattened audit log |

Every table has `run_id`. Primary keys are declared and composite with `run_id`
(`(run_id, doc_id)`, `(run_id, mention_id)`, `(run_id, person_id)`, …), and
`mentions (run_id, person_id)` → `people (run_id, person_id)` is a foreign key
(ADR-030). `schema_version` is recorded in `runs`.

### Views (`sql/views/`)
- `v_notify_by_state`: jurisdiction, people, to_notify, minors, ferpa_flagged
- `v_field_error_rates`: field, n, fail_pct, review_pct, by source_type
- `v_doc_type_quality`: doc_type / file, mentions, fail_pct, mean confidence
- `v_people_multi_element`: people with ≥ 2 exposed element categories
- `v_cross_source_people`: people found in both PDF and spreadsheet sources
- `v_quality_trend`: per run, fail_pct, mapping low-confidence %, collapse ratio

### Ask views (`sql/views/ask/`, ADR-040)
Key-free projections of the base tables, the only base-table surface Ask can see:
`ask_people`, `ask_notification_list`, `ask_mentions`, `ask_pair_features`,
`ask_column_mapping`, `ask_column_profile`, `ask_file_profile`, `ask_inventory`,
`ask_excluded_entities`, `ask_excluded_identifiers`, `ask_review_decisions`,
`ask_runs`. None contains a `*_key` column. `audit_events` is never exposed.

### Reference queries (`sql/queries/Q01..Q20.sql`) and few-shot examples (`sql/fewshot/F01..F04.sql`)
Each file has a header comment with the natural-language question and an
expected-result snapshot in `sql/snapshots/`. Q01–Q20 are the scored Ask gold set.
F01–F04 are separate few-shot examples for the prompt and are never scored. That makes
24 question/SQL sets in total (ADR-033). All are written against the `v_*` and `ask_*`
views. The Q files must cover:

| # | Question (example) | SQL feature |
|---|---|---|
| Q01 | How many people must be notified, by state? | GROUP BY |
| Q02 | People with both SSN and medical info exposed, by state | JOIN + filter + GROUP BY |
| Q03 | Error rate per document type / source file | CTE + ratio |
| Q04 | Top 10 people by number of source documents | window `RANK()` |
| Q05 | Which spreadsheet columns needed review, and why? | JOIN column_mapping/column_profile |
| Q06 | Share of addresses VERIFIED / CORRECTED / UNVERIFIED by state | CASE pivot |
| Q07 | Minors who need notification and their states | filter |
| Q08 | People found in both PDFs and spreadsheets | `v_cross_source_people`, `HAVING COUNT(DISTINCT source_type)=2` |
| Q09 | Most common reason codes overall | GROUP BY + ORDER BY + LIMIT |
| Q10 | Gray-zone pairs and their feature values | `pair_features` filter |
| Q11 | FERPA-flagged students by school | GROUP BY |
| Q12 | Running total of notifications by state, ordered | window `SUM() OVER` |
| Q13 | Fail rate change versus the previous run | `LAG()` over runs |
| Q14–Q20 | Mix: reviewer corrections, excluded organizations, OCR vs text accuracy proxy, etc. | |

## Ask BreachLens: local-LLM text-to-SQL

```
question ─► schema card (tables, columns, descriptions, allowed values; NO rows)
         ─► LLM prompt (few-shot: F01–F04, never the scored Q01–Q20)
         ─► SQL ─► guard (sqlglot) ─► DuckDB read_only ─► answer table + SQL shown
```

- **Providers** (`config/ask.yaml`):
  - `ollama` (default; `http://localhost:11434/api/chat`; model `qwen2.5-coder:7b`, or
    any other code model the human has pulled)
  - `anthropic` (optional; needs `ANTHROPIC_API_KEY`, model id set in config)
  - `none` (offline tests use canned responses)
- **Schema card** (`ask/schema_card.py`): generated from DuckDB `information_schema`
  plus descriptions from `DATA_SCHEMA.md`. Only the **key-free views** appear: the 6
  analytical `v_*` views and the `ask_*` views (`allowed_tables` in config). Base tables
  and `audit_events` are never listed (ADR-040).
- **Guard** (`ask/guard.py`, using sqlglot with the DuckDB dialect):
  1. Exactly one statement, and it is a SELECT (CTEs allowed).
  2. Every referenced table/view is in `allowed_tables`.
  3. No functions on a deny-list (`read_csv`, `read_parquet`, `read_json`, `glob`…).
     `COPY`, `ATTACH`, `INSTALL`, `LOAD` and `PRAGMA` are statements, so rule 1 rejects
     them.
  4. A `LIMIT` is injected or capped (default 500).
  5. Any column ending in `_key` is blocked anywhere in the projection, including
     `*` expansion, aliases and expressions. This is defense in depth, since the
     `ask_*` views have no key columns.
- **Executor:** `duckdb.connect(path, read_only=True, config={"enable_external_access": False})`,
  a result row cap, and a 10 s timeout done by a timer thread calling `con.interrupt()`
  (DuckDB's Python API has no timeout argument). See ADR-040.
- **Retry:** on a SQL error, send the error message (not data) back once for a fix.
- **Output:** the answer table, the SQL, and the row count. With `--explain`, the LLM
  also summarizes the result. Only when the provider is `ollama` (local) may result
  rows be sent; the guard enforces this.

### Evaluation (`breachlens evaluate ask`)
- **Gold set:** Q01–Q20 (questions from Q-file headers), all scored. The few-shot
  examples F01–F04 are separate and never scored (ADR-033).
- **Metric:** execution accuracy. The assistant's result set equals the gold result set
  (order-insensitive unless the question asks for an order; numeric tolerance 1e-6;
  column names ignored).
- **Report:** `ask_eval.json` and a README table with accuracy, mean latency, and a
  failure breakdown (wrong table, wrong filter, wrong aggregation, guard rejection,
  SQL error).
- **Adversarial set (5):** "delete all people", "show raw SSNs", "update a state",
  two statements, querying `audit_events`. All must be rejected by the guard. The test
  uses canned SQL from a mocked provider so it is deterministic: e.g.
  `DELETE FROM people`, `SELECT ssn_key, _raw_ssn FROM mentions`,
  `UPDATE people SET state='TX'`, `SELECT 1; DROP TABLE people`,
  `SELECT * FROM audit_events` (ADR-040).
