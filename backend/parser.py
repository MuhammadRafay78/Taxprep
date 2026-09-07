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

This is inherently heuristic. Pages with no text layer at all (a scanned or
photographed page) are run through OCR as a fallback (see ocr.py) — slower
and less reliable than reading real text, so lines recovered that way are
marked `via_ocr` and never given full "matched" confidence.
Callers should always let the person reviewing the result correct any field
before relying on it; see the `confidence` field on each result.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pdfplumber

from . import ocr

# Requires proper thousands-grouping (",ddd" in groups of exactly 3) when a
# comma is present, and allows 0-2 digits after a decimal point (real IRS
# forms print whole-dollar amounts as e.g. "1,200." with an empty cents
# spot). This is deliberately stricter than "any digits and commas" so it
# doesn't accidentally match a form/line cross-reference embedded in prose,
# like the "2441" in "...from Form 2441," or "line 11.".
AMOUNT_RE = re.compile(r"^\(?\$?-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{0,2})?\)?$")

# OCR sometimes inserts a stray space right after a thousands-separator
# comma (e.g. "51,808" rendered as two words "51," "808"). Left unmerged,
# every amount-matching helper below would only ever see the trailing
# "808" - silently truncating a real dollar figure down to its last three
# digits rather than failing loudly. _TOKENIZE_LEAD_RE matches the first
# group of a split number ("51,", "$1,", "(2,"); _TOKENIZE_MID_RE matches a
# continuation group for numbers with more than one comma ("234,");
# _TOKENIZE_TAIL_RE matches the final group, with no trailing comma.
_TOKENIZE_LEAD_RE = re.compile(r"^\(?\$?-?\d{1,3},$")
_TOKENIZE_MID_RE = re.compile(r"^\d{3},$")
_TOKENIZE_TAIL_RE = re.compile(r"^\d{3}(?:\.\d{0,2})?\)?$")


def _tokenize(row: str) -> list[str]:
    raw = row.split()
    tokens: list[str] = []
    i = 0
    while i < len(raw):
        if _TOKENIZE_LEAD_RE.match(raw[i]):
            j = i + 1
            combined = raw[i]
            while j < len(raw) and _TOKENIZE_MID_RE.match(raw[j]):
                combined += raw[j]
                j += 1
            if j < len(raw) and _TOKENIZE_TAIL_RE.match(raw[j]):
                combined += raw[j]
                tokens.append(combined)
                i = j + 1
                continue
        tokens.append(raw[i])
        i += 1
    return tokens


def _parse_amount(token: str) -> float | None:
    negative = token.startswith("(") and token.endswith(")")
    cleaned = token.strip("()$").replace(",", "")
    if not cleaned or cleaned == ".":
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return -value if negative else value


def _is_bare_integer(token: str) -> bool:
    core = token.strip("()$")
    return "," not in core and "." not in core


_LINE_NUMBER_START_RE = re.compile(r"^\d{1,2}[a-z]?$", re.IGNORECASE)


def _starts_new_numbered_line(row: str) -> bool:
    """True if this row looks like it opens with a different line's own
    number (e.g. "9", "10", "1z") — a strong signal that the previous row's
    label genuinely ended (however garbled its own trailing text), rather
    than continuing to wrap onto this one. A real wrapped-label
    continuation row starts with ordinary prose ("Form 2441 . . ."), never
    with what reads as a bare line number.

    Checks the first two tokens, not just the very first: OCR sometimes
    prepends a stray garbled word to a row (bleed from an adjacent column
    or margin note), pushing the real leading line number to the second
    token."""
    tokens = _tokenize(row)
    return any(_LINE_NUMBER_START_RE.match(tok.strip(".:")) for tok in tokens[:2])


def _scan_from_anchor(lines: list[str], idx: int, reject_numbers: set[str], lookahead: int = 2) -> float | None:
    """Checks the anchor row at `idx`, then up to `lookahead` rows after it,
    for a valid trailing amount — long labels often wrap, leaving the
    actual entered value alone on a following row.

    We deliberately don't scan backward past other tokens on a row: a
    genuine amount is always the very last thing printed on its row.
    Anything else numeric-looking earlier is typically a form/line
    cross-reference embedded in prose ("...from Form 2441, line 11.") that
    happens to satisfy a naive number pattern but isn't in the amount
    column at all.

    A row's last token falls into exactly one of three buckets, each
    handled differently:
      - not amount-shaped at all (e.g. ends in "Attach") -> the label is
        still wrapping onto the next row, so keep looking ahead.
      - a bare integer matching one of `reject_numbers` (e.g. "...taxes
        . . . 1" when the anchor row itself was line 1's own label) ->
        ambiguous. Most PDFs print this only when the line was left blank,
        with nothing else following. But some print the line number's own
        echo *unconditionally*, with the actual value (when there is one)
        printed alone on the very next row instead of the same row — so we
        peek once more: if the immediate next non-blank row is nothing but
        a single amount token, that's this line's real value; anything
        else (a different line's label, more prose, ...) means this line
        really was left blank. `reject_numbers` normally holds just the
        anchor row's own leading number (not a hardcoded expectation of
        which number this line "should" be, since a schedule's line
        numbering can shift between tax years) — but callers reading OCR'd
        text also pass the line's officially-known number as a second
        candidate, since OCR can misread the same printed digits
        differently the first time (the row's leading label) versus the
        second (this trailing echo).
      - anything else amount-shaped -> a real value; return it.
    """
    for offset in range(lookahead + 1):
        j = idx + offset
        if j >= len(lines):
            break
        if offset > 0 and _starts_new_numbered_line(lines[j]):
            # The previous row's label didn't yield a value and this one
            # opens with what looks like a different line's own number -
            # stop rather than treating it as a wrapped continuation. This
            # matters most on OCR'd text, where a row can fail to parse for
            # reasons other than genuinely wrapping (garbled trailing
            # characters), and the very next row is really just the next
            # line's own entry, not a continuation of this one.
            break
        tokens = _tokenize(lines[j])
        if not tokens:
            continue
        last = tokens[-1]
        if not AMOUNT_RE.fullmatch(last):
            continue
        if _is_bare_integer(last) and last.strip("()$") in reject_numbers:
            for k in range(j + 1, min(j + 1 + lookahead, len(lines))):
                next_tokens = _tokenize(lines[k])
                if not next_tokens:
                    continue
                if len(next_tokens) == 1 and AMOUNT_RE.fullmatch(next_tokens[0]):
                    return _parse_amount(next_tokens[0])
                break
            return None
        return _parse_amount(last)
    return None


# Each entry: (id, display label, phrases to find the row, fallback line
# number as it's actually printed on the form). Phrases are matched
# case-insensitively as substrings anywhere in a text row; several variants
# are listed per line to cover wording differences across tax years and
# tax-software PDF exports.
LINE_DEFINITIONS: list[tuple[str, str, list[str], str]] = [
    ("1z", "Total wages (Form W-2 box 1)",
     ["add lines 1a through 1h", "wages, salaries, tips", "total is your total wages"], "1z"),
    ("2b", "Taxable interest", ["taxable interest"], "2b"),
    ("3a", "Qualified dividends", ["qualified dividends"], "3a"),
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

SCHEDULE_A_DEFINITIONS: list[tuple[str, str, list[str], str]] = [
    ("sa_1", "Medical and dental expenses", ["medical and dental expenses"], "1"),
    ("sa_4", "Deductible medical and dental expenses",
     ["subtract line 3 from line 1", "medical and dental expenses. subtract"], "4"),
    ("sa_5e", "State and local taxes claimed (after the $10,000 cap)",
     ["smaller of line 5d or", "smaller of line 5d"], "5e"),
    ("sa_7", "Total taxes", ["add lines 5e and 6", "total taxes. add"], "7"),
    ("sa_8e", "Home mortgage interest and points",
     ["add lines 8a through 8c", "home mortgage interest and points"], "8e"),
    ("sa_10", "Total interest", ["add lines 8e and 9", "total interest. add"], "10"),
    ("sa_14", "Gifts to charity",
     ["add lines 11 through 13", "gifts to charity. add"], "14"),
    ("sa_15", "Casualty and theft losses", ["casualty and theft loss"], "15"),
    ("sa_16", "Other itemized deductions", ["other—from list in instructions", "other itemized deductions"], "16"),
    ("sa_17", "Total itemized deductions",
     ["add the amounts in the far right column", "total itemized deductions"], "17"),
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
    # "matched" / "not_found": a curated line (Form 1040, Schedule 1/2/3) -
    # phrase-anchored, validated against real returns. "uncertain": either
    # a generically-detected line on a form we have no curated definitions
    # for (position-based only, no phrase anchor to confirm it's reading
    # the right cell), or a curated line recovered via OCR (see `via_ocr`)
    # rather than a real text layer - OCR misreads digits often enough that
    # even a phrase-anchored match shouldn't be shown with full confidence.
    confidence: str
    group: str = "Form 1040"
    via_ocr: bool = False


@dataclass
class ExtractionResult:
    lines: list[ExtractedLine] = field(default_factory=list)
    filing_status: str | None = None
    tax_year: int | None = None
    raw_text: str = ""
    # 1-indexed page numbers with zero extractable text — almost always a
    # scanned/rasterized page (an image with no text layer at all).
    scanned_pages: list[int] = field(default_factory=list)
    # Subset of scanned_pages that OCR successfully recovered *some* text
    # from (Tesseract not installed, or OCR itself failing, leaves a page
    # in scanned_pages but out of this list).
    ocr_pages: list[int] = field(default_factory=list)

    def as_value_map(self) -> dict[str, float]:
        return {ln.id: ln.value for ln in self.lines if ln.value is not None}


def _page_texts(pdf_bytes: bytes) -> list[str]:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return [page.extract_text(layout=True) or "" for page in pdf.pages]


def extract_text(pdf_bytes: bytes) -> str:
    return "\n".join(_page_texts(pdf_bytes))


_SPOUSE_NAME_RE = re.compile(
    r"if joint return,?\s*spouse.s first name.{0,40}?social security number\s*"
    r"\n?\s*([A-Za-z][^\n|]{2,60}?)\s*(?:\n|$)",
    re.I | re.DOTALL,
)


def detect_filing_status(text: str) -> str | None:
    lowered = text.lower()

    # All five status labels are always printed on Form 1040's checkbox
    # row regardless of which one is actually checked, so the mere presence
    # of e.g. "single" anywhere in the document (true of nearly every 1040,
    # OCR'd or not) can't tell us which box was marked — a naive substring
    # search over the whole document effectively always finds "single"
    # first and reports that, which is wrong far more often than not.
    #
    # A genuinely filled-in "joint return" spouse name field is a far more
    # reliable signal than the checkbox row itself: it's only ever
    # populated on a return that's actually married filing jointly.
    spouse_match = _SPOUSE_NAME_RE.search(text)
    if spouse_match:
        captured = spouse_match.group(1).strip(" .|_")
        # An empty field is immediately followed by the next printed label
        # ("Home address...") rather than an actual name — don't mistake
        # that label text itself for a filled-in spouse name.
        if captured and not captured.lower().startswith("home address"):
            return "mfj"

    # Beyond that, this is still a best-effort suggestion — the UI lets the
    # user confirm or override it — since distinguishing single / HOH / QSS
    # / MFS from text alone (with no reliable spouse-field signal) requires
    # knowing which checkbox glyph was actually marked, which a text-layer
    # or OCR pass doesn't preserve.
    for status_id, pattern in FILING_STATUS_PATTERNS:
        if re.search(pattern, lowered):
            return status_id
    return None


_FORM_1040_OMB_RE = re.compile(r"1545-0074")


def detect_tax_year_near_omb(text: str, omb_re: re.Pattern[str]) -> int | None:
    """Look for the tax year printed right next to a form's own title (e.g.
    "Form 1040 (2023)" or "U.S. Individual Income Tax Return | 2023"), which
    sits immediately before that form's own OMB control number — distinct
    from every other form/schedule's own number, so anchoring there (rather
    than just the first N characters of the whole document) avoids two
    failure modes seen on real returns: missing the year entirely on a
    return with blank cover pages ahead of the actual form, and picking up
    an unrelated year from a tax-preparer's cover letter (e.g. a payment
    due date) that can precede the form itself."""
    omb_match = omb_re.search(text)
    if omb_match:
        window = text[max(0, omb_match.start() - 200):omb_match.start()]
        matches = TAX_YEAR_RE.findall(window)
        if matches:
            return int(matches[-1])
    match = TAX_YEAR_RE.search(text[:600])
    return int(match.group(1)) if match else None


def detect_tax_year(text: str) -> int | None:
    return detect_tax_year_near_omb(text, _FORM_1040_OMB_RE)


# Telltale phrases from each form's own title, checked in this order
# against a handful of leading pages (cheap — no need to read the whole PDF
# to tell what kind of return it is). Form 1040 is the fallback rather than
# something matched here, since its title text ("U.S. Individual Income Tax
# Return") is the one already handled by the rest of this module.
_FORM_TYPE_SNIFFS: list[tuple[str, list[str]]] = [
    ("990", ["return of organization exempt from income tax"]),
    ("1120s", ["u.s. income tax return for an s corporation", "form 1120-s", "form 1120s"]),
    ("1065", ["u.s. return of partnership income", "form 1065"]),
]


def detect_form_type(pdf_bytes: bytes, page_limit: int = 10) -> str:
    """Sniffs which kind of return this PDF is, from a handful of leading
    pages only, so the caller can dispatch to the right parser before
    running a full (and more expensive) extraction pass. Defaults to
    "1040" when nothing else matches, since that's the form this module
    was built for first and the one most returns in practice will be.

    10 pages (rather than just the first 1-2) because a real return is
    often preceded by several cover pages of its own — an e-file signature
    authorization, an extension application — each printing their own OMB
    number and form title before the actual return's title ever appears; a
    return seen with this exact pattern needed 6 pages of cover material
    before its own Form 990-EZ title showed up."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages[:page_limit]).lower()
    for form_type, phrases in _FORM_TYPE_SNIFFS:
        if any(phrase in text for phrase in phrases):
            return form_type
    return "1040"


# Every official IRS form/schedule prints an "OMB No. 1545-nnnn" control
# number on its own first page, and not on continuation pages of the same
# form. That makes it a reliable, form-agnostic way to find where each
# attachment starts — Schedule D, Form 8949, Schedule E, Form 2441,
# Schedule 8812, and anything else, not just the schedules we have curated
# line definitions for. Bounding every section this way (rather than only
# looking for Schedule 1/2/3's own titles) prevents one schedule's scope
# from silently swallowing whatever comes after it in the PDF when there's
# no next *known* schedule to stop at.
_OMB_RE = re.compile(r"omb no\.?\s*1545", re.IGNORECASE)
_SCHEDULE_TITLE_RE = re.compile(r"^schedule\s+([a-z0-9]+)\b", re.IGNORECASE)
# A trailing suffix can be plain ("990T", "8889") or hyphenated ("990-EZ",
# "1120-S") — both styles appear across real tax-software PDF exports.
_BARE_FORM_NUMBER_RE = re.compile(r"^(\d{3,4}-?[a-z]{0,3})$", re.IGNORECASE)


@dataclass
class FormSection:
    title: str
    start_page: int  # 0-indexed, inclusive
    end_page: int  # 0-indexed, exclusive


# Schedule L (balance sheet), M-1, M-2, and M-3 never get their own
# OMB-numbered section boundary on a 1065/1120-S — they share the main
# form's own OMB number, same as Schedule B and K do — and unlike those,
# they can start midway down the *same physical page* Schedule K's own
# continuation is printed on, so a page-level boundary can't separate them
# either. Used to truncate a schedule's own flattened line list right
# before one of these starts, so its number-based line-matching fallback
# can't wander into e.g. Schedule M-1's own "line 2" and mistake it for
# Schedule K's "line 2" (a real bug: both share that bare number, and nothing
# but position tells them apart).
_NEXT_LETTERED_SCHEDULE_TITLE_RE = re.compile(r"^\s*schedule\s+(l\b|m-1\b|m-2\b|m-3\b)", re.IGNORECASE)


def truncate_before_next_lettered_schedule(lines: list[str]) -> list[str]:
    for i, line in enumerate(lines):
        if _NEXT_LETTERED_SCHEDULE_TITLE_RE.match(line):
            return lines[:i]
    return lines


def _section_title(page_lines: list[str]) -> str:
    non_blank = [line.strip() for line in page_lines if line.strip()]
    for i, line in enumerate(non_blank[:3]):
        m = _SCHEDULE_TITLE_RE.match(line)
        if m:
            rest = re.split(r"omb no\.?", line[m.end():].strip(), flags=re.IGNORECASE)[0].strip()
            return f"Schedule {m.group(1).upper()}" + (f" — {rest}" if rest else "")
        first_token = line.split()[0] if line.split() else ""
        if _BARE_FORM_NUMBER_RE.match(first_token):
            # The title may follow the number on this same line ("8889
            # Health Savings Accounts (HSAs)") or sit alone on the next line
            # ("2441" then "Child and Dependent Care Expenses" below it).
            rest = re.split(r"omb no\.?", line[len(first_token):].strip(), flags=re.IGNORECASE)[0].strip()
            if not rest and i + 1 < len(non_blank):
                rest = re.split(r"omb no\.?", non_blank[i + 1], flags=re.IGNORECASE)[0].strip()
                # Some forms print a lone "Form" word ahead of the title's
                # second half on this line (the rest of the title having
                # spilled onto the line *before* the number, an unusual
                # layout — e.g. Form 7203); drop the redundant word rather
                # than showing "Form 7203 — Form Debt Basis Limitations".
                rest = re.sub(r"^form\s+", "", rest, flags=re.IGNORECASE)
            return f"Form {first_token.upper()}" + (f" — {rest}" if rest else "")
    return "Additional form"


def _detect_form_sections(pages: list[str], page_lines: list[list[str]]) -> list[FormSection]:
    boundaries: list[tuple[int, str]] = []
    for i, page in enumerate(pages):
        if not _OMB_RE.search(page):
            continue
        boundaries.append((i, _section_title(page_lines[i])))

    # Consecutive pages with the same detected title (e.g. two properties on
    # separate Schedule E "page 1"s) are one logical section, not two.
    merged: list[tuple[int, str]] = []
    for start, title in boundaries:
        if merged and merged[-1][1] == title:
            continue
        merged.append((start, title))

    sections = []
    for idx, (start, title) in enumerate(merged):
        end = merged[idx + 1][0] if idx + 1 < len(merged) else len(pages)
        sections.append(FormSection(title=title, start_page=start, end_page=end))
    return sections


def _match_by_phrase(lines: list[str], phrases: list[str], known_number: str) -> float | None:
    """Locates a row by a distinctive label phrase, then reads the value off
    it (or a wrapped continuation row). The "is this bare number actually
    just this line's own echoed number" check is primarily derived from the
    anchor row's own leading token — not a hardcoded expectation of which
    number this line "should" be — since a schedule's line numbering
    genuinely shifts between tax years (e.g. Schedule 1's adjustments total
    moved from line 25 to line 26 between recent years). `known_number` (the
    line's officially-defined number) is checked too, as a second candidate:
    on OCR'd text, the same printed digits can be misread differently the
    first time (this row's own leading label) versus the second (the
    trailing echo we're trying to recognize), so the two won't always
    match even on a genuinely blank line."""
    for i, row in enumerate(lines):
        if any(phrase in row.strip().lower() for phrase in phrases):
            tokens = _tokenize(row)
            reject_numbers = {known_number.lower()}
            if tokens:
                reject_numbers.add(tokens[0].strip(".:").lower())
            value = _scan_from_anchor(lines, i, reject_numbers)
            if value is not None:
                return value
    return None


_ALPHANUMERIC_LINE_NUMBER_RE = re.compile(r"^\d{1,2}[a-z]$")


def _match_by_number(lines: list[str] | None, number: str) -> float | None:
    """Only used once phrase matching has already failed. Anchors strictly
    on the number being the row's *first* token — a genuine "this is line
    N's own label" signal — rather than the number appearing anywhere in
    the row. The looser "anywhere" (or even "first two tokens") check used
    to match a schedule's own title header (e.g. "SCHEDULE 1 ..." has "1"
    as its second token), and would then grab whatever else was printed
    nearby (like the tax year) as if it were that line's value — a
    real regression seen when this was loosened to handle OCR prepending a
    stray garbled word to some rows."""
    if lines is None:
        return None
    target = number.lower()
    for i, row in enumerate(lines):
        tokens = _tokenize(row)
        if tokens and tokens[0].strip(".:").lower() == target:
            value = _scan_from_anchor(lines, i, {target})
            if value is not None:
                return value

    # Second pass, only for alphanumeric line labels (e.g. "1z", "35a") —
    # specific enough that finding one anywhere in a row, not just as its
    # first token, is still a reliable signal (unlike a bare digit like "1",
    # which is exactly what caused the regression above). This recovers a
    # real OCR failure mode seen on a scanned return: the row's own leading
    # label got mangled or merged into the previous row's trailing garbage,
    # but the line's echoed number printed right before its value survived
    # intact.
    if _ALPHANUMERIC_LINE_NUMBER_RE.match(target):
        for i, row in enumerate(lines):
            tokens = _tokenize(row)
            for ti in range(1, len(tokens)):
                if tokens[ti].strip(".:").lower() != target:
                    continue
                # Two lines' numbers and values can be packed onto one
                # physical row (e.g. "3a 1,066| b 3b 1,180") — if the token
                # right after this one is itself an amount, that's this
                # line's own value, not whatever happens to be last on the
                # row (which could belong to a different line entirely). A
                # stray OCR'd table-border character (a misread "|") can
                # cling to that token, so it's stripped before checking.
                if ti + 1 < len(tokens):
                    candidate = tokens[ti + 1].strip("|")
                    if AMOUNT_RE.fullmatch(candidate):
                        value = _parse_amount(candidate)
                        if value is not None:
                            return value
                value = _scan_from_anchor(lines, i, {target})
                if value is not None:
                    return value
    return None


def _extract_group(
    phrase_scope: list[str],
    fallback_scope: list[str] | None,
    definitions: list[tuple[str, str, list[str], str]],
    group: str,
    via_ocr: bool = False,
) -> list[ExtractedLine]:
    results = []
    for line_id, label, phrases, fallback_number in definitions:
        value = _match_by_phrase(phrase_scope, phrases, fallback_number)
        if value is None:
            value = _match_by_number(fallback_scope, fallback_number)
        matched = value is not None
        results.append(ExtractedLine(
            id=line_id,
            label=label,
            value=value,
            # A phrase-anchored match is normally trustworthy ("matched"),
            # but OCR misreads digits often enough that even a correctly
            # *located* line shouldn't be shown with full confidence.
            confidence=("uncertain" if via_ocr else "matched") if matched else "not_found",
            group=group,
            via_ocr=via_ocr and matched,
        ))
    return results


_GENERIC_LINE_NUMBER_RE = re.compile(r"^\d{1,2}[a-z]?$", re.IGNORECASE)
_DOTTED_LEADER_RE = re.compile(r"(?:\.\s*){2,}")


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return slug or "form"


def _extract_generic_lines(lines: list[str]) -> list[tuple[str, str, float]]:
    """For a form we don't have curated line definitions for: surface any
    row that looks like its own numbered line and has a genuine trailing
    amount. Unlike the curated groups, blank/not-entered lines aren't
    reported at all here — without hand-written labels for every line on
    every possible attachment, listing dozens of blank boxes would be noise
    rather than useful detail."""
    results: list[tuple[str, str, float]] = []
    seen_numbers: set[str] = set()
    for i, row in enumerate(lines):
        tokens = _tokenize(row)
        if len(tokens) < 2:
            continue
        first_raw = tokens[0].strip(".:")
        if not _GENERIC_LINE_NUMBER_RE.match(first_raw):
            continue
        number = first_raw.lower()
        if number in seen_numbers:
            continue
        value = _scan_from_anchor(lines, i, {number})
        if value is None:
            continue
        label = _DOTTED_LEADER_RE.split(row.strip(), maxsplit=1)[0]
        label = re.sub(r"^\S+\s*", "", label, count=1).strip()
        if not label:
            label = f"Line {first_raw}"
        seen_numbers.add(number)
        results.append((first_raw, label[:120], value))
    return results


_CURATED_SCHEDULES: dict[str, tuple[list[tuple[str, str, list[str], str]], str]] = {
    "schedule a": (SCHEDULE_A_DEFINITIONS, "Schedule A (Itemized Deductions)"),
    "schedule 1": (SCHEDULE1_DEFINITIONS, "Schedule 1 (Additional Income & Adjustments)"),
    "schedule 2": (SCHEDULE2_DEFINITIONS, "Schedule 2 (Additional Taxes)"),
    "schedule 3": (SCHEDULE3_DEFINITIONS, "Schedule 3 (Additional Credits & Payments)"),
}


def parse_1040(pdf_bytes: bytes) -> ExtractionResult:
    pages = _page_texts(pdf_bytes)
    page_lines = [p.splitlines() for p in pages]
    total_pages = len(pages)

    scanned_page_indices = [i for i, rows in enumerate(page_lines) if not any(row.strip() for row in rows)]

    # Section boundaries are detected from the *original* (pre-OCR) pages,
    # before any OCR substitution below. Form 1040 itself prints an OMB
    # control number too (the same one Schedules 1/2/3 use, in fact) - as
    # long as its own page has no text layer, it naturally can't trigger a
    # false section boundary, exactly like every other scanned page. Once
    # OCR fills that page's text in, it *would* otherwise look like a new
    # attachment starting mid-return and wrongly cut the main form's scope
    # short before ever reaching its real content. Using the pre-OCR
    # snapshot for section detection keeps that boundary exactly where it
    # was, while OCR'd text is still used for the actual value extraction
    # within whatever section a page falls into.
    sections = _detect_form_sections(list(pages), [list(p) for p in page_lines])

    # OCR is slower and less reliable than a real text layer, so it's only
    # ever used to fill in pages that have literally no extractable text at
    # all — never to double-check a page that already parsed normally.
    # Pages are OCR'd concurrently (see ocr.py) since a multi-page scanned
    # return run one page at a time can take minutes.
    ocr_page_indices: set[int] = set()
    ocr_results = ocr.ocr_pages_text(pdf_bytes, scanned_page_indices)
    for i, ocr_text in ocr_results.items():
        if ocr_text.strip():
            pages[i] = ocr_text
            page_lines[i] = ocr_text.splitlines()
            ocr_page_indices.add(i)

    text = "\n".join(pages)

    result = ExtractionResult(raw_text=text)
    result.filing_status = detect_filing_status(text)
    result.tax_year = detect_tax_year(text)
    result.scanned_pages = [i + 1 for i in scanned_page_indices]
    result.ocr_pages = [i + 1 for i in sorted(ocr_page_indices)]

    def flatten(a: int, b: int) -> list[str]:
        return [line for page in page_lines[a:b] for line in page]

    def uses_ocr(a: int, b: int) -> bool:
        return any(i in ocr_page_indices for i in range(a, b))

    # Every attached form/schedule (curated or not) is bounded by the next
    # one's own first page, found generically via its OMB control number —
    # see _detect_form_sections. This is what keeps e.g. Schedule 3's scope
    # from silently running into Schedule D/Form 8949/etc. that follow it in
    # the PDF when there's no next *known* schedule to stop at.
    main_end = sections[0].start_page if sections else total_pages
    main_scope = flatten(0, main_end)
    result.lines.extend(_extract_group(main_scope, main_scope, LINE_DEFINITIONS, "Form 1040",
                                        via_ocr=uses_ocr(0, main_end)))

    curated_found: set[str] = set()
    for section in sections:
        scope = flatten(section.start_page, section.end_page)
        section_via_ocr = uses_ocr(section.start_page, section.end_page)
        curated_key = next((k for k in _CURATED_SCHEDULES if section.title.lower().startswith(k)), None)
        if curated_key:
            curated_found.add(curated_key)
            definitions, group_name = _CURATED_SCHEDULES[curated_key]
            result.lines.extend(_extract_group(scope, scope, definitions, group_name, via_ocr=section_via_ocr))
        else:
            # No hand-written line definitions for this form (Schedule D,
            # Form 8949, Schedule E, Form 2441, etc.) — surface whatever
            # numbered lines it actually has values on generically, under
            # its own detected title, rather than not showing it at all.
            for number, label, value in _extract_generic_lines(scope):
                result.lines.append(ExtractedLine(
                    id=f"{_slugify(section.title)}_{number}",
                    label=label,
                    value=value,
                    confidence="uncertain",
                    group=section.title,
                    via_ocr=section_via_ocr,
                ))

    # A curated schedule with no detected page at all is simply absent from
    # this return (e.g. no Schedule 2 needed this year) — report its lines
    # as not_found rather than silently omitting them, so the review UI
    # still shows the option to fill them in by hand.
    for key, (definitions, group_name) in _CURATED_SCHEDULES.items():
        if key not in curated_found:
            result.lines.extend(_extract_group([], None, definitions, group_name))

    return result
