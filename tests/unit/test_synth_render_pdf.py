from pathlib import Path

import pymupdf
import pytest

from breachlens.synth.casting import cast_pdfs
from breachlens.synth.people import build_population, read_pool
from breachlens.synth.render_pdf import WATERMARK, render_pdf
from breachlens.synth.scanify import scanify
from breachlens.synth.settings import load_synth_settings

ROOT = Path(__file__).resolve().parents[2]
LABELS = {
    ("WAGE_STATEMENT", "A"): "Employee's social security number",
    ("WAGE_STATEMENT", "B"): "SOCIAL SECURITY NO.",
    ("HEALTH_CLAIM", "A"): "PATIENT'S NAME",
    ("HEALTH_CLAIM", "B"): "PATIENT NAME",
    ("NEW_HIRE_ID", "A"): "Legal name (Last, First, Middle)",
    ("NEW_HIRE_ID", "B"): "LAST NAME",
    ("EOB_LETTER", "A"): "Explanation of Benefits",
    ("EOB_LETTER", "B"): "EXPLANATION OF BENEFITS",
}


@pytest.fixture(scope="module")
def world():
    s = load_synth_settings(ROOT / "config")
    pop = build_population(s, read_pool(ROOT / "data" / "reference" / "address_pool.csv"))
    return s, pop, cast_pdfs(pop, s)


def test_casting_counts_and_scan_fraction(world):
    s, _, plans = world
    for doc_type, n in s.config.pdf.counts.items():
        assert sum(p.doc_type == doc_type for p in plans) == n
    assert sum(p.scan for p in plans) == round(s.config.pdf.scan.fraction * len(plans))


def test_every_type_and_variant_renders_with_watermark_and_labels(world, tmp_path):
    s, pop, plans = world
    for (doc_type, variant), label in LABELS.items():
        plan = next(p for p in plans if p.doc_type == doc_type and p.variant == variant)
        out = render_pdf(plan, pop, tmp_path, s.config.seed)
        with pymupdf.open(tmp_path / plan.doc_file) as doc:
            assert all(WATERMARK in page.get_text() for page in doc)
            text = doc[0].get_text()
            assert doc.metadata["subject"] == WATERMARK
        assert label in text
        primary = out.mentions[0]
        assert primary.person is plan.primary and primary.page == 1
        assert primary.fields["last"].replace("'", "") in text.replace("' ", "").replace("'", "")


def test_render_is_byte_identical(world, tmp_path):
    s, pop, plans = world
    render_pdf(plans[0], pop, tmp_path / "a", s.config.seed)
    render_pdf(plans[0], pop, tmp_path / "b", s.config.seed)
    assert (tmp_path / "a" / plans[0].doc_file).read_bytes() == (
        tmp_path / "b" / plans[0].doc_file
    ).read_bytes()


def test_w2_reports_ein_exclusions(world, tmp_path):
    s, pop, plans = world
    w2b = next(p for p in plans if p.doc_type == "WAGE_STATEMENT" and p.variant == "B")
    out = render_pdf(w2b, pop, tmp_path, s.config.seed)
    assert [e.kind for e in out.exclusions] == ["EIN", "EIN"]
    assert "P04" in out.mentions[0].planted


def test_scanify_removes_text_layer_deterministically(world, tmp_path):
    s, pop, plans = world
    render_pdf(plans[1], pop, tmp_path, s.config.seed)
    src = tmp_path / plans[1].doc_file
    scan = s.config.pdf.scan.model_copy(update={"dpi": 100})
    scanify(src, tmp_path / "a.pdf", scan, seed=1)
    scanify(src, tmp_path / "b.pdf", scan, seed=1)
    with pymupdf.open(tmp_path / "a.pdf") as doc:
        assert doc[0].get_text().strip() == ""
        assert doc[0].get_images()
    assert (tmp_path / "a.pdf").read_bytes() == (tmp_path / "b.pdf").read_bytes()
