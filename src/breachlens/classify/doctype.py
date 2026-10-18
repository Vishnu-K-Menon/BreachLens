"""Keyword-rule document-type classifier (one score per template = type + layout).

Score = matched keyword weight / total keyword weight. A keyword matches as a
case-insensitive substring of the page text; for OCR text a fuzzy partial match
(rapidfuzz, >= 90) also counts. The best template wins; below `min_score` -> UNKNOWN.
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from breachlens.extract.templates import Template, norm

UNKNOWN = "UNKNOWN"
FUZZY_MIN = 90.0


@dataclass(frozen=True)
class DocTypeResult:
    template: Template | None
    doc_type: str
    score: float
    scores: dict[str, float]


def keyword_score(template: Template, text: str, ocr: bool) -> float:
    hay = norm(text).lower()
    total = sum(k.weight for k in template.keywords) or 1.0
    got = 0.0
    for k in template.keywords:
        needle = norm(k.text).lower()
        if needle in hay or (ocr and fuzz.partial_ratio(needle, hay) >= FUZZY_MIN):
            got += k.weight
    return round(got / total, 4)


def classify(templates: list[Template], text: str, ocr: bool, min_score: float) -> DocTypeResult:
    scores = {t.name: keyword_score(t, text, ocr) for t in templates}
    best = max(templates, key=lambda t: (scores[t.name], t.name))
    threshold = best.min_score if best.min_score is not None else min_score
    if scores[best.name] < threshold:
        return DocTypeResult(None, UNKNOWN, scores[best.name], scores)
    return DocTypeResult(best, best.doc_type, scores[best.name], scores)
