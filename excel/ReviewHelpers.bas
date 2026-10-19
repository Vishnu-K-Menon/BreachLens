Attribute VB_Name = "ReviewHelpers"
' BreachLens review workbook macros (EXCEL_WORKBOOK.md, ADR-051/068). SYNTHETIC DATA.
' Buttons on the Review_Queue sheet call these two macros. No network access, no
' external references; both work on the Excel Table "tblReview".
Option Explicit

Private Const QUEUE_SHEET As String = "Review_Queue"
Private Const QUEUE_TABLE As String = "tblReview"

Private Function ReviewTable() As ListObject
    Set ReviewTable = ThisWorkbook.Worksheets(QUEUE_SHEET).ListObjects(QUEUE_TABLE)
End Function

' Show only the items whose review_status is PENDING; a second click shows all rows again.
Public Sub ShowPendingOnly()
    On Error GoTo Failed
    Dim lo As ListObject
    Dim col As Long
    Set lo = ReviewTable()
    col = lo.ListColumns("review_status").Index
    If Not lo.ShowAutoFilter Then lo.ShowAutoFilter = True
    If lo.AutoFilter.Filters(col).On Then
        lo.Range.AutoFilter Field:=col
    Else
        lo.Range.AutoFilter Field:=col, Criteria1:="PENDING"
    End If
    Exit Sub
Failed:
    MsgBox "ShowPendingOnly failed: " & Err.Description, vbExclamation, "BreachLens"
End Sub

' Write every row whose review_status is not PENDING to review_decisions_<RunId>.csv
' next to this workbook (ids, statuses and the reviewer's own notes only).
Public Sub ExportDecisions()
    On Error GoTo Failed
    Dim lo As ListObject
    Dim cols As Variant
    Dim idx() As Long
    Dim r As ListRow
    Dim outPath As String
    Dim fileNo As Integer
    Dim i As Long
    Dim written As Long
    Dim rec As String
    Dim isOpen As Boolean

    If ThisWorkbook.Path = "" Then
        MsgBox "Save the workbook first; the CSV is written next to it.", vbExclamation, "BreachLens"
        Exit Sub
    End If
    Set lo = ReviewTable()
    cols = Array("item_id", "item_type", "review_status", "reviewer_note", "reviewed_by", "reviewed_at")
    ReDim idx(LBound(cols) To UBound(cols))
    For i = LBound(cols) To UBound(cols)
        idx(i) = lo.ListColumns(cols(i)).Index
    Next i

    outPath = ThisWorkbook.Path & Application.PathSeparator & "review_decisions_" & _
        CStr(ThisWorkbook.Names("RunId").RefersToRange.Value) & ".csv"
    fileNo = FreeFile
    Open outPath For Output As #fileNo
    isOpen = True
    Print #fileNo, Join(cols, ",")
    For Each r In lo.ListRows
        If CStr(r.Range.Cells(1, idx(2)).Value) <> "PENDING" Then
            rec = ""
            For i = LBound(cols) To UBound(cols)
                If i > LBound(cols) Then rec = rec & ","
                rec = rec & CsvField(r.Range.Cells(1, idx(i)).Value)
            Next i
            Print #fileNo, rec
            written = written + 1
        End If
    Next r
    Close #fileNo
    isOpen = False
    MsgBox written & " decision(s) written to" & vbCrLf & outPath, vbInformation, "BreachLens"
    Exit Sub
Failed:
    If isOpen Then Close #fileNo
    MsgBox "ExportDecisions failed: " & Err.Description, vbExclamation, "BreachLens"
End Sub

Private Function CsvField(ByVal v As Variant) As String
    Dim s As String
    If IsDate(v) And VarType(v) = vbDate Then
        s = Format$(v, "yyyy-mm-dd hh:nn:ss")
    Else
        s = CStr(v)
    End If
    If InStr(s, ",") > 0 Or InStr(s, """") > 0 Or InStr(s, vbLf) > 0 Or InStr(s, vbCr) > 0 Then
        s = """" & Replace(s, """", """""") & """"
    End If
    CsvField = s
End Function
