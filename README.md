# BreachLens
Python + KNIME pipeline that extracts PII/PHI from synthetic breach documents, validates it, verifies addresses, matches people across documents, and produces a state-grouped breach notification list.

## Docs backlog (written into the full docs in M8)
README:
- All identifiers are randomly generated; any match to a real number is coincidental.

ASSUMPTIONS_LIMITATIONS.md:
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
- Spreadsheet fixes are tuned on the planted cases P27–P44 (synthetic Excel damage).
  Real exports will show damage the generator does not produce.
