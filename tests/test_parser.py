import io
import sys
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.parser import parse_1040  # noqa: E402


def make_pdf(rows: list[tuple[str, str]]) -> bytes:
    """Build a one-page PDF with each (label, amount) pair on its own row,
    label starting at the left margin and amount right-aligned — mimicking
    how a fillable Form 1040 lays out its lines."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    y = 750
    for label, amount in rows:
        c.setFont("Helvetica", 10)
        c.drawString(50, y, label)
        if amount:
            c.drawRightString(500, y, amount)
        y -= 20
    c.save()
    return buf.getvalue()


SAMPLE_ROWS = [
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


def test_parses_known_lines():
    pdf_bytes = make_pdf(SAMPLE_ROWS)
    result = parse_1040(pdf_bytes)
    values = result.as_value_map()

    assert values["1z"] == 65000
    assert values["2b"] == 150
    assert values["9"] == 65150
    assert values["11"] == 65150
    assert values["12"] == 13850
    assert values["15"] == 51300
    assert values["16"] == 5845
    assert values["24"] == 5845
    assert values["25d"] == 7000
    assert values["33"] == 7000
    assert values["34"] == 1155
    assert values["35a"] == 1155

    assert result.filing_status == "single"


def test_missing_lines_are_flagged_not_found():
    pdf_bytes = make_pdf([("1z Add lines 1a through 1h. Total is your total wages", "40,000")])
    result = parse_1040(pdf_bytes)
    by_id = {ln.id: ln for ln in result.lines}
    assert by_id["1z"].confidence == "matched"
    assert by_id["27"].confidence == "not_found"
    assert by_id["27"].value is None
