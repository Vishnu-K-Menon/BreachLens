# METHODS.md: how BreachLens works, in plain English

Every number here comes from synthetic data. The decisions behind each step are in
`DECISIONS.md` (ADR numbers in brackets).

## 1. Synthetic data
`breachlens generate` creates a cast of fake people (names, addresses, SSNs, licenses,
medical and student details) from a fixed seed, so every run is reproducible.
- **corpus_v1 (seed 42):** 31 PDFs (21 with a text layer, 9 scans, 1 exact duplicate)
  and 8 messy spreadsheets.
- **Holdout (seed 43):** generated the same way and never used for tuning.

Each corpus comes with a ground truth: who is really who, and who must be notified.
44 **planted cases** cover the problems a real breach review meets: twins, a person
who moved, nicknames, lost leading zeros, numbers in scientific notation, totals rows,
and more. Addresses come from a pool of real public buildings (libraries, city halls),
so the Census check has something real to match. Identifiers are random [ADR-045,
ADR-047].

## 2. PDF track
- **Text:** a PDF with a text layer is read directly (pdfplumber). A scan is rasterized,
  deskewed, cleaned and read with Tesseract OCR, keeping a confidence per word.
- **Doc type:** keyword scores pick one of 4 document types.
- **Fields:** a YAML template per type says where each field sits relative to its
  printed label (right of it, below it, in a block). OCR text gets character repair
  by field shape: an `O` in an SSN becomes `0`.
- **Persons only:** labels decide whether a 9-digit number is an SSN, an EIN or an NPI.
  Business IDs and company names go to separate "excluded" tables, not the people
  list [ADR-054].

## 3. Spreadsheet track
1. **Read:** every sheet is profiled (encoding, delimiter, hidden rows, merged cells).
   The layout is repaired: the header row is found under title rows, two-row headers
   are joined, and totals and blank rows are dropped.
2. **Map columns:** each column gets one of 34 labels (first name, SSN, ZIP, …).
   - Header rules are the baseline.
   - A calibrated ML classifier uses value features (pattern hit rates, dictionaries,
     statistics) plus header n-grams.
   - A decision table combines the two. With normal headers the rules are better
     (macro-F1 0.99 vs 0.87). With headers like `ID` or `Column7` only the classifier
     works (0.90 vs 0.01). Low-confidence mappings go to review [ADR-055].
3. **Repair Excel damage:** leading zeros restored, Excel date serials converted,
   precision-lost numbers flagged (they cannot be recovered), wide tables unpivoted,
   and identifiers found in free-text notes.

## 4. Normalize and validate
- **Normalize:** names are split and upper-cased, nicknames kept for matching.
  Addresses are standardized (USPS abbreviations, unit lines). Dates are parsed.
- **Validate:** a rule engine adds reason codes to each record: SSN area/group rules,
  Luhn for cards, ABA checksum for routing numbers, DOB plausibility and minors, license
  formats by state, missing fields.
- **Status:** a record is `FAIL` if any code is an error, `REVIEW` if any is a warning,
  else `PASS`. "Today" is a fixed `as_of_date`, so ages don't change between runs
  [ADR-053].

## 5. Addresses
An offline ZIP check runs first. Then the US Census batch geocoder confirms each unique
address (street, city, state and ZIP only; no names). Answers are cached by request
hash and the cache is committed, so runs are offline by default.
- A Census "non-exact" match is accepted only if the house number and street still agree.
- Results are VERIFIED, CORRECTED, UNVERIFIED, INVALID or NOT_CHECKED [ADR-063].

## 6. Privacy
After validation, each identifier is replaced by three things:
- a present/valid flag
- a masked value (`***-**-1234`)
- a salted HMAC key, used only for matching inside the database

Raw columns are then dropped. A **leak guard** scans every table and file before it is
written, and fails the run on anything SSN-, card- or account-like outside the allowed
columns. The salt lives only in `.env`.

## 7. Matching people (entity resolution)
1. **Candidate pairs:** records are compared within blocks (same surname sound or same
   DOB, or the same SSN/license key).
2. **Pair features:** each pair gets engineered features: first/last-name Jaro-Winkler
   (after nickname expansion), DOB agreement, ZIP, address token similarity, key
   equality, middle initial.
3. **Score:** a weighted score merges at 0.90 or more and sends 0.70–0.90 to review.
4. **Guards:** two different SSN keys never merge; a DOB conflict caps the score below
   the merge line; a name alone never merges.
5. **People:** merged pairs form clusters (union-find), and each cluster becomes one
   person. Survivorship picks the most complete name, the newest verified address and
   the most common valid DOB [ADR-029, ADR-064].

## 8. Notification
The person's state (from the surviving address) decides the rule set in
`config/jurisdictions.yaml`, an illustrative subset, not legal advice. A person must be
notified when a name is exposed together with at least one element that state covers.
- **Notes:** minors get a guardian note, education records a FERPA note.
- **Unknown states:** states outside the subset use a default rule and are flagged.
- **Status:** each person is READY, NEEDS_REVIEW (an open matching or data question) or
  NOT_REQUIRED.

## 9. Outputs
- **DuckDB database:** the system of record (people, mentions, notification list, pair
  features, review items, audit log). Hand-written SQL runs on it read-only [ADR-067].
- **Review workbook:** 7 sheets with live formulas. Its Summary sheet recalculates every
  count in Excel next to the Python value. Review_Queue lists items to check with a
  dropdown; two macros filter pending items and export decisions [ADR-068].

## 10. Evaluation
`breachlens evaluate pipeline` reruns both corpora and scores each stage against the
ground truth:
- extraction precision/recall per field
- column mapping
- planted validation cases
- address status
- pairwise matching precision/recall
- the notification list by state

The holdout is reported next to the dev corpus and never tuned on. `breachlens
scale-test` times every stage on a 50,000-row file. Results: `sample_output/METRICS.md`.
