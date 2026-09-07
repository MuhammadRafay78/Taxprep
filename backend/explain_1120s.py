"""Plain-language explanations, review flags, and the money-flow/computation
summaries for a Form 1120-S (S corporation) return — see explain_990.py's
docstring for how this mirrors explain.py's Form 1040 support and why
`filing_status` is accepted-and-ignored throughout."""
from __future__ import annotations

from .explain import Flag

LINE_EXPLANATIONS_1120S: dict[str, str] = {
    "p1_1c": "Gross receipts or sales from the corporation's regular business.",
    "p1_2": "Cost of goods sold.",
    "p1_3": "Gross profit: gross receipts minus cost of goods sold.",
    "p1_5": "Other income not captured by the lines above.",
    "p1_6": "Total income: everything above, added together.",
    "p1_7": "Compensation paid to corporate officers.",
    "p1_8": "Salaries and wages paid to other employees.",
    "p1_12": "Taxes and licenses paid.",
    "p1_14": "Depreciation claimed on business property.",
    "p1_19": "Other deductions not captured by the lines above.",
    "p1_20": "Total deductions: everything spent/deducted during the year, added together.",
    "p1_21": "Ordinary business income (loss): total income minus total deductions — this is the "
             "main figure that flows out to each shareholder's Schedule K-1.",
    "p1_22c": "Total tax owed by the corporation itself — usually $0 for an S-corp, since income "
              "normally passes through to shareholders instead, except for certain built-in gains "
              "or excess passive investment income taxes.",
    "p1_23e": "Total payments and refundable credits the corporation made toward that tax.",
    "k_1": "Ordinary business income (loss), restated from page 1 — the starting point for what each "
           "shareholder reports on their own return via Schedule K-1.",
    "k_2": "Net rental real estate income or loss.",
    "k_4": "Interest income earned by the corporation.",
    "k_5a": "Ordinary dividends received by the corporation.",
    "k_6": "Royalty income.",
    "k_7": "Net short-term capital gain or loss.",
    "k_8a": "Net long-term capital gain or loss.",
    "k_12a": "Cash charitable contributions made by the corporation.",
    "k_16d": "Cash and property distributed to shareholders during the year.",
}


def build_flags_1120s(values: dict[str, float], filing_status: str | None = None, tax_year: int | None = None) -> list[Flag]:
    flags: list[Flag] = []

    ordinary_income = values.get("k_1") if values.get("k_1") is not None else values.get("p1_21")
    officer_comp = values.get("p1_7")
    distributions = values.get("k_16d") or 0
    total_tax = values.get("p1_22c")

    if ordinary_income is not None and ordinary_income > 0 and not officer_comp:
        flags.append(Flag("info", "The corporation shows positive ordinary business income but no "
                                   "officer compensation (page 1, line 7) was found. The IRS expects an "
                                   "S-corp with profitable operations and an active shareholder-employee "
                                   "to pay that person reasonable W-2 compensation before profit is "
                                   "distributed — worth confirming this wasn't just parsed as blank."))

    if distributions and ordinary_income is not None:
        if ordinary_income >= 0 and distributions > ordinary_income * 1.5 and distributions > 1000:
            flags.append(Flag("info", f"Distributions to shareholders (${distributions:,.0f}) are well "
                                       f"above this year's ordinary business income (${ordinary_income:,.0f}). "
                                       "That's not automatically a problem — distributions can draw down "
                                       "prior-year earnings — but it's worth checking against each "
                                       "shareholder's stock basis, since a distribution beyond basis is "
                                       "taxable as a capital gain."))

    if total_tax:
        flags.append(Flag("info", f"This return shows ${total_tax:,.0f} of entity-level tax (line 22c) — "
                                   "unusual for an S-corp, which normally passes income through untaxed at "
                                   "the entity level. This can happen if the corporation has built-in gains "
                                   "from a prior C-corp conversion or excess net passive income; worth "
                                   "confirming which applies here."))

    if ordinary_income is not None and ordinary_income < 0:
        flags.append(Flag("info", "Ordinary business income (loss) is negative this year — a loss can "
                                   "still be usable on a shareholder's own return, subject to their stock "
                                   "and debt basis, which isn't visible from this return alone."))

    if not ordinary_income and not values.get("k_4") and not values.get("k_2"):
        flags.append(Flag("info", "No income figures were found on this return — check whether this was "
                                   "a short or dormant year, or whether the PDF's page 1 simply didn't "
                                   "have a readable text layer (common on scanned/signed copies)."))

    return flags


def build_flow_1120s(values: dict[str, float]) -> list[dict]:
    total_income = values.get("p1_6")
    total_deductions = values.get("p1_20")
    ordinary_income = values.get("p1_21") if values.get("p1_21") is not None else values.get("k_1")
    distributions = values.get("k_16d")

    steps = []
    if total_income is not None:
        steps.append({"label": "Total income", "value": total_income, "kind": "start"})
    if total_deductions:
        steps.append({"label": "Total deductions", "value": -total_deductions, "kind": "subtract"})
    if ordinary_income is not None:
        steps.append({"label": "Ordinary business income (loss)", "value": ordinary_income, "kind": "subtotal"})
    if distributions:
        steps.append({"label": "Distributions to shareholders", "value": distributions, "kind": "end"})
    return steps


_MAIN_LINE_IDS = ["p1_1c", "p1_2", "p1_3", "p1_5", "p1_7", "p1_8", "p1_12", "p1_14", "p1_19"]
_K_LINE_IDS = ["k_2", "k_4", "k_5a", "k_6", "k_7", "k_8a", "k_12a"]


def build_computation_1120s(values: dict[str, float], filing_status: str | None = None, tax_year: int | None = None) -> dict:
    def v(line_id: str) -> float | None:
        return values.get(line_id)

    ordinary_income = v("p1_21") if v("p1_21") is not None else v("k_1")
    header = {
        "label": "Form 1120-S",
        "tax_year": tax_year,
        "result_label": "Ordinary business income (loss)",
        "result_amount": ordinary_income,
    }

    income_rows = []
    for line_id in _MAIN_LINE_IDS:
        amount = v(line_id)
        if not amount:
            continue
        income_rows.append({"line": line_id.replace("p1_", ""), "item": LINE_EXPLANATIONS_1120S[line_id].split(".")[0], "amount": amount})
    total_income = v("p1_6")
    if total_income is not None:
        income_rows.append({"line": "6", "item": "Total income", "amount": total_income})
    total_deductions = v("p1_20")
    if total_deductions:
        income_rows.append({"line": "20", "item": "Total deductions", "amount": -total_deductions})
    if ordinary_income is not None:
        income_rows.append({"line": "21", "item": "Ordinary business income (loss)", "amount": ordinary_income})

    k_rows = []
    for line_id in _K_LINE_IDS:
        amount = v(line_id)
        if not amount:
            continue
        k_rows.append({"line": line_id.replace("k_", ""), "item": LINE_EXPLANATIONS_1120S[line_id].split(".")[0], "amount": amount})

    distribution_rows = []
    distributions = v("k_16d")
    if distributions:
        distribution_rows.append({"line": "16d", "item": "Distributions", "amount": distributions})

    tax_rows = []
    total_tax = v("p1_22c")
    if total_tax:
        tax_rows.append({"line": "22c", "item": "Total tax", "amount": total_tax})
    payments = v("p1_23e")
    if payments:
        tax_rows.append({"line": "23e", "item": "Total payments and credits", "amount": payments})

    sections = []
    if income_rows:
        sections.append({"title": "Income and deductions (page 1)", "rows": income_rows})
    if k_rows:
        sections.append({"title": "Schedule K — other corporate items", "rows": k_rows})
    if distribution_rows:
        sections.append({"title": "Distributions to shareholders", "rows": distribution_rows})
    if tax_rows:
        sections.append({"title": "Entity-level tax", "rows": tax_rows})

    reviewer_notes = [{"severity": f.severity, "message": f.message} for f in build_flags_1120s(values, filing_status, tax_year)]

    return {
        "header": header,
        "sections": sections,
        "tax_computation": None,
        "reviewer_notes": reviewer_notes,
    }
