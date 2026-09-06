import io
import sys
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.parser import parse_1040  # noqa: E402


def make_pdf(pages: list[list[tuple[str, str]]]) -> bytes:
    """Build a multi-page PDF; each page is a list of (label, amount) rows,
    label starting at the left margin and amount right-aligned — mimicking
    how a fillable Form 1040 (and its schedules) lay out their lines."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for rows in pages:
        y = 750
        for label, amount in rows:
            c.setFont("Helvetica", 10)
            c.drawString(50, y, label)
            if amount:
                c.drawRightString(500, y, amount)
            y -= 20
        c.showPage()
    c.save()
    return buf.getvalue()


MAIN_PAGE = [
    ("Form 1040 (2023) U.S. Individual Income Tax Return", ""),
    ("Filing Status: Single", ""),
    ("1z  Add lines 1a through 1h. Total is your total wages", "65,000"),
    ("2b  Taxable interest", "150"),
    ("9   Total income. Add lines 1z through 8", "65,150"),
    ("10  Adjustments to income", "0"),
    ("11  Adjusted gross income. Subtract line 10 from line 9", "65,150"),
    ("12  Standard deduction or itemized deductions", "13,850"),
    ("14  Add lines 12 and 13", "13,850"),
    ("15  Taxable income. Subtract line 14 from line 11", "51,300"),
    ("16  Tax (see instructions)", "5,845"),
    ("18  Add lines 16 and 17", "5,845"),
    ("22  Subtract line 21 from line 18", "5,845"),
    ("24  Total tax", "5,845"),
    ("25d Add lines 25a through 25c. Total is your total federal income tax withheld", "7,000"),
    ("33  Total payments", "7,000"),
    ("34  Overpaid. If line 33 is more than line 24, subtract", "1,155"),
    ("35a Amount of line 34 you want refunded to you", "1,155"),
]

SCHEDULE1_PAGE = [
    ("SCHEDULE 1  Additional Income and Adjustments to Income  OMB No. 1545-0074", ""),
    ("(Form 1040)  2023", ""),
    ("1  Taxable refunds, credits, or offsets of state and local income taxes", "0"),
    ("3  Business income or (loss). Attach Schedule C", "12,000"),
    ("7  Unemployment compensation", "2,000"),
    ("9  Add lines 1 through 8. This is your total other income", "14,000"),
    ("10 Total additional income", "14,000"),
    ("25 Add lines 11 through 23. These are your total adjustments", "500"),
]

SCHEDULE2_PAGE = [
    ("SCHEDULE 2  Additional Taxes  OMB No. 1545-0074", ""),
    ("(Form 1040)  2023", ""),
    ("4  Self-employment tax. Attach Schedule SE", "1,695"),
    ("21 Add lines 4 through 18. These are your total other taxes", "1,695"),
]


def test_parses_main_form_lines_and_metadata():
    pdf_bytes = make_pdf([MAIN_PAGE])
    result = parse_1040(pdf_bytes)
    values = result.as_value_map()

    assert values["1z"] == 65000
    assert values["9"] == 65150
    assert values["11"] == 65150
    assert values["15"] == 51300
    assert values["16"] == 5845
    assert values["24"] == 5845
    assert values["33"] == 7000
    assert values["34"] == 1155

    assert result.filing_status == "single"
    assert result.tax_year == 2023


def test_missing_lines_are_flagged_not_found():
    pdf_bytes = make_pdf([[("1z Add lines 1a through 1h. Total is your total wages", "40,000")]])
    result = parse_1040(pdf_bytes)
    by_id = {ln.id: ln for ln in result.lines}
    assert by_id["1z"].confidence == "matched"
    assert by_id["27"].confidence == "not_found"
    assert by_id["27"].value is None


def test_schedules_are_extracted_and_scoped_by_page():
    pdf_bytes = make_pdf([MAIN_PAGE, SCHEDULE1_PAGE, SCHEDULE2_PAGE])
    result = parse_1040(pdf_bytes)
    by_id = {ln.id: ln for ln in result.lines}

    # Schedule 1's own "line 1" shouldn't be confused with the main form's
    # line 1z, Schedule 2's line 4, or vice versa.
    assert by_id["s1_3"].value == 12000
    assert by_id["s1_7"].value == 2000
    assert by_id["s1_10"].value == 14000
    assert by_id["s2_4"].value == 1695
    assert by_id["s2_21"].value == 1695

    # Main form values still resolve correctly with schedules present.
    assert by_id["1z"].value == 65000
    assert by_id["24"].value == 5845

    groups = {ln.id: ln.group for ln in result.lines}
    assert groups["s1_3"] == "Schedule 1 (Additional Income & Adjustments)"
    assert groups["s2_4"] == "Schedule 2 (Additional Taxes)"


def test_schedule_lines_not_present_are_not_found_not_guessed():
    # No Schedule 3 page at all -> every s3_* line should be not_found,
    # never accidentally matched against Schedule 1/2 content.
    pdf_bytes = make_pdf([MAIN_PAGE, SCHEDULE1_PAGE, SCHEDULE2_PAGE])
    result = parse_1040(pdf_bytes)
    by_id = {ln.id: ln for ln in result.lines}
    for line_id in ("s3_1", "s3_8", "s3_13"):
        assert by_id[line_id].confidence == "not_found"
        assert by_id[line_id].value is None


def make_raw_pdf(pages: list[list[str]]) -> bytes:
    """Like make_pdf, but each page is a list of full row strings drawn
    verbatim — used to replicate the real IRS PDF convention of a dotted
    leader ". . . . ." running from the label to a trailing line-number/
    value, all as one string, rather than two separately-positioned runs."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for rows in pages:
        y = 750
        for row in rows:
            c.setFont("Helvetica", 9)
            c.drawString(50, y, row)
            y -= 20
        c.showPage()
    c.save()
    return buf.getvalue()


DOTTED_SCHEDULE1_PAGE = [
    "SCHEDULE 1  Additional Income and Adjustments to Income  OMB No. 1545-0074",
    "(Form 1040)  2023",
    "1  Taxable refunds, credits, or offsets of state and local income taxes . . . . . . . . . . . . . . . 1",
    "3  Business income or (loss). Attach Schedule C . . . . . . . . . . . . . . . . . . . . . . . . . . . 3",
]

DOTTED_SCHEDULE3_PAGE = [
    "SCHEDULE 3  Additional Credits and Payments  OMB No. 1545-0074",
    "(Form 1040)  2023",
    "2  Credit for child and dependent care expenses from Form 2441, line 11. Attach",
    "   Form 2441 . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2 1,200.",
    "3  Education credits from Form 8863, line 19 . . . . . . . . . . . . . . . . . . . . . . . . . . . . 3",
]


def test_unfilled_line_with_echoed_number_is_not_found_not_the_number_itself():
    # Real IRS PDFs reprint a blank line's own number right after its
    # dotted leader when nothing was entered - that echo must not be read
    # back as if it were a $1 (or $3) entry.
    pdf_bytes = make_raw_pdf([DOTTED_SCHEDULE1_PAGE])
    result = parse_1040(pdf_bytes)
    by_id = {ln.id: ln for ln in result.lines}
    assert by_id["s1_1"].confidence == "not_found"
    assert by_id["s1_1"].value is None
    assert by_id["s1_3"].confidence == "not_found"
    assert by_id["s1_3"].value is None


def test_wrapped_label_finds_value_on_continuation_row_not_the_referenced_form_number():
    # The label for line 2 wraps onto a second physical row that starts
    # with "Form 2441" (a cross-reference, not the amount column) before
    # the real "2  1,200." pair - naive "last numeric token in the label
    # row" scanning used to grab the "2441" form number instead.
    pdf_bytes = make_raw_pdf([DOTTED_SCHEDULE3_PAGE])
    result = parse_1040(pdf_bytes)
    by_id = {ln.id: ln for ln in result.lines}
    assert by_id["s3_2"].value == 1200
    assert by_id["s3_2"].confidence == "matched"
    # Line 3 on the same page is genuinely blank - shouldn't pick up 1200
    # (or anything else) by spilling over from line 2's row.
    assert by_id["s3_3"].confidence == "not_found"


def test_absent_schedule_never_searches_unrelated_later_pages():
    # No Schedule 2 in this document at all - its lines must stay
    # not_found rather than falling back to a whole-document search that
    # could pick up an incidental phrase match on Schedule 3's own page.
    pdf_bytes = make_raw_pdf([DOTTED_SCHEDULE1_PAGE, DOTTED_SCHEDULE3_PAGE])
    result = parse_1040(pdf_bytes)
    by_id = {ln.id: ln for ln in result.lines}
    for line_id in ("s2_1", "s2_4", "s2_21"):
        assert by_id[line_id].confidence == "not_found"
        assert by_id[line_id].value is None


UNCURATED_SCHEDULE_D_PAGE = [
    "SCHEDULE D  Capital Gains and Losses  OMB No. 1545-0074",
    "(Form 1040)  2023",
    "7  Net short-term capital gain or (loss) . . . . . . . . . . . . . . . . . . . . . . . . . . . 7 500.",
    "16 Combine lines 7 and 15 . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 16 500.",
]


def test_uncurated_schedule_d_is_surfaced_as_uncertain():
    # We have no hand-written line definitions for Schedule D, but it
    # should still show up (per the user's request that every attached
    # form be visible), marked as lower-confidence "uncertain" rather than
    # silently omitted or claimed with full confidence. MAIN_PAGE uses
    # (label, amount) tuples while the Schedule D page uses raw dotted-
    # leader rows, so this builds the PDF directly rather than reusing
    # make_pdf/make_raw_pdf.
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    y = 750
    for label, amount in MAIN_PAGE:
        c.setFont("Helvetica", 10)
        c.drawString(50, y, label)
        if amount:
            c.drawRightString(500, y, amount)
        y -= 20
    c.showPage()
    y = 750
    for row in UNCURATED_SCHEDULE_D_PAGE:
        c.setFont("Helvetica", 9)
        c.drawString(50, y, row)
        y -= 20
    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()

    result = parse_1040(pdf_bytes)
    schedule_d_lines = [ln for ln in result.lines if ln.group.startswith("Schedule D")]
    assert schedule_d_lines, "Schedule D should be detected even without curated definitions"
    assert all(ln.confidence == "uncertain" for ln in schedule_d_lines)
    values = {ln.id: ln.value for ln in schedule_d_lines}
    assert 500 in values.values()


def test_scanned_image_only_page_is_reported():
    # A page with literally no extractable text (e.g. a scanned Form 1040
    # summary) should be flagged so the UI can explain why its lines are
    # all not_found, instead of leaving that a silent mystery.
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.showPage()  # first page: entirely blank, no text at all
    c.setFont("Helvetica", 10)
    c.drawString(50, 750, "SCHEDULE 1  Additional Income and Adjustments to Income  OMB No. 1545-0074")
    c.showPage()
    c.save()
    result = parse_1040(buf.getvalue())
    assert result.scanned_pages == [1]
