# WORKFLOW.md — How to work in this repo

## Environment
```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,ocr,ml,ask]"
cp .env.example .env            # set BREACHLENS_SALT to a random 32+ char string
```
Windows (PowerShell; the primary dev machine, ADR-042):
```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,ocr,ml,ask]"
Copy-Item .env.example .env     # set BREACHLENS_SALT to a random 32+ char string
# optional: set TESSERACT_CMD / SOFFICE_PATH in .env if they are not on PATH
```
System dependencies (the agent checks each and tells the human what's missing):
| tool | needed for | install |
|---|---|---|
| Tesseract | OCR of scanned PDFs | macOS `brew install tesseract` · Ubuntu `apt-get install tesseract-ocr` · Windows UB Mannheim installer + `TESSERACT_CMD` |
| LibreOffice ≥ 24.8 | `.xls` generation, formula recalculation tests | libreoffice.org; set `SOFFICE_PATH` if not on PATH |
| Ollama | Ask BreachLens (local LLM) | ollama.com, then `ollama pull qwen2.5-coder:7b` |
| Microsoft Excel | one-time macro shell (`vbaProject.bin`), screenshots | human step |
| KNIME Analytics Platform 5.x | workflow assembly | human step |

Core Python dependencies: pandas, pydantic, pyyaml, typer, faker, reportlab, pymupdf,
pdfplumber, pillow, nameparser, usaddress, zipcodes, rapidfuzz, jellyfish,
phonenumbers, requests, openpyxl, xlsxwriter, python-calamine, xlrd,
charset-normalizer, duckdb, python-dotenv. Extras (ADR-038): `[dev]` pytest, ruff ·
`[ocr]` pytesseract · `[ml]` scikit-learn, joblib, matplotlib · `[ask]` sqlglot ·
`[anthropic]` anthropic.

## Commands
```bash
python -m breachlens.synth.address_pool                 # one-time, needs network (ADR-043)
python -m breachlens generate --seed 42 --out data/raw/corpus_v1   # writes docs/ + truth/ (ADR-047)
python -m breachlens train column-classifier            # (optional: match-model, doctype)
python -m breachlens run --config config/pipeline.yaml --input data/raw/corpus_v1/docs
python -m breachlens evaluate --run latest --truth data/raw/corpus_v1/truth   # TARGET defaults to pipeline (ADR-039)
python -m breachlens scale-test                          # times each stage on data/raw/scale/large_claims.csv (50k rows, ADR-051)
python -m breachlens apply-review --decisions data/output/<run_id>/review_decisions_<run_id>.csv
python -m breachlens ask "How many people in Texas had both SSN and medical info exposed?"
python -m breachlens evaluate ask
python -m breachlens report --run latest
pytest -q && ruff check . && ruff format --check .
```

## Working loop
1. Take the next unchecked task in `docs/PLAN.md`.
2. Write tests first for rules, normalizers, repairs, features and the SQL guard
   (table-driven).
3. Implement small, pure functions. Stage signature `run(df, ctx) -> df`.
4. Run the full check (pytest, ruff, an end-to-end run).
5. Tick the box, append to `PROGRESS.md`, commit.
6. At the end of each milestone, verify the acceptance criteria and record the evidence
   (numbers, test counts) in PROGRESS.md. Stop and summarize for the human.

## Commits
One task per commit, Conventional Commits (`feat(sheets): detect header offset`,
`test(ask): guard rejects DDL`). Never commit `data/output/`, `data/cache/`,
anything in `data/raw/` except `data/raw/sample/` (regenerable, ADR-044/047) or `.env`.

## PROGRESS.md format
```markdown
## 2026-10-19 (Day 2)
- [M3] Column classifier: H+V macro-F1 0.91 vs rules 0.64 on hard set.
- Deviation: ADR-0NN (calamine for files > 20k rows).
- Next: repair.py.
```

## Testing conventions
- `tests/unit/`: one file per module.
- `tests/integration/test_pipeline_sample.py`: `data/raw/sample/` (3 PDFs + 3 small
  spreadsheets, committed), offline, under 60 s.
- `tests/test_leak_guard.py`: mandatory, scans every output file.
- `tests/test_ask_guard.py`: adversarial SQL + prompts. The provider is mocked.
- Markers: `network`, `libreoffice`, `ollama`, `tesseract`. Skip automatically when
  the dependency is missing.

## Code style
Python 3.11, type hints, ruff + isort, `logging` (no prints in library code), no
business constants in code, docstrings stating input/output columns.

## Docs the agent writes during the build
- `docs/KNIME_GUIDE.md` (M7): node-by-node assembly for both tracks, flow variables,
  Python environment (`conda create -n breachlens-knime -c knime -c conda-forge
  knime-python-base python=3.11` then `pip install -e .`). Verify the package name and
  version against current KNIME docs.
- `docs/METHODS.md`, `docs/ASSUMPTIONS_LIMITATIONS.md`, `models/model_card.md` (M8).

## README requirements (M8)
Written for a hiring manager with 2 minutes:
1. One-line pitch + demo GIF/screenshot (highlighted workbook, KNIME canvas, Ask in a
   terminal).
2. **Problem** (breach notification) and **what it does** (both tracks, diagram).
3. **Results table:**
   - extraction F1 by track
   - column classifier: rules vs ML
   - matching precision/recall
   - collapse ratio (rows → people)
   - Ask execution accuracy
   - scale throughput
4. **Skills mapped to the job description** (`PROJECT_OVERVIEW.md` table), using the
   JD's language: "engineered features", "data quality monitoring", "Python workflows".
5. **Handoff contract:** a short section explaining that output tables follow a
   versioned schema (`DATA_SCHEMA.md`) that downstream teams can rely on.
6. **SQL:** show 2 of the reference queries with their results.
7. **Excel:** a screenshot of the Summary formulas and the macro buttons, plus
   instructions to unblock macros.
8. **Privacy by design:** synthetic data, no raw values stored, local LLM, offline mode.
9. **Design rationale** (from `DESIGN_RATIONALE.md`), **limitations**, **roadmap**,
   and "not legal advice".
10. Quick start (≤ 6 commands).
