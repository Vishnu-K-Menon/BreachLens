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
