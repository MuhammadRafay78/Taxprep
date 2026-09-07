"""Best-effort extraction of key line values from a Form 1120-S PDF (U.S.
Income Tax Return for an S Corporation) plus its Schedule K summary.

Reuses the same phrase-anchored + line-number-fallback row matching as
`parser.py`'s Form 1040 support, and the same "main form page + Schedule K
page, both found by title phrase and bounded by the next OMB-numbered
attachment" approach as parser_1065.py — see that module's docstring for
why (Schedule B/K/L/M-1/M-2 all share the main form's own OMB number, so
they can't be told apart from it, or from each other, purely by OMB
boundaries). Built and verified against one real return (CJ CPAs PLLC,
2024) whose own page 1 (Income, Deductions, and Tax and Payments, lines
1-27) was, like the 1065 return this module's sibling was built against, a
scanned/signed page with no text layer — so `MAIN_LINE_DEFINITIONS` here
carries the same lower-confidence caveat as parser_1065.py's: matched
against the official form's own wording, not yet checked against a real
return where that page was actually readable."""
from __future__ import annotations

import re

from . import ocr
from .parser import (
    ExtractedLine,
    ExtractionResult,
    TAX_YEAR_RE,
    _OMB_RE,
    _detect_form_sections,
    _extract_generic_lines,
    _extract_group,
    _page_texts,
    _slugify,
    truncate_before_next_lettered_schedule,
)

# Form 1120-S's own Income, Deductions, and Tax and Payments section (page 1
# of the official form). Rarely readable on every real-world export (see
# module docstring) but worth trying.
MAIN_LINE_DEFINITIONS: list[tuple[str, str, list[str], str]] = [
    ("p1_1c", "Gross receipts or sales", ["gross receipts or sales"], "1c"),
    ("p1_2", "Cost of goods sold", ["cost of goods sold"], "2"),
    ("p1_3", "Gross profit", ["gross profit"], "3"),
    ("p1_5", "Other income (loss)", ["other income (loss)"], "5"),
    ("p1_6", "Total income (loss)", ["total income (loss)"], "6"),
    ("p1_7", "Compensation of officers", ["compensation of officers"], "7"),
    ("p1_8", "Salaries and wages", ["salaries and wages"], "8"),
    ("p1_12", "Taxes and licenses", ["taxes and licenses"], "12"),
    ("p1_14", "Depreciation", ["depreciation"], "14"),
    ("p1_19", "Other deductions", ["other deductions"], "19"),
    ("p1_20", "Total deductions", ["total deductions"], "20"),
    ("p1_21", "Ordinary business income (loss)",
     ["ordinary business income (loss)", "subtract line 20 from line 6"], "21"),
    ("p1_22c", "Total tax", ["total tax"], "22c"),
    ("p1_23e", "Total payments and credits", ["total payments and credits"], "23e"),
]

# Schedule K — Shareholders' Pro Rata Share Items. Like parser_1065.py's
# Schedule K, this is where a small S-corp's summary numbers most reliably
# survive as real text even when page 1 itself doesn't.
SCHEDULE_K_DEFINITIONS: list[tuple[str, str, list[str], str]] = [
    ("k_1", "Ordinary business income (loss)",
     ["ordinary business income (loss) (page 1"], "1"),
    ("k_2", "Net rental real estate income (loss)", ["net rental real estate income"], "2"),
    ("k_4", "Interest income", ["interest income"], "4"),
    ("k_5a", "Ordinary dividends", ["ordinary dividends"], "5a"),
    ("k_6", "Royalties", ["royalties"], "6"),
    ("k_7", "Net short-term capital gain (loss)", ["net short-term capital gain"], "7"),
    ("k_8a", "Net long-term capital gain (loss)", ["net long-term capital gain"], "8a"),
    ("k_12a", "Cash charitable contributions", ["cash charitable contributions"], "12a"),
    ("k_16d", "Distributions", ["distributions (attach stmt"], "16d"),
]

_FORM_1120S_TITLE_RE = re.compile(r"u\.?s\.? income tax return for an s corporation", re.IGNORECASE)
_SCHEDULE_K_TITLE_RE = re.compile(r"shareholders.? pro rata share items", re.IGNORECASE)
_FORM_1120S_HEADER_YEAR_RE = re.compile(r"form 1120-s\s*\(?(\d{4})\)?", re.IGNORECASE)


def parse_1120s(pdf_bytes: bytes) -> ExtractionResult:
    pages = _page_texts(pdf_bytes)
    page_lines = [p.splitlines() for p in pages]
    total_pages = len(pages)

    scanned_page_indices = [i for i, rows in enumerate(page_lines) if not any(row.strip() for row in rows)]
    sections = _detect_form_sections(list(pages), [list(p) for p in page_lines])

    ocr_page_indices: set[int] = set()
    ocr_results = ocr.ocr_pages_text(pdf_bytes, scanned_page_indices)
    for i, ocr_text in ocr_results.items():
        if ocr_text.strip():
            pages[i] = ocr_text
            page_lines[i] = ocr_text.splitlines()
            ocr_page_indices.add(i)

    text = "\n".join(pages)
    result = ExtractionResult(raw_text=text)
    result.scanned_pages = [i + 1 for i in scanned_page_indices]
    result.ocr_pages = [i + 1 for i in sorted(ocr_page_indices)]

    def flatten(a: int, b: int) -> list[str]:
        return [line for page in page_lines[a:b] for line in page]

    def uses_ocr(a: int, b: int) -> bool:
        return any(i in ocr_page_indices for i in range(a, b))

    def find_title_page(title_re: re.Pattern[str]) -> int | None:
        return next((i for i, p in enumerate(pages) if title_re.search(p)), None)

    def bounded_scope(start: int) -> tuple[int, int]:
        later_omb = [i for i, p in enumerate(pages) if i > start and _OMB_RE.search(p)]
        end = later_omb[0] if later_omb else total_pages
        return start, end

    main_page = find_title_page(_FORM_1120S_TITLE_RE)
    k_page = find_title_page(_SCHEDULE_K_TITLE_RE)
    main_start, main_end = bounded_scope(main_page if main_page is not None else 0)
    # Schedule B/K/L/M-1/M-2 all share Form 1120-S's own OMB number (same
    # situation as parser_1065.py), so the main scope must stop at Schedule
    # K's own page rather than run into it and pick up its restated values
    # under the wrong line ids (or collide on a shared phrase like "other
    # deductions", which appears in both places).
    if k_page is not None and main_start <= k_page < main_end:
        main_end = k_page
    if main_page is not None:
        m = TAX_YEAR_RE.search(pages[main_page][:600])
        result.tax_year = int(m.group(1)) if m else None
    if result.tax_year is None:
        m = _FORM_1120S_HEADER_YEAR_RE.search(text)
        result.tax_year = int(m.group(1)) if m else None
    main_scope = flatten(main_start, main_end)
    result.lines.extend(_extract_group(main_scope, main_scope, MAIN_LINE_DEFINITIONS, "Form 1120-S",
                                        via_ocr=uses_ocr(main_start, main_end)))

    if k_page is not None:
        k_start, k_end = bounded_scope(k_page)
        k_scope = truncate_before_next_lettered_schedule(flatten(k_start, k_end))
        result.lines.extend(_extract_group(k_scope, k_scope, SCHEDULE_K_DEFINITIONS,
                                            "Schedule K (Shareholders' Pro Rata Share Items)",
                                            via_ocr=uses_ocr(k_start, k_end)))
    else:
        k_start = k_end = None
        result.lines.extend(_extract_group([], None, SCHEDULE_K_DEFINITIONS,
                                            "Schedule K (Shareholders' Pro Rata Share Items)"))

    # Any other attached schedule/form (Schedule K-1s, Schedule K-2, Form
    # 4562, ...) has no curated line definitions here — surface it
    # generically, same as parser.py does for uncurated 1040 attachments.
    covered_ranges = [(main_start, main_end)] + ([(k_start, k_end)] if k_page is not None else [])
    for section in sections:
        if any(section.start_page < end and section.end_page > start for start, end in covered_ranges):
            continue
        scope = flatten(section.start_page, section.end_page)
        section_via_ocr = uses_ocr(section.start_page, section.end_page)
        for number, label, value in _extract_generic_lines(scope):
            result.lines.append(ExtractedLine(
                id=f"{_slugify(section.title)}_{number}",
                label=label,
                value=value,
                confidence="uncertain",
                group=section.title,
                via_ocr=section_via_ocr,
            ))

    return result
