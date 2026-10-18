# VALIDATION_RULES.md — Rule catalogue

Severity → status: **ERROR → FAIL**, **WARN → REVIEW**, **INFO → no status change**.
All rules are declared in `config/rules.yaml` and implemented as registered check
functions. Each code needs ≥ 1 positive and ≥ 1 negative unit test.

## Name rules
| code | sev | check |
|---|---|---|
| NAME_MISSING | ERROR | no last name or no first name/initial |
| NAME_TITLE_REMOVED | INFO | a title (DR, MR, MRS, MS, MX, REV, HON, PROF, SGT…) was moved to `name_title` |
| NAME_SUFFIX_INVALID | WARN | suffix-like token not in {JR, SR, II, III, IV, V}; suggest the closest (e.g. a doubled letter such as JJ → JR) |
| NAME_SUFFIX_IN_NAME | WARN | suffix found inside a first/last name field; moved |
| NAME_ORDER_AMBIGUOUS | WARN | no comma and no field label, and both tokens are plausible first names |
| NAME_PUNCT_FIXED | INFO | stray spaces around an apostrophe/hyphen removed (O' BRIEN → O'BRIEN) |
| NAME_WHITESPACE | INFO | leading/trailing/double spaces trimmed |
| NAME_ORG_LIKE | WARN | the person field contains an org token (INC, LLC, CLINIC…); routed to `excluded_entities` |
| NAME_VARIANT_IN_DOC | WARN | the same person appears with different spellings in one document |

Comma rule: `A, B` means `LAST, FIRST` **unless** the document field label says
otherwise (template YAML `name_format:` overrides). Middle name → `middle_initial` =
first letter.

## Address rules
| code | sev | check |
|---|---|---|
| ADDR_MISSING | WARN | no address line 1 |
| ADDR_LINE2_SPLIT | INFO | unit moved from line 1 to line 2 |
| ADDR_UNIT_FORMAT | INFO | `APT6F` → `APT 6F` |
| ADDR_STATE_INVALID | ERROR | not a USPS 2-letter code |
| ADDR_ZIP_FORMAT | ERROR | not 5 digits (or 5+4); a 4-digit ZIP with a leading-zero state → suggest zero-padding |
| ADDR_ZIP_STATE_MISMATCH | WARN | the ZIP belongs to a different state |
| ADDR_ZIP_CITY_MISMATCH | WARN | the city is not an acceptable city for the ZIP; suggest the canonical one |
| ADDR_GEOCODE_NOMATCH | WARN | Census `No_Match` |
| ADDR_GEOCODE_TIE | WARN | Census `Tie` |
| ADDR_PO_BOX | INFO | PO Box detected |

### Address status mapping
| Evidence | address_status |
|---|---|
| Census `Match` + `Exact`, and ZIP check OK | VERIFIED |
| Census `Match` + `Non_Exact`, OR ZIP check produced an accepted city fix | CORRECTED (+ `address_suggestion`) |
| Census `Tie`, or `No_Match` but ZIP/city/state consistent | UNVERIFIED |
| Invalid state or ZIP format that can't be fixed | INVALID |
| offline mode, or the stage is disabled | NOT_CHECKED |

## Date of birth rules
| code | sev | check |
|---|---|---|
| DOB_UNPARSEABLE | ERROR | cannot be parsed |
| DOB_TWO_DIGIT_YEAR | WARN | 2-digit year; pivot: `yy > as_of_yy` → 19yy, else 20yy, and flag (`as_of_date`, ADR-053) |
| DOB_FUTURE | ERROR | after `as_of_date` |
| DOB_IMPLAUSIBLE | ERROR | age > 120 at `as_of_date` |
| DOB_MINOR | INFO | age < 18 at `as_of_date` → `is_minor` |
| DOB_CONFLICT_IN_CLUSTER | WARN | the same person has different DOBs across documents |

## Identifier rules
| code | sev | check |
|---|---|---|
| SSN_FORMAT | ERROR | not 9 digits |
| SSN_AREA_INVALID | ERROR | area 000, 666 or 900–999 (never assigned; 9xx is the ITIN/other range) |
| SSN_GROUP_INVALID | ERROR | group 00 |
| SSN_SERIAL_INVALID | ERROR | serial 0000 |
| SSN_KNOWN_INVALID | ERROR | on a list of publicized/sample numbers (078-05-1120, 123-45-6789, 219-09-9999) |
| ITIN_DETECTED | INFO | 9xx with an ITIN group range → reclassified, routed to `excluded_identifiers` |
| EIN_EXCLUDED | INFO | EIN found near an employer/payer label; excluded |
| NPI_EXCLUDED | INFO | 10-digit NPI near a provider label; excluded |
| DL_FORMAT_STATE | WARN | license does not match any regex for `dl_state` |
| DL_STATE_MISSING | ERROR | license present but no issuing state |
| PASSPORT_FORMAT | WARN | US passport: 9 alphanumeric (1 letter + 8 digits, or 9 digits) |
| CARD_LUHN_FAIL | ERROR | Luhn checksum fails |
| ROUTING_CHECKSUM_FAIL | ERROR | ABA checksum: `3(d1+d4+d7) + 7(d2+d5+d8) + (d3+d6+d9) ≡ 0 mod 10` fails |

Note: since 2011 SSNs are randomized, so **never infer a state from the SSN.**

Precedence (ADR-035): a 9xx number in an SSN field is checked against the ITIN group
ranges **first**. On a match, only `ITIN_DETECTED` fires and the value goes to
`excluded_identifiers`, so `SSN_AREA_INVALID` does not fire. A 9xx number outside the ITIN
ranges stays an SSN and fails `SSN_AREA_INVALID`.

### `config/dl_formats.yaml` (simplified, illustrative; real states have more variants)
```yaml
CA: ['^[A-Z]\d{7}$']
NY: ['^\d{9}$', '^[A-Z]\d{7}$']
TX: ['^\d{7,8}$']
FL: ['^[A-Z]\d{12}$']
PA: ['^\d{8}$']
VA: ['^[A-Z]\d{8}$', '^\d{9}$']
NJ: ['^[A-Z]\d{14}$']             # added in M1 so NJ/MA licenses can be validated
MA: ['^[A-Z]\d{8}$', '^\d{9}$']
```

## Spreadsheet rules (see SPREADSHEET_TRACK.md)
| code | sev | check |
|---|---|---|
| SHEET_HEADER_OFFSET | INFO | header detected below row 1 |
| SHEET_MERGED_HEADER | INFO | merged/2-row header joined |
| SHEET_HIDDEN_ROWS | INFO | hidden rows present (kept) |
| SHEET_TOTAL_ROW_DROPPED | INFO | summary row removed |
| SHEET_SKIPPED | INFO | sheet has no tabular person data |
| CSV_ENCODING_DETECTED | INFO | encoding other than UTF-8 |
| COL_MAPPING_LOW_CONF | WARN | mapping decision is REVIEW (no rule match and ML < 0.70; disagreement with ML < 0.80; or no rule match and ML unavailable). See ADR-034 |
| COL_MAPPING_AGREE_LOW_PROBA | INFO | rules and ML agree, but ML probability < 0.60 (accepted) |
| COL_MAPPING_ML_OVERRIDE | WARN | rules and ML disagree and ML probability ≥ 0.80; the ML label is used |
| COL_UNMAPPED_SENSITIVE | WARN | values look sensitive but the column is mapped OTHER |
| XL_ZIP_LEADING_ZERO_RESTORED | INFO | 4-digit ZIP padded for a leading-zero state |
| XL_SSN_ZERO_PADDED | WARN | 8-digit numeric SSN padded |
| XL_DATE_SERIAL_CONVERTED | INFO | Excel serial date converted |
| DOB_AMBIGUOUS_FORMAT | WARN | day/month order undecidable |
| XL_NUMBER_PRECISION_LOST | ERROR | long identifier stored as a float / sci-notation |
| XL_ERROR_VALUE | INFO | `#N/A` and similar cleared |
| PREMASKED_VALUE | INFO | value already masked at the source |
| FREE_TEXT_PII_FOUND | WARN | PII found in a notes/comment column |
| ROW_DUPLICATE_IN_FILE | INFO | identical row repeated |

## Completeness and person-level rules
| code | sev | check |
|---|---|---|
| PERSON_NO_QUALIFYING_ELEMENT | WARN | no element in `qualifying_elements` (config, default: ssn, dl, state_id, passport, dob, bank_account, card, mrn, health_member_id, student_id) → the mention is kept but marked not notifiable |
| DUPLICATE_CANDIDATE | WARN | entity-resolution gray-zone pair |
| LOW_OCR_CONFIDENCE | WARN | field confidence < `ocr_conf_threshold` (default 0.80) |
| DOC_TYPE_UNKNOWN | WARN | classifier below the minimum score |
| NOTIFY_STATE_UNKNOWN | WARN | jurisdiction not in config (uses `default`) |
| FERPA_RECORD | INFO | student ID / school / education record present → `ferpa_flag` (informational, not a state trigger) |

## `config/rules.yaml` shape
```yaml
ocr_conf_threshold: 0.80
column_mapping: {agree_low_proba: 0.60, ml_only_min: 0.70, override_min: 0.80}
qualifying_elements: [ssn, dl, state_id, passport, dob, bank_account, card, mrn, health_member_id, student_id]
valid_suffixes: [JR, SR, II, III, IV, V]
titles: [DR, MR, MRS, MS, MX, REV, HON, PROF, SGT, CAPT]
date_display_format: "%m/%d/%Y"
known_invalid_ssns: ["078051120", "123456789", "219099999"]   # SSN_KNOWN_INVALID; the generator avoids them
rules:
  - id: SSN_AREA_INVALID
    fields: [_raw_ssn]
    check: ssn_area
    severity: ERROR
  - id: ADDR_ZIP_CITY_MISMATCH
    fields: [zip5, city, state]
    check: zip_city_consistency
    severity: WARN
    params: {suggest_min_similarity: 0.8}
  # ...one entry per code above
```

## `config/jurisdictions.yaml` (ILLUSTRATIVE — NOT LEGAL ADVICE)
FERPA is a federal privacy law for education records, not a state breach-notification
trigger, so it is handled as `ferpa_flag` plus a note, not as a covered element.
Every state entry has `verified: false` until a human checks the current statute. The
README must say this table is a simplified demo subset.
```yaml
default:
  covered_elements: [ssn, dl, state_id, bank_account, card]
  verified: false
CA:
  covered_elements: [ssn, dl, state_id, passport, bank_account, card, mrn, diagnosis, health_member_id]
  citation: "Cal. Civ. Code § 1798.82"
  verified: false
NY:
  covered_elements: [ssn, dl, state_id, bank_account, card, mrn, diagnosis, health_member_id]
  citation: "N.Y. Gen. Bus. Law § 899-aa"
  verified: false
TX:
  covered_elements: [ssn, dl, state_id, bank_account, card, mrn, diagnosis, health_member_id]
  citation: "Tex. Bus. & Com. Code § 521.002 / 521.053"
  verified: false
FL:
  covered_elements: [ssn, dl, state_id, passport, bank_account, card, mrn, diagnosis, health_member_id]
  citation: "Fla. Stat. § 501.171"
  verified: false
PA:
  covered_elements: [ssn, dl, state_id, bank_account, card, mrn, diagnosis, health_member_id]
  citation: "73 P.S. § 2302"
  verified: false
VA:
  covered_elements: [ssn, dl, state_id, passport, bank_account, card]
  citation: "Va. Code § 18.2-186.6 (medical info: § 32.1-127.1:05)"
  verified: false
```
Card element rules (ADR-052, illustrative): a card is always *present* when printed,
but a pre-masked value (at most the last 4 digits visible) is treated as redacted and does
not trigger notice. A precision-lost value (scientific notation) and a Luhn failure do
trigger notice and also send the person to review (`needs_review`); their field rules
stay ERROR (`XL_NUMBER_PRECISION_LOST`, `CARD_LUHN_FAIL`). Encoded under
`element_rules.card` in `jurisdictions.yaml`.

Financial account generally triggers only with an access code; for the demo, treat
`bank_account` with `routing_number` present as covered, and say so in
ASSUMPTIONS_LIMITATIONS.md.
