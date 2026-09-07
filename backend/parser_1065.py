"""Best-effort extraction of key line values from a Form 1065 PDF (U.S.
Return of Partnership Income) plus its Schedule K summary.

Reuses the same phrase-anchored + line-number-fallback row matching as
`parser.py`'s Form 1040 support — only the line definitions, title phrases,
and section handling are specific to this form. Built and verified against
one real return (PIC2PRINT LLC, 2024) — its own page 1 (the Income and
Deductions section, lines 1-22) happened to be a scanned/signed page with
no text layer at all, so this module's `MAIN_LINE_DEFINITIONS` couldn't be
verified against real values the way Schedule K's were; they're included on
the strength of matching the official form's own wording, for whichever
1065 PDFs do carry a real text layer on that page, but should be treated as
less battle-tested than the rest of this module until checked against a
second real return the way the 1040 parser's definitions were."""
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

# Form 1065's own Income and Deductions section (page 1 of the official
# form). Rarely readable on every real-world export (see module docstring)
# but worth trying — a return whose page 1 does carry a text layer gets full
# detail here instead of falling back to Schedule K's restated totals alone.
MAIN_LINE_DEFINITIONS: list[tuple[str, str, list[str], str]] = [
    ("p1_1c", "Gross receipts or sales", ["gross receipts or sales"], "1c"),
    ("p1_2", "Cost of goods sold", ["cost of goods sold"], "2"),
    ("p1_3", "Gross profit", ["gross profit"], "3"),
    ("p1_7", "Other income (loss)", ["other income (loss)"], "7"),
    ("p1_8", "Total income (loss)", ["total income (loss)"], "8"),
    ("p1_9", "Salaries and wages", ["salaries and wages"], "9"),
    ("p1_10", "Guaranteed payments to partners", ["guaranteed payments to partners"], "10"),
    ("p1_13", "Interest expense", ["interest"], "13"),
    ("p1_16c", "Depreciation", ["depreciation"], "16c"),
    ("p1_20", "Other deductions", ["other deductions"], "20"),
    ("p1_21", "Total deductions", ["total deductions"], "21"),
    ("p1_22", "Ordinary business income (loss)",
     ["ordinary business income (loss)", "subtract line 21 from line 8"], "22"),
]

# Schedule K — Partners' Distributive Share Items. This is where a small
# partnership's summary numbers most reliably survive as real text even
# when page 1 itself doesn't (it's less often a page that gets signed,
# stamped, or otherwise flattened into an image by tax software).
SCHEDULE_K_DEFINITIONS: list[tuple[str, str, list[str], str]] = [
    ("k_1", "Ordinary business income (loss)",
     ["ordinary business income (loss) (page 1"], "1"),
    ("k_2", "Net rental real estate income (loss)", ["net rental real estate income"], "2"),
    ("k_4c", "Guaranteed payments (total)", ["total. add lines 4a and 4b"], "4c"),
    ("k_5", "Interest income", ["interest income"], "5"),
    ("k_6a", "Ordinary dividends", ["ordinary dividends"], "6a"),
    ("k_8", "Net short-term capital gain (loss)", ["net short-term capital gain"], "8"),
    ("k_9a", "Net long-term capital gain (loss)", ["net long-term capital gain"], "9a"),
    ("k_14a", "Net earnings (loss) from self-employment",
     ["net earnings (loss) from self-employment"], "14a"),
    ("k_19a", "Distributions of cash and marketable securities",
     ["distributions of cash and marketable securities"], "19a"),
    ("k_19b", "Distributions of other property", ["distributions of other property"], "19b"),
]

_FORM_1065_TITLE_RE = re.compile(r"u\.?s\.? return of partnership income", re.IGNORECASE)
_SCHEDULE_K_TITLE_RE = re.compile(r"partners.? distributive share items", re.IGNORECASE)
_FORM_1065_HEADER_YEAR_RE = re.compile(r"form 1065\s*\(?(\d{4})\)?", re.IGNORECASE)


def parse_1065(pdf_bytes: bytes) -> ExtractionResult:
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

    def bounded_scope(start: int | None, exclude_before: int = 0) -> tuple[int, int]:
        """A [start, end) page range for a form/schedule found at `start`,
        ending at the next page (after `start`) that opens a new
        OMB-numbered attachment — same approach used in parser_990.py,
        since Form 1065's own Schedule B/K/L/M-1/M-2 pages share the main
        form's OMB number and don't start their own section boundary the
        way a genuinely separate attachment (Schedule K-1, Form 4562, ...)
        does."""
        if start is None:
            return exclude_before, exclude_before
        later_omb = [i for i, p in enumerate(pages) if i > start and _OMB_RE.search(p)]
        end = later_omb[0] if later_omb else total_pages
        return start, end

    main_page = find_title_page(_FORM_1065_TITLE_RE)
    k_page = find_title_page(_SCHEDULE_K_TITLE_RE)
    main_start, main_end = bounded_scope(main_page if main_page is not None else 0)
    # Schedule B/K/L/M-1/M-2 all share Form 1065's own OMB number, so
    # `bounded_scope`'s "next OMB page" heuristic can't tell them apart from
    # the main form's own Income & Deductions page on its own — several of
    # their line phrases collide with page 1's ("other deductions" appears
    # on both, for instance), so the main scope must stop at Schedule K's
    # own page rather than run into it.
    if k_page is not None and main_start <= k_page < main_end:
        main_end = k_page
    if main_page is not None:
        window = pages[main_page][:600]
        m = TAX_YEAR_RE.search(window)
        result.tax_year = int(m.group(1)) if m else None
    if result.tax_year is None:
        # Page 1's own title text is where the year normally prints, but
        # that page is often a scanned/signed copy with no text layer at
        # all — every continuation page still repeats "Form 1065 (YYYY)" in
        # its own running header, so fall back to that instead of leaving
        # the year unknown just because page 1 wasn't readable.
        m = _FORM_1065_HEADER_YEAR_RE.search(text)
        result.tax_year = int(m.group(1)) if m else None
    main_scope = flatten(main_start, main_end)
    result.lines.extend(_extract_group(main_scope, main_scope, MAIN_LINE_DEFINITIONS, "Form 1065",
                                        via_ocr=uses_ocr(main_start, main_end)))

    if k_page is not None:
        k_start, k_end = bounded_scope(k_page)
        k_scope = truncate_before_next_lettered_schedule(flatten(k_start, k_end))
        result.lines.extend(_extract_group(k_scope, k_scope, SCHEDULE_K_DEFINITIONS,
                                            "Schedule K (Partners' Distributive Share Items)",
                                            via_ocr=uses_ocr(k_start, k_end)))
    else:
        k_start = k_end = None
        result.lines.extend(_extract_group([], None, SCHEDULE_K_DEFINITIONS,
                                            "Schedule K (Partners' Distributive Share Items)"))

    # Any other attached schedule/form (Schedule K-1s, Form 4562, ...) has
    # no curated line definitions here — surface it generically, same as
    # parser.py does for uncurated 1040 attachments. Pages already covered
    # by the main form or Schedule K above are skipped.
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
