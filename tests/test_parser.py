import io
import sys
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.parser import parse_1040, detect_filing_status, detect_tax_year  # noqa: E402


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

SCHEDULE_A_PAGE = [
    ("SCHEDULE A  Itemized Deductions  OMB No. 1545-0074", ""),
    ("(Form 1040)  2023", ""),
    ("1  Medical and dental expenses", "5,000"),
    ("4  Subtract line 3 from line 1", "0"),
    ("5e Smaller of line 5d or $10,000", "10,000"),
    ("7  Total taxes. Add lines 5e and 6", "10,000"),
    ("8e Add lines 8a through 8c", "18,000"),
    ("10 Total interest. Add lines 8e and 9", "18,000"),
    ("14 Gifts to charity. Add lines 11 through 13", "4,000"),
    ("17 Total itemized deductions", "32,000"),
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


def test_schedule_a_itemized_deductions_are_extracted_and_scoped():
    pdf_bytes = make_pdf([MAIN_PAGE, SCHEDULE_A_PAGE])
    result = parse_1040(pdf_bytes)
    by_id = {ln.id: ln for ln in result.lines}

    assert by_id["sa_1"].value == 5000
    assert by_id["sa_5e"].value == 10000
    assert by_id["sa_8e"].value == 18000
    assert by_id["sa_14"].value == 4000
    assert by_id["sa_17"].value == 32000
    assert by_id["sa_15"].confidence == "not_found"  # no casualty loss on this return
    assert by_id["sa_1"].group == "Schedule A (Itemized Deductions)"


def test_schedule_a_not_present_is_not_found_when_standard_deduction_used():
    # No Schedule A page at all -> every sa_* line should be not_found,
    # the same graceful-degradation behavior as Schedule 1/2/3.
    pdf_bytes = make_pdf([MAIN_PAGE])
    result = parse_1040(pdf_bytes)
    by_id = {ln.id: ln for ln in result.lines}
    assert by_id["sa_17"].confidence == "not_found"
    assert by_id["sa_17"].value is None


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


def test_ocr_misread_leading_digit_still_recognizes_blank_echo():
    # OCR can misread the same printed line number differently the two
    # times it appears on a row: once as the leading label ("10" -> "4Q")
    # and once as the trailing echo on a blank line (still "10", correctly
    # read the second time). Recognizing that echo as "line 10 was left
    # blank" needs the line's officially-known number as a second
    # candidate, not just what OCR read on this specific row's own label.
    from backend.parser import _match_by_phrase  # noqa: PLC0415

    lines = ["4Q Adjustments to income from Schedule 1, line 26 . 10"]
    value = _match_by_phrase(lines, ["adjustments to income"], "10")
    assert value is None


UNCURATED_SCHEDULE_J_PAGE = [
    "SCHEDULE J  Income Averaging for Farmers and Fishermen  OMB No. 1545-0074",
    "(Form 1040)  2023",
    "1  Taxable income . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 1 500.",
    "23 Tax. Add lines 12, 18, and 22 . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 23 500.",
]


def test_uncurated_schedule_j_is_surfaced_as_uncertain():
    # We have no hand-written line definitions for Schedule J, but it
    # should still show up (per the user's request that every attached
    # form be visible), marked as lower-confidence "uncertain" rather than
    # silently omitted or claimed with full confidence. MAIN_PAGE uses
    # (label, amount) tuples while the Schedule J page uses raw dotted-
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
    for row in UNCURATED_SCHEDULE_J_PAGE:
        c.setFont("Helvetica", 9)
        c.drawString(50, y, row)
        y -= 20
    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()

    result = parse_1040(pdf_bytes)
    schedule_j_lines = [ln for ln in result.lines if ln.group.startswith("Schedule J")]
    assert schedule_j_lines, "Schedule J should be detected even without curated definitions"
    assert all(ln.confidence == "uncertain" for ln in schedule_j_lines)
    values = {ln.id: ln.value for ln in schedule_j_lines}
    assert 500 in values.values()


SCHEDULE_B_PAGE = [
    ("SCHEDULE B  Interest and Ordinary Dividends  OMB No. 1545-0074", ""),
    ("(Form 1040)  2023", ""),
    ("4  Subtract line 3 from line 2. Enter the result here and on Form 1040, line 2b", "500"),
    ("6  Add the amounts on line 5. Enter the total here and on Form 1040, line 3b", "300"),
]

SCHEDULE_C_PAGE = [
    ("SCHEDULE C  Profit or Loss From Business  OMB No. 1545-0074", ""),
    ("(Form 1040)  2023", ""),
    ("1  Gross receipts or sales", "50,000"),
    ("4  Cost of goods sold", "10,000"),
    ("5  Gross profit. Subtract line 4 from line 3", "40,000"),
    ("7  Gross income. Add lines 5 and 6", "40,000"),
    ("28 Total expenses before expenses for business use of home. Add lines 8 through 27a", "20,000"),
    ("31 Net profit or (loss). Subtract line 30 from line 29", "20,000"),
]

SCHEDULE_D_PAGE = [
    ("SCHEDULE D  Capital Gains and Losses  OMB No. 1545-0074", ""),
    ("(Form 1040)  2023", ""),
    ("7  Net short-term capital gain or (loss)", "500"),
    ("15 Net long-term capital gain or (loss)", "1,000"),
    ("16 Combine lines 7 and 15", "1,500"),
]

SCHEDULE_E_PAGE = [
    ("SCHEDULE E  Supplemental Income and Loss  OMB No. 1545-0074", ""),
    ("(Form 1040)  2023", ""),
    ("26 Total rental real estate and royalty income or (loss)", "3,000"),
    ("32 Total partnership and S corporation income or (loss)", "2,000"),
    ("41 Total income or (loss). Combine lines 26, 32, 37, 39, and 40", "5,000"),
]

SCHEDULE_SE_PAGE = [
    ("SCHEDULE SE  Self-Employment Tax  OMB No. 1545-0074", ""),
    ("(Form 1040)  2023", ""),
    ("2  Net profit or (loss) from Schedule C", "20,000"),
    ("3  Combine lines 1a, 1b, and 2", "20,000"),
    ("6  Combine lines 4c and 5b", "18,470"),
    ("10 Multiply the smaller of line 6 or line 9 by 12.4%", "2,290"),
    ("11 Multiply line 6 by 2.9%", "536"),
    ("12 Self-employment tax. Add lines 10 and 11", "2,826"),
    ("13 Deduction for one-half of self-employment tax", "1,413"),
]


def test_schedules_b_c_d_e_se_are_curated_and_scoped():
    pdf_bytes = make_pdf([
        MAIN_PAGE, SCHEDULE_B_PAGE, SCHEDULE_C_PAGE, SCHEDULE_D_PAGE, SCHEDULE_E_PAGE, SCHEDULE_SE_PAGE,
    ])
    result = parse_1040(pdf_bytes)
    by_id = {ln.id: ln for ln in result.lines}

    assert by_id["sb_4"].value == 500
    assert by_id["sb_6"].value == 300
    assert by_id["sb_4"].confidence == "matched"
    assert by_id["sb_4"].group == "Schedule B (Interest & Ordinary Dividends)"

    assert by_id["sc_1"].value == 50000
    assert by_id["sc_4"].value == 10000
    assert by_id["sc_5"].value == 40000
    assert by_id["sc_28"].value == 20000
    assert by_id["sc_31"].value == 20000
    assert by_id["sc_31"].group == "Schedule C (Profit or Loss From Business)"

    assert by_id["sd_7"].value == 500
    assert by_id["sd_15"].value == 1000
    assert by_id["sd_16"].value == 1500
    assert by_id["sd_16"].group == "Schedule D (Capital Gains & Losses)"

    assert by_id["se_26"].value == 3000
    assert by_id["se_32"].value == 2000
    assert by_id["se_41"].value == 5000
    assert by_id["se_41"].group == "Schedule E (Rental, Royalty & Passthrough Income)"

    assert by_id["sse_2"].value == 20000
    assert by_id["sse_6"].value == 18470
    assert by_id["sse_10"].value == 2290
    assert by_id["sse_11"].value == 536
    assert by_id["sse_12"].value == 2826
    assert by_id["sse_13"].value == 1413
    assert by_id["sse_12"].group == "Schedule SE (Self-Employment Tax)"

    # Main form still resolves correctly alongside five extra schedules.
    assert by_id["1z"].value == 65000


def test_schedule_e_income_flows_into_schedule_1_line_5():
    pdf_bytes = make_pdf([MAIN_PAGE, SCHEDULE1_PAGE])
    result = parse_1040(pdf_bytes)
    by_id = {ln.id: ln for ln in result.lines}
    # No line 5 on this SCHEDULE1_PAGE fixture -> not_found, not silently
    # absent, confirming s1_5 is now a real tracked line.
    assert by_id["s1_5"].confidence == "not_found"


SCHEDULE_F_PAGE = [
    ("SCHEDULE F  Profit or Loss From Farming  OMB No. 1545-0074", ""),
    ("(Form 1040)  2023", ""),
    ("9  Gross income. Add amounts in the right column", "40,000"),
    ("14 Depreciation and section 179 expense", "6,000"),
    ("34 Total expenses. Add lines 10 through 32f", "25,000"),
    ("35 Net farm profit or (loss). Subtract line 34 from line 9", "15,000"),
]

FORM_4562_PAGE = [
    ("4562  Depreciation and Amortization  OMB No. 1545-0172", ""),
    ("Department of the Treasury  2023", ""),
    ("12 Section 179 expense deduction. Add lines 9 and 10", "4,000"),
    ("14 Special depreciation allowance for qualified property", "1,000"),
    ("17 MACRS deductions for assets placed in service in earlier years", "1,000"),
    ("22 Enter here and on the appropriate lines of your return", "6,000"),
]


def test_schedule_f_and_form_4562_are_curated_and_scoped():
    pdf_bytes = make_pdf([MAIN_PAGE, SCHEDULE_F_PAGE, FORM_4562_PAGE])
    result = parse_1040(pdf_bytes)
    by_id = {ln.id: ln for ln in result.lines}

    assert by_id["sf_9"].value == 40000
    assert by_id["sf_14"].value == 6000
    assert by_id["sf_34"].value == 25000
    assert by_id["sf_35"].value == 15000
    assert by_id["sf_35"].confidence == "matched"
    assert by_id["sf_35"].group == "Schedule F (Profit or Loss From Farming)"

    assert by_id["f4562_12"].value == 4000
    assert by_id["f4562_14"].value == 1000
    assert by_id["f4562_17"].value == 1000
    assert by_id["f4562_22"].value == 6000
    assert by_id["f4562_22"].group == "Form 4562 (Depreciation and Amortization)"

    # No line 6 on SCHEDULE1_PAGE elsewhere -> confirm s1_6 (farm income) is
    # a real tracked line, not silently absent, same as s1_5.
    assert "s1_6" in {ln.id for ln in result.lines}


def test_schedule_c_depreciation_line_is_curated():
    pdf_bytes = make_pdf([MAIN_PAGE, SCHEDULE_C_PAGE])
    result = parse_1040(pdf_bytes)
    by_id = {ln.id: ln for ln in result.lines}
    # sc_13 (depreciation) isn't on the SCHEDULE_C_PAGE fixture -> not_found
    # rather than silently missing, confirming it's now a real tracked line
    # (the row Form 4562's own drill-down nests under).
    assert by_id["sc_13"].confidence == "not_found"


SCHEDULE_H_PAGE = [
    ("SCHEDULE H  Household Employment Taxes  OMB No. 1545-0074", ""),
    ("(Form 1040)  2023", ""),
    ("9  Total social security, Medicare, and federal income taxes. Add lines 3, 5, 7, and 8", "3,500"),
    ("26 Total household employment taxes", "3,800"),
]

FORM_8863_PAGE = [
    ("8863  Education Credits  OMB No. 1545-0074", ""),
    ("Department of the Treasury  2023", ""),
    ("8  Refundable American Opportunity Credit", "1,000"),
    ("19 Nonrefundable education credits", "1,500"),
]


def test_schedule_h_and_form_8863_are_curated_and_scoped():
    pdf_bytes = make_pdf([MAIN_PAGE, SCHEDULE2_PAGE, SCHEDULE_H_PAGE, FORM_8863_PAGE])
    result = parse_1040(pdf_bytes)
    by_id = {ln.id: ln for ln in result.lines}

    assert by_id["sh_9"].value == 3500
    assert by_id["sh_26"].value == 3800
    assert by_id["sh_26"].confidence == "matched"
    assert by_id["sh_26"].group == "Schedule H (Household Employment Taxes)"

    assert by_id["f8863_8"].value == 1000
    assert by_id["f8863_19"].value == 1500
    assert by_id["f8863_19"].group == "Form 8863 (Education Credits)"

    # s2_9 (household employment taxes) isn't on SCHEDULE2_PAGE's fixture ->
    # not_found rather than silently absent, confirming it's a real tracked
    # line (the row Schedule H's own drill-down hangs off of).
    assert by_id["s2_9"].confidence == "not_found"


def test_line_29_american_opportunity_credit_is_tracked():
    pdf_bytes = make_pdf([MAIN_PAGE])
    result = parse_1040(pdf_bytes)
    by_id = {ln.id: ln for ln in result.lines}
    # Not on MAIN_PAGE's fixture -> not_found rather than silently missing.
    assert by_id["29"].confidence == "not_found"


DOTTED_SCHEDULE2_VALUE_ON_NEXT_ROW_PAGE = [
    "SCHEDULE 2  Additional Taxes  OMB No. 1545-0074",
    "(Form 1040)  2023",
    "1  Alternative minimum tax. Attach Form 6251 . . . . . . . . . . . . . . . . . . . . . . . . . . 1",
    "                                                                               0",
    "2  Excess advance premium tax credit repayment. Attach Form 8962 . . . . . . . . . . 2",
    "3  Add lines 1 and 2. Enter here and on Form 1040, line 17 . . . . . . . . . . . . . . . . 3",
    "                                                                               0",
]


def test_value_printed_alone_on_the_row_after_the_echoed_number():
    # A third real-world layout: the label row *always* ends in the line's
    # own echoed number (filled or not), and an entered value - even an
    # explicit "0" - is printed by itself on the very next row rather than
    # sharing the label row. Line 2 here has no such follow-up row at all
    # (genuinely blank), and line 3's label row is what follows line 2's
    # echo - neither should be mistaken for line 1's value, and line 3
    # should still correctly find its own "0" one row further down.
    pdf_bytes = make_raw_pdf([DOTTED_SCHEDULE2_VALUE_ON_NEXT_ROW_PAGE])
    result = parse_1040(pdf_bytes)
    by_id = {ln.id: ln for ln in result.lines}
    assert by_id["s2_1"].value == 0
    assert by_id["s2_1"].confidence == "matched"
    assert by_id["s2_2"].confidence == "not_found"
    assert by_id["s2_3"].value == 0
    assert by_id["s2_3"].confidence == "matched"


def test_amount_split_by_a_stray_space_after_the_comma_is_reassembled():
    # OCR occasionally renders a thousands-separator comma with a space
    # right after it, splitting a real amount like "51,808" into two words
    # "51," and "808". Reading only the last token would silently truncate
    # the real value down to $808.
    from backend.parser import _tokenize  # noqa: PLC0415

    assert _tokenize("8  Other income from Schedule 1 8 51, 808") == \
        ["8", "Other", "income", "from", "Schedule", "1", "8", "51,808"]
    # A number with two comma groups (over $1,000,000) should reassemble
    # the same way, not just the last split.
    assert _tokenize("9 Total income 9 1, 234, 567") == \
        ["9", "Total", "income", "9", "1,234,567"]
    # An ordinary already-clean amount must pass through unchanged.
    assert _tokenize("11 AGI 11 226,470") == ["11", "AGI", "11", "226,470"]


def test_reassembled_split_amount_is_extracted_correctly():
    pdf_bytes = make_raw_pdf([[
        "SCHEDULE 1  Additional Income and Adjustments to Income  OMB No. 1545-0074",
        "(Form 1040)  2023",
        "9  Add lines 1 through 8. This is your total other income . 9 51, 808",
    ]])
    result = parse_1040(pdf_bytes)
    by_id = {ln.id: ln for ln in result.lines}
    assert by_id["s1_9"].value == 51808


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


def test_filing_status_not_naively_single_when_spouse_field_is_filled():
    # Form 1040's filing status checkbox row always prints all five status
    # labels ("Single Married filing jointly Married filing separately ...")
    # regardless of which is actually checked, so a naive substring search
    # for "single" anywhere in the document would always match — the real
    # tell is whether the joint-return spouse name field further down is
    # actually filled in, which only ever happens on a joint return.
    text = (
        "Filing Status Single Married filing jointly Married filing separately (MFS) "
        "Head of household (HOH) Qualifying surviving spouse (QSS)\n"
        "Your first name and middle initial Last name Your social security number\n"
        "Christopher A Johnson\n"
        "If joint return, spouse's first name and middle initial Last name Spouse's social security number\n"
        "Kimberly R Johnson\n"
    )
    assert detect_filing_status(text) == "mfj"


def test_filing_status_falls_back_to_checkbox_labels_when_spouse_field_is_blank():
    text = (
        "Filing Status Single Married filing jointly Married filing separately (MFS) "
        "Head of household (HOH) Qualifying surviving spouse (QSS)\n"
        "Your first name and middle initial Last name Your social security number\n"
        "Christopher A Johnson\n"
        "If joint return, spouse's first name and middle initial Last name Spouse's social security number\n"
        "Home address (number and street).\n"
    )
    assert detect_filing_status(text) == "single"


def test_tax_year_found_past_blank_cover_pages():
    # Some tax-software exports put several blank/cover pages before the
    # actual Form 1040 — scanning only the first 600 characters of the
    # whole document would miss the year entirely in that case.
    text = "\n".join([" " * 40] * 30) + "\nU.S. Individual Income Tax Return 2022\nOMB No. 1545-0074\n"
    assert detect_tax_year(text) == 2022


def test_tax_year_not_confused_by_preparer_cover_letter_date():
    # A preparer's cover letter ahead of the actual Form 1040 can mention
    # an unrelated year (e.g. a payment due date the following spring) —
    # the real tax year should still come from right next to Form 1040's
    # own OMB number, not whichever year appears first in the document.
    text = (
        "Your payment was due on April 15, 2024. Thank you for the opportunity "
        "to be of service.\n\n"
        "1040 U.S. Individual Income Tax Return | 2023\nOMB No. 1545-0074\n"
    )
    assert detect_tax_year(text) == 2023


def test_alphanumeric_line_number_found_when_its_own_leading_label_is_garbled():
    # Real OCR failure mode: the row's own leading label ("z Add lines 1a
    # through 1h") got mangled and lost its leading "1" (merged into the
    # previous row's trailing garbage instead), but the line's echoed
    # number printed right before its value survived intact.
    pdf_bytes = make_pdf([[
        ("h Other earned income (see instructions) . . 1h", ""),
        ("i Nontaxable combat pay election (see instructions) ........22058 1i", ""),
        ("z Addlinestathroughth . 2 . eee ee 1z", "156,589"),
        ("2a Tax-exempt interest . . . 2a  b Taxable interest ......... 2b", "497"),
    ]])
    result = parse_1040(pdf_bytes)
    by_id = {ln.id: ln for ln in result.lines}
    assert by_id["1z"].value == 156589


def test_two_lines_values_on_one_row_are_not_confused():
    # Some scanned layouts pack two lines' numbers and values onto a single
    # physical row (e.g. "3a 1,066 b 3b 1,180") — each should get its own
    # value, not whichever one happens to be last on the row.
    pdf_bytes = make_pdf([[
        ("if required. Qualified dividendz ..... 3a 1,066| b Ordinary dividendz ........ 3b", "1,180"),
    ]])
    result = parse_1040(pdf_bytes)
    by_id = {ln.id: ln for ln in result.lines}
    assert by_id["3a"].value == 1066
    assert by_id["3b"].value == 1180
