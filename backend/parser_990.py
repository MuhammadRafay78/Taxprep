"""Best-effort extraction of key line values from a Form 990 or 990-EZ PDF
(the annual information return an exempt organization files with the IRS).

Reuses the same phrase-anchored + line-number-fallback row matching as
`parser.py`'s Form 1040 support (see that module's docstring for how the
matching itself works) — only the line definitions, OMB number, and title
phrase are specific to this form. Built and verified against a real
Form 990-EZ; a full Form 990 (larger organizations, with revenue/expense
detail split across Parts VIII/IX/X instead of one Part I) isn't covered by
this module's line definitions yet, since Part I's lines 9/17/18/21 (total
revenue, total expenses, excess/deficit, and net assets) don't exist under
those same numbers on the full form — a return like that would currently
fall back to the generic uncurated-line extraction for its main-form pages,
same as any other page this module has no phrase list for."""
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
)

LINE_DEFINITIONS: list[tuple[str, str, list[str], str]] = [
    ("1", "Contributions, gifts, and grants received",
     ["contributions, gifts, grants, and similar amounts"], "1"),
    ("2", "Program service revenue", ["program service revenue"], "2"),
    ("3", "Membership dues and assessments", ["membership dues and assessments"], "3"),
    ("4", "Investment income", ["investment income"], "4"),
    ("8", "Other revenue", ["other revenue"], "8"),
    ("9", "Total revenue", ["total revenue"], "9"),
    ("10", "Grants and similar amounts paid", ["grants and similar amounts paid"], "10"),
    ("12", "Salaries, other compensation, and employee benefits",
     ["salaries, other compensation, and employee benefits"], "12"),
    ("13", "Professional fees and other payments to independent contractors",
     ["professional fees and other payments"], "13"),
    ("14", "Occupancy, rent, utilities, and maintenance",
     ["occupancy, rent, utilities, and maintenance"], "14"),
    ("16", "Other expenses", ["other expenses"], "16"),
    ("17", "Total expenses", ["total expenses"], "17"),
    ("18", "Excess or (deficit) for the year", ["excess or", "deficit"], "18"),
    ("19", "Net assets or fund balances at beginning of year",
     ["net assets or fund balances at beginning of year"], "19"),
    ("20", "Other changes in net assets or fund balances",
     ["other changes in net assets"], "20"),
    ("21", "Net assets or fund balances at end of year",
     ["net assets or fund balances at end of year"], "21"),
]

_FORM_990_TITLE_RE = re.compile(r"return of organization exempt from income tax", re.IGNORECASE)


def _detect_tax_year_after_title(page_text: str, title_match: re.Match[str]) -> int | None:
    """990/990-EZ can sit behind cover attachments (an e-file signature
    authorization, an extension application) that print this same OMB
    number ahead of the actual return, so anchoring on the first OMB match
    in the whole document (as `detect_tax_year_near_omb` does for Form 1040,
    where no such shared-OMB cover pages exist) would just as often land on
    one of those instead. The tax year reliably prints right after this
    form's own title text on its own page instead (e.g. "...Return of
    Organization Exempt From Income Tax | Form | 2024")."""
    window = page_text[title_match.end():title_match.end() + 200]
    match = TAX_YEAR_RE.search(window)
    return int(match.group(1)) if match else None


def parse_990(pdf_bytes: bytes) -> ExtractionResult:
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

    # The main form's own start page is found directly by its title phrase
    # (searched across the whole page's text, not just the first couple of
    # lines _detect_form_sections itself checks) — more robust than trusting
    # that generic per-section title labeling, since a cover page ahead of
    # it (an e-file signature authorization, an extension application) can
    # collapse into the same "Additional form" fallback label as the main
    # form itself and wrongly merge the two into one section. Its end page
    # is simply the next page anywhere in the document that starts a new
    # OMB-numbered attachment, which is reliable regardless of how that
    # attachment's own title gets labeled.
    title_match = next(((i, m) for i, p in enumerate(pages) if (m := _FORM_990_TITLE_RE.search(p))), None)
    main_start = title_match[0] if title_match else 0
    if title_match:
        result.tax_year = _detect_tax_year_after_title(pages[main_start], title_match[1])
    later_omb_pages = [i for i, p in enumerate(pages) if i > main_start and _OMB_RE.search(p)]
    main_end = later_omb_pages[0] if later_omb_pages else total_pages
    main_scope = flatten(main_start, main_end)
    result.lines.extend(_extract_group(main_scope, main_scope, LINE_DEFINITIONS, "Form 990",
                                        via_ocr=uses_ocr(main_start, main_end)))

    # Any other attached schedule/form (Schedule A, Schedule O, Schedule B,
    # ...) has no curated line definitions here — surface it generically,
    # same as parser.py does for uncurated 1040 attachments. Sections
    # overlapping the main form's own page range are skipped so its pages
    # aren't also dumped into a generic "Additional form" bucket.
    for section in sections:
        if section.start_page < main_end and section.end_page > main_start:
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
