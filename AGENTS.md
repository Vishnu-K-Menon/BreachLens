# AGENTS.md — Instructions for the coding agent

You are building **BreachLens**, a portfolio-scale breach-data preparation pipeline.
It ingests **synthetic** breached data from two kinds of sources:
- **unstructured**: PDFs and scanned images
- **structured**: messy Excel/CSV exports

It maps both into one schema, then cleans, validates, verifies addresses, masks
sensitive values, and merges each person into one record. The results are:
- a notification-ready dataset in **DuckDB**
- an **Excel review workbook** with live formulas and VBA macros
- optional: **"Ask BreachLens"**, a local-LLM text-to-SQL assistant (moved to Optional by
  ADR-051, BreachLens Lite)

Python does the logic. KNIME orchestrates (native nodes for the spreadsheet track).
Excel is the review surface. DuckDB is the system of record.

## Read these first, in this order
1. `docs/PROJECT_OVERVIEW.md`: what and why, in plain words.
2. `docs/PLAN.md`: milestones, tasks, acceptance criteria. **This is your work queue.**
3. `docs/ARCHITECTURE.md`: modules, data flow, interfaces, repo layout.
4. `docs/DATA_SCHEMA.md`: every column. **This is the handoff contract.**
5. `docs/SPREADSHEET_TRACK.md`: the structured-file pipeline.
6. `docs/VALIDATION_RULES.md`: rule catalogue and reason codes.
7. `docs/SYNTHETIC_DATA.md`: corpus, planted cases, ground truth.
8. `docs/ML_MODELS.md`: column-type classifier (required), optional models.
9. `docs/EXCEL_WORKBOOK.md`: sheets, formulas, macros.
10. `docs/DATABASE_AND_ASK.md`: DuckDB schema, views, SQL queries, the Ask assistant.
11. `docs/PRIVACY.md`: **non-negotiable guardrails.**
12. `docs/DECISIONS.md`: ADRs. Do not silently contradict them.
13. `docs/WORKFLOW.md`: environment, commands, tests, commits, progress log.
14. `docs/DESIGN_RATIONALE.md`: public justification for each feature.

## Hard rules
- **No real personal data, ever.** Everything comes from `breachlens.synth` (`src/breachlens/synth/`). PDFs are watermarked
  `SYNTHETIC - NOT REAL`. Spreadsheets carry a first-sheet note or header comment saying
  the same.
- **Never persist a raw sensitive value.** Persist only `*_present`, `*_masked`,
  `*_valid` and HMAC keys. The leak-guard test must pass before any milestone is done.
- **The LLM never sees data rows.** The Ask assistant sends only the schema description
  and the question. SQL runs locally on a read-only connection.
- **Use only public sources and your own design.** No third-party proprietary templates
  or training material. Use our own snake_case column names.
- **Business rules live in `config/*.yaml`, not in code.**
- **Secrets go in `.env`.** Commit `.env.example` only.
- **Cache external API responses.** `offline: true` disables all network calls except
  the local Ollama endpoint.
- **Stay in scope.** Optional items are started only after M8 passes. Cut items
  (ADR-021) and items dropped by BreachLens Lite (ADR-051) are not built.
- **Hand-made work is off limits.** `notebooks/`, `excel/manual/`, `knime/manual/`,
  `docs/memos/` and the content of `sql/queries/*.sql` are the human's own hand-written
  work. Never create, edit, format, run or stage anything in them. In `sql/queries/` the
  agent creates only the folder, the question headers and the snapshot/test harness
  (ADR-051). Stage commits by explicit path, never `git add -A` at the repo root.

## Definition of done (every task)
- Typed code. `ruff format` and `ruff check` are clean. Unit tests exist for new logic.
  `pytest` passes.
- `python -m breachlens run --config config/pipeline.yaml` still runs end to end.
- `PROGRESS.md` is updated. Any deviation is recorded as an ADR in `docs/DECISIONS.md`.

## When unsure
Choose the simplest option that meets the acceptance criteria and record it as an ADR.
Ask the human only when a choice is irreversible or changes a deliverable.
