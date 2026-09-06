"""Plain-language explanations, red flags, and the money-flow summary."""
from __future__ import annotations

from dataclasses import dataclass

from . import tax_data

LINE_EXPLANATIONS: dict[str, str] = {
    "1z": "Wages from your W-2s (box 1 of every W-2 you received), added together.",
    "2b": "Interest income that's taxed at your regular rate (bank interest, bond interest, etc).",
    "3a": "The portion of your dividends that qualifies for lower long-term capital gains tax rates "
          "instead of your regular rate.",
    "3b": "Dividend income from stocks or funds you own.",
    "4b": "The taxable portion of any money you took out of an IRA this year.",
    "5b": "The taxable portion of pension or annuity payments you received.",
    "6b": "The taxable portion of Social Security benefits you received (up to 85% can be taxable).",
    "7": "Net capital gain or loss from selling investments, property, etc.",
    "8": "Other income reported on Schedule 1 — things like unemployment, gambling winnings, or business income.",
    "9": "Total income: everything above, added together, before any adjustments.",
    "10": "Adjustments that reduce income before AGI is calculated — e.g. IRA contributions, student loan interest.",
    "11": "Adjusted Gross Income (AGI) — total income minus adjustments. Many other limits (like IRA "
          "deduction phase-outs) key off this number.",
    "12": "Your deduction — either the standard deduction for your filing status, or your itemized "
          "deductions (Schedule A), whichever you claimed.",
    "13": "Qualified Business Income (QBI) deduction, for income from a pass-through business (sole "
          "proprietorship, partnership, S-corp).",
    "14": "Lines 12 and 13 added together — your total deductions.",
    "15": "Taxable income: AGI minus your total deductions. This is the number the tax tables/brackets "
          "actually apply to.",
    "16": "Tax computed on your taxable income, using the tax tables or a tax computation worksheet/schedule.",
    "17": "Additional tax from Schedule 2, line 3 — commonly Alternative Minimum Tax (AMT) or repayment "
          "of excess advance premium tax credit.",
    "18": "Line 16 plus line 17 — tax before credits.",
    "19": "Child Tax Credit and/or Credit for Other Dependents.",
    "20": "Other credits from Schedule 3, line 8 (e.g. education credits, foreign tax credit, retirement "
          "savings credit).",
    "21": "Lines 19 and 20 added together — your total nonrefundable credits.",
    "22": "Tax after nonrefundable credits are applied (line 18 minus line 21).",
    "23": "Other taxes from Schedule 2 — e.g. self-employment tax, additional Medicare tax, early "
          "withdrawal penalties.",
    "24": "Total tax: your actual tax bill for the year, before counting what you've already paid in.",
    "25d": "Federal income tax already withheld from your paychecks, 1099s, etc.",
    "26": "Estimated tax payments you made during the year, plus any amount applied from last year's refund.",
    "27": "Earned Income Credit (EIC) — a refundable credit for low-to-moderate income workers.",
    "28": "Additional Child Tax Credit — the refundable portion of the Child Tax Credit.",
    "31": "Other refundable credits from Schedule 3, line 13.",
    "32": "Total of the refundable credits above (27, 28, 31, and similar).",
    "33": "Total payments: withholding, estimated payments, and refundable credits, all added together.",
    "34": "Overpayment: how much more you paid in than your total tax — this is your refund before you "
          "decide how to receive/apply it.",
    "35a": "The amount of your overpayment you're asking the IRS to refund to you.",
    "37": "Amount you owe: your total tax minus your total payments, when payments fall short.",
    # Schedule 1 — Additional Income and Adjustments to Income
    "s1_1": "Taxable refunds of state or local income tax you got back — usually only taxable if you "
            "itemized deductions the year you paid that tax.",
    "s1_3": "Net profit or loss from a sole-proprietor business, reported on Schedule C.",
    "s1_7": "Unemployment compensation you received during the year — fully taxable at the federal level.",
    "s1_9": "Other income not covered elsewhere — jury duty pay, gambling winnings, hobby income, etc.",
    "s1_10": "Total additional income from this schedule, which flows into Form 1040, line 8.",
    "s1_11": "Above-the-line deduction for money teachers/educators spend on classroom supplies.",
    "s1_13": "Deduction for contributions you made to a Health Savings Account (HSA).",
    "s1_15": "Half of your self-employment tax (line s2_4) is deductible here — it offsets the fact that "
             "self-employment tax already covers both the employer and employee share of Social Security/Medicare.",
    "s1_20": "Deduction for traditional IRA contributions, if you qualify.",
    "s1_21": "Deduction for interest paid on qualified student loans (subject to an income phase-out).",
    "s1_25": "Total adjustments to income from this schedule, which flows into Form 1040, line 10.",
    # Schedule 2 — Additional Taxes
    "s2_1": "Alternative Minimum Tax (AMT) — a parallel tax calculation that can apply if certain "
            "deductions/exclusions pushed your regular tax unusually low relative to your income.",
    "s2_2": "Repayment of excess Affordable Care Act premium tax credit, if your actual income ended up "
            "higher than what your marketplace insurance subsidy was based on.",
    "s2_3": "Total of the two lines above, which flows into Form 1040, line 17.",
    "s2_4": "Self-employment tax — Social Security and Medicare tax on net self-employment earnings, since "
            "there's no employer to withhold and match it.",
    "s2_11": "Additional 0.9% Medicare tax that applies once wages/self-employment income pass a threshold "
             "based on your filing status.",
    "s2_12": "3.8% Net Investment Income Tax on investment income (interest, dividends, capital gains, "
             "rental income) once your income is above a threshold.",
    "s2_21": "Total other taxes from this schedule, which flows into Form 1040, line 23.",
    # Schedule 3 — Additional Credits and Payments
    "s3_1": "Credit for income tax you paid to a foreign country, so it isn't taxed twice.",
    "s3_2": "Credit for money spent on care for a child or dependent so you (and a spouse, if filing "
            "jointly) could work or look for work.",
    "s3_3": "Education credits (American Opportunity Credit / Lifetime Learning Credit) for tuition and "
            "related expenses.",
    "s3_4": "Credit for lower/moderate-income taxpayers who contributed to a retirement account (the "
            "\"Saver's Credit\").",
    "s3_8": "Total nonrefundable credits from this schedule, which flows into Form 1040, line 20.",
    "s3_9": "Net premium tax credit, if you're owed more ACA marketplace subsidy than you already received "
            "in advance.",
    "s3_13": "Total other payments/refundable credits from this schedule, which flows into Form 1040, line 31.",
}


@dataclass
class Flag:
    severity: str  # "info" | "warning"
    message: str


def build_flags(
    values: dict[str, float],
    filing_status: str | None,
    tax_year: int | None = None,
) -> list[Flag]:
    flags: list[Flag] = []

    total_income = values.get("9")
    agi = values.get("11")
    taxable_income = values.get("15")
    tax = values.get("16")
    total_tax = values.get("24")
    withholding = values.get("25d")
    payments = values.get("33")
    deduction = values.get("12")
    refund = values.get("34")
    owed = values.get("37")
    capital_gains = values.get("7")
    qualified_dividends = values.get("3a")
    dividends = values.get("3b")
    se_tax = values.get("s2_4")
    niit = values.get("s2_12")
    add_medicare = values.get("s2_11")

    if total_tax is not None and total_income is not None and total_tax > total_income:
        flags.append(Flag("warning", "Total tax (line 24) is greater than total income (line 9) — "
                                      "that shouldn't happen. Worth re-checking the entered values."))

    if taxable_income is not None and taxable_income < 0:
        flags.append(Flag("warning", "Taxable income (line 15) is negative. It should be entered as 0 "
                                      "on the actual form — double-check this line."))

    if withholding is not None and withholding == 0 and total_income and total_income > 0:
        flags.append(Flag("info", "No federal withholding (line 25d) shown despite having income. "
                                   "Normal if you're self-employed or paid quarterly estimates instead."))

    if total_tax is not None and payments is not None and total_tax > 0:
        ratio = payments / total_tax
        if ratio > 1.5:
            flags.append(Flag("info", "Total payments are well above your total tax — you likely "
                                       "over-withheld and gave the IRS an interest-free loan this year. "
                                       "Consider adjusting your W-4."))
        elif ratio < 0.5:
            flags.append(Flag("warning", "Total payments cover less than half of your total tax. You may "
                                          "owe a significant amount and possibly an underpayment penalty."))

    if filing_status and deduction is not None and tax_year in tax_data.STANDARD_DEDUCTIONS:
        standard = tax_data.STANDARD_DEDUCTIONS[tax_year].get(filing_status)
        if standard is not None and deduction != 0 and abs(deduction - standard) > 100:
            flags.append(Flag("info", f"Deduction on line 12 (${deduction:,.0f}) doesn't match the "
                                       f"standard deduction for your filing status in {tax_year} "
                                       f"(${standard:,.0f}), which suggests itemized deductions "
                                       "(Schedule A) were used instead."))

    if agi is not None and total_income is not None and agi > total_income + 1:
        flags.append(Flag("warning", "AGI (line 11) is higher than total income (line 9) — adjustments "
                                      "should only reduce this number. Worth re-checking."))

    if tax is not None and taxable_income and taxable_income > 0 and tax == 0:
        flags.append(Flag("info", "Tax (line 16) is $0 despite having taxable income — check whether a "
                                   "credit or special computation applies, or whether this was parsed correctly."))

    if refund and owed:
        flags.append(Flag("warning", "Both a refund (line 34) and an amount owed (line 37) are present — "
                                      "only one of these should be filled in."))

    if tax is not None and taxable_income and filing_status and tax_year in tax_data.TAX_BRACKETS:
        brackets = tax_data.TAX_BRACKETS[tax_year].get(filing_status)
        has_preferential_income = bool(capital_gains and capital_gains > 0) or bool(qualified_dividends)
        cg_brackets = tax_data.CAPITAL_GAINS_BRACKETS.get(tax_year, {}).get(filing_status)
        if brackets and has_preferential_income and cg_brackets:
            expected = tax_data.compute_qdcgt_tax(
                taxable_income, qualified_dividends or 0, capital_gains or 0, brackets, cg_brackets,
            )
            basis = "accounting for the lower rate on your qualified dividends/long-term capital gains"
        elif brackets and not has_preferential_income:
            expected = tax_data.compute_bracket_tax(taxable_income, brackets)
            basis = "using a straightforward bracket calculation"
        else:
            expected = None
            basis = ""
        if expected is not None and expected > 0 and abs(tax - expected) / expected > 0.08 and abs(tax - expected) > 75:
            flags.append(Flag("info", f"Tax on line 16 (${tax:,.0f}) is noticeably different from what "
                                       f"{tax_year} tax rates would give on your taxable income, {basis} "
                                       f"(~${expected:,.0f}). This can be normal (tax table rounding, a "
                                       "special worksheet), but worth a second look if it surprises you."))

    if (
        agi is not None
        and filing_status
        and filing_status != "mfs"
        and tax_year in tax_data.EIC_MAX_AGI_NO_CHILDREN
        and not values.get("27")
    ):
        ceiling = tax_data.EIC_MAX_AGI_NO_CHILDREN[tax_year].get(filing_status)
        if ceiling is not None and 0 < agi <= ceiling:
            flags.append(Flag("info", "No Earned Income Credit (line 27) is shown, but your AGI is within "
                                       "the range where the credit can apply even with no qualifying "
                                       "children (higher-income limits apply with children). Worth checking "
                                       "the IRS EITC Assistant to see if you qualify."))

    if se_tax:
        flags.append(Flag("info", f"Self-employment tax of ${se_tax:,.0f} is on this return (Schedule 2, "
                                   "line 4) — that means self-employment/1099 income was reported, which "
                                   "also entitles you to a deduction for half of it on Schedule 1, line 15."))

    if (
        agi is not None
        and filing_status
        and tax_year in tax_data.AMT_EXEMPTION
        and not values.get("s2_1")
    ):
        exemption = tax_data.AMT_EXEMPTION[tax_year].get(filing_status)
        if exemption is not None and agi > exemption * 1.5:
            flags.append(Flag("info", "AGI is well above the AMT exemption amount for your filing status. "
                                       "No AMT (Schedule 2, line 1) is shown here, which is common, but "
                                       "returns with a lot of itemized deductions or exercised incentive "
                                       "stock options sometimes trigger it at this income level."))

    if agi is not None and filing_status and agi > tax_data.NIIT_THRESHOLD.get(filing_status, float("inf")):
        if (capital_gains or dividends or values.get("2b")) and not niit:
            flags.append(Flag("info", f"AGI is above the Net Investment Income Tax threshold for your "
                                       f"filing status (${tax_data.NIIT_THRESHOLD[filing_status]:,.0f}), and "
                                       "this return has investment income (interest, dividends, or capital "
                                       "gains), but no NIIT (Schedule 2, line 12) is shown. Worth checking "
                                       "whether Form 8960 applies."))

    if (
        agi is not None
        and filing_status
        and agi > tax_data.ADDITIONAL_MEDICARE_THRESHOLD.get(filing_status, float("inf"))
        and values.get("1z")
        and not add_medicare
        and not se_tax
    ):
        flags.append(Flag("info", "Wages plus other income are above the Additional Medicare Tax threshold "
                                   "for your filing status "
                                   f"(${tax_data.ADDITIONAL_MEDICARE_THRESHOLD[filing_status]:,.0f}), but no "
                                   "Additional Medicare Tax (Schedule 2, line 11) is shown. This can be "
                                   "correct if it was already withheld by an employer, so it's just worth "
                                   "a glance at your W-2 box 6."))

    return flags


# Short display names for the computation-walkthrough tables below —
# distinct from LINE_EXPLANATIONS, which is full plain-language prose meant
# for a different part of the UI.
ITEM_LABELS: dict[str, str] = {
    "1z": "Wages", "2b": "Taxable interest", "3b": "Ordinary dividends",
    "4b": "Taxable IRA distributions", "5b": "Taxable pensions/annuities",
    "6b": "Taxable Social Security", "7": "Capital gain or (loss)",
    "8": "Additional income (Schedule 1)", "9": "Total income",
    "10": "Adjustments to income", "11": "Adjusted gross income",
    "12": "Standard/itemized deduction", "13": "QBI deduction",
    "15": "Taxable income", "16": "Tax", "17": "Schedule 2, line 3",
    "18": "Add lines 16 and 17", "19": "Child tax credit / credit for other dependents",
    "20": "Schedule 3, line 8", "21": "Add lines 19 and 20",
    "22": "Subtract line 21 from line 18", "23": "Other taxes (Schedule 2)",
    "24": "Total tax", "25d": "Federal income tax withheld",
    "26": "Estimated tax payments", "27": "Earned income credit",
    "28": "Additional child tax credit", "31": "Schedule 3, line 13",
    "32": "Total other payments/refundable credits", "33": "Total payments",
    "34": "Overpayment", "37": "Amount you owe",
}

FILING_STATUS_LABELS: dict[str, str] = {
    "single": "Single", "mfj": "Married filing jointly", "mfs": "Married filing separately",
    "hoh": "Head of household", "qss": "Qualifying surviving spouse",
}

_INCOME_LINE_IDS = ["1z", "2b", "3b", "4b", "5b", "6b", "7", "8"]
_OUTCOME_LINE_IDS = ["16", "17", "18", "19", "20", "21", "22", "23", "24",
                     "25d", "26", "27", "28", "31", "32", "33"]


def build_computation(
    values: dict[str, float],
    filing_status: str | None,
    tax_year: int | None,
) -> dict:
    """A table-driven walkthrough of how this return's numbers were
    computed, in the order Form 1040 stacks up: income -> AGI -> taxable
    income -> tax (reconstructed via the bracket schedule or the Qualified
    Dividends & Capital Gain Tax Worksheet, whichever applies, and checked
    against what's actually on line 16) -> total tax -> refund/amount owed.
    Mirrors a preparer's own review of a filed return, not a re-preparation
    of it — every figure comes from what's already on the return."""

    def v(line_id: str) -> float | None:
        return values.get(line_id)

    refund = v("34")
    owed = v("37")
    header = {
        "filing_status": FILING_STATUS_LABELS.get(filing_status, filing_status),
        "tax_year": tax_year,
        "result_type": "refund" if refund else ("owed" if owed else None),
        "result_amount": refund if refund else (owed if owed else None),
    }

    # Income -> AGI
    income_rows = []
    for line_id in _INCOME_LINE_IDS:
        amount = v(line_id)
        if not amount:
            continue
        note = None
        if line_id == "3b" and v("3a"):
            note = f"of which ${v('3a'):,.0f} is qualified"
        income_rows.append({"line": line_id, "item": ITEM_LABELS[line_id], "amount": amount, "note": note})
    total_income = v("9")
    if total_income is not None:
        income_rows.append({"line": "9", "item": "Total income", "amount": total_income, "note": None})
    adjustments = v("10")
    if adjustments:
        income_rows.append({"line": "10", "item": "Adjustments to income", "amount": -adjustments, "note": None})
    agi = v("11")
    if agi is not None:
        income_rows.append({"line": "11", "item": "Adjusted gross income (AGI)", "amount": agi, "note": None})

    # AGI -> Taxable income
    deduction = v("12")
    qbi = v("13")
    taxable_income = v("15")
    deduction_note = None
    if deduction is not None and filing_status and tax_year in tax_data.STANDARD_DEDUCTIONS:
        standard = tax_data.STANDARD_DEDUCTIONS[tax_year].get(filing_status)
        if standard is not None:
            deduction_note = "standard deduction" if abs(deduction - standard) <= 1 else "itemized (Schedule A)"
    agi_to_taxable = {
        "agi": agi,
        "deduction": deduction,
        "deduction_note": deduction_note,
        "qbi": qbi,
        "taxable_income": taxable_income,
    }

    # How the tax figure is built
    tax_computation = None
    reported_tax = v("16")
    capital_gains = v("7")
    qualified_dividends = v("3a")
    if taxable_income and filing_status and tax_year in tax_data.TAX_BRACKETS:
        brackets = tax_data.TAX_BRACKETS[tax_year].get(filing_status)
        has_preferential = bool(capital_gains and capital_gains > 0) or bool(qualified_dividends)
        cg_brackets = tax_data.CAPITAL_GAINS_BRACKETS.get(tax_year, {}).get(filing_status)
        if brackets and has_preferential and cg_brackets:
            preferential = max(0.0, qualified_dividends or 0) + max(0.0, capital_gains or 0)
            preferential = min(preferential, taxable_income)
            ordinary = taxable_income - preferential
            ordinary_tax = tax_data.compute_bracket_tax(ordinary, brackets)
            cg_rows = []
            lower = ordinary
            for ceiling, rate in cg_brackets:
                upper = ceiling if ceiling is not None else float("inf")
                if taxable_income <= lower:
                    break
                band_top = min(taxable_income, max(upper, ordinary))
                taxed = max(0.0, band_top - lower)
                if taxed > 0:
                    cg_rows.append({"rate": rate, "amount": taxed, "tax": round(taxed * rate, 2)})
                lower = band_top
            reconstructed = round(ordinary_tax + sum(r["tax"] for r in cg_rows), 2)
            tax_computation = {
                "method": "qdcgt",
                "ordinary_income": ordinary,
                "ordinary_tax": ordinary_tax,
                "preferential_income": preferential,
                "preferential_rows": cg_rows,
                "reconstructed_tax": reconstructed,
                "reported_tax": reported_tax,
                "ties_out": reported_tax is not None and abs(reported_tax - reconstructed) <= max(75, reconstructed * 0.08),
            }
        elif brackets:
            bracket_rows = []
            lower = 0.0
            for ceiling, rate in brackets:
                upper = ceiling if ceiling is not None else float("inf")
                if taxable_income <= lower:
                    break
                taxed = min(taxable_income, upper) - lower
                if taxed > 0:
                    bracket_rows.append({
                        "range": f"${lower:,.0f}–${upper:,.0f}" if ceiling is not None else f"${lower:,.0f}+",
                        "rate": rate, "amount": taxed, "tax": round(taxed * rate, 2),
                    })
                lower = upper
            reconstructed = round(sum(r["tax"] for r in bracket_rows), 2)
            tax_computation = {
                "method": "brackets",
                "bracket_rows": bracket_rows,
                "reconstructed_tax": reconstructed,
                "reported_tax": reported_tax,
                "ties_out": reported_tax is not None and abs(reported_tax - reconstructed) <= max(75, reconstructed * 0.08),
            }

    # Tax -> Total tax -> Refund/Balance due
    outcome_rows = []
    for line_id in _OUTCOME_LINE_IDS:
        amount = v(line_id)
        if amount is None:
            continue
        note = None
        if line_id == "20" and v("s3_1"):
            note = "includes foreign tax credit"
        outcome_rows.append({"line": line_id, "item": ITEM_LABELS[line_id], "amount": amount, "note": note})
    if refund:
        outcome_rows.append({"line": "34", "item": "Overpayment (refund)", "amount": refund, "note": None})
    elif owed:
        outcome_rows.append({"line": "37", "item": "Amount you owe", "amount": owed, "note": None})

    reviewer_notes = [{"severity": f.severity, "message": f.message} for f in build_flags(values, filing_status, tax_year)]

    return {
        "header": header,
        "income_to_agi": income_rows,
        "agi_to_taxable": agi_to_taxable,
        "tax_computation": tax_computation,
        "tax_to_outcome": outcome_rows,
        "reviewer_notes": reviewer_notes,
    }


def build_flow(values: dict[str, float]) -> list[dict]:
    """A simplified income -> tax -> outcome waterfall for the flow diagram."""
    total_income = values.get("9")
    adjustments = values.get("10")
    agi = values.get("11")
    deductions = values.get("14")
    taxable_income = values.get("15")
    total_tax = values.get("24")
    payments = values.get("33")
    refund = values.get("34")
    owed = values.get("37")

    steps = []
    if total_income is not None:
        steps.append({"label": "Total income", "value": total_income, "kind": "start"})
    if adjustments:
        steps.append({"label": "Adjustments to income", "value": -adjustments, "kind": "subtract"})
    if agi is not None:
        steps.append({"label": "Adjusted gross income", "value": agi, "kind": "subtotal"})
    if deductions:
        steps.append({"label": "Deductions", "value": -deductions, "kind": "subtract"})
    if taxable_income is not None:
        steps.append({"label": "Taxable income", "value": taxable_income, "kind": "subtotal"})
    if total_tax is not None:
        steps.append({"label": "Total tax", "value": total_tax, "kind": "subtotal"})
    if payments is not None:
        steps.append({"label": "Total payments made", "value": payments, "kind": "info"})
    if refund:
        steps.append({"label": "Refund", "value": refund, "kind": "end"})
    elif owed:
        steps.append({"label": "Amount owed", "value": owed, "kind": "end"})
    return steps
