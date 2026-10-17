# PLAN.md — Build plan (6 days)

Goal: a public GitHub repo that demonstrates a privacy-safe, two-source breach-data
pipeline (PDF/scan + Excel/CSV), producing:
- a notification-ready dataset in DuckDB
- a formula- and macro-driven Excel review workbook
- an evaluated text-to-SQL assistant

Everything is reproducible with one command and measured against ground truth.

Milestones run in order. Do not start the next until the current acceptance criteria
(AC) pass. Tick the boxes as you go.

| Day | Milestones |
|---|---|
| 1 | M0 Scaffold, M1 Synthetic corpus |
| 2 | M2 PDF track, M3 Spreadsheet track (start) |
| 3 | M3 finish (incl. ML column classifier), M4 Normalize + validate + privacy |
| 4 | M5 Address + matching + notification + scale test, M6 Database + SQL |
| 5 | M7 Excel workbook (formulas + macros), KNIME workflow, evaluation |
| 6 | M8 Ask BreachLens + evaluation, README/docs, release |

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
- [ ] `synth/people.py`: 40 base people across CA, NY, TX, FL, PA and VA, plus planted
      variants, dependents, students + guardians, and 8 organizations.
- [ ] `data/reference/address_pool.csv`: ≥ 40 public, non-residential addresses
      (libraries, city halls, post offices found by web search), each verified live
      with the Census single-line geocoder (ADR-043).
- [ ] `synth/render_pdf.py`: 4 PDF types × 2 layout variants each, ~30 documents.
      `synth/scanify.py` turns ~30% into image-only scans.
- [ ] `synth/render_sheets.py`: the 8 messy corpus spreadsheet files, with every mess
      listed in `SYNTHETIC_DATA.md §Spreadsheets` (ADR-032).
- [ ] `doc_date` set on every generated document (ADR-029).
- [ ] `synth/column_corpus.py`: training tables for the column classifier
      (`ML_MODELS.md §C`).
- [ ] `synth/scale.py`: generator for N flat records (default 10,000) for the scale
      test, plus `large_claims.csv` (50k rows) in `data/raw/scale/`, never in the
      corpus (ADR-031).
- [ ] Ground truth: `gt_mentions.csv`, `gt_people.csv`, `gt_columns.csv`,
      `manifest.json`.
- [ ] Preview PNGs of one PDF per type → `data/output/previews/` for human review.

**AC:** The generator is deterministic (identical ground truth on re-run). Every
planted case P01–P44 exists. **Human checks the previews before M2.**

## M2 — PDF track (Day 2, morning)
- [ ] `ingest/inventory.py`: all files (PDF + spreadsheet). sha256, type, size, exact
      duplicates.
- [ ] `ingest/text_extract.py` (pdfplumber) and `ingest/ocr.py` (PyMuPDF raster +
      Tesseract with word confidences).
- [ ] `classify/doctype.py`: keyword-rule classifier from `config/doc_templates/*.yaml`.
- [ ] `extract/templates.py`: label-anchored extraction from YAML.
- [ ] `extract/identifiers.py`: SSN vs EIN/ITIN/NPI disambiguation → `excluded_identifiers`.
- [ ] `extract/entity_type.py`: PERSON vs ORG → `excluded_entities`.
- [ ] Emit `mentions` rows with `source_type=PDF` (in memory only until M4; ADR-044).

**AC:** Recall ≥ 0.95 for name, DOB and SSN-present on text-layer PDFs. Scans are
processed and their accuracy is reported separately.

## M3 — Spreadsheet track + ML column classifier (Day 2 afternoon → Day 3 morning)
Spec: `SPREADSHEET_TRACK.md`, `ML_MODELS.md §C`.
- [ ] `sheets/reader.py`: xlsx/xls/csv reading, encoding + delimiter detection,
      multi-sheet handling.
- [ ] `sheets/profile.py`: `file_profile` + `column_profile` tables.
- [ ] `sheets/layout.py`: header-row detection, merged-cell fill, drop title, total and
      blank rows, hidden-row flag.
- [ ] `sheets/features.py`: column feature engineering.
- [ ] `sheets/mapping.py`: header-rules mapper (baseline) plus ML mapper
      (`breachlens train column-classifier`). The decision table (ADR-034) and
      confidence go to `column_mapping`; REVIEW columns go to review.
- [ ] `sheets/repair.py`: ZIP padding, date serials, precision-loss flags, Excel error
      values, combined-field splits, pre-masked values.
- [ ] `sheets/reshape.py`: unpivot wide dependent columns into rows.
- [ ] `sheets/freetext.py`: regex + validator scan of notes/comment columns.
- [ ] Emit `mentions` rows with `source_type=SPREADSHEET`, `source_file`,
      `source_sheet`, `source_row` (in memory only until M4; ADR-044).
- [ ] `knime/`: document the native-node version of steps reader → layout → repair.

**AC:**
- The ML mapper beats the header-only baseline on macro-F1 for the held-out
  "confusing headers" set. Report both.
- Every planted spreadsheet mess (P27–P44) is handled or flagged.
- The vendor file produces 0 person mentions.

## M4 — Normalize + validate + privacy (Day 3)
- [ ] `normalize/names.py`, `normalize/addresses.py`, `normalize/dates.py`,
      `normalize/contact.py` per `VALIDATION_RULES.md`.
- [ ] `validate/engine.py`: every rule in `config/rules.yaml`, with reason codes and
      severities.
- [ ] `privacy/`: masking, HMAC keys, `drop_raw()`, `leak_guard` (patterns and scope
      per ADR-027).

**AC:** Every reason code has positive and negative tests. All planted validation cases
are caught. The leak-guard test passes on both tracks.

## M5 — Address + matching + notification + scale test (Day 4, morning)
- [ ] `address/zipcheck.py` (offline `zipcodes`) and `address/census.py` (batch, cached).
- [ ] `resolve/`: 3-pass matching, union-find clusters, survivorship. Persist
      `pair_features` (the engineered features) for every scored pair.
- [ ] `notify/triggers.py`: per-state triggers, minor/guardian note, FERPA flag.
- [ ] `breachlens scale-test --n 10000` plus `data/raw/scale/large_claims.csv` (50k rows): time each
      stage and write `scale_report.json` (rows/sec per stage, peak memory).

**AC:**
- Matching: pairwise precision ≥ 0.95 and recall ≥ 0.90.
- The twins case is not merged. The moved-address case is merged.
- **Cross-source merge works:** a person in `payroll_export.csv` and a W-2 PDF ends up
  as one `person_id`.
- The scale report is generated.

## M6 — Database + SQL (Day 4, afternoon)
Spec: `DATABASE_AND_ASK.md`.
- [ ] `db/load.py`: write all tables into `data/output/breachlens.duckdb`, with keys
      composite with `run_id` (ADR-030). Append a row to `runs`.
- [ ] `sql/views/*.sql`: the 6 analytical views, plus the key-free `ask_*` views in
      `sql/views/ask/` (ADR-040).
- [ ] `sql/queries/Q01..Q20.sql`: reference queries with expected-result snapshots.
      These are the scored Ask gold set. Plus `sql/fewshot/F01..F04.sql`, the separate
      few-shot examples (ADR-033).
- [ ] `breachlens apply-review`: import review decisions (CSV from the macro, or the
      edited workbook) into `review_decisions`, then re-run downstream stages.

**AC:** All 24 queries (Q01–Q20, F01–F04) run. They cover joins, GROUP BY/HAVING, CTEs, window functions
and a CASE pivot. Snapshots are committed.

## M7 — Excel workbook + KNIME + evaluation (Day 5)
Spec: `EXCEL_WORKBOOK.md`.
- [ ] `report/excel_writer.py` (XlsxWriter): every sheet, Excel Tables, named ranges,
      live formulas, formula-based conditional formatting, data validation.
- [ ] `excel/ReviewHelpers.bas` (4 macros). **Human step:** import it into a blank
      workbook, save as `.xlsm`, and run `vba_extract.py` →
      `excel/vbaProject.bin`. The writer then embeds it and adds buttons.
- [ ] `report/recalc.py`: LibreOffice headless recalculation (dedicated profile,
      ADR-041) for tests and screenshots. Assert there are no `#REF!`/`#NAME?` errors and that
      `Formula_Checks` matches Python.
- [ ] `evaluate/metrics.py`: per-field P/R/F1 by track, column-classifier metrics,
      matching metrics, address status accuracy, collapse ratio, throughput →
      `metrics.json`, `METRICS.md`; one row appended to `runs`.
- [ ] `knime/nodes/*.py` + `docs/KNIME_GUIDE.md`: spreadsheet track mostly in native
      nodes, Python Script nodes for mapping, validation, matching and export.

**AC:** The `.xlsm` opens with working buttons. The formula checks agree with Python
on 100% of checked cells. The KNIME guide can be assembled by a human in 45 minutes or
less.

## M8 — Ask BreachLens + docs + release (Day 6)
Spec: `DATABASE_AND_ASK.md §Ask`.
- [ ] `ask/`: schema card (key-free views only), prompt, Ollama client (Claude API
      optional), sqlglot guard, read-only executor (external access off, interrupt
      timer), answer formatter (ADR-040).
- [ ] `breachlens ask "<question>"` prints the answer table and the SQL.
- [ ] `breachlens evaluate ask`: run the 20 gold questions and report execution
      accuracy, with failures categorized.
- [ ] `README.md` per `WORKFLOW.md §README requirements`; `docs/METHODS.md`;
      `docs/ASSUMPTIONS_LIMITATIONS.md`.
- [ ] `sample_output/`: workbook, metrics, scale report, ask evaluation.
- [ ] Fresh-clone test. Tag `v1.0`.

**AC:** Ask execution accuracy is reported (target ≥ 15/20 with the local model). The
guard rejects all 5 adversarial prompts (DROP, UPDATE, raw-column requests, multiple
statements, non-allowed tables), tested with canned SQL (ADR-040). A fresh clone reproduces `sample_output/`.

---

## Optional (only after M8, in this order)
1. **B. Learned duplicate matcher.** Logistic regression on `pair_features`, compared
   with the hand weights (`ML_MODELS.md §B`).
2. **A. Document-type ML classifier.** TF-IDF + logistic regression, compared with the
   keyword rules (`ML_MODELS.md §A`).
3. Streamlit page for Ask (question box, answer table, "show SQL").
4. Multiprocessing for the scale test.

## Cut from scope (ADR-021)
Geocodio second opinion, Presidio, Streamlit review UI, Splink, 7 PDF types.

## Roadmap (README only, do not build)
LayoutLMv3/Donut extraction, CASS-certified addresses, NCOA, 50-state rules matrix,
email/PST ingestion, containerized on-prem deployment, active-learning review loop.
