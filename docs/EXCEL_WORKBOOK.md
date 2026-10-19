# EXCEL_WORKBOOK.md — Review workbook specification

> **Scope (ADR-051, BreachLens Lite):** build only `Summary`, `Mentions`, `Review_Queue`,
> `People`, `Notification_List`, `Excluded` and `About`, and only the macros
> `ShowPendingOnly` and `ExportDecisions`. `State_View`, `Formula_Checks`,
> `Column_Mappings`, `File_Profiles`, `MarkSelectedAccepted` and `RefreshHighlights` are
> dropped; their specs below are kept for reference only. `RunDate` = `as_of_date`.
>
> **As built (M7, ADR-068):**
> - `breachlens report` writes the workbook from the DuckDB database to
>   `data/output/<run_id>/`. It is an `.xlsx` until `excel/vbaProject.bin` exists.
> - Summary rows are `section | item | excel | python | match`.
> - `Review_Queue` adds the reviewer columns `review_status` (dropdown PENDING /
>   ACCEPTED / REJECTED / RESOLVED), `reviewer_note`, `reviewed_by`, `reviewed_at` and a
>   `go` link.
> - The Summary formulas below are examples; the real ones are in
>   `report/excel_writer.py` (`summary_rows`).

Output: `breachlens_<run_id>.xlsm`, written with **XlsxWriter**
(`Workbook(path, {"use_future_functions": True})` so `XLOOKUP`, `FILTER`, `UNIQUE`,
`SORT` and `IFS` get the required `_xlfn.` prefixes). openpyxl is used only to **read**
reviewer edits back.

Every data block is an **Excel Table** (`worksheet.add_table`) with a stable name, so
formulas use structured references (`tblPeople[state]`). ZIP and ID-like columns use
the text format `@`.

## Sheets
| Sheet | Table name | Content | Excel skills shown |
|---|---|---|---|
| `Summary` | — | KPI block + by-state block + by-field error block | `COUNTIFS`, `SUMPRODUCT`, `IFERROR`, `ROUND`, named ranges (`RunDate` = `as_of_date`, `RunId`) |
| `Mentions` | `tblMentions` | full mention schema | Formula-based conditional formatting, freeze panes, autofilter |
| `Review_Queue` | `tblReview` | issues to review + macro buttons | Data validation dropdown, `HYPERLINK` to source, macros |
| `People` | `tblPeople` | golden records | Calculated columns |
| `Notification_List` | `tblNotify` | one row per person, by jurisdiction | `XLOOKUP` (+ `INDEX/MATCH` fallback column), `IF(AND(...))`, `TEXTJOIN` |
| `State_View` | — | pick a state from a dropdown → live list | `FILTER`, `SORT`, `UNIQUE`, `LET` (dynamic arrays via `write_dynamic_array_formula`) |
| `Formula_Checks` | `tblChecks` | Excel re-implementation of 6 Python rules | `LEN`, `ISNUMBER(MATCH())`, `RunDate`, `DATEDIF`, `AND/OR`, agreement % |
| `Column_Mappings` | `tblColMap` | spreadsheet column mapping + confidence | Data bars on `ml_proba` |
| `File_Profiles` | `tblFiles` | per-file / per-column quality | Color scales on null % |
| `Excluded` | `tblExcluded` | ORG names, EIN/NPI/TIN | — |
| `QC_Summary` | `tblQC` | per-field present / FAIL / REVIEW rates | `COUNTIFS` over `tblMentions` |
| `About` | — | synthetic-data notice, schema version, "not legal advice", how to enable macros | — |

`Review_Queue` items (ADR-062): one item per **column** for column-level warnings
(COL_MAPPING_LOW_CONF, COL_MAPPING_ML_OVERRIDE, COL_UNMAPPED_SENSITIVE), with an
`affected_rows` count of the mentions that used the column. Row-level reason codes stay
one item per mention. A column decision is recorded in `config/review_overrides.yaml`
(ADR-061) and applied on the next run.

`LET` parameter names must carry the `_xlpm.` prefix in the written formula (e.g.
`=LET(_xlpm.st,$B$1,…)`); `use_future_functions` does not add it (ADR-041).
`tblPeople[notify_required]` and `tblPeople[medical_exposed]` are real `people`
columns (ADR-028).

## Required formulas (examples; adjust the references to the real table names)
**Summary**
```
People total           =ROWS(tblPeople[person_id])
Mentions total         =ROWS(tblMentions[mention_id])
Collapse ratio         =ROUND(B3/B2,2)
To notify              =COUNTIFS(tblPeople[notify_required],TRUE)
By state (row per st.) =COUNTIFS(tblPeople[state],$A10,tblPeople[notify_required],TRUE)
SSN+Medical by state   =SUMPRODUCT((tblPeople[state]=$A10)*(tblPeople[ssn_exposed]=TRUE)*(tblPeople[medical_exposed]=TRUE))
Field FAIL rate        =IFERROR(COUNTIFS(tblMentions[qc_reasons],"*"&$A20&"*")/ROWS(tblMentions[mention_id]),0)
```
**Notification_List**
```
elements (lookup)      =XLOOKUP([@person_id],tblPeople[person_id],tblPeople[elements_exposed],"NOT FOUND")
elements (fallback)    =INDEX(tblPeople[elements_exposed],MATCH([@person_id],tblPeople[person_id],0))
status                 =IF(AND([@notify_required],[@address_status]<>"INVALID"),"READY",IF([@notify_required],"NEEDS ADDRESS","NO NOTICE"))
```
**State_View** (B1 = state dropdown)
```
=SORT(FILTER(tblNotify[[last_name]:[elements_exposed]],tblNotify[jurisdiction]=$B$1,"none"),1)
```
**Formula_Checks**: one row per mention, 6 check columns, each with a matching
Python result column written as a value. Every date check uses the `RunDate` named
range, never `TODAY()`, so Excel agrees with Python whenever the file is opened
(ADR-036):
```
zip_ok      =LEN([@zip5])=5
dob_ok      =AND(ISNUMBER([@dob_date]),[@dob_date]<=RunDate,DATEDIF([@dob_date],RunDate,"y")<=120)
suffix_ok   =OR([@name_suffix]="",ISNUMBER(MATCH([@name_suffix],ValidSuffixes,0)))
dl_state_ok =OR([@dl_present]=FALSE,LEN([@dl_state])=2)
state_ok    =ISNUMBER(MATCH([@state],StateCodes,0))
minor_ok    =[@is_minor]=(DATEDIF([@dob_date],RunDate,"y")<18)
agree       =AND(zip_ok=py_zip_ok, ...)   → Summary shows "Excel vs Python agreement: x%"
```

## Conditional formatting (formula type, applied to `tblMentions`)
- Red fill: `=ISNUMBER(SEARCH("ERROR_FIELD_CODE",$qc_reasons))` per field column (the
  writer generates one rule per field → code mapping).
- Yellow fill: the REVIEW codes, the same way.
- Green fill on the address columns: `=$address_status="VERIFIED"`.
- Whole row grey: `=$review_status="REJECTED"`.

## Macros (`excel/ReviewHelpers.bas`)
| Macro | Button (on Review_Queue) | Behaviour |
|---|---|---|
| `ShowPendingOnly` | "Show pending" | AutoFilter `tblReview[review_status]` = PENDING; a second click clears it |
| `MarkSelectedAccepted` | "Accept selected" | Selected rows → ACCEPTED, `reviewed_by = Application.UserName`, `reviewed_at = Now` |
| `RefreshHighlights` | "Refresh colors" | Re-applies row fills from `qc_status` / `review_status` after edits |
| `ExportDecisions` | "Export decisions" | Writes non-PENDING rows to `review_decisions_<RunId>.csv` next to the workbook (read by `breachlens apply-review`) |

Requirements: `Option Explicit`, error handling with a message box, no network access,
no external references.

### One-time build of `vbaProject.bin` (human step, Windows + Excel desktop)
The agent wrote `excel/ReviewHelpers.bas`. Then:
1. Start Excel → **Blank workbook**.
2. Press **Alt+F11** (VBA editor) → **File › Import File…** →
   `D:\git\BreachLens\excel\ReviewHelpers.bas`. The module `ReviewHelpers` appears
   under *Modules*.
3. Close the VBA editor (**Alt+Q**).
4. **File › Save As › Browse** → folder `D:\git\BreachLens\excel`, **Save as type**
   *Excel Macro-Enabled Workbook (\*.xlsm)*, file name `macro_shell.xlsm` → **Save**.
   Close Excel.
5. Extract the binary (PowerShell, from the repo root; `vba_extract.py` ships with
   XlsxWriter and writes into the current folder):
   ```powershell
   cd D:\git\BreachLens\excel
   ..\.venv\Scripts\python.exe ..\.venv\Scriptsba_extract.py macro_shell.xlsm
   cd ..
   ```
   This writes `excelbaProject.bin`. Commit it. `macro_shell.xlsm` is only a
   carrier and does not need committing.
6. `.\.venv\Scripts\python.exe -m breachlens report` now writes
   `breachlens_<run_id>.xlsm`. It embeds the binary with `add_vba_project` and puts
   "Show pending" / "Export decisions" buttons on `Review_Queue` (`insert_button`).
   Open the file, click **Enable Content**, and try both buttons.

"Trust access to the VBA project object model" is only needed for programmatic
imports, not for this manual one.

Note for the README: files downloaded from the internet open with macros blocked
(Mark of the Web). Right-click → Properties → Unblock.

## Recalculation and tests (`report/recalc.py`)
XlsxWriter writes formulas without cached results. For tests and screenshots, run
LibreOffice headless with a dedicated profile set to always recalculate on load
(ADR-041):
`soffice -env:UserInstallation=file:///<tmp>/lo_profile --headless --convert-to xlsx --outdir <tmp> <file>`
(needs LibreOffice ≥ 24.8 for `XLOOKUP`/`FILTER`/`SORT`/`UNIQUE`/`LET`). The profile's
`registrymodifications.xcu` sets the OOXML "recalculation on file load" option to
*always*. A separate profile also avoids the lock when the LibreOffice GUI is open. Then
read the values with openpyxl `data_only=True` and assert:
- no `#REF!`, `#NAME?`, `#VALUE!`, `#DIV/0!` anywhere
- Summary counts equal the Python counts
- Formula_Checks agreement = 100%

If LibreOffice is unavailable, skip those tests with a clear message.
