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
   payments, refund/owed, etc.) using pdfplumber's layout-aware text
   extraction.
2. You review the extracted numbers in the browser and fix anything that
   didn't parse correctly (parsing a form's text layout is inherently
   heuristic — line label wording shifts between tax years).
3. `POST /api/analyze` takes your (possibly corrected) numbers and returns:
   - Plain-English explanations for each line (see `backend/explain.py`).
   - Red flags — inconsistencies (e.g. tax exceeding total income) and
     "worth a second look" notes (e.g. heavy over-withholding, a deduction
     that doesn't match the standard amount for your filing status).
   - A step-by-step money-flow breakdown from total income down to your
     refund or amount owed, rendered as a simple bar-based waterfall.

## What it deliberately doesn't do

- **No OCR.** Scanned or photographed returns aren't supported. Only PDFs
  with a real text layer work. Handling scanned documents reliably would
  need a proper OCR pipeline (e.g. Tesseract) and is out of scope for this
  version.
- **No e-filing, no tax calculation from scratch, no advice.** It explains
  the numbers that are already on the return; it doesn't compute what your
  taxes *should* be.

## Running it

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Then open http://127.0.0.1:8000/.

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

`tests/test_parser.py` builds a synthetic Form-1040-shaped PDF (via
`reportlab`) to verify the line-matching and amount-extraction logic without
needing a real tax return on disk.

## Project layout

```
backend/
  parser.py   PDF -> extracted line values (pdfplumber-based)
  explain.py  line explanations, anomaly flags, money-flow breakdown
  main.py     FastAPI app (/api/extract, /api/analyze) + serves frontend/
frontend/
  index.html  single-page upload/review/results UI (vanilla JS, no build step)
tests/
  test_parser.py
```
