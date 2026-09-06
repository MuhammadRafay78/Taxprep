"""Plain-language explanations, red flags, and the money-flow summary."""
from __future__ import annotations

from dataclasses import dataclass

from . import tax_data

LINE_EXPLANATIONS: dict[str, str] = {
    "1z": "Wages from your W-2s (box 1 of every W-2 you received), added together.",
    "2b": "Interest income that's taxed at your regular rate (bank interest, bond interest, etc).",
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
    dividends = values.get("3b")
    se_tax = values.get("s2_4")

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

    if (
        tax is not None
        and taxable_income
        and filing_status
        and tax_year in tax_data.TAX_BRACKETS
        and not capital_gains
        and not dividends
    ):
        brackets = tax_data.TAX_BRACKETS[tax_year].get(filing_status)
        if brackets:
            expected = tax_data.compute_bracket_tax(taxable_income, brackets)
            if expected > 0 and abs(tax - expected) / expected > 0.08 and abs(tax - expected) > 75:
                flags.append(Flag("info", f"Tax on line 16 (${tax:,.0f}) is noticeably different from a "
                                           f"straightforward {tax_year} bracket calculation on your taxable "
                                           f"income (~${expected:,.0f}). This can be normal (tax table "
                                           "rounding, a special worksheet), but worth a second look if it "
                                           "surprises you."))

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

    return flags


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
