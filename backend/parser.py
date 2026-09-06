"""Best-effort extraction of key line values from a Form 1040 PDF (plus
Schedules 1, 2, and 3).

Form 1040 is a fillable form: text extracted from it comes out as rows of
labels followed by a dollar amount at the far right of the row. We rely on
pdfplumber's layout-preserving extraction to keep that row structure, then
locate each row two ways: first by a distinctive phrase from the official
line label, and — since label wording shifts across tax years and between
tax-software exports — by the row starting with the line's own number/letter
as a fallback. Either way we pull the trailing dollar amount off the row.

The number-based fallback is scoped to the page range of the schedule it
belongs to (found via each schedule's title text), since bare line numbers
like "1" repeat across the main form and every schedule — matching one
anywhere in the document would happily grab the wrong line.

This is inherently heuristic, and OCR'd (scanned) PDFs won't extract at all.
Callers should always let the person reviewing the result correct any field
before relying on it; see the `confidence` field on each result.
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


def _starts_with_number(row_lower: str, number: str) -> bool:
    tokens = row_lower.split()
    if not tokens:
        return False
    return tokens[0].strip(".:") == number.lower()


# Each entry: (id, display label, phrases to find the row, fallback line
# number as it's actually printed on the form). Phrases are matched
# case-insensitively as substrings anywhere in a text row; several variants
# are listed per line to cover wording differences across tax years and
# tax-software PDF exports.
LINE_DEFINITIONS: list[tuple[str, str, list[str], str]] = [
    ("1z", "Total wages (Form W-2 box 1)",
     ["add lines 1a through 1h", "wages, salaries, tips", "total is your total wages"], "1z"),
    ("2b", "Taxable interest", ["taxable interest"], "2b"),
    ("3b", "Ordinary dividends", ["ordinary dividends"], "3b"),
    ("4b", "Taxable IRA distributions", ["ira distributions", "taxable amount"], "4b"),
    ("5b", "Taxable pensions and annuities", ["pensions and annuities"], "5b"),
    ("6b", "Taxable social security benefits", ["social security benefits"], "6b"),
    ("7", "Capital gain or (loss)", ["capital gain or", "capital gain (or loss)"], "7"),
    ("8", "Additional income (Schedule 1)",
     ["additional income from schedule 1", "other income from schedule 1"], "8"),
    ("9", "Total income", ["total income"], "9"),
    ("10", "Adjustments to income", ["adjustments to income"], "10"),
    ("11", "Adjusted gross income (AGI)", ["adjusted gross income"], "11"),
    ("12", "Standard deduction or itemized deductions",
     ["standard deduction or itemized", "itemized deductions (from schedule a)"], "12"),
    ("13", "Qualified business income deduction", ["qualified business income deduction"], "13"),
    ("14", "Total deductions", ["add lines 12 and 13"], "14"),
    ("15", "Taxable income", ["taxable income"], "15"),
    ("16", "Tax", ["tax (see instructions)", "check if any from form"], "16"),
    ("17", "Schedule 2, line 3 (AMT / excess APTC)", ["amount from schedule 2, line 3"], "17"),
    ("18", "Add lines 16 and 17", ["add lines 16 and 17"], "18"),
    ("19", "Child tax credit / credit for other dependents",
     ["child tax credit or credit for other dependents"], "19"),
    ("20", "Schedule 3, line 8", ["amount from schedule 3, line 8"], "20"),
    ("21", "Add lines 19 and 20", ["add lines 19 and 20"], "21"),
    ("22", "Subtract line 21 from line 18", ["subtract line 21 from line 18"], "22"),
    ("23", "Other taxes (Schedule 2)",
     ["other taxes, including self-employment tax", "amount from schedule 2, line 21"], "23"),
    ("24", "Total tax", ["total tax"], "24"),
    ("25d", "Federal income tax withheld",
     ["add lines 25a through 25c", "total is your total federal income tax withheld"], "25d"),
    ("26", "Estimated tax payments", ["estimated tax payments"], "26"),
    ("27", "Earned income credit (EIC)", ["earned income credit"], "27"),
    ("28", "Additional child tax credit", ["additional child tax credit"], "28"),
    ("31", "Schedule 3, line 13", ["amount from schedule 3, line 13"], "31"),
    ("32", "Total other payments and refundable credits",
     ["total other payments or refundable credits"], "32"),
    ("33", "Total payments", ["total payments"], "33"),
    ("34", "Overpayment (refund)", ["overpaid"], "34"),
    ("35a", "Refund amount", ["amount of line 34 you want refunded"], "35a"),
    ("37", "Amount you owe", ["subtract line 33 from line 24", "amount you owe"], "37"),
]

# Title text that appears at the top of each schedule's page(s), used to
# find where each schedule's fallback-scope starts.
SCHEDULE_TITLE_MARKERS = {
    "s1": ["additional income and adjustments to income"],
    "s2": ["additional taxes"],
    "s3": ["additional credits and payments"],
}

SCHEDULE1_DEFINITIONS: list[tuple[str, str, list[str], str]] = [
    ("s1_1", "Taxable refunds of state/local taxes", ["taxable refunds, credits"], "1"),
    ("s1_3", "Business income or (loss) (Schedule C)", ["business income or (loss)"], "3"),
    ("s1_7", "Unemployment compensation", ["unemployment compensation"], "7"),
    ("s1_9", "Total other income", ["add lines 1 through 8", "total other income"], "9"),
    ("s1_10", "Total additional income", ["combine lines 1 through 7 and 9", "add lines 1, 2c",
                                          "total additional income"], "10"),
    ("s1_11", "Educator expenses", ["educator expenses"], "11"),
    ("s1_13", "HSA deduction", ["health savings account deduction"], "13"),
    ("s1_15", "Deductible part of self-employment tax", ["deductible part of self-employment tax"], "15"),
    ("s1_20", "IRA deduction", ["ira deduction"], "20"),
    ("s1_21", "Student loan interest deduction", ["student loan interest deduction"], "21"),
    ("s1_25", "Total adjustments to income", ["add lines 11 through 23", "total adjustments"], "25"),
]

SCHEDULE2_DEFINITIONS: list[tuple[str, str, list[str], str]] = [
    ("s2_1", "Alternative Minimum Tax (AMT)", ["alternative minimum tax"], "1"),
    ("s2_2", "Excess advance premium tax credit repayment", ["excess advance premium tax credit"], "2"),
    ("s2_3", "Total (Part I)", ["add lines 1 and 2", "amount from schedule 2, line 3"], "3"),
    ("s2_4", "Self-employment tax", ["self-employment tax"], "4"),
    ("s2_11", "Additional Medicare Tax", ["additional medicare tax"], "11"),
    ("s2_12", "Net investment income tax", ["net investment income tax"], "12"),
    ("s2_21", "Total other taxes (Part II)", ["add lines 4 through 18", "total other taxes"], "21"),
]

SCHEDULE3_DEFINITIONS: list[tuple[str, str, list[str], str]] = [
    ("s3_1", "Foreign tax credit", ["foreign tax credit"], "1"),
    ("s3_2", "Child and dependent care credit", ["credit for child and dependent care"], "2"),
    ("s3_3", "Education credits", ["education credits"], "3"),
    ("s3_4", "Retirement savings contributions credit", ["retirement savings contributions credit"], "4"),
    ("s3_8", "Total nonrefundable credits (Part I)",
     ["add lines 1 through 4", "amount from schedule 3, line 8"], "8"),
    ("s3_9", "Net premium tax credit", ["net premium tax credit"], "9"),
    ("s3_13", "Total other payments/refundable credits (Part II)",
     ["add lines 9 through 12", "amount from schedule 3, line 13"], "13"),
]

FILING_STATUS_PATTERNS = [
    ("single", r"\bsingle\b"),
    ("mfj", r"married filing jointly"),
    ("mfs", r"married filing separately"),
    ("hoh", r"head of household"),
    ("qss", r"qualifying surviving spouse"),
]

TAX_YEAR_RE = re.compile(r"\b(20[1-3][0-9])\b")


@dataclass
class ExtractedLine:
    id: str
    label: str
    value: float | None
    confidence: str  # "matched" or "not_found"
    group: str = "Form 1040"


@dataclass
class ExtractionResult:
    lines: list[ExtractedLine] = field(default_factory=list)
    filing_status: str | None = None
    tax_year: int | None = None
    raw_text: str = ""

    def as_value_map(self) -> dict[str, float]:
        return {ln.id: ln.value for ln in self.lines if ln.value is not None}


def _page_texts(pdf_bytes: bytes) -> list[str]:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return [page.extract_text(layout=True) or "" for page in pdf.pages]


def extract_text(pdf_bytes: bytes) -> str:
    return "\n".join(_page_texts(pdf_bytes))


def detect_filing_status(text: str) -> str | None:
    lowered = text.lower()
    # The filing status section is near the top of page 1; scanning the
    # whole document risks false positives from later mentions, so this is
    # only a suggestion — the UI lets the user confirm or override it.
    for status_id, pattern in FILING_STATUS_PATTERNS:
        if re.search(pattern, lowered):
            return status_id
    return None


def detect_tax_year(text: str) -> int | None:
    """Look for the tax year near the top of the document (e.g. "Form 1040
    (2023)" or "...Tax Return  2023"). Scanning only the first ~600
    characters avoids picking up an unrelated year mentioned deeper in the
    form (a birthdate, a prior-year comparison, etc.)."""
    header = text[:600]
    match = TAX_YEAR_RE.search(header)
    return int(match.group(1)) if match else None


def _find_schedule_page_starts(pages: list[str]) -> dict[str, int | None]:
    starts: dict[str, int | None] = {"s1": None, "s2": None, "s3": None}
    for key, markers in SCHEDULE_TITLE_MARKERS.items():
        for i, page in enumerate(pages):
            page_lower = page.lower()
            if any(marker in page_lower for marker in markers):
                starts[key] = i
                break
    return starts


def _match_by_phrase(lines: list[str], phrases: list[str]) -> float | None:
    for row in lines:
        row_lower = row.strip().lower()
        if any(phrase in row_lower for phrase in phrases):
            candidate = _last_amount_in_line(row)
            if candidate is not None:
                return candidate
    return None


def _match_by_number(lines: list[str] | None, number: str) -> float | None:
    if lines is None:
        return None
    for row in lines:
        row_lower = row.strip().lower()
        if _starts_with_number(row_lower, number):
            candidate = _last_amount_in_line(row)
            if candidate is not None:
                return candidate
    return None


def _extract_group(
    phrase_scope: list[str],
    fallback_scope: list[str] | None,
    definitions: list[tuple[str, str, list[str], str]],
    group: str,
) -> list[ExtractedLine]:
    results = []
    for line_id, label, phrases, fallback_number in definitions:
        value = _match_by_phrase(phrase_scope, phrases)
        if value is None:
            value = _match_by_number(fallback_scope, fallback_number)
        results.append(ExtractedLine(
            id=line_id,
            label=label,
            value=value,
            confidence="matched" if value is not None else "not_found",
            group=group,
        ))
    return results


def parse_1040(pdf_bytes: bytes) -> ExtractionResult:
    pages = _page_texts(pdf_bytes)
    text = "\n".join(pages)
    page_lines = [p.splitlines() for p in pages]

    result = ExtractionResult(raw_text=text)
    result.filing_status = detect_filing_status(text)
    result.tax_year = detect_tax_year(text)

    starts = _find_schedule_page_starts(pages)
    total_pages = len(pages)
    schedule_starts = [s for s in starts.values() if s is not None]
    first_schedule_page = min(schedule_starts) if schedule_starts else total_pages

    def flatten(a: int, b: int) -> list[str]:
        return [line for page in page_lines[a:b] for line in page]

    def scope_for(key: str) -> list[str] | None:
        start = starts[key]
        if start is None:
            return None
        later_starts = [s for k, s in starts.items() if k != key and s is not None and s > start]
        end = min(later_starts) if later_starts else total_pages
        return flatten(start, end)

    main_scope = flatten(0, first_schedule_page)
    all_lines = flatten(0, total_pages)
    s1_scope = scope_for("s1")
    s2_scope = scope_for("s2")
    s3_scope = scope_for("s3")

    result.lines.extend(_extract_group(main_scope, main_scope, LINE_DEFINITIONS, "Form 1040"))
    result.lines.extend(_extract_group(s1_scope or all_lines, s1_scope, SCHEDULE1_DEFINITIONS,
                                        "Schedule 1 (Additional Income & Adjustments)"))
    result.lines.extend(_extract_group(s2_scope or all_lines, s2_scope, SCHEDULE2_DEFINITIONS,
                                        "Schedule 2 (Additional Taxes)"))
    result.lines.extend(_extract_group(s3_scope or all_lines, s3_scope, SCHEDULE3_DEFINITIONS,
                                        "Schedule 3 (Additional Credits & Payments)"))
    return result
