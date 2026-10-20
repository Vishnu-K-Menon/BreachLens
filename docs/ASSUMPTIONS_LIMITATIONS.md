# ASSUMPTIONS_LIMITATIONS.md

What BreachLens assumes, where it falls short, and what the numbers do not show. All
data is synthetic; any match to a real person or number is coincidental. Nothing here is
legal advice.

## Assumptions
- **Fixed "today":** ages, minors, DOB plausibility and the workbook's RunDate all use
  the configured `as_of_date` (2026-10-01), so results are reproducible (ADR-053).
- **Notification rules** are a demo subset in `config/jurisdictions.yaml`. NJ and MA
  use the `default` rule and are flagged `NOTIFY_STATE_UNKNOWN`.
- **Pre-masked cards:** a card value that shows at most the last 4 digits counts as
  present but does not trigger notice, treated as redacted the way many state laws
  define it (ADR-052). Card numbers that lost precision (scientific notation) or fail
  the Luhn check do trigger notice, and the person goes to review.
- **FERPA** is an informational flag for the institution, not a state-law trigger.
- **Street lines** are kept as printed, apart from standard abbreviations.
- **Addresses:**
  - The offline ZIP check uses USPS-based `zipcodes` data; the address pool uses Census
    ZIPs.
  - Without the Census answer an address can only be INVALID or NOT_CHECKED.
  - Mention-level REVIEW counts include column-level mapping doubts, copied to every
    affected person (ADR-059).

## Known limitations
- **Review volume:** 43 people need review on corpus_v1, against 10 card-review cases in
  the ground truth.
  - Most are household members who share a surname and address, with no DOB on one
    side. Their pair scores land in the gray zone (0.70–0.87), so they go to review
    instead of merging.
  - Possible fix: cap the pair score when first names conflict.
- **Guardian rows** with only a name stay separate people in review: a name alone never
  merges (ADR-064), even when the guardian has other records.
- **Census batch vs single lookup:** for 125 14TH ST, Oakland (a pool address) the batch
  geocoder returns `Match` + `Non_Exact` → "125 14TH, OAKLAND, CA, 94612", without the
  street type.
  - The single-line lookup matches it.
  - The acceptance rule for non-exact matches (same house number and street,
    token-sort ≥ 95; ADR-063) scores the street at 84 and rejects it.
  - So its mentions are UNVERIFIED + `ADDR_GEOCODE_NOMATCH` instead of VERIFIED: 2/398 on
    corpus_v1, 8/394 on the holdout.
  - Possible fixes: compare the street without its type in the acceptance rule, or
    retry rejected rows with the single-line lookup.
- **Census ZIPs can differ from USPS ZIPs:** 630 W 5th St, Los Angeles is USPS 90071
  and Census 90012. Census confirms an address-range match, not USPS deliverability.
- **Fake streets:** the batch geocoder snaps them to real streets nearby. Such non-exact
  matches are rejected.
- **OCR:** the `eng` model drops accents, and `Jr.` can read as `Ir.`. Neither is fixed,
  because the holdout numbers must stay untuned.
- **Matching with no DOB:** household members who share a surname and address, with no
  DOB on one side, land in review rather than merging, which raises `needs_review`.

## What the numbers do and don't show
- **Tuned vs untuned:** PDF extraction numbers on corpus_v1 are tuned; the templates and
  OCR settings were adjusted on that corpus. The seed-43 holdout gives the untuned
  numbers:
  - text layer: still 1.000
  - OCR: name 0.78, SSN-present 0.86, a few single-field misses
  - Neither represents real-world scans.
- **Column classifier (ADR-055):** corpus_v1's spreadsheets are the dev set; the holdout
  spreadsheets are the test set.
  - Both reuse the same 8 header templates, so the holdout tests new values under known
    layouts. The header-blind test is the out-of-fold set of uninformative headers.
  - One known wrong ML override (`Insurer` → SCHOOL, p 0.83) is reported, not patched.
- **Spreadsheet fixes** are tuned on the planted cases P27–P44 (synthetic Excel damage).
  Real exports will show damage the generator does not produce.
- **Ground-truth quirks** (found in M4; reported, not changed):
  - Routing is left out of the truth when the account cell is `#N/A`. This causes the 3
    spreadsheet field false positives in METRICS.md.
  - Guardian rows carry the person's suffix even when it isn't printed.
  - The seed-43 generator gave one person the suffix `MR`.
- **Holdout P41:** the payroll CSV + W-2 → one person case is not merged on the holdout
  (an OCR miss on the scanned W-2). Reported as is.

## Privacy exceptions: two hand-made exercise files
Both are the project owner's hand-made exercises, not pipeline output. Their values are
synthetic and randomly generated.
- **`excel/manual/hr_roster_clean.xlsm`** (Excel exercise):
  - **What it holds:** the full SSN column (56 synthetic values) on the Roster sheet,
    hidden by its macro.
  - **Why it stays:** `SSN_Masked` and `SSN_Check` are live formulas that read it to
    demonstrate the masking.
- **`notebooks/01_explore_messy_files.ipynb`** (exploration notebook):
  - **What it holds:** the saved outputs of 5 display cells that preview the raw HR
    roster and payroll export. They show synthetic SSNs, and for payroll, routing and
    account numbers.
  - **Why it stays:** the notebook shows the messy files as they arrive. Its masking
    cells then demonstrate the masking.
- **Scans:** the M8 privacy scan reports both files as known exceptions. Every pipeline
  output passes the leak guard with 0 findings.

## Out of scope (v1.0)
- No real data, no CASS address certification, no legal advice.
- **Ask BreachLens** (a local-LLM text-to-SQL assistant) is optional future work
  (ADR-051).
- `apply-review` (importing review decisions) is dropped in BreachLens Lite. The
  workbook's Export decisions CSV is a record for editing `config/review_overrides.yaml`.
