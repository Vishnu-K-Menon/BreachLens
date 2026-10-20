# METRICS.md: BreachLens pipeline metrics (SYNTHETIC DATA)

Generated 2026-10-20T03:09:52+00:00 by `breachlens evaluate pipeline` (ADR-068). corpus_v1 is the dev corpus (tuned on); the seed-43 holdout is untuned.

## Headline

| metric | corpus_v1 (dev) | holdout seed 43 (untuned) |
|---|---|---|
| mentions / people | 438 / 215 | 434 / 217 |
| collapse ratio (mentions per person) | 2.04 | 2.0 |
| notification list vs truth | 155/155 (missed 0, extra 0) | 159/159 (missed 0, extra 0) |
| matching pairwise P / R / F1 | 1.0 / 0.9326 / 0.9651 | 1.0 / 0.918 / 0.9572 |
| shared-address pairs merged | 0/78 | 0/59 |
| address status vs expected (ADR-050) | 396/398 = 0.995 | 386/394 = 0.9797 |
| planted validation cases caught | 306/306 | 299/302 |
| planted spreadsheet cases handled | 18/18 | 18/18 |
| column mapping final accuracy / macro-F1 | 1.0 / 1.0 | 1.0 / 1.0 |
| pipeline seconds (in memory) | 14.83 | 13.27 |
| fields PDF-OCR micro P / R / F1 | 1.0 / 0.9878 / 0.9939 | 0.962 / 0.9048 / 0.9325 |
| fields PDF-TEXT micro P / R / F1 | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 |
| fields SPREADSHEET micro P / R / F1 | 0.9991 / 1.0 / 0.9996 | 0.9991 / 1.0 / 0.9996 |

## Matching cases

| metric | corpus_v1 (dev) | holdout seed 43 (untuned) |
|---|---|---|
| P18 twins not merged | yes | yes |
| P17 mover merged, newer address kept | yes | yes |
| P05 nickname (Bob/Robert) row merged | yes | yes |
| P08 one-letter surname variant row merged | yes | yes |
| P24 4+ sources -> one record | yes | yes |
| P41 payroll CSV + W-2 -> one person_id | yes | NO |

## Notification by state (listed / truth)

| metric | corpus_v1 (dev) | holdout seed 43 (untuned) |
|---|---|---|
| CA | 30 / 30 | 24 / 24 |
| FL | 18 / 18 | 26 / 26 |
| MA | 7 / 7 | 5 / 5 |
| NJ | 8 / 8 | 7 / 7 |
| NY | 23 / 23 | 29 / 29 |
| PA | 22 / 22 | 22 / 22 |
| TX | 23 / 23 | 22 / 22 |
| VA | 24 / 24 | 24 / 24 |

## Field precision / recall / F1: corpus_v1 (dev)

| track | field | TP | FP | FN | precision | recall | F1 |
|---|---|---|---|---|---|---|---|
| PDF-OCR | city | 10 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | date_of_service | 4 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | diagnosis | 3 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | dl | 1 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | dl_state | 1 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | dob | 4 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | line1 | 10 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | member_id | 3 | 0 | 1 | 1.000 | 0.750 | 0.857 |
| PDF-OCR | name | 10 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | phone | 1 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | procedure | 4 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | ssn_present | 5 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | ssn_value | 5 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | state | 10 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | zip5 | 10 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | city | 23 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | date_of_service | 12 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | diagnosis | 5 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | dl | 4 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | dl_state | 3 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | dob | 10 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | email | 3 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | line1 | 23 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | member_id | 11 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | name | 23 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | passport | 1 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | phone | 5 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | procedure | 12 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | ssn_present | 9 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | ssn_value | 9 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | state | 23 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | zip5 | 23 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | bank_account | 27 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | card | 54 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | city | 365 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | dob | 241 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | email | 56 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | employee_id | 170 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | group_number | 40 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | line1 | 365 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | member_id | 105 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | mrn | 65 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | name | 405 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | phone | 234 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | routing | 27 | 3 | 0 | 0.900 | 1.000 | 0.947 |
| SPREADSHEET | ssn_present | 281 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | ssn_value | 281 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | state | 365 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | student_id | 30 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | zip5 | 365 | 0 | 0 | 1.000 | 1.000 | 1.000 |

## Field precision / recall / F1: holdout seed 43 (untuned)

| track | field | TP | FP | FN | precision | recall | F1 |
|---|---|---|---|---|---|---|---|
| PDF-OCR | city | 9 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | date_of_service | 2 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | diagnosis | 0 | 1 | 1 | 0.000 | 0.000 | 0.000 |
| PDF-OCR | dl | 2 | 0 | 1 | 1.000 | 0.667 | 0.800 |
| PDF-OCR | dl_state | 2 | 0 | 1 | 1.000 | 0.667 | 0.800 |
| PDF-OCR | dob | 5 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | email | 1 | 0 | 1 | 1.000 | 0.500 | 0.667 |
| PDF-OCR | line1 | 9 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | member_id | 2 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | name | 7 | 2 | 2 | 0.778 | 0.778 | 0.778 |
| PDF-OCR | passport | 1 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | phone | 4 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | procedure | 2 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | ssn_present | 6 | 0 | 1 | 1.000 | 0.857 | 0.923 |
| PDF-OCR | ssn_value | 6 | 0 | 1 | 1.000 | 0.857 | 0.923 |
| PDF-OCR | state | 9 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-OCR | zip5 | 9 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | city | 24 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | date_of_service | 14 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | diagnosis | 7 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | dl | 2 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | dl_state | 1 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | dob | 9 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | email | 1 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | line1 | 24 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | member_id | 13 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | name | 24 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | phone | 2 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | procedure | 14 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | ssn_present | 7 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | ssn_value | 7 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | state | 24 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PDF-TEXT | zip5 | 24 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | bank_account | 25 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | card | 50 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | city | 361 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | dob | 241 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | email | 56 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | employee_id | 170 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | group_number | 40 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | line1 | 361 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | member_id | 105 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | mrn | 65 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | name | 401 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | phone | 230 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | routing | 25 | 3 | 0 | 0.893 | 1.000 | 0.943 |
| SPREADSHEET | ssn_present | 281 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | ssn_value | 281 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | state | 361 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | student_id | 30 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| SPREADSHEET | zip5 | 361 | 0 | 0 | 1.000 | 1.000 | 1.000 |

## Column classifier (models/column_classifier_metrics.json)

Chosen model `HV_lr`. Macro-F1 on the hard tests:

| test set | chosen model | rules only |
|---|---|---|

| metric | corpus_v1 (dev) | holdout seed 43 (untuned) |
|---|---|---|
| spreadsheet columns, rules: accuracy / macro-F1 | 0.9796 / 0.9911 | 0.9796 / 0.9911 |
| spreadsheet columns, ml: accuracy / macro-F1 | 0.9082 / 0.8718 | 0.9082 / 0.8718 |
| spreadsheet columns, final: accuracy / macro-F1 | 1.0 / 1.0 | 1.0 / 1.0 |

## Address status: expected -> got (mentions)

- corpus_v1 (dev): CORRECTED->CORRECTED 1, INVALID->INVALID 1, UNVERIFIED->UNVERIFIED 121, VERIFIED->UNVERIFIED 2, VERIFIED->VERIFIED 273
- holdout seed 43 (untuned): CORRECTED->CORRECTED 1, INVALID->INVALID 1, UNVERIFIED->UNVERIFIED 130, VERIFIED->UNVERIFIED 8, VERIFIED->VERIFIED 254

## Throughput

| stage | corpus_v1 (dev) | holdout seed 43 (untuned) |
|---|---|---|
| pdf_track | 11.06 s (33 rows) | 10.18 s (33 rows) |
| sheet_track | 2.84 s (438 rows) | 2.28 s (434 rows) |
| normalize | 0.43 s (438 rows) | 0.49 s (434 rows) |
| validate | 0.18 s (438 rows) | 0.1 s (434 rows) |
| address | 0.13 s (438 rows) | 0.06 s (434 rows) |
| privacy | 0.02 s (438 rows) | 0.02 s (434 rows) |
| resolve | 0.1 s (438 rows) | 0.08 s (434 rows) |
| notify | 0.07 s (438 rows) | 0.06 s (434 rows) |

Scale test (latest `scale_report.json`, R20261020-011900-7710): 50,000 rows in 38.85 s = 1,287 rows/s end to end.
