# DATABASE_AND_ASK.md

> **Scope (ADR-067, M6 as built):** DuckDB as the system of record, 6 tables + a
> `schema_version` table, 3 views, and a harness for 5 queries **that the project owner
> writes by hand** (`sql/queries/q1…q5`). The agent wrote only the question comment in
> each file. Ask BreachLens is Optional; its spec further down applies only if it is
> built.

## DuckDB: system of record
- **File:** `data/output/breachlens.duckdb`.
- **Source:** `breachlens db build` rebuilds it from one run folder
  (`data/output/<run_id>/`, default: the newest run that has `people.csv`).
- **Leak guard:** the build goes to a temp file. Every table and view is read back
  through the leak guard; on any finding nothing is saved.
- **Keys:** every table keeps `run_id`, and primary keys are composite with it
  (ADR-030), so loading more runs later stays possible. Today the database holds one
  run.
- **Nothing raw:**
  - Identifiers exist only as `*_present` (BOOLEAN), `*_masked` (last 4 visible),
    `*_valid` (`PASS`, a reason code, or NULL) and `*_key` (HMAC, for joins inside the
    database only).
  - The printed-text columns `raw_name`, `raw_address` and `source_snippet` are left out.
- **Types:**
  - ZIPs and IDs are VARCHAR (leading zeros kept).
  - `dob` / `doc_date` are DATE.
  - `processed_at` / `ts` / `built_at` are UTC TIMESTAMP.
  - Flags are BOOLEAN; scores are DOUBLE.

### Writing q1–q5
**Write q1–q5 against base tables (`people`, `notification_list`, `mentions`); use the
views only to check your answers.**

How to run:
```powershell
.\.venv\Scripts\python.exe -m breachlens db build
.\.venv\Scripts\python.exe -m breachlens sql run
```

Rules the harness enforces:
- **Connection:** read-only, with `enable_external_access=false`. No writes, `COPY`,
  `ATTACH` or file reads.
- **Statements:** one `SELECT` / `WITH` statement per file.
- **No keys:** a query fails if any result column ends in `_key`. This includes
  `SELECT *` from `mentions`.
- **Empty files:** a file with only comments is reported EMPTY and skipped.
- **Output:** results go to `data/output/sql/<file>.csv` through the leak guard.

Hints (reference only):
- **q1:** "gets a notice" means `notification_list.notify_required` is true. The state
  of a notice is `notification_list.jurisdiction`.
- **q2:** `notification_list.notify_status` is `READY`, `NEEDS_REVIEW` or
  `NOT_REQUIRED`. There is one row per person.
- **q3:** use `people.address_status`. It can be NULL for a person without an address.
- **q4:** a minor is `people.is_minor`. The guardian instruction is in
  `notification_list.notify_note` (text starting `Notify parent/guardian`). Join the two
  tables on `(run_id, person_id)`.
- **q5:** `mentions.qc_reasons` is a `;`-joined list per mention, e.g.
  `NAME_TITLE_REMOVED;DUPLICATE_CANDIDATE`. DuckDB has `string_split()` and `unnest()`
  for turning a list into rows. Severities are in `config/rules.yaml`.

### Tables
Primary keys are in **bold**. Every table has `run_id`.

**`people`**: one golden record per resolved person (`breachlens.resolve.survivorship`).
PK (**run_id, person_id**).

| column | type | meaning |
|---|---|---|
| person_id | VARCHAR | `P0001`… within a run |
| first_name, middle_initial, last_name, name_suffix | VARCHAR | most complete version across the person's mentions |
| address_line1, address_line2, city, state, zip5, country | VARCHAR | surviving address: newest `doc_date`, then the most frequent VERIFIED address (ADR-029). Dependents and minors may use the household address |
| address_status | VARCHAR | VERIFIED / CORRECTED / UNVERIFIED / INVALID / NOT_CHECKED, or NULL |
| dob | DATE | mode of the valid DOBs |
| is_minor | BOOLEAN | under 18 at `as_of_date` (2026-10-01) |
| `<element>_exposed` | BOOLEAN | ssn, dl, state_id, passport, bank_account, card, mrn, diagnosis, procedure, date_of_service, health_member_id, health_group_number, dob, student_id |
| elements_exposed | VARCHAR | display list, e.g. `SSN; MEDICAL INFO` |
| gov_id_exposed, financial_exposed, medical_exposed, health_insurance_exposed, education_exposed | BOOLEAN | category flags (ADR-028) |
| mention_count | BIGINT | mentions in the cluster |
| source_docs, source_types | VARCHAR | `;`-joined source files / `PDF;SPREADSHEET` |
| cluster_confidence | DOUBLE | minimum merge-edge score (1.0 for a single mention) |
| ferpa_flag | BOOLEAN | education record exposed (informational, not a trigger) |
| needs_review | BOOLEAN | card PRECISION_LOST / LUHN_FAIL, gray-zone pair, or DOB conflict |
| notify_required | BOOLEAN | same value as in `notification_list` |

**`notification_list`**: one row per person (`breachlens.notify.triggers`). PK
(**run_id, person_id**).

| column | type | meaning |
|---|---|---|
| person_id | VARCHAR | → `people` |
| jurisdiction | VARCHAR | the golden record's state (`UNKNOWN` if none). NJ/MA use the `default` rules |
| last_name, first_name, middle_initial, name_suffix, address_line1, address_line2, city, state, zip5, country | VARCHAR | mailing name and address |
| elements_exposed | VARCHAR | display list |
| notify_required | BOOLEAN | ≥ 1 covered element for the jurisdiction (`config/jurisdictions.yaml`, illustrative) |
| notify_reason | VARCHAR | `;`-joined covered elements hit, e.g. `ssn;card` |
| notify_note | VARCHAR | `Notify parent/guardian (P…)`, `Address from household P…` and/or the FERPA note, `; `-joined |
| ferpa_flag | BOOLEAN | |
| address_status | VARCHAR | |
| notify_status | VARCHAR | READY / NEEDS_REVIEW / NOT_REQUIRED |

**`mentions`**: one row per person per source document. PK (**run_id, mention_id**). FK
(run_id, person_id) → `people`.

| column | type | meaning |
|---|---|---|
| mention_id | VARCHAR | `M00001`… |
| source_type | VARCHAR | PDF / SPREADSHEET |
| doc_id, source_file, source_sheet | VARCHAR | provenance |
| page, source_row | BIGINT | page (PDF); 1-based Excel row / CSV line (sheets) |
| related_mention_id | VARCHAR | dependent → subscriber, guardian → student, patient → insured |
| doc_type | VARCHAR | e.g. WAGE_STATEMENT, HEALTH_CLAIM, SPREADSHEET |
| doc_date | DATE | |
| person_role | VARCHAR | EMPLOYEE, PATIENT, INSURED, SUBSCRIBER, DEPENDENT, STUDENT, GUARDIAN, … |
| entity_type | VARCHAR | PERSON |
| name_title, first_name, middle_name, middle_initial, last_name, name_suffix, name_order_detected | VARCHAR | normalized name |
| address_line1, address_line2, city, state, zip5, zip4, country | VARCHAR | normalized address |
| address_status, address_suggestion, address_source | VARCHAR | status (ADR-063), suggestion, ZIPCHECK / CENSUS |
| phone, email | VARCHAR | E.164 / lower case |
| dob | DATE | |
| age_at_run | BIGINT | age at `as_of_date` |
| is_minor | BOOLEAN | |
| ssn_present / ssn_masked / ssn_valid / ssn_key | BOOLEAN / VARCHAR ×3 | trio + HMAC key. The same pattern applies to `dl_*` (+ `dl_state`), `state_id_*`, `passport_*` (+ `passport_country`) |
| bank_account_present / _masked / _valid; routing_number_present / _valid; card_present / _masked / _valid | | financial |
| mrn_present / _masked; health_member_id_present / _masked; health_group_number_present; diagnosis_present; procedure_present; date_of_service_present | | health |
| employee_id_present, student_id_present, student_id_masked | | employment / education |
| insurer_name, employer_name, school_name | VARCHAR | organization context |
| ferpa_flag | BOOLEAN | |
| field_confidence | VARCHAR | JSON `{field: confidence}` |
| extraction_method | VARCHAR | TEXT / OCR / SHEET |
| qc_status | VARCHAR | PASS / REVIEW / FAIL |
| qc_reasons | VARCHAR | `;`-joined reason codes (VALIDATION_RULES.md) |
| person_id | VARCHAR | → `people` |
| cluster_confidence | DOUBLE | |
| review_status | VARCHAR | PENDING unless PASS |
| processed_at | TIMESTAMP | |

**`pair_features`**: every scored candidate pair (ADR-025, ADR-064). PK (**run_id,
mention_a, mention_b**).

| column | type | meaning |
|---|---|---|
| mention_a, mention_b | VARCHAR | → `mentions` |
| f_first_jw, f_last_jw, f_dob, f_zip_eq, f_addr_tsr, f_ssn_key_eq, f_dl_key_eq, f_same_source_file, f_mi_eq | DOUBLE | features in [0, 1], NULL when a side lacks the field |
| score | DOUBLE | |
| pass | VARCHAR | A (SSN key) / B (DL / passport key) / C (weighted score) |
| decision | VARCHAR | MERGE / REVIEW / NO_MERGE |
| guard_fired | VARCHAR | SSN_KEY_DIFFERS, DOB_CONFLICT, NAME_ONLY, SAME_SOURCE_ROW, RELATED_MENTIONS, CLUSTER_CONFLICT |
| same_person_id | BOOLEAN | the two mentions ended in one person |

**`review_items`**: one row per review item (ADR-062). PK (**run_id, item_id**).

| column | type | meaning |
|---|---|---|
| item_id | VARCHAR | `COL:<doc>:<sheet>:<col>`, `MEN:<mention>`, `PAIR:<a>~<b>` |
| item_type | VARCHAR | COLUMN (column-level mapping warning, once per column), MENTION (the mention's own WARN/ERROR codes, without COL_*), PAIR (gray-zone pair) |
| doc_id, sheet, header | VARCHAR | for COLUMN items |
| mention_id, person_id | VARCHAR | for MENTION items (PAIR: first mention; `P…~P…`) |
| codes | VARCHAR | `;`-joined |
| severity | VARCHAR | ERROR / WARN |
| affected_rows | BIGINT | COLUMN: mentions that took a value from the column; MENTION 1; PAIR 2 |
| status | VARCHAR | OPEN; RESOLVED for a column with a human decision in `config/review_overrides.yaml` |

**`audit_log`**: the run's audit trail (ADR-037), values masked. PK (**run_id,
event_id**). Columns:
- event_id, ts (TIMESTAMP), stage
- event_type (RULE_FIRED, MERGE, ROUTED_EXCLUDED, REVIEW_OVERRIDE_APPLIED)
- item_id, field, code
- old_value_masked, new_value_masked, detail_json

**`schema_version`**: one row. Columns: schema_version (`1.1`), run_id, built_at,
source_dir, table_rows (JSON counts).

### Views (`sql/views/`, created by `db build`)
- `v_notify_by_state`: jurisdiction, people, to_notify, needs_review, minors,
  ferpa_flagged.
- `v_review_queue`: OPEN `review_items`, ordered by severity, then by affected_rows
  descending. Columns: item_type, item_id, doc_id, sheet, header, mention_id, person_id,
  codes, severity, affected_rows. Column-level warnings are one row per column.
- `v_address_status`: address_status (`NONE` = no address), people, mentions.

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
