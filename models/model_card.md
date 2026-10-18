# Model card: column-type classifier (SYNTHETIC DATA)

Version `column-classifier-1`, chosen model `HV_lr` (sigmoid-calibrated).

## Task and data
Predict the semantic label of a spreadsheet column (34 labels, SPREADSHEET_TRACK.md §4) from its header and values. Training data: the synthetic column corpus (6071 columns, `breachlens.synth.column_corpus`). No real data; no raw values are stored in the model (value features are aggregate rates; the header TF-IDF vocabulary holds header n-grams only).

## Features
Value shape, pattern hit rates (SSN, ZIP, phone, email, dates, Luhn, ABA, state codes, sci-notation, masks, ID shapes), dictionary rates (first names, surnames, cities, org suffixes), value statistics and column position; plus header character 3-5-gram TF-IDF (300 features).

## Evaluation sets
- validation: GroupKFold(5) on the column corpus, grouped by header alias (unseen aliases)
- uninformative headers (`Column7`, `ID`, blank …): scored out-of-fold
- spreadsheet sets: `dev_corpus_v1`, `test_holdout`, read through the real reader/layout path. `dev_corpus_v1` was used to diagnose the training-data shift (ADR-055); `test_holdout` (seed 43) was never inspected before scoring.

## Results (macro-F1)

| model | validation | uninformative_headers_oof | sheets_dev_corpus_v1 | sheets_test_holdout | combined_dev_corpus_v1 | combined_test_holdout |
|---|---|---|---|---|---|---|
| R (header rules) | 0.6396 | 0.0054 | 0.9911 | 0.9911 | 0.1467 | 0.1467 |
| V (values only, HGB) | 0.6233 | 0.6618 | 0.793 | 0.8077 | 0.6708 | 0.6739 |
| H+V (HV_lr) | 0.8983 | 0.899 | 0.8718 | 0.8718 | 0.8992 | 0.8992 |

Validation macro-F1 of the other H+V candidate (HV_hgb): 0.7893.

## Calibration
ECE out-of-fold (uncalibrated) 0.0311; after sigmoid calibration: dev_corpus_v1 0.0813, test_holdout 0.0534. See `reliability.png`; the mapping decision uses thresholds 0.60 / 0.70 / 0.80 (ADR-034).

## Limitations
- Synthetic headers and values: dictionary features match the generator's name lists, which flatters name/city labels. Real exports will be harder.
- All spreadsheet sets come from the same generator family as the training corpus, and the 8 corpus spreadsheets keep their header templates across seeds: the holdout tests new values under known layouts. The header-blind test is the uninformative-header set.
- 34 fixed labels; anything else is OTHER.

Files: `confusion_matrix.png`, `reliability.png`, `column_classifier_metrics.json` (per-label F1, top permutation features per label, per-column predictions).
