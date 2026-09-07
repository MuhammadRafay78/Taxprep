"""Plain-language explanations, review flags, and the money-flow/computation
summaries for a Form 1065 (partnership) return — see explain_990.py's
docstring for how this mirrors explain.py's Form 1040 support and why
`filing_status` is accepted-and-ignored throughout (no such concept for a
partnership return; kept only so main.py's dispatch table can call every
form type's functions identically)."""
from __future__ import annotations

from .explain import Flag

LINE_EXPLANATIONS_1065: dict[str, str] = {
    "p1_1c": "Gross receipts or sales from the partnership's regular business.",
    "p1_2": "Cost of goods sold.",
    "p1_3": "Gross profit: gross receipts minus cost of goods sold.",
    "p1_7": "Other income not captured by the lines above.",
    "p1_8": "Total income: everything above, added together.",
    "p1_9": "Salaries and wages paid to employees (not to partners themselves).",
    "p1_10": "Guaranteed payments made to partners for services or use of capital.",
    "p1_13": "Interest expense on business debt.",
    "p1_16c": "Depreciation claimed on business property.",
    "p1_20": "Other deductions not captured by the lines above.",
    "p1_21": "Total deductions: everything spent/deducted during the year, added together.",
    "p1_22": "Ordinary business income (loss): total income minus total deductions — this is the "
             "main figure that flows out to each partner's Schedule K-1.",
    "k_1": "Ordinary business income (loss), restated from page 1 — the starting point for what each "
           "partner reports on their own return via Schedule K-1.",
    "k_2": "Net rental real estate income or loss.",
    "k_4c": "Guaranteed payments to partners (for services and/or capital), total.",
    "k_5": "Interest income earned by the partnership.",
    "k_6a": "Ordinary dividends received by the partnership.",
    "k_8": "Net short-term capital gain or loss.",
    "k_9a": "Net long-term capital gain or loss.",
    "k_14a": "Net earnings (loss) from self-employment — what self-employment tax, if any, is based on "
             "for the partners.",
    "k_19a": "Cash and marketable securities distributed to partners during the year.",
    "k_19b": "Other property distributed to partners during the year.",
}


def build_flags_1065(values: dict[str, float], filing_status: str | None = None, tax_year: int | None = None) -> list[Flag]:
    flags: list[Flag] = []

    ordinary_income = values.get("k_1") if values.get("k_1") is not None else values.get("p1_22")
    guaranteed_payments = values.get("k_4c") or 0
    self_employment = values.get("k_14a")
    distributions = (values.get("k_19a") or 0) + (values.get("k_19b") or 0)

    if ordinary_income is not None and ordinary_income < 0:
        flags.append(Flag("info", "Ordinary business income (loss) is negative this year — a loss can "
                                   "still be usable on a partner's own return, subject to their basis and "
                                   "at-risk limits, which aren't visible from this return alone."))

    if distributions and ordinary_income is not None:
        available = ordinary_income + guaranteed_payments
        if available >= 0 and distributions > available * 1.5 and distributions > 1000:
            flags.append(Flag("info", f"Distributions to partners (${distributions:,.0f}) are well above "
                                       f"this year's ordinary business income plus guaranteed payments "
                                       f"(${available:,.0f}). That's not automatically a problem — "
                                       "distributions can draw down prior-year earnings or capital — but "
                                       "it's worth checking against each partner's basis."))

    if (
        ordinary_income is not None and self_employment is not None
        and abs(self_employment - (ordinary_income + guaranteed_payments)) > max(50, abs(ordinary_income) * 0.05)
    ):
        flags.append(Flag("info", "Self-employment earnings (Schedule K, line 14a) differ noticeably from "
                                   "ordinary business income plus guaranteed payments. That can be normal "
                                   "(a limited partner's share is often excluded from self-employment "
                                   "earnings), but worth a second look if it surprises you."))

    if not ordinary_income and not values.get("k_5") and not values.get("k_2"):
        flags.append(Flag("info", "No income figures were found on this return — check whether this was "
                                   "a short or dormant year, or whether the PDF's page 1 simply didn't "
                                   "have a readable text layer (common on scanned/signed copies)."))

    return flags


def build_flow_1065(values: dict[str, float]) -> list[dict]:
    total_income = values.get("p1_8")
    total_deductions = values.get("p1_21")
    ordinary_income = values.get("p1_22") if values.get("p1_22") is not None else values.get("k_1")
    distributions = (values.get("k_19a") or 0) + (values.get("k_19b") or 0)

    steps = []
    if total_income is not None:
        steps.append({"label": "Total income", "value": total_income, "kind": "start"})
    if total_deductions:
        steps.append({"label": "Total deductions", "value": -total_deductions, "kind": "subtract"})
    if ordinary_income is not None:
        steps.append({"label": "Ordinary business income (loss)", "value": ordinary_income, "kind": "subtotal"})
    if distributions:
        steps.append({"label": "Distributions to partners", "value": distributions, "kind": "end"})
    return steps


_MAIN_LINE_IDS = ["p1_1c", "p1_2", "p1_3", "p1_7", "p1_9", "p1_10", "p1_13", "p1_16c", "p1_20"]
_K_LINE_IDS = ["k_2", "k_4c", "k_5", "k_6a", "k_8", "k_9a"]


def build_computation_1065(values: dict[str, float], filing_status: str | None = None, tax_year: int | None = None) -> dict:
    def v(line_id: str) -> float | None:
        return values.get(line_id)

    ordinary_income = v("p1_22") if v("p1_22") is not None else v("k_1")
    header = {
        "label": "Form 1065",
        "tax_year": tax_year,
        "result_label": "Ordinary business income (loss)",
        "result_amount": ordinary_income,
    }

    def row(line_id: str, display_line: str, item: str, amount: float) -> dict:
        # Every row carries its full plain-language explanation as a note,
        # not just the short item label — this is what actually shows up
        # under each line in the calculation walkthrough.
        return {"line": display_line, "item": item, "amount": amount, "note": LINE_EXPLANATIONS_1065.get(line_id)}

    income_rows = []
    for line_id in _MAIN_LINE_IDS:
        amount = v(line_id)
        if not amount:
            continue
        display = line_id.replace("p1_", "")
        income_rows.append(row(line_id, display, LINE_EXPLANATIONS_1065[line_id].split(".")[0], amount))
    total_income = v("p1_8")
    if total_income is not None:
        income_rows.append(row("p1_8", "8", "Total income", total_income))
    total_deductions = v("p1_21")
    if total_deductions:
        income_rows.append(row("p1_21", "21", "Total deductions", -total_deductions))
    if ordinary_income is not None:
        income_rows.append(row("p1_22", "22", "Ordinary business income (loss)", ordinary_income))

    k_rows = []
    for line_id in _K_LINE_IDS:
        amount = v(line_id)
        if not amount:
            continue
        display = line_id.replace("k_", "")
        k_rows.append(row(line_id, display, LINE_EXPLANATIONS_1065[line_id].split(".")[0], amount))
    self_employment = v("k_14a")
    if self_employment:
        k_rows.append(row("k_14a", "14a", "Net earnings (loss) from self-employment", self_employment))

    distribution_rows = []
    for line_id in ("k_19a", "k_19b"):
        amount = v(line_id)
        if not amount:
            continue
        display = line_id.replace("k_", "")
        distribution_rows.append(row(line_id, display, LINE_EXPLANATIONS_1065[line_id].split(".")[0], amount))

    sections = []
    if income_rows:
        sections.append({"title": "Income and deductions (page 1)", "rows": income_rows,
                          "description": "The partnership's own income and expenses, before anything is "
                                          "passed through to individual partners."})
    if k_rows:
        sections.append({"title": "Schedule K — other partnership items", "rows": k_rows,
                          "description": "Additional items reported separately on Schedule K because each "
                                          "partner needs to know their own share, rather than just a "
                                          "single combined total."})
    if distribution_rows:
        sections.append({"title": "Distributions to partners", "rows": distribution_rows,
                          "description": "Cash and property actually paid out to partners during the year "
                                          "— separate from (and not necessarily equal to) their share of "
                                          "ordinary business income."})

    reviewer_notes = [{"severity": f.severity, "message": f.message} for f in build_flags_1065(values, filing_status, tax_year)]

    return {
        "header": header,
        "sections": sections,
        "tax_computation": None,
        "reviewer_notes": reviewer_notes,
    }
