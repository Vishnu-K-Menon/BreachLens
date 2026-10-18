"""OCR for image-only PDFs: PyMuPDF raster -> binarize -> Tesseract word boxes (ADR-015).

Binarizing at `binarize_threshold` removes the light-gray watermark before OCR. Word
boxes are converted from pixels to PDF points, and confidence is Tesseract conf / 100.
The Tesseract binary comes from `TESSERACT_CMD` (or PATH); if it is missing, callers
skip scanned documents and count them.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image

from breachlens.ingest.tokens import Token


class TesseractMissingError(RuntimeError):
    """Tesseract is not installed or not configured."""


def tesseract_cmd() -> str | None:
    env = os.environ.get("TESSERACT_CMD", "").strip()
    if env and Path(env).is_file():
        return env
    return shutil.which("tesseract")


def page_images(path: Path, dpi: int) -> list[Image.Image]:
    with pymupdf.open(path) as doc:
        out = []
        for page in doc:
            pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
            out.append(Image.frombytes("L", (pix.width, pix.height), pix.samples))
    return out


def binarize(img: Image.Image, threshold: int) -> Image.Image:
    arr = np.asarray(img.convert("L"))
    return Image.fromarray(np.where(arr < threshold, 0, 255).astype(np.uint8), mode="L")


def _runs(dark: np.ndarray, min_len: int) -> np.ndarray:
    """Mask of pixels inside horizontal runs of at least `min_len` dark pixels."""
    h, w = dark.shape
    if w < min_len:
        return np.zeros_like(dark)
    cs = np.concatenate(
        [np.zeros((h, 1), dtype=np.int32), np.cumsum(dark, axis=1, dtype=np.int32)], axis=1
    )
    full = (cs[:, min_len:] - cs[:, :-min_len]) == min_len  # window starting at x is all dark
    starts = np.zeros((h, w + 1), dtype=np.int32)
    starts[:, : w - min_len + 1] += full
    starts[:, min_len : w + 1] -= full
    return np.cumsum(starts, axis=1)[:, :w] > 0


def remove_lines(img: Image.Image, min_len_px: int) -> Image.Image:
    """Erase form box borders: dark runs longer than any character stroke (both axes).

    Box edges next to field values confuse Tesseract (a clean street line next to a
    border was read as garbage), so they are whited out before OCR.
    """
    dark = np.asarray(img.convert("L")) < 128
    lines = _runs(dark, min_len_px) | _runs(dark.T, min_len_px).T
    out = np.asarray(img.convert("L")).copy()
    out[lines] = 255
    return Image.fromarray(out, mode="L")


def estimate_skew(img: Image.Image, max_deg: float = 3.0, step: float = 0.1) -> float:
    """Skew angle (degrees) that makes text rows sharpest (projection-profile method).

    Scans are rotated by up to ±2°, which splits label/value rows that share a line on
    the form. The angle maximizing the variance of dark-pixel row sums wins.
    """
    small = img.convert("L").resize((img.width // 4, img.height // 4))
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-max_deg, max_deg + step / 2, step):
        rot = np.asarray(small.rotate(float(angle), fillcolor=255)) < 128
        profile = rot.sum(axis=1).astype(np.float64)
        score = float(np.square(np.diff(profile)).sum())
        if score > best_score:
            best_angle, best_score = float(angle), score
    return round(best_angle, 2)


def deskew(img: Image.Image) -> tuple[Image.Image, float]:
    angle = estimate_skew(img)
    if abs(angle) < 0.05:
        return img, 0.0
    return img.rotate(angle, resample=Image.Resampling.BILINEAR, fillcolor=255), angle


def ocr_tokens(
    path: Path,
    *,
    dpi: int,
    lang: str,
    psm: int,
    binarize_threshold: int,
    remove_lines_min_px: int = 0,
    min_conf: float = 0.0,
    min_height_pt: float = 0.0,
) -> list[Token]:
    import pytesseract

    cmd = tesseract_cmd()
    if cmd is None:
        raise TesseractMissingError("Tesseract not found: install it or set TESSERACT_CMD")
    pytesseract.pytesseract.tesseract_cmd = cmd
    scale = 72.0 / dpi
    tokens: list[Token] = []
    for page_no, img in enumerate(page_images(path, dpi), start=1):
        straight, _ = deskew(img)
        clean = binarize(straight, binarize_threshold)
        if remove_lines_min_px:
            clean = remove_lines(clean, remove_lines_min_px)
        data = pytesseract.image_to_data(
            clean,
            lang=lang,
            config=f"--psm {psm}",
            output_type=pytesseract.Output.DICT,
        )
        for i, text in enumerate(data["text"]):
            conf = float(data["conf"][i])
            # Skip empty words, border remnants with no letters/digits (|, _, ;) and noise
            # below `min_conf`.
            if not any(ch.isalnum() for ch in text) or conf < 100 * min_conf:
                continue
            x, y, w, h = (data[k][i] * scale for k in ("left", "top", "width", "height"))
            if h < min_height_pt:  # flat remnants of erased box borders
                continue
            tokens.append(
                Token(text.strip().strip("'\"`"), x, y, x + w, y + h, conf / 100.0, page_no)
            )
    return tokens
