# PRIVACY.md — Guardrails (non-negotiable)

1. **Synthetic only.** Never add real documents, real people, scraped leak data, or
   personal documents of the developer. Every generated page is watermarked
   `SYNTHETIC - NOT REAL`.
2. **Data minimization.** Persist only what notification needs:
   - presence flags (`*_present`)
   - masked values (`*_masked`, last 4 only)
   - validity results (`*_valid`)
   - HMAC keys for matching (`*_key`)
3. **Transient raw values.** `_raw_*` columns may exist only in memory between
   extraction and `privacy.drop_raw()`. They must never be written to CSV, Excel,
   DuckDB, logs, the audit trail, exceptions or the cache.
4. **Leak guard.** `privacy/leak_guard.py` scans every DataFrame and every string before
   any write (ADR-027). It fails on:
   - `\b\d{3}([- ]?)\d{2}\1\d{4}\b` (SSN-like, one consistent separator, so a ZIP+4
     such as `12345-6789` does not match), in every string column that isn't exempt
   - `\b\d{13,19}\b` (card-like), in every string column that isn't exempt
   - `\b\d{9,17}\b` (account-like), **only** in the explicit list of string columns in
     config (free-text and masked columns such as `source_snippet`, `raw_name`,
     `raw_address`, `address_suggestion`, `*_masked`, `value_masked`, `detail_json`)
   - any `_raw_` column

   Exempt columns: numeric/meta columns (`bytes`, `processing_ms`, counts, and
   timestamps such as `started_at`, `finished_at`, `processed_at`, `reviewed_at`,
   `ts`), plus `*_key`, `zip4` and `phone`. `run_id` uses the format
   `R20261017-153000-ab12`, which none of the patterns match.

   `tests/test_leak_guard.py` runs the whole pipeline on the sample corpus and scans
   every output file. The guard is built in M4. Until then, no stage persists mentions
   or identifiers to disk (ADR-044).
5. **Masked snippets.** `source_snippet` and audit entries are masked before storage.
6. **Secrets.** `BREACHLENS_SALT`, `ANTHROPIC_API_KEY` (optional) and others live in `.env`. Commit
   `.env.example` only.
7. **What leaves the machine.** Only street/city/state/ZIP strings go to the Census
   Geocoder. Never names or identifiers. `offline: true`
   disables all network calls (the on-prem mode).
8. **Ground truth exception.** `gt_*.csv` contains synthetic raw values by
   design. It carries a header comment and is excluded from the leak-guard scan by
   explicit path only (`data/raw/corpus_v1/truth/`, ADR-047). The generated input
   corpus is synthetic input, not pipeline output, and is never committed.
9. **LLM boundary.** The Ask assistant sends the LLM only the schema card, few-shot
   examples and the question. Result rows may go to the LLM only with the local `ollama`
   provider in `--explain` mode. Ask sees only views without `_key` columns, and the
   guard also blocks `_key` columns. The connection is read-only with external access
   disabled (ADR-040).
10. **Spreadsheet profiles.** `column_profile` stores masked shapes (`ddd-dd-dddd`) and
    statistics, never sample values. Model files contain no raw values.
11. **Logging.** Never log row contents at INFO or above. Debug logs must use masked
   values.
