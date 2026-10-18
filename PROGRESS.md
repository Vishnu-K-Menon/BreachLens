# PROGRESS.md

Append-only build log. Format: see docs/WORKFLOW.md.

## 2026-10-17 (Day 1)
- [docs] Read-through findings resolved before any code: ADR-027 … ADR-044,
  `schema_version` 1.0 → 1.1, affected docs updated (commit `docs: resolve read-through
  findings`).
- [M0] Scaffold complete. AC evidence (Windows 11, `.venv` on Python 3.11.9):
  - `pip install -e ".[dev]"` succeeds.
  - `python -m breachlens --help` lists all 8 commands: generate, run, evaluate,
    train, apply-review, ask, scale-test, report.
  - `python -m breachlens run --config config/pipeline.yaml` exits 0 (0 stages
    registered yet; it needs `BREACHLENS_SALT` in `.env` and exits 2 with a clear
    message without it).
  - `pytest -q`: 48 passed. `ruff check .` and `ruff format --check .` clean.
  - Leak guard: N/A until M4 (ADR-044). M0 writes nothing to disk.
- Notes:
  - Ruff ≥ 0.17 also formats Python blocks inside Markdown, so `[tool.ruff] include`
    limits it to `*.py`/`*.pyi`.
  - The stage toggle is `stages.validation` (not `validate`, which shadows pydantic's
    `BaseModel.validate`).
  - pip resolved pandas 3.0 (string dtype and copy-on-write are the defaults). Keep
    this in mind for `dtype=str` reads in M3.
  - Open for M1: `synth/` sits at the repo root (ARCHITECTURE layout), outside the
    installed package. `breachlens generate` needs it importable (add it to the wheel
    packages or move it under `src/`; decide in M1 and record an ADR).
- Next: M1 synthetic corpus. Needs LibreOffice (for `.xls`) and network access for the
  Census address-pool check.
- [M1] Decisions: ADR-045 (`synth` moved into the package), ADR-046 (pandas <3),
  ADR-047 (generated-data layout), ADR-048 (safe-by-construction identifiers), ADR-049
  (Census ZIPs, reuse cap, shared-address truth), ADR-050 (expected address status).
- [M1] Address pool (checkpoint 1, approved): 45 public-building candidates from
  official pages, 42 verified Census `Match` (CA 7, FL 5, MA 3, NJ 4, NY 6, PA 6, TX 5,
  VA 6). Responses cached in `data/cache/census/`; an offline rerun is byte-identical.
- [M1] Previews (checkpoint 2, approved): `data/output/previews/` (PNGs + PREVIEW.md).
- [M1] Corpus `corpus_v1`, seed 42. AC evidence:
  - Files: 39 in `docs/`: WAGE_STATEMENT 8, HEALTH_CLAIM 8, NEW_HIRE_ID 6,
    EOB_LETTER 8 (9 of the 30 scanned), 1 exact duplicate, 8 spreadsheets.
  - People: 207 (40 base, 10 dependents, 8 students, 127 extras, 22 extra guardians),
    plus 25 organizations. 441 mentions (439 person, 2 ORG). Exclusions: EIN 37,
    NPI 8, provider TIN 8, ORG 27. 163 notify_required, 30 FERPA-flagged, 33 minors.
  - Overlap: 27 people in both a PDF and a spreadsheet (need ≥ 12); 58 in two or
    more spreadsheets (need ≥ 5).
  - Planted cases: all of P01–P44 are covered, each at least once (the generator
    fails otherwise).
  - Address mix: base people 34 pool / 6 fake street; extras 59 / 90; household
    members 16 / 2. Expected person status: VERIFIED 109, UNVERIFIED 98. Expected
    mention status: VERIFIED 275, UNVERIFIED 122, CORRECTED 1, INVALID 1 (ADR-050).
    78 unrelated same-address pairs, with at most 2 unrelated households per address.
  - Column corpus: 400 tables, 6,075 columns, 34 labels, 185 alias groups, 954
    uninformative headers (15.7%). Scale file: 50,000 rows in `data/raw/scale/`.
  - Determinism: the real corpus plus two scratch runs give byte-identical
    `truth/*` (all 6 files including manifest.json), 31/31 PDFs, 6/6 xlsx, the CSV, the
    401 column-corpus files and the scale file. Only `legacy_export.xls` bytes differ
    (LibreOffice); the manifest records its `cell_content_sha256`, which matches.
  - `pytest -q`: 130 passed (including the LibreOffice-marked integration test that
    generates twice). ruff check/format clean. `run --config config/pipeline.yaml`
    exits 0. Full generation takes about 20 s.
  - Leak guard: N/A until M4 (ADR-044). Generated data is synthetic input,
    git-ignored, and no pipeline stage persists mentions yet.
- Notes:
  - Expected values assume the generator's `reference_date` 2026-10-01; `is_minor` in
    ground truth is computed at that date.
  - Ground truth counts pre-masked and precision-lost cards as card *present*
    (SPREADSHEET_TRACK §5 semantics). Whether a masked card should trigger notice is
    an open point for ASSUMPTIONS_LIMITATIONS.md.
- Next: M2 PDF track. Needs Tesseract (not installed yet) for the 9 scans.

## 2026-10-17/18 (Day 1–2)
- [scope] BreachLens Lite (ADR-051): PLAN.md M5–M8 reduced, Ask moved to Optional. A
  hand-made-work rule now protects `notebooks/`, `excel/manual/`, `knime/manual/`,
  `docs/memos/` and the `sql/queries/*.sql` content (AGENTS.md; ruff excludes them).
  `jupyter` and `ipykernel` added to `[dev]`.
- [rules] ADR-052: pre-masked cards count as present but don't trigger notice;
  precision-lost and Luhn-fail cards trigger and go to review. ADR-053: required
  `as_of_date` (2026-10-01) in pipeline.yaml is the single source. corpus_v1 truth
  regenerated: notify_required 163 → 155, card_review 10. All 39 `docs/` files
  verified unchanged (the .xls by cell content) and left untouched; only `truth/` was
  replaced.
- [M2] PDF track complete. Tesseract 5.5.3 verified (`TESSERACT_CMD`). AC evidence on
  corpus_v1 (`python -m breachlens.evaluate.extraction`):
  - Text layer (21 docs, 23 person mentions): recall 1.000 for every field,
    including the AC fields name 23/23, DOB 10/10 and SSN-present 9/9.
  - OCR (9 scans, 10 person mentions): name 10/10, DOB 4/4, SSN-present 5/5, address
    10/10, diagnosis/procedure/date of service 1.000, member ID 3/4.
  - Mentions 33/33 matched (0 missing, 0 extra). Doc type 30/30 and doc_date 30/30.
    The exact duplicate (P25) was flagged and skipped (0 mentions).
  - Exclusions: EIN 12/12, NPI 8/8, provider TIN 8/8, ORG 1/1 (P21), all at precision
    1.0.
  - Remaining failure: one scan's insured member ID, which Tesseract read as
    `$LO829114678` (one letter lost). A genuine OCR misread, left unfixed.
  - Fixed during tuning (worst first): W-2 B addresses absorbing the next box
    (`boundaries` + per-line column stop); scanned W-2 A mentions missing (OCR merged
    "Employee'sname" → space-tolerant labels); a clean street line OCR'd as garbage
    next to box borders (border erasing); titles dropped by psm 6 (psm 11); border
    remnants and stray `~` read as text (height/confidence filters, stray-mark repair);
    rotated scans splitting rows (deskew).
  - `pytest -q`: 191 passed (incl. the integration test that generates a corpus and runs
    OCR). ruff check/format clean. `run --config config/pipeline.yaml` exits 0 and
    reports 31 PDFs (21 text, 9 OCR, 1 duplicate skipped), 33 mentions.
  - Leak guard: still N/A (ADR-044). Mentions stay in memory; nothing is written.
- Notes:
  - ADR-054 records the design: `Context.tables`, extra transient `_raw_*` columns, and
    OCR preprocessing. Templates and OCR settings were tuned on corpus_v1's layouts; this
    is a known limitation.
  - The Windows console shows accented names as `�`. That's display only (cp1252 bytes
    in a UTF-8 terminal); the extracted text is correct (U+00D1 etc.).
- Next: M3 spreadsheet track.
