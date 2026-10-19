# BreachLens
Python + KNIME pipeline that extracts PII/PHI from synthetic breach documents, validates it, verifies addresses, matches people across documents, and produces a state-grouped breach notification list.

## Status (interim, 2026-10-19)
Milestones M0–M7 are done; M8 (docs + v1.0 release) is planned. Details per milestone
are in `PROGRESS.md`, and the full README arrives in M8. SYNTHETIC DATA ONLY.
- **M6:** the DuckDB system of record (`breachlens db build`) and a read-only harness for
  hand-written queries (`breachlens sql run`, `DATABASE_AND_ASK.md`).
- **M7:**
  - the Excel review workbook (`breachlens report`): 7 sheets of live formulas, checked
    in LibreOffice against the Python counts
  - two VBA macros (`excel/ReviewHelpers.bas`)
  - `breachlens evaluate pipeline` (`METRICS.md`)
  - a KNIME guide for a hand-built spreadsheet-cleanup workflow (`docs/KNIME_GUIDE.md`)

| metric (synthetic data) | value |
|---|---|
| Notification list vs ground truth, corpus_v1 | **155/155** people, by state identical, 0 missed / 0 extra |
| Notification list, held-out seed-43 corpus (untuned) | **159/159** |
| Entity resolution, pairwise precision / recall (corpus_v1) | **1.000 / 0.933** (holdout 1.000 / 0.918); twins kept apart, 0/78 unrelated shared-address pairs merged |
| Scale test, 50k-row claims file | **50,000 rows in 40 s** end to end (~1,240 rows/s, peak ~1 GB) |
| PDF extraction recall (text layer / OCR) | text 1.000 on every field (corpus_v1 and holdout); OCR on corpus_v1 1.000 except member ID 3/4. Holdout OCR, untuned, on small counts: name 7/9, SSN-present 6/7, DL 2/3, diagnosis 0/1, email 1/2 |
| Spreadsheet extraction recall | 1.000 per field; every planted spreadsheet case P27–P44 handled |
| Planted validation cases caught | 306/306 (holdout 299/302) |
| Address status vs expected (Census) | 396/398 mentions |
| Leak guard | 0 findings on every written output; no raw identifier in any output byte |
| Review workbook (corpus_v1), recalculated in LibreOffice | 47/47 Summary formulas equal the Python counts, 0 error values, notify-status formula agrees on 215/215 people |

**Hand-built parts.** These are the project owner's own work, never created or edited by
the coding agent (AGENTS.md):
- `notebooks/`: exploration notebooks
- `excel/manual/`: a manual Excel cleanup of the HR roster with formulas, a pivot and a
  macro
- also protected: `knime/manual/`, `docs/memos/` and the content of `sql/queries/*.sql`
- the KNIME workflow (`knime/breachlens_sheet_cleanup.knwf`, `knime/workflow.png`),
  built by hand from `docs/KNIME_GUIDE.md`

**Census cache.** `data/cache/census/` is committed (Census Geocoder responses for the
synthetic corpora's addresses only; no names or identifiers). A fresh clone therefore
gets real address statuses offline, with no network call. The pipeline is offline by
default. `breachlens run --online` is only needed for addresses that are not cached yet
(e.g. a new seed); it sends street/city/state/ZIP only. In offline runs, addresses with
no cache entry are NOT_CHECKED (ADR-063).

## Docs backlog (written into the full docs in M8)
README:
- All identifiers are randomly generated; any match to a real number is coincidental.
- `sample_output/` (M8): copy the final review workbook (synthetic, masked) and a
  screenshot of it, plus `METRICS.md`, because `data/output/` is git-ignored (ADR-068).
- Macros: files downloaded from the internet open with macros blocked (Mark of the Web).
  Right-click → Properties → Unblock.

ASSUMPTIONS_LIMITATIONS.md:
- **Known limitations (M5):**
  - Review volume: 43 people need review on corpus_v1 vs 10 card-review cases in the
    ground truth. Most come from household members who share surname and address, with
    no DOB on one side: their pair scores land in the gray zone (0.70–0.87) and are sent
    to review, not merged. Possible fix: cap the pair score when first names conflict.
  - 125 14TH ST, Oakland (a pool address) comes back from the Census batch geocoder as
    `Match` + `Non_Exact` → "125 14TH, OAKLAND, CA, 94612": the street type is dropped.
    The single-line lookup in M1 matched it. The pipeline's Non_Exact acceptance rule
    (same house number and street, token-sort ≥ 95; ADR-063) scores the street at 84 and
    rejects it, so its mentions are UNVERIFIED + ADDR_GEOCODE_NOMATCH instead of VERIFIED
    (2/398 on corpus_v1, 8/394 on the holdout). (Corrected 2026-10-18: earlier notes
    called this a batch No_Match.) Possible fixes: compare the street without its
    type/suffix in the acceptance rule, or retry rejected and No_Match batch rows with the
    single-line lookup.
  - Guardian rows with only a name stay separate, in review, by design: a name alone
    never merges (ADR-064), even when the guardian is a person with other records.
- The address pool uses Census-assigned ZIPs, which can differ from USPS ZIPs
  (630 W 5th St, Los Angeles: USPS 90071 vs Census 90012; Corpus Christi City Hall:
  78401 vs 78408). Census confirms an address-range match, not USPS deliverability.
- Card exposure (ADR-052, illustrative, not legal advice): pre-masked card values (at most
  the last 4 digits) count as present but do not trigger notice, treated as redacted the
  way many state laws define it. Precision-lost (scientific-notation) and Luhn-failing
  numbers do trigger notice and send the person to review.
- PDF extraction numbers on corpus_v1 are **tuned**: the templates and OCR settings were
  adjusted on that corpus. The seed-43 held-out corpus gives the **untuned** numbers
  (text layer still 1.000; OCR name 0.78, SSN-present 0.86, a few single-field misses,
  accents lost by the `eng` OCR model). Report both; neither represents real-world scans.
- All dates that depend on "today" (age, minors, DOB plausibility, workbook RunDate) use
  the configured `as_of_date` so results are reproducible (ADR-053).
- Column classifier (ADR-055): corpus_v1's spreadsheets are a **dev** set (used to find
  the training-data shift); the seed-43 holdout spreadsheets are the **test** set. Both
  reuse the same 8 header templates, so the holdout tests new values under known
  layouts. The header-blind test is the out-of-fold uninformative-header set. With
  normal headers the alias rules beat the ML (0.99 vs 0.87 macro-F1); the ML earns its
  place on headers like `ID` / `Column7` (0.90 vs 0.01), and the decision table
  combines both. One known wrong ML override (`Insurer` → SCHOOL, p 0.83) is reported,
  not patched.
- Validation (M4): street lines are kept as printed; the offline ZIP check uses USPS-based
  `zipcodes` data, while the address pool has Census ZIPs. In M4 an address is INVALID or
  NOT_CHECKED; VERIFIED/CORRECTED need Census (M5). Mention-level REVIEW counts include
  column-level mapping doubts copied to every affected person (ADR-059).
- Ground-truth quirks found in M4 (reported, not changed): routing is left out of the
  truth when the account cell is `#N/A`; guardian rows carry the person's suffix even
  when it isn't printed; the seed-43 generator gave one person the suffix `MR`.
- OCR on accented names (`eng` model) loses accents, and `Jr.` can read as `Ir.`. Neither
  is fixed (holdout numbers are untuned).
- Census (M5, ADR-063): the pipeline is offline by default. Address status comes from
  cached Census batch results; `breachlens run --online` fills the cache once (addresses
  only), and addresses with no cache entry are NOT_CHECKED. The batch geocoder can differ
  from the oneline one (Oakland 125 14TH ST: batch drops the street type, see Known
  limitations). It also snaps fake streets to real ones nearby; such Non_Exact matches
  are rejected.
- Matching (M5): a name alone never merges. Household members who share a surname and
  address, with no DOB on one side, land in the gray zone (REVIEW) rather than merging,
  which raises `needs_review`. Guardian rows (name only) stay separate people in review.
- Notification rules are the demo subset in `jurisdictions.yaml` (NOT LEGAL ADVICE); NJ
  and MA use `default` and are flagged NOTIFY_STATE_UNKNOWN.
- Spreadsheet fixes are tuned on the planted cases P27–P44 (synthetic Excel damage).
  Real exports will show damage the generator does not produce.
