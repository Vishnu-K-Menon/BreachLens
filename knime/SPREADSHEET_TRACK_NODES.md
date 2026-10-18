# Spreadsheet track in native KNIME nodes: reader → layout → repair

This is the M3 reference for rebuilding the first three spreadsheet-track steps
(`sheets/reader.py`, `layout.py`, `repair.py`) with built-in KNIME nodes (KNIME Analytics
Platform 5.x), without Python. The M7 guide (`docs/KNIME_GUIDE.md`) will build the full
workflow on top of this. Column mapping (rules + ML) stays in Python, because the
classifier runs there.

Input: the synthetic files in `data/raw/corpus_v1/docs/sheets/`. SYNTHETIC DATA. The
rules quoted below come from `config/sheets.yaml`, `config/rules.yaml` and
`config/header_aliases.yaml`. Keep the two in sync.

## 1. Reader

| file | node | settings |
|---|---|---|
| `.xlsx` / `.xls` | **Excel Reader** | *Read from* each sheet (or loop with **Read Excel Sheet Names** + **Table Row To Variable Loop Start**); *Table specification*: **no column header** (header detection happens in step 2); *Advanced*: tick **Read hidden rows**, tick **Add row ID as column** (= Excel row number for provenance), **Replace empty strings with missing values** off; *Formula cells*: read cached values; *Error cells*: **Insert error pattern** `#N/A` |
| `.csv` | **CSV Reader** | *Autodetect format* (delimiter `;` / `,` / tab / `|`); *Encoding*: **Windows-1252** when UTF-8 shows `�` (the payroll export is cp1252); *Comment char* `#` (skips the synthetic notice); *Has column header* off; *Transfer all columns as String* (keeps ZIP leading zeros and long IDs exact) |

Notes:
- The Excel Reader's *Read hidden rows* keeps P29 rows. To flag them, use a **Java
  Snippet** that reads `.hidden` through Apache POI, or carry the hidden row numbers in
  from the Python `file_profile` table (**CSV Reader** + **Joiner** on the row number).
  No built-in node exposes row visibility.
- The `.xls` creation date (`doc_date`) is not available in native nodes. Take it from
  the Python `inventory` table.

## 2. Layout (header row, merged headers, title/total/blank rows)

1. **Row Filter** (*Exclude rows by attribute value*: all columns missing) drops blank
   rows.
2. Header row: a **Column Expressions** node computes, per row, the share of string
   cells and of numeric/date cells. A **Row Filter** then keeps the first row (within
   the first 15) with string share ≥ 0.60 and numeric share ≤ 0.20 whose next 3 rows look
   like data. Store its row number as a flow variable (**Table Row To Variable**).
3. Merged 2-row header (P28): when the row above the header is a group row (e.g.
   `Employee | | Address | |`), **Missing Value** (*Previous value*, transposed with
   **Transpose**) fills the merged cells to the right. A **String Manipulation**
   `join($group$, " ", $header$)` then gives `Employee SSN`.
4. **Row Filter** by row number drops everything up to the header row (P27 title rows).
   **Extract Column Header** + **Insert Column Header** (or **Column Rename (Regex)**)
   promotes the header.
5. Total row (P30): **Rule-based Row Filter**
   `$Col0$ MATCHES "(?i)^(total|grand total|count|sum)\b.*" => FALSE`, plus
   `TRUE => TRUE`.
6. Skip non-data sheets (the `Notes` sheet): **Empty Table Switch** after the filters,
   or a **Row Filter** that requires at least 2 data rows and 2 columns.

## 3. Repair (per mapped column)

Join the column labels from the Python `column_mapping` table first (**Joiner** on
doc_id/sheet/col_idx), or hard-code them for a fixed file. Then:

| case | node(s) | expression / setting | reason code |
|---|---|---|---|
| Excel errors (P43) | **String Replacer** (all string columns, whole-word) | `#N/A`, `#REF!`, `#VALUE!`, `#DIV/0!`, `#NAME?`, `#NULL!`, `#NUM!` → missing; a **Column Expressions** flag `XL_ERROR_VALUE` per row before replacing | XL_ERROR_VALUE |
| ZIP leading zero (P31) | **Column Expressions** | `if (length(column("Zip")) == 4 && arrayContains(["CT","MA","ME","NH","NJ","PR","RI","VT","VI"], column("State"))) "0" + column("Zip") else column("Zip")` | XL_ZIP_LEADING_ZERO_RESTORED |
| date serials (P32) | **Rule Engine** to detect `^\d{4,5}$` in a DOB column, then **Math Formula** `$serial$ - 25569` (days since 1970-01-01) → **Number to String** → **String to Date&Time** (epoch days). Other values: **String to Date&Time** with the formats `MM/dd/yyyy`, `yyyy-MM-dd`, `dd MMM yyyy` (one node per format, **Missing Value** merge) | 1899-12-30 epoch | XL_DATE_SERIAL_CONVERTED |
| ambiguous day/month | **Rule Engine** `$a$ <= 12 AND $b$ <= 12 AND $a$ != $b$ => "DOB_AMBIGUOUS_FORMAT"` on the split parts; use the column majority (**GroupBy**) for the order | | DOB_AMBIGUOUS_FORMAT |
| precision loss (P33) | **Rule Engine** on the card column read as string: `$Card$ MATCHES "^\d(\.\d+)?[Ee]\+?\d+$" OR $Card$ MATCHES "^\d{16,}$" AND <cell was numeric>` | the Excel Reader's *column type* tells numeric from text cells | XL_NUMBER_PRECISION_LOST |
| pre-masked (P34) | **Rule Engine** `$SSN$ MATCHES "^[Xx*#]{3}-[Xx*#]{2}-\d{4}$" => "PREMASKED_VALUE"` (same for cards: `^([Xx*#]{2,}[- ]?)+\d{2,4}$`) | | PREMASKED_VALUE |
| SSN as 8-digit number (P44) | **Column Expressions** `if (length(column("SSN")) == 8 && regexMatcher(column("SSN"), "\\d+")) padLeft(column("SSN"), 9, "0") else column("SSN")` | | XL_SSN_ZERO_PADDED |
| `City, ST 12345` (customer cards) | **Regex Split** `^\s*(.*?),\s*([A-Za-z]{2})\s+(\d{3,5}(?:-\d{4})?)\s*$` → City, State, ZIP | | |
| duplicate rows (P42) | **Duplicate Row Filter** (all columns; *keep first*; *add column showing duplicates*) | | ROW_DUPLICATE_IN_FILE |
| wide dependents (P37) | **Unpivoting** (*value columns*: regex `Dep\d+_.*`) → **Regex Split** on the column name `Dep(\d+)_(.*)` → **Pivoting** back to one row per (row, group) | | |

## Check against Python

Compare the KNIME output with the Python stage on the same file. Run
`python -m breachlens.evaluate.sheets` and compare row counts, the dropped title/total
rows and the codes per row. The planted-case table there lists the expected outcome for
P27–P44.
