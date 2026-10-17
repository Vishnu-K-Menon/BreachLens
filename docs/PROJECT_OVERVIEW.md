# PROJECT_OVERVIEW.md — BreachLens in plain words

> **BreachLens** — from breached documents and spreadsheets to a validated,
> deduplicated notification list.

## The problem
After a cyber incident, a company must work out **who** was in the stolen data,
**what** of theirs was exposed (SSN, license, medical, financial, student records), and
**where** they live, because the state of residence decides which notification law
applies. The stolen data arrives in two forms:

1. **Unstructured documents**: PDFs and scans (tax forms, claim forms, letters, ID
   worksheets).
2. **Structured files**: large, messy Excel/CSV exports from HR, payroll, patient,
   student and customer systems.

Both must be cleaned, standardized, validated, merged to one record per person, and
turned into a notification-ready dataset that people can review and downstream teams
can rely on.

## What BreachLens does
```
PDFs/scans ─► extract text ─► find fields ───────────────────────────┐
                                                                       ├─► one schema ─► clean ─► validate ─► verify address
Excel/CSV ──► profile ─► fix layout ─► map columns (ML) ─► repair ─────┘                     │
                                                                                              ▼
                       Excel review workbook ◄── notify rules ◄── match people ◄── mask sensitive values
                       (formulas + macros)              │
                                                         ▼
                                              DuckDB database ─► "Ask BreachLens" (local LLM → SQL)
```

## Skills it demonstrates (job-description language)
| Requirement | Where |
|---|---|
| Python workflows for text and data processing | Both input tracks, end to end |
| Structured + unstructured sources | Spreadsheet track + PDF/OCR track |
| Clean, structure, validate at scale | Normalizers, ~60 rule codes, 50k-row scale test |
| Feature engineering | Column-type features; matching features |
| Review and validate extracted data | Review queue, Excel macros, apply-review round trip |
| Monitor data quality across sources | File and column profiles, QC summary, `runs` history |
| Document methods, assumptions, limitations | METHODS / ASSUMPTIONS_LIMITATIONS / DECISIONS |
| Advanced Excel: formulas and macros | Live-formula workbook + VBA review macros |
| SQL | DuckDB schema, views, 20 reference queries |
| PII/PHI/GDPR/FERPA | Element coverage, FERPA flag, data minimization |
| AI/ML, NLP | Column-type classifier, text-to-SQL assistant with evaluation, OCR/text parsing |
| Collaborate with data engineering/IT | Fixed "handoff contract" schema, config-driven rules, KNIME workflow |

## Scope boundaries
- Synthetic data only. Six illustrative states. 4 PDF document types, 8 corpus
  spreadsheet files, plus one 50k-row scale file kept outside the corpus.
- No model fine-tuning. No CASS address certification. No legal advice.
