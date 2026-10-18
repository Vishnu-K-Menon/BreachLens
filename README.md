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
- All dates that depend on "today" (age, minors, DOB plausibility, workbook RunDate) use
  the configured `as_of_date` so results are reproducible (ADR-053).
