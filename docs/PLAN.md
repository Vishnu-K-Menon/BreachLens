# PLAN.md — Build plan (6 days)

Goal: a public GitHub repo that demonstrates a privacy-safe, two-source breach-data
pipeline (PDF/scan + Excel/CSV), producing:
- a notification-ready dataset in DuckDB
- a formula- and macro-driven Excel review workbook
- (optional, ADR-051) an evaluated text-to-SQL assistant

Everything is reproducible with one command and measured against ground truth.

Milestones run in order. Do not start the next until the current acceptance criteria
(AC) pass. Tick the boxes as you go.

| Day | Milestones |
|---|---|
| 1 | M0 Scaffold, M1 Synthetic corpus |
| 2 | M2 PDF track, M3 Spreadsheet track (start) |
| 3 | M3 finish (incl. ML column classifier), M4 Normalize + validate + privacy |
| 4 | M5 Address + matching + notification + scale test (50k timing), M6 Database + SQL (Lite) |
| 5 | M7 Excel workbook (Lite: 7 sheets, 2 macros), KNIME guide (spreadsheet track), evaluation |
| 6 | M8 README/docs, release (Ask BreachLens is optional, ADR-051) |

---

## M0 — Scaffold (Day 1, ~1 hr)
- [x] Repo layout per `ARCHITECTURE.md §Repo layout`.
- [x] `pyproject.toml` (Python 3.11, `src/breachlens`). Core deps per `WORKFLOW.md`
      (incl. `requests`). Extras (ADR-038): `[dev]` (pytest, ruff), `[ocr]`
      (pytesseract), `[ml]` (scikit-learn, joblib, matplotlib), `[ask]` (sqlglot),
      `[anthropic]` (anthropic).
- [x] `.gitignore`, `.env.example`, `PROGRESS.md`.
- [x] Typer CLI stubs: `generate`, `run`, `evaluate [TARGET]`, `train MODEL`,
      `apply-review`, `ask`, `scale-test`, `report` (ADR-039).
- [x] Pydantic config loader.

**AC:** `pip install -e .[dev]` works, `python -m breachlens --help` lists all
commands, and `pytest` runs.

## M1 — Synthetic corpus + ground truth (Day 1)
Spec: `SYNTHETIC_DATA.md`.
- [x] `src/breachlens/synth/people.py`: 40 base people across CA, NY, TX, FL, PA and VA, plus planted
      variants, dependents, students + guardians, and 8 organizations.
- [x] `data/reference/address_pool.csv`: ≥ 40 public, non-residential addresses
      (libraries, city halls, post offices found by web search), each verified live
      with the Census single-line geocoder (ADR-043).
- [x] `src/breachlens/synth/render_pdf.py`: 4 PDF types × 2 layout variants each, ~30 documents.
      `src/breachlens/synth/scanify.py` turns ~30% into image-only scans.
- [x] `src/breachlens/synth/render_sheets.py`: the 8 messy corpus spreadsheet files, with every mess
      listed in `SYNTHETIC_DATA.md §Spreadsheets` (ADR-032).
- [x] `doc_date` set on every generated document (ADR-029).
- [x] `src/breachlens/synth/column_corpus.py`: training tables for the column classifier
      (`ML_MODELS.md §C`).
- [x] `src/breachlens/synth/scale.py`: generator for N flat records (default 10,000) for the scale
      test, plus `large_claims.csv` (50k rows) in `data/raw/scale/`, never in the
      corpus (ADR-031).
- [x] Ground truth in `data/raw/corpus_v1/truth/`: `gt_mentions.csv`, `gt_people.csv`,
      `gt_columns.csv`, `gt_excluded.csv`, `manifest.json` (ADR-047).
- [x] Preview PNGs of one PDF per type → `data/output/previews/` for human review.

**AC:** The generator is deterministic (identical ground truth on re-run). Every
planted case P01–P44 exists. **Human checks the previews before M2.**

## M2 — PDF track (Day 2, morning)
- [x] `ingest/inventory.py`: all files (PDF + spreadsheet). sha256, type, size, exact
      duplicates.
- [x] `ingest/text_extract.py` (pdfplumber) and `ingest/ocr.py` (PyMuPDF raster +
      Tesseract with word confidences).
- [x] `classify/doctype.py`: keyword-rule classifier from `config/doc_templates/*.yaml`.
- [x] `extract/templates.py`: label-anchored extraction from YAML.
- [x] `extract/identifiers.py`: SSN vs EIN/ITIN/NPI disambiguation → `excluded_identifiers`.
- [x] `extract/entity_type.py`: PERSON vs ORG → `excluded_entities`.
- [x] Emit `mentions` rows with `source_type=PDF` (in memory only until M4; ADR-044).

**AC:** Recall ≥ 0.95 for name, DOB and SSN-present on text-layer PDFs. Scans are
processed and their accuracy is reported separately.

## M3 — Spreadsheet track + ML column classifier (Day 2 afternoon → Day 3 morning)
Spec: `SPREADSHEET_TRACK.md`, `ML_MODELS.md §C`.
- [x] `sheets/reader.py`: xlsx/xls/csv reading, encoding + delimiter detection,
      multi-sheet handling.
- [x] `sheets/profile.py`: `file_profile` + `column_profile` tables.
- [x] `sheets/layout.py`: header-row detection, merged-cell fill, drop title, total and
      blank rows, hidden-row flag.
- [x] `sheets/features.py`: column feature engineering.
- [x] `sheets/mapping.py`: header-rules mapper (baseline) plus ML mapper
      (`breachlens train column-classifier`). The decision table (ADR-034) and
      confidence go to `column_mapping`; REVIEW columns go to review.
- [x] `sheets/repair.py`: ZIP padding, date serials, precision-loss flags, Excel error
      values, combined-field splits, pre-masked values.
- [x] `sheets/reshape.py`: unpivot wide dependent columns into rows.
- [x] `sheets/freetext.py`: regex + validator scan of notes/comment columns.
- [x] Emit `mentions` rows with `source_type=SPREADSHEET`, `source_file`,
      `source_sheet`, `source_row` (in memory only until M4; ADR-044).
- [x] `knime/`: document the native-node version of steps reader → layout → repair.

**AC:**
- The ML mapper beats the header-only baseline on macro-F1 for the held-out
  "confusing headers" set. Report both.
- Every planted spreadsheet mess (P27–P44) is handled or flagged.
- The vendor file produces 0 person mentions.

## M4 — Normalize + validate + privacy (Day 3)
- [x] `normalize/names.py`, `normalize/addresses.py`, `normalize/dates.py`,
      `normalize/contact.py` per `VALIDATION_RULES.md`.
- [x] `validate/engine.py`: every rule in `config/rules.yaml`, with reason codes and
      severities.
- [x] `privacy/`: masking, HMAC keys, `drop_raw()`, `leak_guard` (patterns and scope
      per ADR-027).

**AC:** Every reason code has positive and negative tests. All planted validation cases
are caught. The leak-guard test passes on both tracks.

## M5 — Address + matching + notification + scale test (Day 4, morning)
- [x] `address/zipcheck.py` (offline `zipcodes`) and `address/census.py` (batch, cached).
- [x] `resolve/`: 3-pass matching, union-find clusters, survivorship. Persist
      `pair_features` (the engineered features) for every scored pair.
- [x] `notify/triggers.py`: per-state triggers, minor/guardian note, FERPA flag.
- [x] `breachlens scale-test`: time each stage on `data/raw/scale/large_claims.csv`
      (50k rows) only, and write `scale_report.json` (rows/sec per stage, peak memory).
      BreachLens Lite (ADR-051): no separate generated-records run.

**AC:**
- Matching: pairwise precision ≥ 0.95 and recall ≥ 0.90.
- Address status is reported as agreement with `expected_address_status` from ground
  truth, shown next to the expected distribution in `manifest.json` (ADR-050). A high
  UNVERIFIED share from fake streets is expected, not a failure. No merges among the
  unrelated pairs in `gt_shared_addresses.csv` (ADR-049).
- The twins case is not merged. The moved-address case is merged.
- **Cross-source merge works:** a person in `payroll_export.csv` and a W-2 PDF ends up
  as one `person_id`.
- The scale report is generated.

## M6 — Database + SQL (Day 4, afternoon) — Lite scope (ADR-051, as restated in ADR-067)
Spec: `DATABASE_AND_ASK.md`.
- [x] `breachlens db build` → `data/output/breachlens.duckdb`:
  - tables `people`, `mentions`, `notification_list`, `pair_features`, `review_items`,
    `audit_log` + `schema_version`
  - masked/present/valid/key columns only, nothing raw
  - leak guard on the database before it is saved
- [x] 3 views: `v_notify_by_state`, `v_review_queue` (one row per column-level item with
      `affected_rows`, ADR-062), `v_address_status`.
- [x] `breachlens sql run`: every `sql/queries/*.sql` runs on a read-only connection,
      results go to `data/output/sql/<name>.csv` (guarded), and a query selecting any
      `*_key` column fails.
- [x] `sql/queries/q1…q5`: question comments only. **The human writes the SQL.**
- [x] `docs/DATABASE_AND_ASK.md`: table/column reference for writing the queries.

**AC:** The database builds. The views return the expected totals (155 notified). The
read-only connection and the `*_key` guard are enforced, and the leak guard finds 0.

## M7 — Excel workbook + KNIME + evaluation (Day 5) — Lite scope (ADR-051, as restated in ADR-068)
Spec: `EXCEL_WORKBOOK.md` (as reduced by ADR-051).
- [x] `report/excel_writer.py` (XlsxWriter), run by `breachlens report`, built from the
      DuckDB database:
  - sheets `Summary`, `Mentions`, `Review_Queue`, `People`, `Notification_List`,
    `Excluded`, `About`
  - Excel Tables, named ranges (`RunDate` = `as_of_date`, `RunId`)
  - live formulas (`COUNTIFS`, `SUMPRODUCT`, `XLOOKUP`, `IF(AND(...))`, `TEXTJOIN`,
    `DATEDIF`)
  - formula-based conditional formatting, data validation
  - `Review_Queue`: one item per column for COL_* warnings, with `affected_rows`
    (ADR-062); reviewed columns show as RESOLVED
  - masked values only; leak guard on the workbook
- [x] `excel/ReviewHelpers.bas` with 2 macros (`ShowPendingOnly`, `ExportDecisions`).
      **Human step:** import it into a blank workbook, save as `.xlsm`, and run
      `vba_extract.py` → `excel/vbaProject.bin` (`EXCEL_WORKBOOK.md`). The writer then
      embeds it and adds the buttons.
- [x] `report/recalc.py`: LibreOffice headless recalculation (dedicated profile,
      ADR-041). Asserts no `#REF!`/`#NAME?`/`#VALUE!`/`#DIV/0!` errors and that the
      Summary counts equal the Python counts.
- [x] `evaluate/metrics.py` (`breachlens evaluate pipeline`):
  - per-field P/R/F1 by track
  - column-classifier metrics, matching metrics
  - address status accuracy vs expected (ADR-050)
  - collapse ratio, throughput
  - output: `metrics.json` and `METRICS.md`, plus one row in `runs.csv`
- [x] KNIME guide: a spreadsheet-cleanup workflow **the human builds by hand** in KNIME
      5.12, with built-in nodes only (no Python Script nodes, no agent-made `.knwf`,
      ADR-068). The guide is kept locally, not published; the workflow is in `knime/`
      (ADR-069).

**AC:** The `.xlsm` opens with working buttons (after the human macro step).
Recalculated Summary counts equal Python. The KNIME guide can be assembled by a human in
45 minutes or less.

## M8 — Docs + release (Day 6) — Lite scope (ADR-051)
- [x] `README.md` per `WORKFLOW.md §README requirements` (without the Ask items), in
      the project owner's order: hands-on work first (ADR-069). The quick start includes
      `breachlens train column-classifier`, because the model file is git-ignored
      (ADR-057); `docs/METHODS.md`; `docs/ASSUMPTIONS_LIMITATIONS.md`.
- [x] `sample_output/`: the final workbook (synthetic, masked) with 3 screenshots,
      `METRICS.md`, the scale report. `data/output/` is git-ignored (ADR-068).
- [ ] Fresh-clone test. Tag `v1.0`.

**AC:** A fresh clone reproduces `sample_output/`.

---

## Optional (only after M8, in this order)
1. **Ask BreachLens** (moved here by ADR-051): local-LLM text-to-SQL per
   `DATABASE_AND_ASK.md §Ask` (schema card, guard, read-only executor, evaluation on gold
   questions, adversarial guard tests).
2. **B. Learned duplicate matcher.** Logistic regression on `pair_features`, compared
   with the hand weights (`ML_MODELS.md §B`).
3. **A. Document-type ML classifier.** TF-IDF + logistic regression, compared with the
   keyword rules (`ML_MODELS.md §A`).
4. Streamlit page for Ask (question box, answer table, "show SQL").
5. Multiprocessing for the scale test.

## Dropped by BreachLens Lite (ADR-051)
`apply-review` and `review_decisions` import, the views `v_doc_type_quality`,
`v_people_multi_element`, `v_quality_trend` and the `ask_*` views (unless Ask is built),
reference queries beyond 5 and the F01–F04 few-shot files, workbook sheets `State_View`,
`Formula_Checks`, `Column_Mappings`, `File_Profiles`, macros `MarkSelectedAccepted` and
`RefreshHighlights`, the generated 10k-record scale run, the KNIME guide for the PDF
track.

## Cut from scope (ADR-021)
Geocodio second opinion, Presidio, Streamlit review UI, Splink, 7 PDF types.

## Roadmap (README only, do not build)
LayoutLMv3/Donut extraction, CASS-certified addresses, NCOA, 50-state rules matrix,
email/PST ingestion, containerized on-prem deployment, active-learning review loop,
pandas 3 upgrade with a dtype audit of the spreadsheet track (ADR-046).
