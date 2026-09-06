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
import os
from concurrent.futures import ThreadPoolExecutor

import pypdfium2 as pdfium
import pytesseract
from PIL import Image

# Tesseract's LSTM engine uses OpenMP internally and defaults to spawning
# one thread per CPU core *per invocation*. Combined with running several
# pages concurrently below, that oversubscribes the machine badly (4
# workers x 4 internal threads each = 16 threads fighting over 4 cores) —
# measured on a real 22-scanned-page return, this alone was the difference
# between every page finishing in 1-3 seconds solo and nearly all of them
# blowing through a 20-second timeout when run as a batch. Constraining
# each invocation to one thread and parallelizing purely at the page level
# (via ocr_pages_text's ThreadPoolExecutor) uses the same total CPU
# without the contention.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

# 200 DPI is a reasonable balance for OCR accuracy on a standard printed tax
# form without making a multi-page scanned return prohibitively slow to
# process synchronously.
OCR_DPI = 200

# Some pages make Tesseract's layout analysis hang outright rather than
# just run slowly (seen on a real return with a dense embedded graphic —
# confirmed by running the tesseract CLI directly on the rendered image
# with no Python involved at all). Without a hard per-page timeout, one
# such page blocks the entire request indefinitely; pytesseract passes
# this straight to subprocess's own timeout, which kills the process.
OCR_TIMEOUT_SECONDS = 20

# pytesseract shells out to the tesseract CLI as a subprocess per call, so
# running several pages at once (via threads — each opens its own
# pypdfium2 document from the same bytes, so there's no shared mutable
# state) gets close to linear speedup up to the machine's core count. A
# multi-page scanned return run one page at a time can otherwise take
# minutes, which is well past what anyone will wait on for a PDF upload.
_MAX_OCR_WORKERS = max(1, min(8, os.cpu_count() or 1))


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
        return pytesseract.image_to_string(image, timeout=OCR_TIMEOUT_SECONDS)
    except Exception:
        return ""


def ocr_pages_text(pdf_bytes: bytes, page_indices: list[int]) -> dict[int, str]:
    """OCRs several pages concurrently. Returns a dict mapping each input
    page index to its recovered text (possibly "" on failure) — always one
    entry per input index, in no particular order internally."""
    if not page_indices:
        return {}
    with ThreadPoolExecutor(max_workers=_MAX_OCR_WORKERS) as pool:
        results = pool.map(lambda i: (i, ocr_page_text(pdf_bytes, i)), page_indices)
        return dict(results)
