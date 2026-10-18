import shutil

import pymupdf
from openpyxl import Workbook
from reportlab.pdfgen import canvas

from breachlens.ingest.inventory import build_inventory


def _text_pdf(path, text="WAGE AND TAX STATEMENT synthetic test page"):
    c = canvas.Canvas(str(path), invariant=1)
    c.drawString(72, 720, text)
    c.showPage()
    c.drawString(72, 720, text)
    c.save()


def _image_pdf(path):
    doc = pymupdf.open()
    page = doc.new_page()
    page.draw_rect(pymupdf.Rect(50, 50, 200, 120), color=(0, 0, 0), fill=(0, 0, 0))
    doc.save(path)


def test_inventory_rows(tmp_path):
    (tmp_path / "pdf").mkdir()
    (tmp_path / "sheets").mkdir()
    (tmp_path / ".ipynb_checkpoints").mkdir()
    _text_pdf(tmp_path / "pdf" / "a.pdf")
    shutil.copyfile(tmp_path / "pdf" / "a.pdf", tmp_path / "pdf" / "a_copy.pdf")
    _image_pdf(tmp_path / "pdf" / "scan.pdf")
    wb = Workbook()
    wb.create_sheet("Second")
    wb.save(tmp_path / "sheets" / "x.xlsx")
    (tmp_path / "sheets" / "y.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (tmp_path / ".ipynb_checkpoints" / "junk.csv").write_text("x", encoding="utf-8")
    inv = build_inventory(tmp_path).set_index("path")
    assert list(inv["doc_id"]) == ["D0001", "D0002", "D0003", "D0004", "D0005"]
    assert inv.loc["pdf/a.pdf", "pages"] == 2 and inv.loc["pdf/a.pdf", "has_text_layer"]
    assert not inv.loc["pdf/scan.pdf", "has_text_layer"]
    assert (
        inv.loc["pdf/a_copy.pdf", "is_exact_duplicate"]
        and not inv.loc["pdf/a.pdf", "is_exact_duplicate"]
    )
    assert inv.loc["sheets/x.xlsx", "sheets"] == 2 and inv.loc["sheets/y.csv", "file_kind"] == "CSV"
    assert inv.loc["pdf/a.pdf", "sha256"] == inv.loc["pdf/a_copy.pdf", "sha256"]
