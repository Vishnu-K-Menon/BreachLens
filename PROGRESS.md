# PROGRESS.md

Append-only build log. Format: see docs/WORKFLOW.md.

## 2026-10-17 (Day 1)
- [docs] Read-through findings resolved before any code: ADR-027 … ADR-044,
  `schema_version` 1.0 → 1.1, affected docs updated (commit `docs: resolve read-through
  findings`).
- [M0] Scaffold complete. AC evidence (Windows 11, `.venv` on Python 3.11.9):
  - `pip install -e ".[dev]"` succeeds.
  - `python -m breachlens --help` lists all 8 commands: generate, run, evaluate,
    train, apply-review, ask, scale-test, report.
  - `python -m breachlens run --config config/pipeline.yaml` exits 0 (0 stages
    registered yet; it needs `BREACHLENS_SALT` in `.env` and exits 2 with a clear
    message without it).
  - `pytest -q`: 48 passed. `ruff check .` and `ruff format --check .` clean.
  - Leak guard: N/A until M4 (ADR-044). M0 writes nothing to disk.
- Notes:
  - Ruff ≥ 0.17 also formats Python blocks inside Markdown, so `[tool.ruff] include`
    limits it to `*.py`/`*.pyi`.
  - The stage toggle is `stages.validation` (not `validate`, which shadows pydantic's
    `BaseModel.validate`).
  - pip resolved pandas 3.0 (string dtype and copy-on-write are the defaults). Keep
    this in mind for `dtype=str` reads in M3.
  - Open for M1: `synth/` sits at the repo root (ARCHITECTURE layout), outside the
    installed package. `breachlens generate` needs it importable (add it to the wheel
    packages or move it under `src/`; decide in M1 and record an ADR).
- Next: M1 synthetic corpus. Needs LibreOffice (for `.xls`) and network access for the
  Census address-pool check.
