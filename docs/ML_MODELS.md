# ML_MODELS.md

All models use scikit-learn, fixed seeds, and are saved to `models/*.joblib`, each with
a `model_card.md` (data, features, metrics, limitations). Metrics go into
`metrics.json` and the README. Training: `breachlens train <model>`.

---

## C. Column-type classifier — REQUIRED (M3)

**Task:** given one spreadsheet column (header + values), predict its semantic label
(the label list is in `SPREADSHEET_TRACK.md §4`).

### Training data (`src/breachlens/synth/column_corpus.py` → `data/raw/column_corpus/`, ADR-047)
- Generate ~400 random synthetic tables (5–25 columns, 20–500 rows) from Faker people.
  That's about 6,000 labelled columns.
- **Header noise:** pick from an alias pool per label, then randomly apply
  case/underscores/abbreviation/typos. ~15% of columns get **uninformative headers**
  (`Column7`, `ID`, `Field_3`, blank).
- **Value noise:** masked values, Excel damage (lost zeros, serials, sci-notation),
  5–40% nulls, mixed formats.
- **Confusables on purpose:** EMPLOYEE_ID vs SSN (9 digits, no dashes), MRN vs
  MEMBER_ID, ZIP vs 5-digit EMPLOYEE_ID, DOB vs hire date (labelled OTHER), PHONE vs
  ACCOUNT.

### Engineered features (`sheets/features.py`), computed per column on ≤ 500 sampled non-null values
- **Shape:** mean/std length, % digits, % letters, % containing `-` `/` `@` `.`
  `,`, % all-digit
- **Pattern hit rates:** SSN shape, SSN-valid (area/group/serial), ZIP5/ZIP+4, phone,
  email, ISO/US date parse rate, Luhn-valid rate, ABA-valid rate, 2-letter state code
  rate, sci-notation rate, masked-pattern rate
- **Dictionary rates:** % in a first-name list, % in a surname list, % in the US
  city list, % ending in an org suffix
- **Value statistics:** distinct ratio, null %, numeric mean/std (if numeric), %
  plausible birth years (1900–today) after date parse
- **Header features:** character 3–5-gram TF-IDF of the normalized header (`max_features=300`)
- **Context:** column position / n_cols, neighbor header n-grams (optional, behind a flag)

**Privacy:** features are aggregate statistics. No raw values are stored with the
model.

### Models compared
1. **Baseline R:** header-alias rules only.
2. **Model V:** value-features only, with `HistGradientBoostingClassifier`.
3. **Model H+V:** header + value features, with `LogisticRegression` (scaled,
   `class_weight="balanced"`) **and** `HistGradientBoostingClassifier`. Keep the better
   one by macro-F1 on validation.

### Evaluation (the honest part)
- **Split by header alias group** (GroupKFold), so test headers are aliases the model
  never saw. Plus a separate **hard test set**: the 8 corpus spreadsheets
  (`gt_columns.csv`; the scale file is not included, ADR-032) and the
  uninformative-header columns.
- Report:
  - macro-F1 and per-label F1
  - confusion matrix (PNG)
  - top features per label (permutation importance)
  - calibration: reliability curve for `ml_proba`, needed because the decision table
    uses 0.60/0.70/0.80 thresholds (ADR-034)
- Expected story: rules win on clean headers, lose badly on `ID`/`Column7`; V and H+V
  recover those columns from value patterns.

**AC:** H+V macro-F1 > R on the hard test set, with numbers reported.

---

## A. Document-type classifier — OPTIONAL
TF-IDF (word 1–2-grams) + `LogisticRegression` on page text. Train on text-layer
PDFs and test on OCR'd scans. 2 layout variants per type; split by person. Compare with
the keyword rules: accuracy, confusion matrix, and top weighted terms per class. The
README must note that synthetic forms make this an easy task.

## B. Learned duplicate matcher — OPTIONAL
- **Data:** the `pair_features` table from entity resolution. Labels from ground truth
  (same `true_person_id`).
- **Model:** `LogisticRegression` (interpretable coefficients) and optionally
  `HistGradientBoostingClassifier`.
- **Split:** by true-person cluster (GroupKFold), so no person appears in both training
  and test.
- **Compare:** with the hand-weighted score, using pairwise precision/recall/F1 at the
  operating threshold, a PR curve, and gray-zone size (how many pairs go to review).
- **Report:** learned coefficients next to the hand weights. Talking point: "Which
  features did the data say matter?"
