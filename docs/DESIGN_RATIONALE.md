# DESIGN_RATIONALE.md — Why each feature exists (public sources only)

Use this table in the README. Every feature must trace to a public source or a general
data-quality principle.

| Feature | Why it exists | Public basis |
|---|---|---|
| Name parsing (title, first, middle initial, last, suffix) | Notification letters need clean name parts. Titles and suffixes break matching | ACTFORE's public data-mining page lists first name, last name, middle initial and suffix among extracted elements |
| "Last, First" order detection | Forms print names in both orders | General form conventions |
| Person vs organization classifier | Only individuals are notified. Tax and health forms always carry employer/payer/provider names | Layouts of W-2, 1099-NEC and CMS-1500 (public IRS/CMS forms) |
| SSN vs EIN/ITIN/NPI disambiguation | 9- and 10-digit numbers appear side by side on tax and claim forms. Only personal identifiers matter | IRS EIN format; SSA SSN rules; CMS NPI standard |
| SSN validity rules (area 000/666/9xx, group 00, serial 0000) | Catches OCR and keying errors | SSA, "Social Security Number Randomization" FAQ |
| Never infer a state from the SSN | Post-2011 randomization removed geographic meaning | SSA randomization (June 25, 2011) |
| Luhn / ABA routing checksums | Cheap, deterministic validity checks | ISO/IEC 7812 (Luhn); ABA routing number checksum |
| License format per state + issuing state | A license number is meaningless without the issuing state | ACTFORE's public element list includes license state; DMV formats |
| Address line 1/2 split, USPS abbreviations | Mailability and matching | USPS Publication 28 |
| ZIP→city/state check, then geocoding | Typos are the most common address error. State drives jurisdiction | USPS ZIP data; US Census Geocoder documentation |
| Entity resolution to one record per person | One person appears in many files. Over-merging under-notifies, under-merging double-notifies | ACTFORE publicly describes "collapse related entries … single entry per individual"; Fellegi-Sunter record linkage |
| Gray-zone matches go to human review | Merges carry legal consequences | ACTFORE publicly describes dedup "in collaboration with legal counsel and client approval" |
| Per-state notification triggers | Which elements trigger notice varies by state | NCSL breach notification law summaries; state statutes cited in config |
| Minor flag → guardian note | Minors are usually notified via a guardian | General notification practice |
| Present / masked / valid columns; no raw values stored | Data minimization | GDPR Art. 5(1)(c); HIPAA minimum-necessary standard (45 CFR 164.502(b)) |
| Audit log | Deliverables are audited before publication | ACTFORE publicly describes audits of "reports, extraction logs, and datasets" |
| Accuracy metrics vs ground truth | Accuracy is the product | ACTFORE publicly markets audited accuracy |
| Rules in config | Every engagement has custom requirements | ACTFORE publicly advertises per-engagement customizations |
| Spreadsheet track (profile → layout fix → column mapping → repair) | Breach data often arrives as large exports from HR, payroll, patient, student and customer systems; Excel damage (lost zeros, serial dates, scientific notation) silently corrupts identifiers | General data-quality practice; Microsoft documentation on Excel's 15-digit precision limit and date serials |
| ML column-type classifier | Client headers are inconsistent or meaningless ("ID", "Column7"); value patterns reveal what a column holds | Standard semantic type detection approach (feature-based column classification) |
| Free-text PII scan in notes columns | Sensitive data hides in comment fields | General PII discovery practice |
| FERPA flag | Education records carry federal privacy obligations for institutions | U.S. Department of Education, FERPA (20 U.S.C. § 1232g; 34 CFR Part 99) |
| DuckDB system of record + versioned schema | Downstream teams need a stable, queryable handoff | General data-engineering practice |
| Excel workbook with formulas, macros and a formula cross-check | Analysts and reviewers work in Excel; an independent Excel check validates the Python rules | General QA practice (independent verification) |
| Local-LLM text-to-SQL with a guard and evaluation | Lets non-SQL users query results without sending data off-machine | ACTFORE publicly markets AI-led, on-premise processing |
| Offline mode | Sensitive data is often processed on-prem | ACTFORE publicly markets on-premise/on-shore processing |

Sources for the README (agent: confirm each URL resolves before publishing; replace any that moved):
- https://actfore.com/incident-response-services/data-mining/
- https://www.ncsl.org/technology-and-communication/security-breach-notification-laws
- https://www.ssa.gov/employer/randomizationfaqs.html
- https://pe.usps.com/text/pub28/welcome.htm
- https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.pdf
- https://studentprivacy.ed.gov/ferpa
- https://learn.microsoft.com/en-us/office/troubleshoot/excel/long-numbers-incorrectly-in-excel
- https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/minimum-necessary-requirement/index.html
