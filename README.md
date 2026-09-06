# Taxprep — Understand Your Tax Return

A small web app that takes a Form 1040 PDF, extracts the key line items, and
gives you a plain-language explanation of each one, a list of things worth
double-checking, and a visual walkthrough of how your income turns into a
refund or a bill.

**This is not tax software.** It doesn't file anything, doesn't give tax
advice, and its PDF parsing is best-effort — you review and can correct every
extracted number before it explains anything.

## What it does

1. Upload a Form 1040 PDF (a fillable/text-based one — a real, printed IRS
   form or one exported from tax software). `POST /api/extract` pulls out
   values for the standard 1040 lines (wages, AGI, taxable income, tax,
   payments, refund/owed, tax year, filing status, etc.) plus **Schedules 1,
   2, and 3** (extra income/adjustments, AMT/self-employment tax, extra
   credits) using pdfplumber's layout-aware text extraction. Matching first
   tries a distinctive phrase from the official line label (with several
   wording variants per line, to survive differences across tax years and
   tax-software exports), then falls back to a row simply starting with the
   line's own number — scoped to that schedule's own pages, so a bare "line
   1" in Schedule 2 is never confused with "line 1" in Schedule 1 or 3.
2. You review the extracted numbers in the browser and fix anything that
   didn't parse correctly (parsing a form's text layout is inherently
   heuristic). Schedule sections only show up if something from that
   schedule was actually found.
3. `POST /api/analyze` takes your (possibly corrected) numbers and returns:
   - Plain-English explanations for each line (see `backend/explain.py`),
     across the main form and all three schedules.
   - Red flags — inconsistencies (e.g. tax exceeding total income) and
     "worth a second look" notes: heavy over-withholding, a deduction that
     doesn't match the standard amount for your filing status and tax year,
     a reported tax that's noticeably off from what the year's tax rates
     would give on your taxable income — using the IRS Qualified Dividends
     and Capital Gains Tax Worksheet approximation when the return has
     long-term capital gains or qualified dividends, so those returns get a
     real check instead of being skipped — a hint that you might qualify
     for the Earned Income Credit but didn't claim it, a note when
     self-employment tax shows up (with the deduction it entitles you to),
     and proximity hints for the Alternative Minimum Tax exemption, the Net
     Investment Income Tax threshold, and the Additional Medicare Tax
     threshold. Bracket/capital-gains/AMT/EIC/standard-deduction figures
     live in `backend/tax_data.py` for 2020–2025 and degrade gracefully for
     years outside that table.
   - A step-by-step money-flow breakdown from total income down to your
     refund or amount owed, rendered as a simple bar-based waterfall.
4. Optionally, upload a **second year's** Form 1040 to compare against the
   first — a side-by-side table of income, AGI, taxable income, tax,
   payments, and refund/owed, with the dollar and percent change between
   the two (computed client-side from whatever you've reviewed/corrected in
   both review tables).

5. **Scanned pages fall back to OCR.** Any page with zero extractable text
   (a photographed or scanned page in an otherwise text-based PDF) is
   rendered to an image and run through Tesseract (`backend/ocr.py`).
   Section-boundary detection (which pages belong to which schedule) is
   still computed from the *original*, pre-OCR pages — Form 1040 itself
   prints an OMB control number too, and once OCR reveals it, it would
   otherwise look like a new attachment starting mid-return and truncate
   the main form's scope. Every value recovered via OCR is marked
   `confidence: "uncertain"` and `via_ocr: true` and shown with a "verify
   this, OCR can misread digits" caption — it's meaningfully less reliable
   than reading a real text layer (digit misreads, merged/garbled words),
   so it's never treated with the same confidence as a phrase-anchored
   match on real text. The UI banner tells you which pages needed OCR and
   whether it actually recovered anything from each one.

   Scanned pages are OCR'd concurrently (one Tesseract subprocess per page,
   in a thread pool sized to the CPU count) — a multi-page scanned return
   run one page at a time can take minutes, which is well past what anyone
   will wait on for a PDF upload. Each Tesseract invocation is also capped
   at 20 seconds and constrained to a single internal thread
   (`OMP_THREAD_LIMIT=1`); without that, running several multi-threaded
   Tesseract processes at once oversubscribes the machine badly (measured:
   4 workers × 4 internal threads each on a 4-core box turned a ~20-second
   job into a 2-minute one where nearly every page hit the timeout).

## What it deliberately doesn't do

- **No e-filing, no tax calculation from scratch, no advice.** It explains
  the numbers that are already on the return; it doesn't compute what your
  taxes *should* be.
- **No OCR on the Cloudflare Workers port** (`worker/`). Workers can't run
  the `tesseract-ocr` native binary this needs (no native binaries in its
  WASM sandbox) — see `worker/README.md`. That deployment stays text-layer
  only; a scanned page there is reported as such with no fallback.

## Running it

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

OCR requires the `tesseract-ocr` system package (not just the Python
`pytesseract` wrapper installed via pip) — e.g. `apt-get install
tesseract-ocr` on Debian/Ubuntu, `brew install tesseract` on macOS. Without
it, `backend/ocr.py` fails closed: scanned pages are still reported in
`scanned_pages`, just never recovered into `ocr_pages`.

Then open http://127.0.0.1:8000/.

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

`tests/test_parser.py` builds synthetic Form-1040/Schedule-shaped PDFs (via
`reportlab`) to verify the line-matching, schedule-scoping, and
amount-extraction logic without needing a real tax return on disk.
`tests/test_explain.py` covers the bracket-based tax check, the EIC hint,
and the self-employment tax note.

## Project layout

```
backend/
  parser.py     PDF -> extracted line values, incl. Schedules 1-3 (pdfplumber-based)
  ocr.py        OCR fallback (Tesseract) for pages with no text layer
  tax_data.py   reference standard deductions / brackets / EIC limits for sanity checks
  explain.py    line explanations, anomaly flags, money-flow breakdown
  main.py       FastAPI app (/api/extract, /api/analyze) + serves frontend/
frontend/
  index.html    single-page upload/review/results/compare UI (vanilla JS, no build step)
tests/
  test_parser.py
  test_explain.py
```
