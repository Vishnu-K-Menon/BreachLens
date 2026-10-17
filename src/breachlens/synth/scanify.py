"""Turn a text-layer PDF into an image-only "scan" (SYNTHETIC_DATA.md).

Raster at `dpi` with PyMuPDF → Gaussian noise (σ) → small rotation → blur → JPEG at
`quality` → wrapped back into a one-image-per-page PDF. The randomness comes only from
the given seed, and the PDF is saved without a new file ID, so output is reproducible.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pymupdf as fitz
from PIL import Image, ImageFilter

from breachlens.synth.settings import ScanSettings

FIXED_METADATA = {
    "title": "SYNTHETIC - NOT REAL - scanned copy",
    "author": "BreachLens synthetic generator",
    "subject": "SYNTHETIC - NOT REAL",
    "producer": "BreachLens synthetic generator",
    "creator": "BreachLens synthetic generator",
    "creationDate": "D:20260101000000Z",
    "modDate": "D:20260101000000Z",
}


def degrade(img: Image.Image, scan: ScanSettings, rng: np.random.Generator) -> Image.Image:
    gray = np.asarray(img.convert("L"), dtype=np.float32)
    noisy = np.clip(gray + rng.normal(0.0, scan.noise_sigma, gray.shape), 0, 255).astype(np.uint8)
    out = Image.fromarray(noisy, mode="L")
    angle = float(rng.uniform(-scan.max_rotation_deg, scan.max_rotation_deg))
    out = out.rotate(angle, resample=Image.Resampling.BILINEAR, fillcolor=255)
    return out.filter(ImageFilter.GaussianBlur(radius=scan.blur_radius))


def scanify(src: Path, dst: Path, scan: ScanSettings, seed: int) -> None:
    """Replace `dst` with an image-only, degraded copy of `src` (may be the same path)."""
    rng = np.random.default_rng(seed)
    with fitz.open(src) as doc:
        pages = []
        for page in doc:
            pix = page.get_pixmap(dpi=scan.dpi, colorspace=fitz.csGRAY)
            img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
            buf = io.BytesIO()
            degrade(img, scan, rng).save(buf, format="JPEG", quality=scan.jpeg_quality)
            pages.append((page.rect, buf.getvalue()))
    out = fitz.open()
    for rect, jpeg in pages:
        page = out.new_page(width=rect.width, height=rect.height)
        page.insert_image(page.rect, stream=jpeg)
    out.set_metadata(FIXED_METADATA)
    tmp = dst.with_suffix(".tmp.pdf")
    out.save(tmp, garbage=4, deflate=True, no_new_id=True)
    out.close()
    tmp.replace(dst)
