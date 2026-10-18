import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from breachlens.ingest import ocr


def _page_with_box_and_text() -> Image.Image:
    img = Image.new("L", (900, 300), 255)
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 880, 280], outline=0, width=3)  # form box border
    font = ImageFont.load_default()
    d.text((60, 120), "2461 BRYANT TERRACE", fill=0, font=font)
    return img


def test_binarize_drops_light_gray():
    img = Image.fromarray(np.array([[219, 30, 150, 200]], dtype=np.uint8), mode="L")
    assert np.asarray(ocr.binarize(img, 160)).tolist() == [[255, 0, 0, 255]]


def test_remove_lines_erases_borders_but_keeps_text():
    img = _page_with_box_and_text()
    out = np.asarray(ocr.remove_lines(img, 80)) < 128
    assert not out[20, 100:800].any() and not out[100:200, 21].any()  # borders gone
    assert out[110:140, 55:200].any()  # text strokes kept


def test_estimate_skew_recovers_a_small_rotation():
    img = Image.new("L", (1200, 1200), 255)
    d = ImageDraw.Draw(img)
    for y in range(100, 1100, 40):  # text-like rows
        d.rectangle([100, y, 1100, y + 8], fill=0)
    tilted = img.rotate(-1.5, fillcolor=255)
    assert abs(ocr.estimate_skew(tilted) - 1.5) <= 0.3


@pytest.mark.tesseract
def test_ocr_reads_a_rendered_page(tmp_path):
    from reportlab.pdfgen import canvas

    path = tmp_path / "scan.pdf"
    c = canvas.Canvas(str(path), invariant=1)
    c.setFont("Courier", 12)
    c.drawString(72, 700, "MEMBER ID SVY097439533")
    c.save()
    toks = ocr.ocr_tokens(path, dpi=300, lang="eng", psm=11, binarize_threshold=160)
    assert "SVY097439533" in {t.text for t in toks}
    assert all(0 <= t.conf <= 1 for t in toks)
