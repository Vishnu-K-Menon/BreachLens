from pathlib import Path

from breachlens.classify.doctype import UNKNOWN, classify, keyword_score
from breachlens.extract.templates import load_templates

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = load_templates(ROOT / "config" / "doc_templates")


def test_header_text_picks_type_and_layout():
    r = classify(
        TEMPLATES, "PROFESSIONAL SERVICES CLAIM SUBSCRIBER NAME PROVIDER TIN DX CODES", False, 0.5
    )
    assert (r.doc_type, r.template.layout, r.score) == ("HEALTH_CLAIM", "B", 1.0)


def test_weak_text_is_unknown():
    r = classify(TEMPLATES, "Quarterly newsletter for members", False, 0.5)
    assert r.doc_type == UNKNOWN and r.template is None


def test_ocr_fuzzy_keywords_count_only_for_ocr():
    t = next(t for t in TEMPLATES if t.name == "WAGE_STATEMENT_A")
    noisy = "WAGE AND TAX STATEMNT Employee's social securty number Employer identification numbr"
    assert keyword_score(t, noisy, ocr=True) > keyword_score(t, noisy, ocr=False)
