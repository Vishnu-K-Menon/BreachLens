# SYNTHETIC_DATA.md — Test corpus specification

Purpose: a realistic but 100% fake "breach" corpus with ground truth, so every metric is
measured rather than claimed. Seed 42. Output (ADR-047): `data/raw/corpus_v1/docs/` (the
breach input), `data/raw/corpus_v1/truth/` (ground truth + manifest),
`data/raw/column_corpus/` and `data/raw/scale/`. All of it is regenerable and git-ignored.

Safe by construction (ADR-048): card numbers come only from test IIN prefixes (`411111`,
`555555`) with a Luhn check digit (P14 changes only the check digit). Phones use
`555-01xx`; emails use `example.com/.org/.net`. All identifiers are randomly generated;
any match to a real number is coincidental.

## People and organizations (`src/breachlens/synth/people.py`)
- **People:**
  - 40 base people: CA, NY, TX, FL, PA, VA (6 each), plus NJ and MA (2 each, for
    leading-zero ZIPs; these use `default` jurisdiction rules)
  - dependents (≈ 10, some minors)
  - 8 students (some minors), each with a guardian
- **Fields:**
  - name: title (10%), first, middle (70%), last, suffix (15%)
  - DOB
  - SSN: Faker; regenerate if it hits the known-invalid list
  - license + state: format from `dl_formats.yaml`
  - passport (20%)
  - contact: phone, email
  - financial: bank account + valid ABA routing number (30%), Luhn-valid card (20%)
  - health: MRN, member ID, group number, insurer, ICD-10-like diagnosis
  - employment: employer, employee ID
  - education: student ID, school
- **Addresses:**
  - 80% from `data/reference/address_pool.csv` (public, non-residential, Census-verified)
  - 20% Faker addresses (expected UNVERIFIED)
  - some shared households
- **8 organizations:** employer, payer, clinic, insurer, school district, university,
  bank, vendor. Each has an EIN (`##-#######`); providers also get an NPI-like 10-digit
  number.

## PDF documents (`src/breachlens/synth/render_pdf.py`, reportlab): 4 types × 2 layout variants, ~30 docs
Generic, original layouts "in the style of" common forms. Do not reproduce official
artwork. Watermark `SYNTHETIC - NOT REAL` on every page. ~30% become image-only scans
(`src/breachlens/synth/scanify.py`: 300 dpi, Gaussian noise σ≈8, rotation ±2°, blur, JPEG q70). One
exact duplicate file.

| type id | content | persons | count |
|---|---|---|---|
| WAGE_STATEMENT | W-2 style: employee name/address/SSN, employer name/EIN | EMPLOYEE | 8 |
| HEALTH_CLAIM | claim form style: patient + insured, DOB, member/group ID, diagnosis codes, provider NPI/TIN | PATIENT, INSURED | 8 |
| NEW_HIRE_ID | identity worksheet: name, DOB, SSN, license + state or passport | NEW_HIRE | 6 |
| EOB_LETTER | free-text letter: patient, member ID, date of service, procedure | PATIENT | 8 |

## Spreadsheets (`src/breachlens/synth/render_sheets.py`): 8 corpus files + 1 scale file
Write with openpyxl so the damage is real (numbers stored as numbers, real merged
ranges, hidden rows, number formats). Make `.xls` via LibreOffice headless conversion
(fallback: `xlwt`). The first sheet or a header comment carries
`SYNTHETIC - NOT REAL`. The 8 corpus files go to `data/raw/corpus_v1/docs/`. The scale
file `large_claims.csv` goes to `data/raw/scale/` and never into the corpus
(ADR-031, ADR-032).

`doc_date` (ADR-029): xlsx/xls files get an export date in their document properties.
CSV files have none (null). PDFs: W-2 → tax-year end (Dec 31), health claim → date of
service, EOB letter → letter date. Planted case P17 (moved address) must use dated
sources, with the newer address on the later `doc_date`.

| file | rows | people | mess |
|---|---|---|---|
| `hr_roster.xlsx` | ~60 | employees | 3 title rows, merged 2-row header, hidden rows, ZIP as number (lost zeros), total row, duplicate row |
| `payroll_export.csv` | ~80 | employees | Latin-1 with accented names, `;` delimiter, header `SS#`, SSN as 8-digit number (lost zero), `#N/A` values |
| `patient_list.xlsx` | ~70 | patients | 2 sheets (Patients, Notes-only), DOB as date serial + mixed text formats, MRN, member ID, `Notes` column containing SSN/MRN in prose |
| `benefits_enrollment.xlsx` | ~40 | subscribers + dependents | `Dep1_First … Dep3_DOB` wide columns (unpivot), minors |
| `student_roster.xlsx` | ~30 | students + guardians | student ID, school, DOB (minors), guardian name/phone → FERPA |
| `customer_cards.xlsx` | ~50 | customers | card numbers as floats (sci-notation, precision lost), some pre-masked `XXXX-XXXX-XXXX-1234`, `City, ST ZIP` combined |
| `vendor_list.xlsx` | ~25 | none | organizations only, with EINs (all excluded) |
| `legacy_export.xls` | ~40 | members | old format, header `ID` that actually holds SSNs, `Column7` with DOBs |
| `large_claims.csv` | 50,000 | generated | **scale file, not a corpus file**: written to `data/raw/scale/` by `src/breachlens/synth/scale.py`; scale test only, not part of accuracy metrics |

Overlap: ≥ 12 people appear in both a spreadsheet and a PDF, and ≥ 5 appear in two
spreadsheets.

## Column-classifier corpus (`src/breachlens/synth/column_corpus.py`)
See `ML_MODELS.md §C`: ~400 random tables, ~6,000 labelled columns, with alias groups
recorded for GroupKFold.

## Planted cases (record each in ground truth `planted_case`; each must appear ≥ 1 time)
| id | case | expected |
|---|---|---|
| P01 | Title "DR." / "REV." | moved to `name_title` |
| P02 | Suffix variants Jr./JR/Junior/III | normalized |
| P03 | Suffix typo (doubled letter, e.g. JJ) | NAME_SUFFIX_INVALID, suggest JR |
| P04 | "LAST, FIRST M" order | parsed |
| P05 | Nickname across sources (ROBERT/BOB) | merged |
| P06 | Hyphen/particle surnames (GARCIA-LOPEZ, DE LA VEGA, VAN DYKE) | intact |
| P07 | Apostrophe spacing "O' BRIEN" | fixed |
| P08 | One-letter surname variant across sources (ANDERSON/ANDERSEN) | merged or REVIEW |
| P09 | Unit inline, "APT6F", UPPER/LOWER | line 2, formatted |
| P10 | City typo with correct ZIP | ZIP-city mismatch + suggestion |
| P11 | ZIP missing a digit | ADDR_ZIP_FORMAT |
| P12 | Two-digit-year DOB | DOB_TWO_DIGIT_YEAR |
| P13 | Invalid SSN (area 666 / group 00) | SSN_* ERROR |
| P14 | Card failing Luhn | CARD_LUHN_FAIL |
| P15 | License not matching the state format | DL_FORMAT_STATE |
| P16 | License present, state missing | DL_STATE_MISSING |
| P17 | Same SSN, different address (moved) | merged; newer address survives |
| P18 | Twins: same last name + address, different DOB/SSN | NOT merged |
| P19 | EIN printed near the SSN | EIN excluded |
| P20 | Provider NPI/TIN on a claim | excluded |
| P21 | Organization in a name field | `excluded_entities` |
| P22 | Minor dependent | `is_minor`, guardian note |
| P23 | Name only, no qualifying element | not notifiable |
| P24 | Same person in 4+ sources | 1 golden record |
| P25 | Exact duplicate file | flagged, not double-counted |
| P26 | Leading/trailing spaces | trimmed |
| P27 | Title rows above the header | header offset detected |
| P28 | Merged 2-row header | joined header names |
| P29 | Hidden rows | kept + flagged |
| P30 | Total row at the bottom | dropped |
| P31 | ZIP leading zero lost (NJ/MA) | restored |
| P32 | DOB as Excel serial + mixed formats | converted / flagged |
| P33 | Card in sci-notation | XL_NUMBER_PRECISION_LOST |
| P34 | Pre-masked values | PREMASKED_VALUE |
| P35 | Latin-1, `;` delimiter, `SS#` header | read + mapped |
| P36 | `.xls` with an `ID` column holding SSNs, `Column7` with DOBs | ML mapper catches what the rules miss |
| P37 | Wide dependent columns | unpivoted |
| P38 | Notes column with SSN/MRN in prose | FREE_TEXT_PII_FOUND |
| P39 | Vendor file (orgs only) | 0 person mentions |
| P40 | Student + guardian (FERPA) | `ferpa_flag`, minor note |
| P41 | Same person in payroll CSV and a W-2 PDF | one `person_id` |
| P42 | Duplicate row within a file | ROW_DUPLICATE_IN_FILE |
| P43 | `#N/A` cells | XL_ERROR_VALUE |
| P44 | SSN stored as an 8-digit number | XL_SSN_ZERO_PADDED |

## Ground truth (`data/raw/corpus_v1/truth/`)
`doc_id` follows the shared rule in `breachlens.ingest.doc_ids` (sorted POSIX relative
paths under `docs/`). CSV `source_row` is the 1-based physical line number (ADR-047).
- `gt_mentions.csv`: source (doc_id + sheet + row, or doc_id + page), person_role,
  true_person_id, expected normalized values (raw synthetic identifiers allowed here
  only; first line `# SYNTHETIC GROUND TRUTH - NOT REAL PEOPLE`), planted_case.
- `gt_people.csv`: true_person_id, canonical fields, expected elements_exposed,
  notify_required, jurisdiction, ferpa_flag.
- `gt_columns.csv`: doc_id, sheet, header_raw, true_label (for the 8 corpus
  spreadsheets).
- `gt_shared_addresses.csv` (addition, ADR-049): address, true_person_id_a,
  true_person_id_b, household_a, household_b — unrelated people sharing a pool address
  (at most 2 unrelated households per address); none of them may be merged.
- `gt_excluded.csv` (addition, ADR-047): doc_id, page, kind (ORG / EIN / NPI /
  PROVIDER_TIN / ITIN), value, planted_case — the exclusions the PDF track must find.
- `manifest.json`: seed, version, counts, scanned docs, planted-case coverage.

## Address pool (`data/reference/address_pool.csv`)
pool_id, name (e.g. "<City> Public Library - Central"), line1, city, state, zip5,
census_match, verified_on, plus matched_address and source_url. Public, non-residential
buildings only: public libraries, city halls and post offices found by web search,
including NJ/MA buildings for the leading-zero ZIPs (ADR-043). `source_url` must be the
building's official page or the USPS locator, never a page that names an individual
(ADR-048). Candidates live in `data/reference/address_candidates.csv`. The builder is
`python -m breachlens.synth.address_pool`; it is the only network user in M1, and its
responses are cached in `data/cache/census/`. Each candidate is verified live via
`https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?address=...&benchmark=Public_AR_Current&format=json`.
Drop non-matches. Never hand-type unverified addresses.
