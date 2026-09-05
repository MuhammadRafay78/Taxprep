"""Best-effort extraction of key line values from a Form 1040 PDF.

Form 1040 is a fillable form: text extracted from it comes out as rows of
labels followed by a dollar amount at the far right of the row. We rely on
pdfplumber's layout-preserving extraction to keep that row structure, then
match each row against a distinctive phrase from the official line label and
pull the trailing dollar amount off of it.

This is inherently heuristic — label wording shifts slightly between tax
years, and OCR'd (scanned) PDFs may not extract cleanly at all. Callers
should always let the person reviewing the result correct any field before
relying on it; see the `confidence` field on each result.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pdfplumber

AMOUNT_RE = re.compile(r"^\(?\$?-?[\d,]+(?:\.\d{1,2})?\)?$")


def _parse_amount(token: str) -> float | None:
    negative = token.startswith("(") and token.endswith(")")
    cleaned = token.strip("()$").replace(",", "")
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return -value if negative else value


def _last_amount_in_line(line: str) -> float | None:
    tokens = line.split()
    for token in reversed(tokens):
        if AMOUNT_RE.fullmatch(token):
            amount = _parse_amount(token)
            if amount is not None:
                return amount
    return None


# Each entry: line id -> (display label, phrase(s) used to locate the row).
# Phrases are matched case-insensitively as substrings anywhere in a text row.
LINE_DEFINITIONS: list[tuple[str, str, list[str]]] = [
    ("1z", "Total wages (Form W-2 box 1)", ["total is", "add lines 1a through 1h", "wages, salaries, tips"]),
    ("2b", "Taxable interest", ["taxable interest"]),
    ("3b", "Ordinary dividends", ["ordinary dividends"]),
    ("4b", "Taxable IRA distributions", ["ira distributions", "taxable amount"]),
    ("5b", "Taxable pensions and annuities", ["pensions and annuities"]),
    ("6b", "Taxable social security benefits", ["social security benefits"]),
    ("7", "Capital gain or (loss)", ["capital gain or", "loss"]),
    ("8", "Additional income (Schedule 1)", ["additional income from schedule 1"]),
    ("9", "Total income", ["total income"]),
    ("10", "Adjustments to income", ["adjustments to income"]),
    ("11", "Adjusted gross income (AGI)", ["adjusted gross income"]),
    ("12", "Standard deduction or itemized deductions", ["standard deduction or itemized"]),
    ("13", "Qualified business income deduction", ["qualified business income deduction"]),
    ("14", "Total deductions", ["add lines 12 and 13"]),
    ("15", "Taxable income", ["taxable income"]),
    ("16", "Tax", ["tax (see instructions)", "check if any from form"]),
    ("17", "Schedule 2, line 3 (AMT / excess APTC)", ["amount from schedule 2, line 3"]),
    ("18", "Add lines 16 and 17", ["add lines 16 and 17"]),
    ("19", "Child tax credit / credit for other dependents", ["child tax credit or credit for other dependents"]),
    ("20", "Schedule 3, line 8", ["amount from schedule 3, line 8"]),
    ("21", "Add lines 19 and 20", ["add lines 19 and 20"]),
    ("22", "Subtract line 21 from line 18", ["subtract line 21 from line 18"]),
    ("23", "Other taxes (Schedule 2)", ["other taxes, including self-employment tax"]),
    ("24", "Total tax", ["total tax"]),
    ("25d", "Federal income tax withheld", ["add lines 25a through 25c", "total is your total federal income tax withheld"]),
    ("26", "Estimated tax payments", ["estimated tax payments"]),
    ("27", "Earned income credit (EIC)", ["earned income credit"]),
    ("28", "Additional child tax credit", ["additional child tax credit"]),
    ("31", "Schedule 3, line 13", ["amount from schedule 3, line 13"]),
    ("32", "Total other payments and refundable credits", ["total other payments or refundable credits"]),
    ("33", "Total payments", ["total payments"]),
    ("34", "Overpayment (refund)", ["overpaid"]),
    ("35a", "Refund amount", ["amount of line 34 you want refunded"]),
    ("37", "Amount you owe", ["subtract line 33 from line 24", "amount you owe"]),
]

FILING_STATUS_PATTERNS = [
    ("single", r"\bsingle\b"),
    ("mfj", r"married filing jointly"),
    ("mfs", r"married filing separately"),
    ("hoh", r"head of household"),
    ("qss", r"qualifying surviving spouse"),
]


@dataclass
class ExtractedLine:
    id: str
    label: str
    value: float | None
    confidence: str  # "matched" or "not_found"


@dataclass
class ExtractionResult:
    lines: list[ExtractedLine] = field(default_factory=list)
    filing_status: str | None = None
    raw_text: str = ""

    def as_value_map(self) -> dict[str, float]:
        return {ln.id: ln.value for ln in self.lines if ln.value is not None}


def extract_text(pdf_bytes: bytes) -> str:
    rows: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=True) or ""
            rows.extend(text.splitlines())
    return "\n".join(rows)


def detect_filing_status(text: str) -> str | None:
    lowered = text.lower()
    # The filing status section is near the top of page 1; scanning the
    # whole document risks false positives from later mentions, so this is
    # only a suggestion — the UI lets the user confirm or override it.
    for status_id, pattern in FILING_STATUS_PATTERNS:
        if re.search(pattern, lowered):
            return status_id
    return None


def parse_1040(pdf_bytes: bytes) -> ExtractionResult:
    text = extract_text(pdf_bytes)
    lines = text.splitlines()
    result = ExtractionResult(raw_text=text)
    result.filing_status = detect_filing_status(text)

    for line_id, label, phrases in LINE_DEFINITIONS:
        value = None
        for row in lines:
            row_lower = row.strip().lower()
            if any(phrase in row_lower for phrase in phrases):
                candidate = _last_amount_in_line(row)
                if candidate is not None:
                    value = candidate
                    break
        result.lines.append(
            ExtractedLine(
                id=line_id,
                label=label,
                value=value,
                confidence="matched" if value is not None else "not_found",
            )
        )
    return result
