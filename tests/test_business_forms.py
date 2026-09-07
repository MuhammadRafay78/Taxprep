import io
import sys
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.parser import detect_form_type  # noqa: E402
from backend.parser_990 import parse_990  # noqa: E402
from backend.parser_1065 import parse_1065  # noqa: E402
from backend.parser_1120s import parse_1120s  # noqa: E402
from backend.explain_990 import build_flags_990, build_computation_990  # noqa: E402
from backend.explain_1065 import build_flags_1065, build_computation_1065  # noqa: E402
from backend.explain_1120s import build_flags_1120s, build_computation_1120s  # noqa: E402


def make_pdf(pages: list[list[tuple[str, str]]]) -> bytes:
    """Same fixture-building approach as test_parser.py's make_pdf: each
    page is a list of (label, amount) rows, label at the left margin and
    amount right-aligned, mimicking a fillable form's own layout."""
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


# --- Form 990-EZ ---

FORM_990_MAIN_PAGE = [
    ("Short Form  OMB No. 1545-0047", ""),
    ("990-EZ", ""),
    ("Return of Organization Exempt From Income Tax  2024", ""),
    ("1  Contributions, gifts, grants, and similar amounts received", "26,957"),
    ("9  Total revenue. Add lines 1, 2, 3, 4, 5c, 6d, 7c, and 8", "26,957"),
    ("16 Other expenses (describe in Schedule O)", "2,621"),
    ("17 Total expenses. Add lines 10 through 16", "2,621"),
    ("18 Excess or (deficit) for the year", "24,336"),
    ("19 Net assets or fund balances at beginning of year", "0"),
    ("21 Net assets or fund balances at end of year", "24,336"),
]


def test_990_parses_main_form_lines_and_tax_year():
    pdf_bytes = make_pdf([FORM_990_MAIN_PAGE])
    result = parse_990(pdf_bytes)
    values = {ln.id: ln.value for ln in result.lines if ln.value is not None}
    assert values["1"] == 26957
    assert values["9"] == 26957
    assert values["17"] == 2621
    assert values["18"] == 24336
    assert values["21"] == 24336
    assert result.tax_year == 2024


def test_990_flags_mismatched_excess_deficit():
    values = {"9": 26957, "17": 2621, "18": 999}
    flags = build_flags_990(values)
    assert any("Excess/deficit" in f.message for f in flags)


def test_990_computation_sections_are_generic_shape():
    values = {"1": 26957, "9": 26957, "17": 2621, "18": 24336, "19": 0, "21": 24336}
    comp = build_computation_990(values, None, 2024)
    assert "sections" in comp
    assert comp["tax_computation"] is None
    assert comp["header"]["result_amount"] == 24336


def test_detect_form_type_finds_990():
    pdf_bytes = make_pdf([FORM_990_MAIN_PAGE])
    assert detect_form_type(pdf_bytes) == "990"


# --- Form 1065 ---

FORM_1065_SCHEDULE_K_PAGE = [
    ("Form 1065 (2024) Page 3  OMB No. 1545-0123", ""),
    ("Schedule K  Partners' Distributive Share Items  Total amount", ""),
    ("1  Ordinary business income (loss) (page 1, line 22)", "-4,577"),
    ("2  Net rental real estate income (loss)  . . . . . . . . . . . . . . 2", ""),
    ("5  Interest income", "2"),
    ("14a Net earnings (loss) from self-employment", "-4,577"),
]

# A same-page-shared-OMB-number Schedule M-1 immediately follows Schedule K
# in real returns and reuses bare line numbers like "2" for something
# completely unrelated — this regression-tests the fix that keeps Schedule
# K's own number-based fallback matching from wandering into it.
FORM_1065_SCHEDULE_M1_PAGE = [
    ("Schedule M-1  Reconciliation of Income (Loss) per Books With Income (Loss) per Return", ""),
    ("2  Income included on Schedule K, lines 1, 2, 3c, 4, 5a, 6, 7, on Schedule K, lines 1 through 10 (itemize):", ""),
]


def test_1065_schedule_k_values_and_m1_boundary():
    pdf_bytes = make_pdf([FORM_1065_SCHEDULE_K_PAGE, FORM_1065_SCHEDULE_M1_PAGE])
    result = parse_1065(pdf_bytes)
    values = {ln.id: ln.value for ln in result.lines
              if ln.value is not None and "Schedule K" in ln.group}
    assert values["k_1"] == -4577
    assert values["k_5"] == 2
    assert values["k_14a"] == -4577
    # Net rental real estate income (blank on the real Schedule K page) must
    # not pick up Schedule M-1's own unrelated "line 2" from the next page.
    assert "k_2" not in values


def test_1065_flags_negative_ordinary_income():
    values = {"k_1": -4577, "k_14a": -4577}
    flags = build_flags_1065(values)
    assert any("negative" in f.message for f in flags)


def test_1065_computation_falls_back_to_schedule_k_ordinary_income():
    values = {"k_1": -4577}
    comp = build_computation_1065(values, None, 2024)
    assert comp["header"]["result_amount"] == -4577


def test_detect_form_type_finds_1065():
    pdf_bytes = make_pdf([FORM_1065_SCHEDULE_K_PAGE])
    assert detect_form_type(pdf_bytes) == "1065"


# --- Form 1120-S ---

FORM_1120S_SCHEDULE_K_PAGE = [
    ("Form 1120-S (2024) Page 3  OMB No. 1545-0123", ""),
    ("Schedule K  Shareholders' Pro Rata Share Items  Total amount", ""),
    ("1  Ordinary business income (loss) (page 1, line 22)", "150,972"),
    ("2  Net rental real estate income (loss)  . . . . . . . . . . . . . . 2", ""),
    ("12a Cash charitable contributions", "835"),
    ("16d Distributions (attach stmt if required) (see instrs)", "65,225"),
]

FORM_1120S_SCHEDULE_L_PAGE = [
    ("Schedule L  Balance Sheets per Books  Beginning of tax year  End of tax year", ""),
    ("2  Some balance-sheet line that also happens to be numbered 2", "999,999"),
]


def test_1120s_schedule_k_values_and_schedule_l_boundary():
    pdf_bytes = make_pdf([FORM_1120S_SCHEDULE_K_PAGE, FORM_1120S_SCHEDULE_L_PAGE])
    result = parse_1120s(pdf_bytes)
    values = {ln.id: ln.value for ln in result.lines
              if ln.value is not None and "Schedule K" in ln.group}
    assert values["k_1"] == 150972
    assert values["k_12a"] == 835
    assert values["k_16d"] == 65225
    assert "k_2" not in values


def test_1120s_flags_missing_officer_compensation():
    values = {"k_1": 150972}
    flags = build_flags_1120s(values)
    assert any("officer compensation" in f.message for f in flags)


def test_detect_form_type_finds_1120s():
    pdf_bytes = make_pdf([FORM_1120S_SCHEDULE_K_PAGE])
    assert detect_form_type(pdf_bytes) == "1120s"


def test_detect_form_type_still_defaults_to_1040():
    pdf_bytes = make_pdf([[("Form 1040 (2023) U.S. Individual Income Tax Return", ""),
                            ("1z  Total wages", "65,000")]])
    assert detect_form_type(pdf_bytes) == "1040"
