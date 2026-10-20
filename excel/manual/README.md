# Excel cleanup (done by hand)
File: hr_roster_clean.xlsm (copy of hr_roster.xlsx)
- Unhid 3 hidden rows, unmerged the 2-row header, removed title, total and company rows
- Removed 1 duplicate with Remove Duplicates (56 people left)
- Formulas: TRIM/UPPER for names, TEXT(ZIP,"00000") for lost leading zeros,
  IF/OR to flag impossible SSNs (1 flagged), DATEDIF for age, XLOOKUP for state names
- PivotTable: people per state; COUNTIFS for review counts
- Macro `Format_Report` (recorded, then cleaned up and edited): highlights REVIEW rows, autofits,
  freezes the header, hides the full SSN column every time it runs (privacy by default)
  and shows a review count. Runs from a button on the Summary sheet.

![Roster](excel_roster.png)
![Summary](excel_summary.png)
