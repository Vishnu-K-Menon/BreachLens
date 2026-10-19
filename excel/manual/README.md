   # Excel cleanup (done by hand)
   File: hr_roster_clean.xlsm (copy of hr_roster.xlsx)
   - Unhid 3 hidden rows, unmerged the 2-row header, removed title, total and company rows
   - Removed 1 duplicate with Remove Duplicates (56 people left)
   - Formulas: TRIM/UPPER for names, TEXT(ZIP,"00000") for lost leading zeros,
     IF/OR to flag impossible SSNs (1 flagged), DATEDIF for age, XLOOKUP for state names
   - PivotTable: people per state; COUNTIFS for review counts
   - Macro FormatReport (recorded, then edited to show a review count), run from a button
   Time taken: __ min