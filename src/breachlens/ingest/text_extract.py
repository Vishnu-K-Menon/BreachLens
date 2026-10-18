"""Text-layer extraction with pdfplumber: words with boxes -> `Token`s.

The diagonal `SYNTHETIC - NOT REAL` watermark is drawn at 54 pt; pdfplumber reports its
glyphs as single-letter words, so words above `max_font_size` are dropped.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber

from breachlens.ingest.tokens import Token


def extract_tokens(path: Path, max_font_size: float = 30.0) -> list[Token]:
    tokens: list[Token] = []
    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            for w in page.extract_words(extra_attrs=["size"]):
                if w["size"] > max_font_size or not w["text"].strip():
                    continue
                tokens.append(
                    Token(w["text"], w["x0"], w["top"], w["x1"], w["bottom"], 1.0, page_no)
                )
    return tokens
