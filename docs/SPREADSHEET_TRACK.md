# SPREADSHEET_TRACK.md — Structured-file pipeline (Excel / CSV / XLS)

Breached systems export large, messy spreadsheets (HR, payroll, patient, student and
customer lists). This track turns each one into standard `mentions` rows, with full
provenance and a data quality profile.

## Stages

### 1. Read (`sheets/reader.py`)
- **`.xlsx`:** openpyxl (to see merged ranges, hidden rows/columns and number formats)
  plus pandas with `engine="calamine"` for fast value reads on large sheets.
- **`.xls`:** pandas + `xlrd`.
- **`.csv`:**
  - encoding via `charset-normalizer`
  - delimiter via `csv.Sniffer` on the first 64 KB
  - read everything as `dtype=str` first (never let pandas guess types, which destroys
    leading zeros)
- **Multi-sheet:** each sheet is a unit. Skip sheets that profile as notes or empty
  (`SHEET_SKIPPED`).
- **Files over 100k rows:** read in chunks (CSV) or with calamine (xlsx), and log the
  row count.
- **`doc_date`:** for xlsx/xls, the export date from the document properties; null for
  CSV (ADR-029).

### 2. Profile (`sheets/profile.py`)
- **`file_profile`:** columns exactly as in `DATA_SCHEMA.md` (doc_id, sheet, n_rows,
  n_cols, header_row, merged_ranges, hidden_rows, hidden_cols, title_rows_dropped,
  total_rows_dropped, encoding, delimiter, skipped, skip_reason).
- **`column_profile`** (one row per column): header_raw, null_pct, distinct_pct,
  inferred_type, top 3 patterns (masked shape, e.g. `ddd-dd-dddd`), min/max length.
  **No raw sample values are stored.**

### 3. Fix layout (`sheets/layout.py`)
- **Header detection:** score the first 15 rows. The header row is the first row where
  ≥ 60% of cells are non-empty strings, few are numeric, and the next 3 rows are
  "data-like". Log `SHEET_HEADER_OFFSET` if it isn't row 1.
- **Merged header cells:** fill the merged value across the range, and join two-row
  headers ("Employee" over "SSN" → "Employee SSN").
- **Drop rows:** title/banner rows above the header, total/summary rows (the first cell
  matches `^(total|grand total|count|sum)\b`), and fully blank rows.
- **Hidden rows:** keep them (they are still breached data) and flag
  `SHEET_HIDDEN_ROWS`.

### 4. Map columns (`sheets/mapping.py` + `ml/column_classifier.py`)
- **Target labels:** `FULL_NAME, FIRST_NAME, MIDDLE_NAME, LAST_NAME, SUFFIX, ADDRESS_FULL,
  ADDRESS_LINE1, ADDRESS_LINE2, CITY, STATE, ZIP, CITY_STATE_ZIP, PHONE, EMAIL, DOB, SSN,
  DL_NUMBER, DL_STATE, PASSPORT, BANK_ACCOUNT, ROUTING, CARD, MRN, MEMBER_ID,
  GROUP_NUMBER, DIAGNOSIS, STUDENT_ID, SCHOOL, GUARDIAN_NAME, EMPLOYEE_ID, ORG_NAME,
  EIN, FREE_TEXT, OTHER`.
- **Baseline:** header-alias rules (`config/header_aliases.yaml`, e.g. SSN ← `ssn`,
  `social`, `ss#`, `soc sec`, `emp_ssn`).
- **ML:** classifier on engineered column features (`ML_MODELS.md §C`).
- **Decision** (ADR-034; thresholds live in config, not code). "Rules none" means no
  header alias matched.

  | rules | ML | decision | outcome |
  |---|---|---|---|
  | label | same label | `AGREE` | accept; `COL_MAPPING_AGREE_LOW_PROBA` (INFO) if ml_proba < 0.60 |
  | none | ml_proba ≥ 0.70 | `ML_ONLY` | accept |
  | none | ml_proba < 0.70 | `REVIEW` | `COL_MAPPING_LOW_CONF` (WARN) |
  | label | different label, ml_proba ≥ 0.80 | `ML_OVERRIDE` | accept; `COL_MAPPING_ML_OVERRIDE` (WARN) |
  | label | different label, ml_proba < 0.80 | `REVIEW` | `COL_MAPPING_LOW_CONF` (WARN) |
  | label | unavailable | `RULE_ONLY` | accept |
  | none | unavailable | `REVIEW` | `COL_MAPPING_LOW_CONF` (WARN), final_label OTHER |
- **Output table `column_mapping`:** columns exactly as in `DATA_SCHEMA.md` (doc_id,
  sheet, col_idx, header_raw, rule_label, ml_label, ml_proba, final_label, decision,
  reviewed_label).
- **Sensitive-looking but unmapped columns** (e.g. ≥ 50% of values fit the SSN shape but
  the label is OTHER) → `COL_UNMAPPED_SENSITIVE`.

### 5. Repair (`sheets/repair.py`)
| Problem | Fix / flag |
|---|---|
| ZIP lost its leading zero (4 digits, state in the leading-zero set CT/MA/ME/NH/NJ/PR/RI/VT…) | pad → `XL_ZIP_LEADING_ZERO_RESTORED` |
| Excel date serial (e.g. `32874`) in a DOB column | convert from epoch 1899-12-30 → `XL_DATE_SERIAL_CONVERTED` |
| Mixed date formats in one column | parse per cell; ambiguous `03/04/90` uses the column's dominant format → `DOB_AMBIGUOUS_FORMAT` (WARN) if it can't be decided |
| Scientific notation / float for a long ID (`4.11E+15`, `4111111111111110.0`) | **cannot be recovered** → `XL_NUMBER_PRECISION_LOST` (ERROR), present=Y, valid=FAIL |
| SSN stored as a number with lost leading zeros (8 digits) | pad to 9 only if the column is mapped as SSN → `XL_SSN_ZERO_PADDED` (WARN) |
| Excel error values (`#N/A`, `#REF!`, `#VALUE!`) | null → `XL_ERROR_VALUE` |
| Pre-masked values (`XXX-XX-1234`, `***1234`) | present=Y, masked kept, valid=`PREMASKED` → `PREMASKED_VALUE` (INFO) |
| Combined `CITY_STATE_ZIP` / `FULL_NAME` / `ADDRESS_FULL` | split with usaddress / nameparser |
| Numbers stored as text, stray whitespace, non-breaking spaces | normalize |

### 6. Reshape (`sheets/reshape.py`)
Wide dependent columns (`Dep1_First, Dep1_DOB, Dep2_First…`) are unpivoted into one
row per dependent, with `person_role=DEPENDENT` and a link to the subscriber row
(`related_mention_id`).

### 7. Free-text scan (`sheets/freetext.py`)
Columns mapped `FREE_TEXT` (notes, comments) are scanned with the same regexes and
validators as the PDF track (SSN, card with Luhn, MRN pattern, DOB). Hits attach to the
row's person as additional elements → `FREE_TEXT_PII_FOUND` (WARN, reviewer should
confirm). The snippet is stored masked.

### 8. Emit mentions
One mention per person per row (subscriber + each dependent). Provenance:
`source_type=SPREADSHEET`, `source_file`, `source_sheet`, `source_row` (1-based Excel
row number, so a reviewer can jump straight to it). Exact duplicate rows within a file
→ `ROW_DUPLICATE_IN_FILE` (INFO), kept once.

## Data quality monitoring outputs
- `file_profile`, `column_profile`, `column_mapping` → DuckDB and the workbook's
  `File_Profiles` and `Column_Mappings` sheets.
- `runs` history in DuckDB lets you compare null %, mapping confidence and FAIL rate
  across runs (`v_quality_trend`).
