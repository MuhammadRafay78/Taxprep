"""OCR fallback for PDF pages with no extractable text layer (scanned or
photographed pages).

This is a Python-only feature: it needs the `tesseract-ocr` system binary,
which isn't available in a Cloudflare Workers-style sandbox (no native
binaries) — see worker/README.md for that side of the tradeoff. It's also
slower and less reliable than reading a real text layer, which is why every
value it produces is marked with lower confidence downstream (see
parser.py's `via_ocr` handling) rather than treated the same as a phrase-
anchored match on real text.
"""
from __future__ import annotations

import io

import pypdfium2 as pdfium
import pytesseract
from PIL import Image

# 200 DPI is a reasonable balance for OCR accuracy on a standard printed tax
# form without making a multi-page scanned return prohibitively slow to
# process synchronously.
OCR_DPI = 200


def is_tesseract_available() -> bool:
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def ocr_page_text(pdf_bytes: bytes, page_index: int) -> str:
    """Renders one page (0-indexed) to an image and runs OCR on it,
    returning text laid out as best-effort rows — close enough in shape to
    pdfplumber's `layout=True` text for the same line-matching logic to run
    against it. Returns "" if OCR isn't available or fails for this page;
    callers should treat that the same as "still no text"."""
    try:
        pdf = pdfium.PdfDocument(io.BytesIO(pdf_bytes))
        page = pdf[page_index]
        scale = OCR_DPI / 72
        bitmap = page.render(scale=scale)
        image: Image.Image = bitmap.to_pil()
        return pytesseract.image_to_string(image)
    except Exception:
        return ""
