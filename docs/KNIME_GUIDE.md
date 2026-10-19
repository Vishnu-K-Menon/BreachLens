# KNIME_GUIDE.md: clean the payroll export in KNIME (built by hand)

> **Scope (ADR-068).** One beginner workflow for the spreadsheet track, built **by hand**
> in **KNIME Analytics Platform 5.12** (new UI). Built-in nodes only: no Python Script
> nodes, no extensions. The agent wrote this guide but did not build or export the
> workflow. SYNTHETIC DATA: every name and number in the file was generated.
>
> **Time:** about 40 minutes (5 to set up, about 2–3 per node).

**Input:** `data/raw/corpus_v1/docs/sheets/payroll_export.csv`. It is the same file the
notebook cleans, which makes it the best first file:
- one table, with no header detection, merged cells or hidden rows
- real cleaning work:
  - a `# SYNTHETIC - NOT REAL` first line
  - `;` delimiter and decimal commas (`2972,82`)
  - Latin-1 accents (Muñoz, José)
  - **8 SSNs stored with only 8 digits** (their leading zero was lost, planted case P44)
  - `#N/A` text in `Dept`
  - **80 rows = 40 employees × 2 pay dates**

**Output:** `data/output/knime/payroll_clean.xlsx` (git-ignored) with 3 sheets:
- `employees`: 40 rows
- `needs_review`: 2 rows
- `by_state`: 8 rows

The numbers under every "You should see" below were computed with pandas, which mirrors
each node on the same file. `tests/unit/test_knime_guide.py` re-checks them.

## Privacy rule for this workflow (read first)
Built-in nodes cannot mask a value while reading a file. So the **CSV Reader (node 1) is
the only node that ever holds full SSNs**:
- its dialog preview
- its output table
- the bottom panel when node 1 is selected

The workflow therefore masks the SSN in the **very next node**. From node 2 on, no table
contains a full SSN, and node 11 proves it. While you work:
- Don't open node 1's output table, and don't screenshot its dialog.
- After executing node 1, click node 2 before you look at the bottom panel.
- The two bank columns are switched off inside the reader (step 1), so they never enter
  KNIME at all.
- Reset the workflow before you export it (end of this guide), so no data is saved
  inside the `.knwf`.

## Before you start (5 min)
1. Start KNIME 5.12 → **Home** → **Create workflow** in your Local space → name it
   `breachlens_sheet_cleanup`.
2. **Adding a node:** type its name in the search box of the **Nodes** panel (left side),
   then drag it onto the canvas. Faster: drag from a node's output port (the triangle on
   its right) into empty canvas and type the name in the quick-add box that appears.
   That inserts the node and connects it.
3. **Configuring a node:** select it. Modern nodes show their settings in the right-hand
   panel. A few older nodes (String Manipulation, Rule Engine) open a dialog window:
   double-click them.
4. **Running a node:** **Execute** (the play button on the node, or F7). The traffic
   light turns green. The bottom panel shows the output table of the selected node.

The settings below name only what you change; leave everything else at the default.

## The workflow

```
1 CSV Reader ─┬─ 2 mask SSN ─ 5 Column Renamer ─ 6 last_name ─ 7 given_names ─ 8 Rule Engine
              │     ─ 9 String to Date&Time ─ 10 Duplicate Row Filter ─┬─ 11 Row Filter (SSN check, 0 rows)
              │                                                       ├─ 12 Row Filter (needs_review) ─┐
              │                                                       ├─ 13 GroupBy (by_state) ────────┤
              │                                                       └──────────────────────────── 14 Excel Writer
              └─ 3 SSN → digit count ─ 4 GroupBy (8 vs 9 digits)
```

---

### 1. CSV Reader: read the file
- **Where:** Nodes panel → search `CSV Reader` (IO › Read).
- **Settings:**
  - **File:** browse → *Local file system* →
    `D:\git\BreachLens\data\raw\corpus_v1\docs\sheets\payroll_export.csv`.
  - **Format:**
    - **Column delimiter** `;`
    - **Quote character** `"`
    - **Decimal separator** `,`
    - **Thousands separator** empty
  - **First row contains column names:** ticked.
  - **Skip first lines of file:** ticked, `1`. This skips `# SYNTHETIC - NOT REAL`.
    Leave **Comment line character** as it is: it only acts on lines that *start* with
    it, so the `SS#` header is safe.
  - **Encoding:** `ISO-8859-1`. For this file it is identical to Windows-1252. UTF-8
    would turn `Muñoz` into `Mu�oz`.
  - **Table Transformation** (bottom of the settings):
    - Untick **Include in output** for `Bank Routing` and `Account No`.
    - Set the **Column type** of `Emp No`, `SS#`, `Pay Date`, `Zip` and every other text
      column to **String**. A detected Integer would drop the ZIP's leading zero
      (`07102` → `7102`).
    - `Gross Pay` and `Net Pay` stay **Number (Float)**.
- **You should see** (don't open it, see the privacy rule): **80 rows × 11 columns**:
  Emp No, Employee Name, SS#, Pay Date, Gross Pay, Net Pay, Dept, Street, City, State,
  Zip.

### 2. String Manipulation: pad the SSN to 9 digits, then mask it
- **Where:** `String Manipulation` (Manipulation › Column › Convert & Replace). Connect
  it to node 1, then double-click it.
- **Settings:**
  - **Expression** (double-click `SS#` in the column list to insert it):
    ```
    join("***-**-", substr(padLeft($SS#$, 9, "0"), 5, 4))
    ```
    - `padLeft(..., 9, "0")` restores the lost leading zero first, like the notebook's
      `zfill(9)`.
    - `substr(..., 5, 4)` keeps the last 4 digits. The start index is 0-based.
  - **Replace column:** `SS#`. Do not append: the raw column must disappear here.
- **You should see:** 80 rows × 11 columns. `SS#` now reads `***-**-2648`,
  `***-**-3751`, `***-**-2089` in the first three rows. From here on, no table holds a
  full SSN.

### 3. String Manipulation: SSN → its digit count (side branch)
This lets you count the short SSNs without ever showing one.
- **Where:** a second `String Manipulation`, connected to **node 1's** output (not
  node 2's).
- **Settings:**
  - **Expression:** `string(length($SS#$))`
  - **Replace column:** `SS#`
- **You should see:** 80 rows. `SS#` now holds `9` or `8`, never a number.

### 4. GroupBy: how many SSNs have 8 digits?
- **Where:** `GroupBy` (Manipulation › Row › Transform), after node 3.
- **Settings:**
  - **Groups → Group columns:** `SS#`.
  - **Manual Aggregation → Add manual:** `Emp No`, method **Count**.
- **You should see:** **2 rows**: `9` → **72**, `8` → **8**. Those 8 rows belong to
  4 employees (each appears in both pay periods).

### 5. Column Renamer: snake_case names
- **Where:** `Column Renamer` (Manipulation › Column › Convert & Replace), after **node 2**.
- **Settings:** **Add column** once per column; **New name**:

  | column | new name |
  |---|---|
  | Emp No | `emp_no` |
  | Employee Name | `employee_name` |
  | SS# | `ssn_masked` |
  | Pay Date | `pay_date` |
  | Gross Pay | `gross_pay` |
  | Net Pay | `net_pay` |
  | Dept | `dept` |
  | Street | `street` |
  | City | `city` |
  | State | `state` |
  | Zip | `zip` |

- **You should see:** 80 rows, the 11 new names.

### 6. String Manipulation: `last_name`
- **Settings:**
  - **Expression:**
    ```
    upperCase(strip(substr($employee_name$, 0, indexOf($employee_name$, ","))))
    ```
  - **Append a new column:** `last_name`
- **You should see:** row 1 `Fowler, Edwin` → `FOWLER`. Accents survive: `Muñoz, José`
  → `MUÑOZ`. Suffixes stay in the last name (`YOUNG JR`, `TUCKER III`, `VAN DYKE II`).
  The notebook splits them out; that's optional here.

### 7. String Manipulation: `given_names`
- **Settings:**
  - **Expression:**
    ```
    upperCase(strip(substr($employee_name$, indexOf($employee_name$, ",") + 1)))
    ```
  - **Append a new column:** `given_names`
- **You should see:** `EDWIN`, `ANTHONY`, `LEE K` in the first three rows; `JOSÉ` for
  Muñoz.

  Tip: copy node 6 (Ctrl+C / Ctrl+V) and change only the expression and the column
  name.

### 8. Rule Engine: `#N/A` and department names
- **Where:** `Rule Engine` (Manipulation › Row › Other). Double-click it.
- **Settings:**
  - **Expression** (one rule per line; the first match wins):
    ```
    $dept$ = "#N/A" => "UNKNOWN"
    $dept$ = "OPS" => "Operations"
    $dept$ = "SLS" => "Sales"
    $dept$ = "FIN" => "Finance"
    $dept$ = "IT" => "IT"
    $dept$ = "CS" => "Customer Service"
    $dept$ = "WHS" => "Warehouse"
    TRUE => $dept$
    ```
  - **Replace column:** `dept`
- **You should see:** 80 rows. `dept` counts:

  | dept | rows |
  |---|---|
  | IT | 15 |
  | Customer Service | 15 |
  | Operations | 14 |
  | Warehouse | 12 |
  | Sales | 10 |
  | Finance | 8 |
  | **UNKNOWN** | **6** (4 on 09/15, 2 on 09/30) |

  KNIME reads `#N/A` as text. pandas turned it into a missing value by default, which is
  why the notebook found 0 `#N/A` strings.

### 9. String to Date&Time: `pay_date` as a date
- **Where:** `String to Date&Time` (search the name).
- **Settings:**
  - **String columns:** only `pay_date`.
  - **Output type:** *Local date*.
  - **Input format:** `MM/dd/yyyy`.
  - **Output columns:** replace.
- **You should see:** `pay_date` shows `2026-09-15` / `2026-09-30`, 40 rows each.

### 10. Duplicate Row Filter: one row per employee, newest pay date
- **Where:** `Duplicate Row Filter` (Manipulation › Row › Filter).
- **Settings:**
  - **Choose columns for duplicates detection:** only `emp_no`.
  - **Duplicate rows:** *Remove duplicate rows*.
  - **Row chosen in case of duplicate:** *Maximum of* → `pay_date`.
- **You should see:** **80 → 40 rows**, every `pay_date` = `2026-09-30`. Row 1 is
  emp_no `111280`, FOWLER. This is the notebook's
  `sort_values("Pay Date").drop_duplicates("Emp No", keep="last")`.

### 11. Row Filter: prove that no full SSN is left
- **Where:** `Row Filter` (Manipulation › Row › Filter), after node 10.
- **Settings:**
  - **Filter column:** `ssn_masked`
  - **Operator:** *Matches regex*, **Pattern** `.*[0-9]{5,}.*` (5 or more digits in a row)
  - **Filter behavior:** *Output matching rows*
- **You should see:** **0 rows**. Every value is `***-**-dddd`.

### 12. Row Filter: the review list
- **Where:** a second `Row Filter`, after node 10.
- **Settings:**
  - **Filter column:** `dept`
  - **Operator:** `=` (equals), value `UNKNOWN`
  - **Filter behavior:** *Output matching rows*
- **You should see:** **2 rows**: emp_no `503447` (HUFF, VA) and `955744` (BRÜCKNER, PA).

### 13. GroupBy: employees and gross pay by state
- **Where:** `GroupBy`, after node 10.
- **Settings:**
  - **Groups → Group columns:** `state`.
  - **Manual Aggregation:** `emp_no` → **Count**, and `gross_pay` → **Sum**.
  - **Column naming:** *Aggregation method (column name)*.
- **You should see:** **8 rows**:

  | state | Count(emp_no) | Sum(gross_pay) |
  |---|---|---|
  | CA | 6 | 27,172.28 |
  | FL | 6 | 28,516.22 |
  | MA | 2 | 7,173.99 |
  | NJ | 2 | 10,473.20 |
  | NY | 6 | 24,132.46 |
  | PA | 6 | 27,873.69 |
  | TX | 6 | 30,774.03 |
  | VA | 6 | 25,580.96 |

  Total: 40 employees, 181,696.83. The NJ ZIPs read `07102` and `08608`: the leading
  zero is still there because `zip` is a String.

### 14. Excel Writer: 3 sheets
- **Where:** `Excel Writer` (IO › Write).
- **Add input ports:** click **+** on the node (**Sheet Input Ports**) twice, so it has
  3 table inputs. Connect them:
  - node 10 → port 1
  - node 12 → port 2
  - node 13 → port 3
- **Settings:**
  - **File:** *Local file system* →
    `D:\git\BreachLens\data\output\knime\payroll_clean.xlsx`. Tick **Create missing
    folders** if shown. **If exists:** overwrite.
  - **Sheet name:** `employees`, `needs_review`, `by_state`.
  - **Write column headers:** ticked. **Write row key:** unticked.
- **You should see:** the file opens in Excel with 40 / 2 / 8 data rows, and `ssn_masked`
  as `***-**-dddd`.

---

## Finish: export and screenshot (3 min)
1. **Reset first:** select all nodes (Ctrl+A) → right-click → **Reset**. Every traffic light turns red/yellow, and no table data stays in the
   workflow.
2. **Save:** Ctrl+S.
3. **Export:** in the **Space explorer** (left), right-click `breachlens_sheet_cleanup` →
   **Export** → save as `D:\git\BreachLens\knime\breachlens_sheet_cleanup.knwf`. If the
   export asks about data, choose to exclude it.
4. **Screenshot:** execute all once more (so the lights are green), arrange the canvas,
   **Win+Shift+S** → select the canvas → paste into Paint → save as
   `D:\git\BreachLens\knime\workflow.png`. Make sure no table panel showing node 1 is in
   the picture.
5. Commit both files yourself. `knime/manual/` stays yours too (AGENTS.md).

## pandas vs KNIME (same file, same steps)

| step | notebook (pandas) | this workflow (KNIME) | BreachLens pipeline |
|---|---|---|---|
| read | `read_csv(sep=";", encoding="latin-1", skiprows=1, dtype=str)` | CSV Reader: `;`, ISO-8859-1, skip 1 line, String types | `sheets/reader.py` detects encoding and delimiter (`CSV_ENCODING_DETECTED`) |
| rows read | 80 | 80 | 80 mentions |
| short SSNs (8 digits) | 8 (`str.len()`) | 8 (nodes 3–4, no SSN shown) | 8 flagged `XL_SSN_ZERO_PADDED` |
| SSN fix | `zfill(9)` | `padLeft($SS#$, 9, "0")` | zero-padded in `sheets/repair.py` |
| SSN shown as | `***` + last 4 (`mask()`) | `***-**-` + last 4 | `ssn_masked` `***-**-` + last 4, plus an HMAC `ssn_key` |
| `#N/A` in Dept | read as missing (0 left as text) | 6 rows → `UNKNOWN` | `XL_ERROR_VALUE` on 6 mentions (cell nulled) |
| decimal commas | `str.replace(",", ".")` | Decimal separator `,` | parsed in repair |
| one row per employee | `drop_duplicates("Emp No", keep="last")` → **40** | Duplicate Row Filter, max `pay_date` → **40** | entity resolution → **40** `person_id`s |
| by state | — | CA 6, FL 6, MA 2, NJ 2, NY 6, PA 6, TX 6, VA 6 | the same 8 states and counts |
| needs review | — | 2 employees (dept `UNKNOWN`) | 43 of 80 mentions REVIEW (row and column codes, ADR-059) |

**What the comparison shows:**
- All three tools agree on the basic counts: 80 rows, 8 short SSNs, 40 people.
- They differ in what counts as "review". KNIME flags only the unknown department. The
  pipeline also raises the column-mapping and address codes of VALIDATION_RULES.md.
