# DATA_SCHEMA.md — Column contract (the handoff contract)

This schema is the **handoff contract** for downstream teams: DuckDB tables and workbook
sheets follow it exactly. `schema_version` = 1.1. Any change needs an ADR and a version
bump. Where another doc disagrees with this one, this one wins (ADR-037).

Changes in 1.1 (ADR-028, 029, 030, 034, 037): `inventory.bytes`, `inventory.doc_date`,
`mentions.doc_date`, `people.notify_required` + category flags, `column_mapping`
decisions `ML_ONLY`/`RULE_ONLY`, `audit_events` spec, composite keys with `run_id`.

Keys: every table carries `run_id` (format `R20261017-153000-ab12`, ADR-027), and every
primary key is composite with it, e.g. `(run_id, doc_id)`, `(run_id, mention_id)`,
`(run_id, person_id)`. The foreign key `mentions (run_id, person_id)` →
`people (run_id, person_id)` (ADR-030).

Naming: our own snake_case. Strings are uppercase after normalization unless noted.
Dates are stored ISO (`YYYY-MM-DD`) and displayed per config (default `MM/DD/YYYY`).
"Sensitive trio" means three columns: `<e>_present` (bool), `<e>_masked` (str, e.g.
`***-**-1234`), and `<e>_valid` (`PASS` | reason code | null). Strong identifiers also
get `<e>_key` (HMAC, 16 hex characters).

## Table: `inventory` (one row per file)
| column | type | description |
|---|---|---|
| doc_id | str | `D0001`… stable sort by filename |
| path | str | relative path |
| file_kind | str | PDF / XLSX / XLS / CSV |
| sheets | int | spreadsheets only |
| sha256 | str | file hash |
| bytes | int | file size |
| pages | int | |
| doc_date | date | nullable. W-2 tax-year end, claim date of service, letter date, or xlsx/xls export date from the document properties; null for CSV (ADR-029) |
| has_text_layer | bool | False → OCR path |
| is_exact_duplicate | bool | sha256 seen earlier |
| doc_type | str | classifier output or `UNKNOWN` |
| doc_type_score | float | |
| extraction_method | str | `TEXT` / `OCR` |
| mean_ocr_conf | float | null for TEXT |
| processing_ms | int | |

## Table: `mentions` (one row per person per document)
| group | column | type | notes |
|---|---|---|---|
| ids | mention_id | str | `M00001`… |
| | source_type | str | PDF / SPREADSHEET |
| | doc_id, page | str, int | provenance (page for PDFs) |
| | source_file, source_sheet, source_row | str, str, int | spreadsheet provenance (1-based Excel row) |
| | related_mention_id | str | dependent → subscriber, student → guardian |
| | doc_type | str | |
| | doc_date | date | nullable, inherited from `inventory.doc_date` |
| | person_role | str | EMPLOYEE, RECIPIENT, PATIENT, INSURED, SUBSCRIBER, DEPENDENT, NEW_HIRE, CUSTOMER, MEMBER, STUDENT, GUARDIAN |
| | entity_type | str | PERSON (ORG rows go to `excluded_entities`) |
| | source_snippet | str | ≤120 chars around the name, **masked** |
| name | raw_name | str | as printed |
| | name_title | str | DR, MR, MRS, MS, REV, HON, PROF… |
| | first_name | str | |
| | middle_name | str | |
| | middle_initial | str | one letter, no period |
| | last_name | str | keeps hyphens, apostrophes and particles (DE LA VEGA) |
| | name_suffix | str | JR, SR, II, III, IV, V |
| | name_order_detected | str | `FIRST_LAST` / `LAST_COMMA_FIRST` |
| address | raw_address | str | as printed |
| | address_line1 | str | number + street |
| | address_line2 | str | APT/UNIT/STE/LOWER/UPPER… |
| | city | str | |
| | state | str | 2-letter USPS |
| | zip5 | str | 5 chars, leading zeros kept |
| | zip4 | str | optional |
| | country | str | ISO 3166-1 alpha-2, default `US` |
| | address_status | str | VERIFIED / CORRECTED / UNVERIFIED / INVALID / NOT_CHECKED |
| | address_suggestion | str | standardized suggestion if any |
| | address_source | str | ZIPCHECK / CENSUS |
| contact | phone | str | E.164 |
| | email | str | lowercase |
| demographics | dob | date | ISO |
| | age_at_run | int | |
| | is_minor | bool | age < 18 |
| gov IDs | ssn_present, ssn_masked, ssn_valid, ssn_key | trio + key | |
| | dl_present, dl_masked, dl_valid, dl_key | trio + key | |
| | dl_state | str | issuing state |
| | state_id_present, state_id_masked, state_id_valid, state_id_key | | |
| | state_id_state | str | |
| | passport_present, passport_masked, passport_valid, passport_key | | |
| | passport_country | str | |
| financial | bank_account_present, bank_account_masked, bank_account_valid | trio | |
| | routing_number_present, routing_number_valid | | ABA checksum |
| | card_present, card_masked, card_valid | trio | Luhn |
| health (PHI) | mrn_present, mrn_masked | | medical record number |
| | health_member_id_present, health_member_id_masked | | |
| | health_group_number_present | bool | |
| | insurer_name | str | organization name, not sensitive alone |
| | diagnosis_present | bool | ICD-10-like code or diagnosis text present |
| | procedure_present | bool | CPT-like code present |
| | date_of_service_present | bool | |
| employment/edu | employee_id_present | bool | |
| | employer_name | str | ORG, kept for context |
| | student_id_present, student_id_masked | | FERPA |
| | school_name | str | ORG |
| | ferpa_flag | bool | education-record elements present |
| quality | field_confidence | json str | `{field: conf}` (OCR conf or column-mapping proba) |
| | extraction_method | str | TEXT / OCR |
| | qc_status | str | PASS / REVIEW / FAIL |
| | qc_reasons | str | `;`-joined reason codes |
| resolution | person_id | str | `P0001`… |
| | cluster_confidence | float | |
| review | review_status | str | PENDING / ACCEPTED / CORRECTED / REJECTED |
| meta | run_id, processed_at | str | |

Transient (never persisted): `_raw_ssn`, `_raw_dl`, `_raw_state_id`, `_raw_passport`,
`_raw_bank_account`, `_raw_routing`, `_raw_card`, `_raw_mrn`, `_raw_member_id`.

## Table: `people` (golden records)
person_id, first_name, middle_initial, last_name, name_suffix, address_line1,
address_line2, city, state, zip5, country, address_status, dob, is_minor,
`<element>_exposed` (bool for each element above), elements_exposed (`;`-joined
human-readable list, e.g. `SSN; DRIVER LICENSE; MEDICAL INFO`), mention_count,
source_docs, source_types, cluster_confidence, ferpa_flag, needs_review (bool),
notify_required (bool, same value as in `notification_list`).

Category flags (bool, each the OR of its element flags; ADR-028):
| column | OR of |
|---|---|
| gov_id_exposed | ssn, dl, state_id, passport |
| financial_exposed | bank_account, card |
| medical_exposed | mrn, diagnosis, procedure, date_of_service |
| health_insurance_exposed | health_member_id, health_group_number |
| education_exposed | student_id |

Survivorship for the address: newest `doc_date` (nulls last), then the most frequent
VERIFIED address, then the highest confidence (ADR-029).

## Table: `notification_list`
person_id, jurisdiction, last_name, first_name, middle_initial, name_suffix,
address_line1, address_line2, city, state, zip5, country, elements_exposed,
notify_required, notify_reason, notify_note, ferpa_flag, address_status, notify_status.

## Table: `excluded_entities` / `excluded_identifiers`
doc_id, page, value_masked, kind (ORG / EIN / NPI / PROVIDER_TIN / ITIN), reason.

## Element display names (for `elements_exposed`)
ssn → SSN · dl → DRIVER LICENSE · state_id → STATE ID · passport → PASSPORT ·
bank_account → FINANCIAL ACCOUNT · card → PAYMENT CARD · mrn / diagnosis / procedure /
date_of_service → MEDICAL INFO · health_member_id / health_group_number →
HEALTH INSURANCE INFO · dob → DATE OF BIRTH · student_id → STUDENT RECORD

## Spreadsheet-track tables
- `file_profile`: doc_id, sheet, n_rows, n_cols, header_row, merged_ranges,
  hidden_rows, hidden_cols, title_rows_dropped, total_rows_dropped, encoding, delimiter,
  skipped (bool), skip_reason.
- `column_profile`: doc_id, sheet, col_idx, header_raw, null_pct, distinct_pct,
  inferred_type, top_shapes (masked shape strings), min_len, max_len.
- `column_mapping`: doc_id, sheet, col_idx, header_raw, rule_label, ml_label, ml_proba,
  final_label, decision (AGREE / ML_ONLY / ML_OVERRIDE / RULE_ONLY / REVIEW; see
  `SPREADSHEET_TRACK.md §4` and ADR-034), reviewed_label.

## Matching and review tables
- `pair_features`: mention_a, mention_b, f_first_jw, f_last_jw, f_dob, f_zip_eq,
  f_addr_tsr, f_ssn_key_eq, f_dl_key_eq, f_same_source_file, f_mi_eq, score,
  pass (A/B/C), decision (MERGE / REVIEW / NO_MERGE), guard_fired.
- `review_decisions`: run_id, item_id, item_type (FIELD / PAIR / COLUMN), field,
  decision, reviewer_value_masked, reviewed_by, reviewed_at, note.
- `runs`: run_id, started_at, finished_at, config_hash, schema_version, n_files,
  n_mentions, n_people, n_notify, metrics_json.

## Table: `audit_events` (one row per audit event; ADR-037)
| column | type | description |
|---|---|---|
| event_id | str | `E000001`… within a run |
| run_id | str | |
| ts | timestamp | event time |
| stage | str | pipeline stage, e.g. `validate`, `resolve` |
| event_type | str | e.g. `RULE_FIRED`, `VALUE_CHANGED`, `MERGE`, `ROUTED_EXCLUDED`, `REVIEW_APPLIED` |
| item_id | str | mention_id / person_id / doc_id / column id |
| field | str | affected column, if any |
| code | str | reason code, if any |
| old_value_masked | str | masked before storage |
| new_value_masked | str | masked before storage |
| detail_json | json str | extra context, masked |
