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

## 2026-10-18 (Day 2) — held-out PDF check
- [M2 holdout] Second corpus, `--seed 43 --out data/raw/corpus_holdout --corpus-only`
  (git-ignored). Same templates and config, **no retuning**; nothing was fixed based on
  this result. `--corpus-only` writes docs/ + truth/ only, so the seed-42 column corpus
  and scale file are untouched (hash checked). Recall, corpus_v1 (**tuned**) vs
  holdout (**untuned**):

  | field | v1 TEXT | v1 OCR | holdout TEXT | holdout OCR |
  |---|---|---|---|---|
  | name | 1.000 (23/23) | 1.000 (10/10) | 1.000 (24/24) | 0.778 (7/9) |
  | DOB | 1.000 (10/10) | 1.000 (4/4) | 1.000 (9/9) | 1.000 (5/5) |
  | SSN present | 1.000 (9/9) | 1.000 (5/5) | 1.000 (7/7) | 0.857 (6/7) |
  | address line1/city/state/ZIP | 1.000 | 1.000 | 1.000 | 1.000 (9/9) |
  | member ID | 1.000 (11/11) | 0.750 (3/4) | 1.000 (13/13) | 1.000 (2/2) |
  | DL / DL state | 1.000 | 1.000 (1/1) | 1.000 | 0.667 (2/3) |
  | diagnosis | 1.000 (5/5) | 1.000 (3/3) | 1.000 (7/7) | 0.000 (0/1) |
  | procedure / date of service | 1.000 | 1.000 | 1.000 | 1.000 |
  | phone | 1.000 | 1.000 (1/1) | 1.000 (2/2) | 1.000 (4/4) |
  | email | 1.000 (3/3) | — | 1.000 (1/1) | 0.500 (1/2) |
  | doc type / doc_date | 30/30, 30/30 | | 30/30, 30/30 | |
  | EIN / NPI / TIN / ORG | 12/12, 8/8, 8/8, 1/1 | | 11/12, 8/8, 8/8, 1/1 | |

  Holdout OCR failures (reported, not fixed): accents lost by the `eng` OCR model
  (MUÑOZ → MUNOZ, 2 names); one SSN label not found on a scanned W-2; DL and state not
  found on one new-hire scan; E11.9 read as B11.9; one email not found; one EIN missed.
  Text-layer extraction generalizes fully; OCR loses about 10–20% on some fields once
  untuned.

## 2026-10-18 (Day 2–3) — M3 spreadsheet track + ML column classifier
- [M3] Spreadsheet track complete (`sheets/` reader → layout → profile → mapping →
  repair → reshape → free text → `sheet_track` stage, after `pdf_track`). Mentions stay
  in memory (ADR-044). Side tables and transient columns are recorded in ADR-057.
- [ML] Column classifier. The first model scored 0.97 out-of-fold but 0.75 on
  corpus_v1's sheets, because of a training/test shift in the column-corpus generator.
  The generator was broadened (ADR-055), and corpus_v1's sheets became the **dev** set.
  The seed-43 holdout sheets are the **test** set. Macro-F1 (`models/model_card.md`):

  | model | validation (GroupKFold by alias) | **uninformative headers (OOF)** | dev sheets | test sheets | combined (OOF + test) |
  |---|---|---|---|---|---|
  | R header rules | 0.640 | **0.005** | 0.991 | 0.991 | 0.147 |
  | V values only (HGB) | 0.623 | 0.662 | 0.793 | 0.808 | 0.674 |
  | H+V (HV_lr, calibrated) | 0.898 | **0.899** | 0.872 | 0.872 | 0.899 |

  - AC: ML beats the header-only baseline on the held-out confusing-headers set, 0.899 vs
    0.005 (combined with the test sheets: 0.899 vs 0.147).
  - On normal headers the rules are better (0.991 vs 0.872). Final mapping after the
    ADR-034 decision table: accuracy 0.990, macro-F1 0.976 on both dev and test.
    Decisions: AGREE 74, ML_ONLY 14, RULE_ONLY 6, REVIEW 3, ML_OVERRIDE 1.
  - One wrong final label: `Insurer` ORG_NAME → SCHOOL, an ML override at p 0.83.
    Reported, not patched.
  - ECE: 0.031 out-of-fold (uncalibrated); after sigmoid calibration, 0.081 on dev and
    0.053 on test.
- [eval] `python -m breachlens.evaluate.sheets` (dev) and with `--input/--truth` on the
  holdout (test). Identical outcome on both: 405/405 (dev) and 401/401 (test) person
  mentions matched, field recall 1.000 on every field, 0 field failures. Exclusions:
  EIN 25/25, ORG 26/26.
- [AC] Planted cases, all handled on dev and test:
  - P27 header at row 5, 3 title rows dropped. P28 merged headers joined (`Employee SSN`).
  - P29 hidden rows kept and flagged. P30 total row dropped. P31 ZIP leading zeros
    restored. P32 all DOBs correct (serials and mixed formats).
  - P33 sci-notation / numeric cards flagged XL_NUMBER_PRECISION_LOST. P34 pre-masked
    values flagged.
  - P35 cp1252 + `;` + `SS#` → SSN, with accents intact. P36 `ID` → SSN (ML 0.63,
    REVIEW) and `Column7` → DOB (ML 0.70–0.71).
  - P37 10 dependents unpivoted and linked. P38 notes PII flagged. P39 vendor file:
    0 person mentions. P40 30 students, guardians linked.
  - P41 exact SSNs (the merge is M5). P42 duplicate kept once and flagged. P43 `#N/A`
    flagged and nulled. P44 8-digit SSNs padded.
- [process] Fixed during M3 on dev:
  - cards stored as 16+ digit numbers weren't flagged as precision-lost (P33)
  - `#N/A` in unmapped columns wasn't flagged (P43)
  - the `shape()` mask bug
  - `Home Address State` matched `address` before `state` (ADR-056)
  - ML OTHER overriding a concrete rule label (ADR-056)
  **Disclosure:** the ML error list behind the OTHER rule was first printed for the
  test set. The dev set has the identical errors, so the fix holds on dev alone, but the
  test set is no longer strictly unseen for that rule. Nothing else was changed after
  looking at test results.
- [data] Column corpus regenerated (seed 42, 6071 columns). corpus_v1 was regenerated in
  the scratchpad and compared: `docs/` unchanged (the .xls by cell content), and the only
  manifest change is the column_corpus block. Only `truth/manifest.json` was copied, so
  `docs/` was not touched.
- [knime] `knime/SPREADSHEET_TRACK_NODES.md`: native nodes for reader → layout → repair.
- [checks] `pytest -q`: 253 passed. This includes `tests/integration/test_sheet_track.py`,
  which generates a corpus, trains a small model and asserts P27–P44 handled or flagged,
  0 vendor mentions, and ML > rules on uninformative headers. ruff check/format clean.
  `run` exits 0 with 438 mentions (33 PDF + 405 spreadsheet) and writes nothing.
- Next: M4 normalize + validate + privacy.

## 2026-10-18 (Day 3) — M4 normalize + validate + privacy
- [M4] New stages `normalize → validate → privacy` after both tracks. This is the first
  milestone that writes outputs: `data/output/<run_id>/` (8 CSV tables + audit JSONL +
  counts-only summary), all through `privacy/writer.py` and the leak guard (ADR-058).
  ADR-059: rules.yaml is the one severity source; COL_* WARN codes reach the mentions
  that used the column. ADR-060: masks, HMAC keys, PII in notes counts as exposure.
- [AC: reason codes] Of 63 declared codes, 58 are emitted in M4 and each has ≥ 1
  positive and ≥ 1 negative case. That is 68 positive + 68 negative cases in
  `tests/unit/code_cases.py`, plus a meta-test that fails if any M4 code lacks either.
  Five codes need Census or clusters and come in M5: ADDR_GEOCODE_NOMATCH,
  ADDR_GEOCODE_TIE, DOB_CONFLICT_IN_CLUSTER, DUPLICATE_CANDIDATE, NOTIFY_STATE_UNKNOWN.
- [AC: planted cases] `python -m breachlens.evaluate.validation`:

  | corpus | planted-case recall | mentions matched | qc_status |
  |---|---|---|---|
  | corpus_v1 (dev, tuned) | **306/306 = 1.000** (P01–P04, P06, P07, P09–P16, P19–P23, P26–P44) | 438/438 | PASS 235, REVIEW 189, FAIL 14 |
  | holdout seed 43 (untuned) | 299/302 = 0.990 | 434/434 | PASS 226, REVIEW 197, FAIL 11 |

  - Holdout misses (reported, not fixed), all OCR:
    - P02: `Jr.` was read as `Ir.`, so the suffix was lost and the last name became IR.
    - P19: one EIN was not found (the same miss as the M2 holdout).
    - P41: one scanned W-2 SSN label was not found, so that mention has no `ssn_key`.
  - Rule precision on dev: every planted-code rule fires only where the truth expects it.
    The one exception is PERSON_NO_QUALIFYING_ELEMENT on a scan whose member ID OCR
    misread in M2, so the mention correctly goes to review.
  - Normalized fields vs `exp_*` on dev:
    - 1.000 for first/last/line1/city/state/zip5/dob on both tracks.
    - PDF middle initial 25/26: the M2 extraction lost it.
    - Sheet suffix 19/21: the truth stores a person's suffix on guardian rows that don't
      print it.
  - `*_present` vs truth `has_*`: ssn 438/438.
    - routing 435/438: the generator omits routing from the truth when the account cell is
      `#N/A`, but the routing number is printed.
    - health member/group 437 and 436/438: OCR misses from M2.
  - REVIEW volume on dev: 104 mentions come from 3 REVIEW columns (`Employee Middle`, `ID`,
    `Guardian Name`) and 65 from the `Insurer` ML_OVERRIDE (ADR-059). Those 65 also get
    `ferpa_flag` through the wrong SCHOOL label. Known, not patched.
- [AC: leak guard] Both tracks were scanned.
  - `tests/test_leak_guard.py` (generated corpus with text PDFs, OCR scans and all 8 sheets):
    - 10 files scanned: mentions, inventory, excluded_entities, excluded_identifiers,
      doc_codes, file_profile, column_profile, column_mapping, audit_<run>.jsonl and
      run_summary.json
    - 0 findings, and none of the raw ground-truth identifiers appear in any output byte
  - corpus_v1 run R20261018-030553-079f: `python -m breachlens.privacy.leak_guard` gives
    10 files, 0 findings. Cross-check: 0 of 122 SSNs, 34 cards, 15 accounts, 15 routing
    numbers, 65 MRNs, 89 member IDs, 56 employee IDs, 30 student IDs, 5 DLs, 1 passport
    and 26 excluded business IDs appear in any output.
  - Holdout run R20261018-031800-3cea: 10 files written, 0 findings.
- [checks] `pytest -q`: 426 passed (incl. both M4 integration suites). ruff clean. New tests:
  - `tests/unit/test_reason_codes.py`, `test_privacy.py`, `test_validate_engine.py`
  - `tests/test_leak_guard.py`
  - `tests/integration/test_validation_planted.py`, sharing the session fixture
    `generated_run`
- [fixed during M4, dev]:
  - per-row update merge: an ITIN routed out of one row nulled `_raw_ssn` in every row
    (caught by a unit test before any corpus run)
  - preflight scan of all tables, so no partial run directory is written
- [docs] PRIVACY §4, DATA_SCHEMA (doc_codes, run outputs), VALIDATION_RULES
  implementation notes. PLAN M4 ticked, and PLAN M8 now has the README quick start with
  `breachlens train column-classifier`.
- Next: M5 address (Census) + matching + notification + scale test.

## 2026-10-18 (Day 4) — review overrides + M5 address, resolution, notification, scale
- [review] ADR-061: `config/review_overrides.yaml` holds human column decisions, applied
  on every run, with an audit event `REVIEW_OVERRIDE_APPLIED`. The model and the decision
  table are unchanged. First entry: patient_list `Insurer` → INSURER. Before/after on
  corpus_v1 (pre-M5 stages):
  - REVIEW mentions 189 → 137
  - FERPA flag on the 65 patients 65 → 0; `insurer_name` set 0 → 65
  - 13 patients stay in REVIEW for their own row codes
  ADR-062 (for M7): Review_Queue groups column-level warnings into one item per column,
  with `affected_rows`.
- [address] ADR-063. Census batch geocoder, cache-first; `offline: true` stays the
  default, and `run --online` (used once per corpus) fills the cache with addresses only.
  - corpus_v1: 129 unique addresses fetched once, then cached.
  - Mention status vs `expected_address_status`: **396/398 = 0.995**
    (VERIFIED 273/275, CORRECTED 1/1, UNVERIFIED 121/121, INVALID 1/1). No fake street
    was VERIFIED.
  - Both misses are the pool address 125 14TH ST, Oakland. Corrected 2026-10-18: the
    batch result is Match + Non_Exact "125 14TH" (street type dropped), which the
    Non_Exact acceptance rule rejects (street similarity 84 < 95); it is not a No_Match.
    The oneline geocoder matched it in M1.
  - A live probe showed Non_Exact matches snapping fake streets to real ones, so these
    are now rejected.
  - People: expected VERIFIED 109 / UNVERIFIED 98; got 115 / 100 (215 records, see the
    split people below).
- [matching] ADR-064 (`python -m breachlens.evaluate.resolution`):

  | metric | corpus_v1 (dev) | holdout (untuned) |
  |---|---|---|
  | pairwise precision | **1.000** (664/664) | 1.000 (649/649) |
  | pairwise recall | **0.933** (664/712) | 0.918 (649/707) |
  | twins (P18) not merged | yes | yes |
  | mover (P17) merged, newer address kept | yes (RICHMOND 23219) | yes (BUFFALO 14202) |
  | payroll + W-2 (P41) one person_id | 8/8 | 7/8 (one W-2 lost its SSN to OCR, M2) |
  | nickname P05 / surname variant P08 / P24 4+ sources | yes / yes / yes | yes / yes / yes |
  | unrelated shared-address pairs merged | **0/78** | 0/59 |
  | people predicted vs truth | 215 vs 207 (8 split) | 217 vs 207 (9 split) |

  - The recall loss is guardian rows: name only, so capped at REVIEW by design.
  - Gray zone on dev: 142 REVIEW pairs in 48 cluster pairs.
    - 8 are the same person: a guardian row (name only, 0.89 NAME_ONLY) vs that
      person's other records.
    - 40 are different people: household members sharing surname and address with no
      DOB on one side (0.70–0.87, e.g. R. G. / C. G. at 0.873).
    - None of them merged; all are review items. This drives `needs_review` 43 (truth
      card_review 10).
- [notify] ADR-065:
  - **155 listed vs 155 truth**, the same 155 people (0 missed, 0 extra, 0 duplicate
    letters).
  - By state, truth = listed: CA 30, FL 18, MA 7, NJ 8, NY 23, PA 22, TX 23, VA 24.
  - NJ/MA use `default` + NOTIFY_STATE_UNKNOWN (19 records).
  - 33 minors (truth 33) carry "Notify parent/guardian (P…)", with the linked
    subscriber/guardian where one exists; students also get the FERPA note.
  - Holdout: 159 vs 159.
- [scale] ADR-066, `breachlens scale-test` on the 50k claims file: 40.3 s end to end
  (1,240 rows/s), peak 973 MB.

  | stage | s | rows/s |
  |---|---|---|
  | sheet_track (read + layout + ML mapping + repair) | 11.1 | 4,521 |
  | normalize | 9.0 | 5,548 |
  | validate | 2.6 | 19,141 |
  | address (cache only) | 3.4 | 14,654 |
  | privacy | 2.5 | 19,796 |
  | resolve | 7.2 | 6,966 |
  | notify | 4.5 | 11,094 |

  - Resolve skips the 8,293,309 soundex-blocked pairs whose SSN keys differ.
  - The first version scored them: 265 s and 10.9 GB, fixed in ADR-064.
- [checks] `pytest -q`: 488 passed (incl. tests/integration/test_resolution.py). ruff clean.
- [codes] All 63 reason codes are now emitted; the 5 M5 codes got positive/negative
  cases, and the meta-test covers every code.
- [leak guard] Runs write 13 files (+ people, notification_list, pair_features); 0
  findings on corpus_v1, the holdout and the generated test corpus.
- [fixed during M5, dev]:
  - accent folding for the soundex key (MUÑOZ lost its Ñ)
  - per-group pandas loops (validate 66 s → 3 s)
  - SSN-guarded pairs dropped at blocking time
  - evaluator checks for P05/P08/P41 test the tagged rows. Their second clusters are
    name-only guardian rows of the same person.
- Next: M6 database + SQL (Lite).

## 2026-10-18 (Day 4) — post-M5 docs follow-ups
- [cache] `data/cache/census/` was git-ignored (`data/cache/*`). It is now committed:
  266 files, 491 KB (220 per-address batch entries for corpus_v1 + holdout, 46
  single-line entries from building the M1 pool).
  - Audited before committing: only `fetched_at` + Census response fields (input
    address, match status, matched address, coordinates, TIGER line), no names or
    identifiers.
  - A fresh clone gets real address statuses offline. `*.tmp` stays ignored.
- [README] Interim "Status" section (M0–M5 done, M6–M8 planned, key metrics, hand-built
  parts `notebooks/` and `excel/manual/`). Census cache note. "Known limitations" in the
  backlog: review volume (fix idea: cap the score on first-name conflict), the Oakland
  address rejected by the Non_Exact rule (fix ideas: compare streets without their type,
  or a single-line retry), and name-only guardian rows staying in
  review.
- No pipeline code changed. Next: M6.
- [correction] A fresh-clone check of the committed cache showed that the Oakland
  address is not a batch No_Match. Census returns Match + Non_Exact "125 14TH" with the
  street type dropped, and the ADR-063 acceptance rule rejects it (street similarity
  84 < 95). The M5 report, ADR-063, PROGRESS and the README are corrected; the code is
  unchanged.

## 2026-10-19 (Day 5) — M6 DuckDB + SQL harness (ADR-067)
- [db] `breachlens db build` on corpus_v1 run R20261019-161315-5cac →
  `data/output/breachlens.duckdb`:
  - rows: people 215, mentions 438, notification_list 215, pair_features 1,173,
    review_items 431, audit_log 1,288, + `schema_version` (1.1)
  - views `v_notify_by_state`, `v_review_queue`, `v_address_status`
  - leak guard: 10 tables/views scanned, 0 findings
  - nothing raw: no `raw_*` / `_` columns; identifiers only as present/masked/valid/key
  - ZIPs stay text (`02139`); DOB is DATE, flags BOOLEAN, scores DOUBLE
- [views] `v_notify_by_state`: to_notify sums to **155**.
  - By state: CA 30, FL 18, MA 7, NJ 8, NY 23, PA 22, TX 23, VA 24.
  - Minors per state: CA 4, FL 3, MA 2, NJ 1, NY 7, PA 7, TX 5, VA 4.
  - `v_review_queue`: 3 open COLUMN items, each one row with affected_rows
    (`Employee Middle` 34, `ID` 40, `Guardian Name` 30), 285 MENTION items and 142 PAIR
    items. The Insurer column is RESOLVED (ADR-061) and not in the queue.
  - `v_address_status`: people VERIFIED 115 / UNVERIFIED 100. Mentions VERIFIED 273 /
    UNVERIFIED 123 / CORRECTED 1 / INVALID 1 / none 40.
- [harness] `breachlens sql run`: 5 × EMPTY (question-only files) and exit 0. The tests
  show the following:
  - A `*_key` column fails the query, including `SELECT *` from mentions.
  - DELETE, two statements in one file, and bad SQL all fail.
  - The read-only connection blocks CREATE / INSERT / DELETE / COPY / `read_csv`
    (`enable_external_access=false`).
  - A leak-guard finding aborts the build and leaves no file.
- [pipeline] Small M6 change: `column_mapping.affected_rows` (validate stage) feeds
  `review_items`.
- [checks] `pytest -q`: 498 passed (incl. `tests/unit/test_db.py`,
  `tests/integration/test_db_build.py`). ruff clean.
- [docs] `DATABASE_AND_ASK.md`: table/column reference plus "write q1–q5 against base
  tables; use the views only to check". ADR-067, PLAN M6, DATA_SCHEMA, README status.
- Next: the project owner writes q1–q5; then M7.

## 2026-10-19 (Day 5) — M7 review workbook, macros, recalc, metrics, KNIME guide (ADR-068)
- [workbook] `breachlens report` on corpus_v1 (run R20261019-161315-5cac) →
  `data/output/R20261019-161315-5cac/breachlens_R20261019-161315-5cac.xlsx`. It is
  `.xlsm` once `excel/vbaProject.bin` exists.
  - 7 sheets: Summary, Mentions, Review_Queue, People, Notification_List, Excluded,
    About.
  - 5 Excel Tables, the `RunDate`/`RunId` named ranges, and conditional formatting
    (red ERROR / yellow WARN codes per field group, green VERIFIED address, grey
    resolved/rejected rows).
  - Review_Queue: one row per item, 431 rows.
    - 3 open COLUMN items, each with affected_rows (`ID` 40, `Employee Middle` 34,
      `Guardian Name` 30).
    - 1 RESOLVED (`Insurer`, review_overrides.yaml).
    - 285 MENTION items and 142 PAIR items.
    - a `review_status` dropdown and a `go` link
  - Masked only: no `*_key`, `_` or `run_id` columns. The leak guard scanned the
    workbook before and after writing (0 findings). `scan_dir` on the run folder:
    14 files, 0 findings.
- [recalc] LibreOffice 26.8 headless (dedicated profile, recalc on load):
  - 0 error values, 47/47 Summary formulas equal Python
    - people 215, mentions 438, collapse 2.04
    - to notify **155**: READY 112 / NEEDS_REVIEW 43 / NOT_REQUIRED 60
    - by state: CA 30, FL 18, MA 7, NJ 8, NY 23, PA 22, TX 23, VA 24
    - minors 33 (flag) = 33 (DATEDIF from RunDate)
    - FERPA 30, SSN+medical 72
    - top 10 reason codes
  - The Excel notify-status formula agrees on 215/215 people.
  - Opened in Excel desktop as well (read-only, via COM): 5 tables intact, 47/47 Summary
    values equal, status 215/215.
  - Found and fixed: LibreOffice gave `#N/A` for XlsxWriter's unqualified `[@col]`
    table references, so they are written as `tblX[@[col]]`. An empty table counts one
    row in `ROWS()`, so Excluded uses `COUNTA`.
- [macros] `excel/ReviewHelpers.bas` (`ShowPendingOnly` toggle, `ExportDecisions` →
  `review_decisions_<RunId>.csv`), CRLF.
  - Programmatic VBA import is not allowed on this machine (no `AccessVBOM`), so the
    macros were reviewed, not run, by the agent.
  - The human step is in EXCEL_WORKBOOK.md.
- [metrics] `breachlens evaluate pipeline` (66 s, both corpora) →
  `data/output/metrics/{metrics.json, METRICS.md, runs.csv}`:

  | metric | corpus_v1 (dev) | holdout (untuned) |
  |---|---|---|
  | notified vs truth | 155/155 | 159/159 |
  | pairwise P / R / F1 | 1.000 / 0.933 / 0.965 | 1.000 / 0.918 / 0.957 |
  | shared-address merges | 0/78 | 0/59 |
  | address vs expected | 396/398 | 386/394 |
  | planted validation caught | 306/306 | 299/302 |
  | planted spreadsheet cases | 18/18 | 18/18 |
  | fields PDF-TEXT P / R | 1.000 / 1.000 | 1.000 / 1.000 |
  | fields PDF-OCR P / R | 1.000 / 0.988 | 0.962 / 0.905 |
  | fields SPREADSHEET P / R | 0.999 / 1.000 | 0.999 / 1.000 |

  - The spreadsheet FPs are 3 routing numbers. They are the documented ground-truth
    quirk: the truth leaves routing out when the account cell is `#N/A`.
  - Holdout P41 (payroll + W-2) is NO: one scanned W-2 lost its SSN to OCR, as reported
    in M5.
- [knime] `docs/KNIME_GUIDE.md`: 14 built-in nodes on `sheets/payroll_export.csv` for
  KNIME 5.12. Option labels were taken from the installed 5.12 node classes.
  - SSN handling: `padLeft` to 9 digits, then mask in node 2. A side branch counts the
    short SSNs (72 × 9 digits, 8 × 8) without showing one, and a regex Row Filter proves
    0 digit runs remain.
  - Flow: 80 rows → 40 employees; 2 to review (dept `#N/A`); 8 states.
  - Ends with a pandas vs KNIME vs pipeline table.
  - Numbers re-checked by `tests/unit/test_knime_guide.py`.
  - The project owner builds, exports and commits `knime/breachlens_sheet_cleanup.knwf`
    and `knime/workflow.png`.
- [other] `LeakGuard.scan_file` reads workbooks. `GuardedWriter.write_text`.
  `schema_version.source_dir` is absolute for runs outside the project root.
- [docs] ADR-068, PLAN M7 (and the M8 `sample_output/` workbook + screenshot note),
  EXCEL_WORKBOOK (human macro steps), WORKFLOW, SPREADSHEET_TRACK_NODES, README status.
- [checks] `pytest -q`: 511 passed, including the LibreOffice integration test
  `tests/integration/test_report.py`: the generated corpus recalculates to 155 to
  notify, 0 errors, guard 0. ruff clean.
- Next: the human macro step (`vbaProject.bin`) and the KNIME workflow; then M8.
- [fix] KNIME_GUIDE.md, reported by the project owner: the classic category paths
  (e.g. Manipulation › Column › Convert & Replace) don't exist in the 5.12 Nodes panel.
  Every node is now found by searching its name. String Manipulation and Rule Engine
  have modern expression-editor dialogs in 5.12, so the output setting reads
  *Output column → Replace/Append column*. The numbers are unchanged.
- [fix] KNIME_GUIDE.md step 14, reported by the project owner: the Excel Writer refused
  `data\output\knime\payroll_clean.xlsx` because the folder doesn't exist. **Create missing
  folders** (off by default in 5.12) is now a required setting, not "if shown", and
  "Before you start" gives the `mkdir` alternative.

## 2026-10-19 (Day 6) — M8 docs + release (ADR-069)
- [outputs] Fresh offline run R20261020-011706-51da on corpus_v1: 438 mentions → 215
  people, 155 to notify, leak guard 0.
  - `db build`: 10 tables/views, guard 0.
  - `report` now writes an `.xlsm`, because `excel/vbaProject.bin` exists. LibreOffice
    recalc: 0 error values, 0 Summary mismatches, status formula agrees on 215/215.
- [metrics] `evaluate pipeline`, unchanged from M7:
  - corpus_v1: 155/155 notified, P 1.0 / R 0.9326, address 396/398, planted 306/306
  - holdout (untuned): 159/159, 1.0 / 0.918, 386/394, 299/302
  - `scale-test`: 50,000 rows in 38.85 s (1,287 rows/s, peak 976 MB).
- [sql] `breachlens sql run` failed q5 ("only one statement per file"). The cause was in
  the harness: the `';'` literal in `string_split`. Fixed (literals are ignored by the
  check; test added). The SQL files are unchanged. All 5 queries run. Cross-check:
  - q1 (by state, 155) = the workbook
  - q2 (112/43/60) = the workbook
  - q5 (top 10 codes) = the workbook
  - q4: 11 minors need a guardian notice
- [sample_output] Contents:
  - the workbook `.xlsm`
  - `workbook_summary.png`, `workbook_review_queue.png`, `workbook_mentions.png`
    (Excel COM, read-only, macros force-disabled)
  - `METRICS.md`, `metrics.json`, `scale_report.json`, `README.md`

  Leak guard: 8 files, 0 findings; OCR of the PNGs: 0.
- [docs] Changed or new:
  - README rewritten: hands-on work first, the project owner's skill table and
    screenshots, results, quick start, limitations.
  - New `docs/METHODS.md` and `docs/ASSUMPTIONS_LIMITATIONS.md` (the README backlog
    moved there).
  - PLAN M8 ticked, ADR-069.
  - `.gitignore`: `excel/macro_shell.xlsm`.
  - CLI stub messages no longer name M6/M8.
- [links] 67 distinct URLs in tracked files:
  - 60 real URLs resolve. ssa.gov and hhs.gov return 403 to scripts and were confirmed
    by a browser fetch.
  - 7 skipped: 2 test placeholders, localhost, XML namespaces.
- [privacy] Leak guard + OCR over all 496 tracked files and the new ones:
  - `.env` was never committed; the salt is in none of the 45 commits.
  - Findings outside the pipeline outputs:
    - leak-guard test fixtures in `tests/` (planted on purpose)
    - Census cache `tigerLineId` values (9-digit public road-segment IDs)
    - format examples and publicized sample numbers in DECISIONS / VALIDATION_RULES /
      SPREADSHEET_TRACK
    - one OCR artifact in `excel/manual/excel_roster.png`: a ZIP and a phone number
      read as one 16-digit run
    - the project owner's two hand-made files: the notebook (34, saved cell outputs,
      to be fixed by the owner) and `hr_roster_clean.xlsm` (56, hidden SSN column; kept
      as a documented exception)
- Next: the owner fixes the notebook display cells. Then the final scan, the
  fresh-clone test and the v1.0 tag.
