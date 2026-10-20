# sample_output/: what a v1.0 run produces (SYNTHETIC DATA)

`data/output/` is git-ignored, so these copies of one corpus_v1 run are committed for
readers who don't run the pipeline (ADR-068, ADR-069). The leak guard reports 0 findings
on every file here.

| file | what it is | made by |
|---|---|---|
| `breachlens_review_corpus_v1.xlsm` | The review workbook: 7 sheets, live formulas, 2 macros, masked values only | `breachlens report` |
| `workbook_summary.png` | Summary sheet: each Excel formula next to the pipeline value | Excel, read-only, macros disabled |
| `workbook_review_queue.png` | Review_Queue with the status dropdown and macro buttons | Excel, read-only, macros disabled |
| `workbook_mentions.png` | Mentions: extracted records with validation highlighting | Excel, read-only, macros disabled |
| `METRICS.md`, `metrics.json` | Scores vs ground truth: corpus_v1 (dev) and the seed-43 holdout (untuned) | `breachlens evaluate pipeline` |
| `scale_report.json` | Per-stage timing on the 50,000-row claims file | `breachlens scale-test` |

**Regenerate** (after the quick start in the main README): `breachlens run`,
`breachlens db build`, `breachlens report`, `breachlens scale-test`, then
`breachlens evaluate pipeline` (it adds the latest scale report to the metrics).
- **Same:** the counts. A fresh clone with a different salt gives the same workbook
  values and metrics.
- **Different:** the run id and the timings.

**Macros:** a workbook downloaded from the internet opens with macros blocked (Mark of
the Web). Close it, right-click the file → Properties → tick **Unblock** → OK, reopen
it and click **Enable Content**.

**Not legal advice.** The notification rules are an illustrative subset.
