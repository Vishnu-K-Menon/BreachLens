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
