"""Plain-language explanations, review flags, and the money-flow/computation
summaries for a Form 990-EZ (exempt organization) return — the Form 990
counterpart to explain.py's Form 1040 support. See explain.py for the
shared `Flag` type and the overall approach; the functions here follow the
same shape (`build_flags_990`, `build_flow_990`, `build_computation_990`)
so `main.py` can dispatch to either form type identically, but there's no
`filing_status`/tax-bracket concept for an exempt organization, so those
functions accept and ignore a `filing_status` argument purely so the
dispatch table in main.py can call every form type's functions the same
way."""
from __future__ import annotations

from .explain import Flag

LINE_EXPLANATIONS_990: dict[str, str] = {
    "1": "Contributions, gifts, and grants the organization received during the year.",
    "2": "Revenue from providing the organization's actual programs/services (including government fees and contracts).",
    "3": "Membership dues and assessments collected from members.",
    "4": "Interest, dividends, and other investment income.",
    "8": "Other revenue not captured by the lines above.",
    "9": "Total revenue: everything above, added together.",
    "10": "Grants and similar amounts the organization paid out to others.",
    "12": "Salaries, other compensation, and employee benefits paid.",
    "13": "Fees paid to independent contractors and other professionals.",
    "14": "Rent, utilities, and other costs of occupying the organization's space.",
    "16": "Other expenses not captured by the lines above.",
    "17": "Total expenses: everything spent during the year, added together.",
    "18": "Excess or deficit for the year: total revenue minus total expenses.",
    "19": "Net assets or fund balances the organization had at the start of the year.",
    "20": "Any other changes to net assets during the year not already counted above (e.g. an accounting adjustment).",
    "21": "Net assets or fund balances at the end of the year — what the organization is carrying forward.",
}


def build_flags_990(values: dict[str, float], filing_status: str | None = None, tax_year: int | None = None) -> list[Flag]:
    flags: list[Flag] = []

    total_revenue = values.get("9")
    total_expenses = values.get("17")
    excess = values.get("18")
    net_assets_begin = values.get("19")
    other_changes = values.get("20")
    net_assets_end = values.get("21")

    if total_revenue is not None and total_expenses is not None and excess is not None:
        expected_excess = round(total_revenue - total_expenses, 2)
        if abs(excess - expected_excess) > 1:
            flags.append(Flag("warning", f"Excess/deficit on line 18 (${excess:,.0f}) doesn't match total "
                                          f"revenue minus total expenses (${expected_excess:,.0f}). Worth "
                                          "re-checking the entered values."))

    if net_assets_begin is not None and excess is not None and net_assets_end is not None:
        expected_end = round(net_assets_begin + excess + (other_changes or 0), 2)
        if abs(net_assets_end - expected_end) > 1:
            flags.append(Flag("warning", f"Net assets at end of year (line 21, ${net_assets_end:,.0f}) don't "
                                          f"match beginning net assets plus this year's excess/deficit and "
                                          f"other changes (${expected_end:,.0f}). Worth re-checking."))

    if net_assets_end is not None and net_assets_end < 0:
        flags.append(Flag("warning", "Net assets or fund balances at end of year are negative — the "
                                      "organization owes more than it holds. Worth a closer look at its "
                                      "financial position."))

    if (
        total_revenue and total_expenses is not None and total_expenses > 0
        and total_expenses > total_revenue * 1.5
    ):
        flags.append(Flag("info", "Total expenses are well above total revenue this year — a deficit like "
                                   "this can be normal for one year (e.g. spending down reserves for a "
                                   "planned project), but worth confirming it was intentional."))

    if not total_revenue and not total_expenses:
        flags.append(Flag("info", "No revenue or expenses were found on this return — check whether this "
                                   "was a short year, a dormant organization, or a parsing issue."))

    return flags


def build_flow_990(values: dict[str, float]) -> list[dict]:
    total_revenue = values.get("9")
    total_expenses = values.get("17")
    excess = values.get("18")
    net_assets_begin = values.get("19")
    net_assets_end = values.get("21")

    steps = []
    if total_revenue is not None:
        steps.append({"label": "Total revenue", "value": total_revenue, "kind": "start"})
    if total_expenses:
        steps.append({"label": "Total expenses", "value": -total_expenses, "kind": "subtract"})
    if excess is not None:
        steps.append({"label": "Excess or (deficit) for the year", "value": excess, "kind": "subtotal"})
    if net_assets_begin is not None:
        steps.append({"label": "Net assets, start of year", "value": net_assets_begin, "kind": "info"})
    if net_assets_end is not None:
        steps.append({"label": "Net assets, end of year", "value": net_assets_end, "kind": "end"})
    return steps


_REVENUE_LINE_IDS = ["1", "2", "3", "4", "8"]
_EXPENSE_LINE_IDS = ["10", "12", "13", "14", "16"]


def build_computation_990(values: dict[str, float], filing_status: str | None = None, tax_year: int | None = None) -> dict:
    """A table-driven walkthrough of a 990-EZ's numbers, in the shape
    `renderComputation` expects for any non-1040 form type: a header, a
    generic list of labeled sections (each a small table of rows), and
    reviewer notes — no tax-bracket worksheet section, since an exempt
    organization has no individual tax computation to reconstruct."""

    def v(line_id: str) -> float | None:
        return values.get(line_id)

    net_assets_end = v("21")
    header = {
        "label": "Form 990-EZ",
        "tax_year": tax_year,
        "result_label": "Net assets, end of year",
        "result_amount": net_assets_end,
    }

    revenue_rows = []
    for line_id in _REVENUE_LINE_IDS:
        amount = v(line_id)
        if not amount:
            continue
        revenue_rows.append({"line": line_id, "item": LINE_EXPLANATIONS_990[line_id].split(".")[0], "amount": amount})
    total_revenue = v("9")
    if total_revenue is not None:
        revenue_rows.append({"line": "9", "item": "Total revenue", "amount": total_revenue})

    expense_rows = []
    for line_id in _EXPENSE_LINE_IDS:
        amount = v(line_id)
        if not amount:
            continue
        expense_rows.append({"line": line_id, "item": LINE_EXPLANATIONS_990[line_id].split(".")[0], "amount": -amount})
    total_expenses = v("17")
    if total_expenses:
        expense_rows.append({"line": "17", "item": "Total expenses", "amount": -total_expenses})

    outcome_rows = []
    excess = v("18")
    if excess is not None:
        outcome_rows.append({"line": "18", "item": "Excess or (deficit) for the year", "amount": excess})
    net_assets_begin = v("19")
    if net_assets_begin is not None:
        outcome_rows.append({"line": "19", "item": "Net assets, start of year", "amount": net_assets_begin})
    other_changes = v("20")
    if other_changes:
        outcome_rows.append({"line": "20", "item": "Other changes in net assets", "amount": other_changes})
    if net_assets_end is not None:
        outcome_rows.append({"line": "21", "item": "Net assets, end of year", "amount": net_assets_end})

    sections = []
    if revenue_rows:
        sections.append({"title": "Revenue", "rows": revenue_rows})
    if expense_rows:
        sections.append({"title": "Expenses", "rows": expense_rows})
    if outcome_rows:
        sections.append({"title": "Change in net assets", "rows": outcome_rows})

    reviewer_notes = [{"severity": f.severity, "message": f.message} for f in build_flags_990(values, filing_status, tax_year)]

    return {
        "header": header,
        "sections": sections,
        "tax_computation": None,
        "reviewer_notes": reviewer_notes,
    }
