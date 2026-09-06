/** Plain-language explanations, red flags, and the money-flow summary.
 * Ported from backend/explain.py. */
import * as taxData from "./taxData";
import type { FilingStatus } from "./taxData";

export const LINE_EXPLANATIONS: Record<string, string> = {
  "1z": "Wages from your W-2s (box 1 of every W-2 you received), added together.",
  "2b": "Interest income that's taxed at your regular rate (bank interest, bond interest, etc).",
  "3a": "The portion of your dividends that qualifies for lower long-term capital gains tax rates " +
        "instead of your regular rate.",
  "3b": "Dividend income from stocks or funds you own.",
  "4b": "The taxable portion of any money you took out of an IRA this year.",
  "5b": "The taxable portion of pension or annuity payments you received.",
  "6b": "The taxable portion of Social Security benefits you received (up to 85% can be taxable).",
  "7": "Net capital gain or loss from selling investments, property, etc.",
  "8": "Other income reported on Schedule 1 — things like unemployment, gambling winnings, or business income.",
  "9": "Total income: everything above, added together, before any adjustments.",
  "10": "Adjustments that reduce income before AGI is calculated — e.g. IRA contributions, student loan interest.",
  "11": "Adjusted Gross Income (AGI) — total income minus adjustments. Many other limits (like IRA " +
        "deduction phase-outs) key off this number.",
  "12": "Your deduction — either the standard deduction for your filing status, or your itemized " +
        "deductions (Schedule A), whichever you claimed.",
  "13": "Qualified Business Income (QBI) deduction, for income from a pass-through business (sole " +
        "proprietorship, partnership, S-corp).",
  "14": "Lines 12 and 13 added together — your total deductions.",
  "15": "Taxable income: AGI minus your total deductions. This is the number the tax tables/brackets " +
        "actually apply to.",
  "16": "Tax computed on your taxable income, using the tax tables or a tax computation worksheet/schedule.",
  "17": "Additional tax from Schedule 2, line 3 — commonly Alternative Minimum Tax (AMT) or repayment " +
        "of excess advance premium tax credit.",
  "18": "Line 16 plus line 17 — tax before credits.",
  "19": "Child Tax Credit and/or Credit for Other Dependents.",
  "20": "Other credits from Schedule 3, line 8 (e.g. education credits, foreign tax credit, retirement " +
        "savings credit).",
  "21": "Lines 19 and 20 added together — your total nonrefundable credits.",
  "22": "Tax after nonrefundable credits are applied (line 18 minus line 21).",
  "23": "Other taxes from Schedule 2 — e.g. self-employment tax, additional Medicare tax, early " +
        "withdrawal penalties.",
  "24": "Total tax: your actual tax bill for the year, before counting what you've already paid in.",
  "25d": "Federal income tax already withheld from your paychecks, 1099s, etc.",
  "26": "Estimated tax payments you made during the year, plus any amount applied from last year's refund.",
  "27": "Earned Income Credit (EIC) — a refundable credit for low-to-moderate income workers.",
  "28": "Additional Child Tax Credit — the refundable portion of the Child Tax Credit.",
  "31": "Other refundable credits from Schedule 3, line 13.",
  "32": "Total of the refundable credits above (27, 28, 31, and similar).",
  "33": "Total payments: withholding, estimated payments, and refundable credits, all added together.",
  "34": "Overpayment: how much more you paid in than your total tax — this is your refund before you " +
        "decide how to receive/apply it.",
  "35a": "The amount of your overpayment you're asking the IRS to refund to you.",
  "37": "Amount you owe: your total tax minus your total payments, when payments fall short.",
  // Schedule 1 — Additional Income and Adjustments to Income
  "s1_1": "Taxable refunds of state or local income tax you got back — usually only taxable if you " +
          "itemized deductions the year you paid that tax.",
  "s1_3": "Net profit or loss from a sole-proprietor business, reported on Schedule C.",
  "s1_7": "Unemployment compensation you received during the year — fully taxable at the federal level.",
  "s1_9": "Other income not covered elsewhere — jury duty pay, gambling winnings, hobby income, etc.",
  "s1_10": "Total additional income from this schedule, which flows into Form 1040, line 8.",
  "s1_11": "Above-the-line deduction for money teachers/educators spend on classroom supplies.",
  "s1_13": "Deduction for contributions you made to a Health Savings Account (HSA).",
  "s1_15": "Half of your self-employment tax (line s2_4) is deductible here — it offsets the fact that " +
           "self-employment tax already covers both the employer and employee share of Social Security/Medicare.",
  "s1_20": "Deduction for traditional IRA contributions, if you qualify.",
  "s1_21": "Deduction for interest paid on qualified student loans (subject to an income phase-out).",
  "s1_25": "Total adjustments to income from this schedule, which flows into Form 1040, line 10.",
  // Schedule 2 — Additional Taxes
  "s2_1": "Alternative Minimum Tax (AMT) — a parallel tax calculation that can apply if certain " +
          "deductions/exclusions pushed your regular tax unusually low relative to your income.",
  "s2_2": "Repayment of excess Affordable Care Act premium tax credit, if your actual income ended up " +
          "higher than what your marketplace insurance subsidy was based on.",
  "s2_3": "Total of the two lines above, which flows into Form 1040, line 17.",
  "s2_4": "Self-employment tax — Social Security and Medicare tax on net self-employment earnings, since " +
          "there's no employer to withhold and match it.",
  "s2_11": "Additional 0.9% Medicare tax that applies once wages/self-employment income pass a threshold " +
           "based on your filing status.",
  "s2_12": "3.8% Net Investment Income Tax on investment income (interest, dividends, capital gains, " +
           "rental income) once your income is above a threshold.",
  "s2_21": "Total other taxes from this schedule, which flows into Form 1040, line 23.",
  // Schedule 3 — Additional Credits and Payments
  "s3_1": "Credit for income tax you paid to a foreign country, so it isn't taxed twice.",
  "s3_2": "Credit for money spent on care for a child or dependent so you (and a spouse, if filing " +
          "jointly) could work or look for work.",
  "s3_3": "Education credits (American Opportunity Credit / Lifetime Learning Credit) for tuition and " +
          "related expenses.",
  "s3_4": "Credit for lower/moderate-income taxpayers who contributed to a retirement account (the " +
          "\"Saver's Credit\").",
  "s3_8": "Total nonrefundable credits from this schedule, which flows into Form 1040, line 20.",
  "s3_9": "Net premium tax credit, if you're owed more ACA marketplace subsidy than you already received " +
          "in advance.",
  "s3_13": "Total other payments/refundable credits from this schedule, which flows into Form 1040, line 31.",
};

export interface Flag {
  severity: "info" | "warning";
  message: string;
}

export function buildFlags(
  values: Record<string, number>,
  filingStatus: string | null,
  taxYear: number | null,
): Flag[] {
  const flags: Flag[] = [];

  const totalIncome = values["9"];
  const agi = values["11"];
  const taxableIncome = values["15"];
  const tax = values["16"];
  const totalTax = values["24"];
  const withholding = values["25d"];
  const payments = values["33"];
  const deduction = values["12"];
  const refund = values["34"];
  const owed = values["37"];
  const capitalGains = values["7"];
  const qualifiedDividends = values["3a"];
  const dividends = values["3b"];
  const seTax = values["s2_4"];
  const niit = values["s2_12"];
  const addMedicare = values["s2_11"];

  if (totalTax !== undefined && totalIncome !== undefined && totalTax > totalIncome) {
    flags.push({ severity: "warning", message: "Total tax (line 24) is greater than total income (line 9) — " +
      "that shouldn't happen. Worth re-checking the entered values." });
  }

  if (taxableIncome !== undefined && taxableIncome < 0) {
    flags.push({ severity: "warning", message: "Taxable income (line 15) is negative. It should be entered " +
      "as 0 on the actual form — double-check this line." });
  }

  if (withholding === 0 && totalIncome !== undefined && totalIncome > 0) {
    flags.push({ severity: "info", message: "No federal withholding (line 25d) shown despite having " +
      "income. Normal if you're self-employed or paid quarterly estimates instead." });
  }

  if (totalTax !== undefined && payments !== undefined && totalTax > 0) {
    const ratio = payments / totalTax;
    if (ratio > 1.5) {
      flags.push({ severity: "info", message: "Total payments are well above your total tax — you likely " +
        "over-withheld and gave the IRS an interest-free loan this year. Consider adjusting your W-4." });
    } else if (ratio < 0.5) {
      flags.push({ severity: "warning", message: "Total payments cover less than half of your total tax. " +
        "You may owe a significant amount and possibly an underpayment penalty." });
    }
  }

  if (filingStatus && deduction !== undefined && taxYear !== null && taxData.STANDARD_DEDUCTIONS[taxYear]) {
    const standard = taxData.STANDARD_DEDUCTIONS[taxYear][filingStatus as FilingStatus];
    if (standard !== undefined && deduction !== 0 && Math.abs(deduction - standard) > 100) {
      flags.push({ severity: "info", message: `Deduction on line 12 ($${deduction.toLocaleString()}) ` +
        `doesn't match the standard deduction for your filing status in ${taxYear} ` +
        `($${standard.toLocaleString()}), which suggests itemized deductions (Schedule A) were used instead.` });
    }
  }

  if (agi !== undefined && totalIncome !== undefined && agi > totalIncome + 1) {
    flags.push({ severity: "warning", message: "AGI (line 11) is higher than total income (line 9) — " +
      "adjustments should only reduce this number. Worth re-checking." });
  }

  if (tax !== undefined && taxableIncome && taxableIncome > 0 && tax === 0) {
    flags.push({ severity: "info", message: "Tax (line 16) is $0 despite having taxable income — check " +
      "whether a credit or special computation applies, or whether this was parsed correctly." });
  }

  if (refund && owed) {
    flags.push({ severity: "warning", message: "Both a refund (line 34) and an amount owed (line 37) are " +
      "present — only one of these should be filled in." });
  }

  if (tax !== undefined && taxableIncome && filingStatus && taxYear !== null && taxData.TAX_BRACKETS[taxYear]) {
    const brackets = taxData.TAX_BRACKETS[taxYear][filingStatus as FilingStatus];
    const hasPreferentialIncome = !!(capitalGains && capitalGains > 0) || !!qualifiedDividends;
    const cgBrackets = taxData.CAPITAL_GAINS_BRACKETS[taxYear]?.[filingStatus as FilingStatus];
    let expected: number | undefined;
    let basis = "";
    if (brackets && hasPreferentialIncome && cgBrackets) {
      expected = taxData.computeQdcgtTax(
        taxableIncome, qualifiedDividends || 0, capitalGains || 0, brackets, cgBrackets,
      );
      basis = "accounting for the lower rate on your qualified dividends/long-term capital gains";
    } else if (brackets && !hasPreferentialIncome) {
      expected = taxData.computeBracketTax(taxableIncome, brackets);
      basis = "using a straightforward bracket calculation";
    }
    if (expected !== undefined && expected > 0 && Math.abs(tax - expected) / expected > 0.08 && Math.abs(tax - expected) > 75) {
      flags.push({ severity: "info", message: `Tax on line 16 ($${tax.toLocaleString()}) is noticeably ` +
        `different from what ${taxYear} tax rates would give on your taxable income, ${basis} ` +
        `(~$${expected.toLocaleString()}). This can be normal (tax table rounding, a special worksheet), ` +
        "but worth a second look if it surprises you." });
    }
  }

  if (
    agi !== undefined &&
    filingStatus &&
    filingStatus !== "mfs" &&
    taxYear !== null &&
    taxData.EIC_MAX_AGI_NO_CHILDREN[taxYear] &&
    !values["27"]
  ) {
    const ceiling = taxData.EIC_MAX_AGI_NO_CHILDREN[taxYear][filingStatus as FilingStatus];
    if (ceiling !== undefined && agi > 0 && agi <= ceiling) {
      flags.push({ severity: "info", message: "No Earned Income Credit (line 27) is shown, but your AGI is " +
        "within the range where the credit can apply even with no qualifying children (higher-income limits " +
        "apply with children). Worth checking the IRS EITC Assistant to see if you qualify." });
    }
  }

  if (seTax) {
    flags.push({ severity: "info", message: `Self-employment tax of $${seTax.toLocaleString()} is on this ` +
      "return (Schedule 2, line 4) — that means self-employment/1099 income was reported, which also " +
      "entitles you to a deduction for half of it on Schedule 1, line 15." });
  }

  if (agi !== undefined && filingStatus && taxYear !== null && taxData.AMT_EXEMPTION[taxYear] && !values["s2_1"]) {
    const exemption = taxData.AMT_EXEMPTION[taxYear][filingStatus as FilingStatus];
    if (exemption !== undefined && agi > exemption * 1.5) {
      flags.push({ severity: "info", message: "AGI is well above the AMT exemption amount for your filing " +
        "status. No AMT (Schedule 2, line 1) is shown here, which is common, but returns with a lot of " +
        "itemized deductions or exercised incentive stock options sometimes trigger it at this income level." });
    }
  }

  if (agi !== undefined && filingStatus && agi > (taxData.NIIT_THRESHOLD[filingStatus as FilingStatus] ?? Infinity)) {
    if ((capitalGains || dividends || values["2b"]) && !niit) {
      const threshold = taxData.NIIT_THRESHOLD[filingStatus as FilingStatus];
      flags.push({ severity: "info", message: "AGI is above the Net Investment Income Tax threshold for " +
        `your filing status ($${threshold.toLocaleString()}), and this return has investment income ` +
        "(interest, dividends, or capital gains), but no NIIT (Schedule 2, line 12) is shown. Worth checking " +
        "whether Form 8960 applies." });
    }
  }

  if (
    agi !== undefined &&
    filingStatus &&
    agi > (taxData.ADDITIONAL_MEDICARE_THRESHOLD[filingStatus as FilingStatus] ?? Infinity) &&
    values["1z"] &&
    !addMedicare &&
    !seTax
  ) {
    const threshold = taxData.ADDITIONAL_MEDICARE_THRESHOLD[filingStatus as FilingStatus];
    flags.push({ severity: "info", message: "Wages plus other income are above the Additional Medicare Tax " +
      `threshold for your filing status ($${threshold.toLocaleString()}), but no Additional Medicare Tax ` +
      "(Schedule 2, line 11) is shown. This can be correct if it was already withheld by an employer, so " +
      "it's just worth a glance at your W-2 box 6." });
  }

  return flags;
}

export interface FlowStep {
  label: string;
  value: number;
  kind: "start" | "subtract" | "subtotal" | "info" | "end";
}

/** A simplified income -> tax -> outcome waterfall for the flow diagram. */
export function buildFlow(values: Record<string, number>): FlowStep[] {
  const totalIncome = values["9"];
  const adjustments = values["10"];
  const agi = values["11"];
  const deductions = values["14"];
  const taxableIncome = values["15"];
  const totalTax = values["24"];
  const payments = values["33"];
  const refund = values["34"];
  const owed = values["37"];

  const steps: FlowStep[] = [];
  if (totalIncome !== undefined) steps.push({ label: "Total income", value: totalIncome, kind: "start" });
  if (adjustments) steps.push({ label: "Adjustments to income", value: -adjustments, kind: "subtract" });
  if (agi !== undefined) steps.push({ label: "Adjusted gross income", value: agi, kind: "subtotal" });
  if (deductions) steps.push({ label: "Deductions", value: -deductions, kind: "subtract" });
  if (taxableIncome !== undefined) steps.push({ label: "Taxable income", value: taxableIncome, kind: "subtotal" });
  if (totalTax !== undefined) steps.push({ label: "Total tax", value: totalTax, kind: "subtotal" });
  if (payments !== undefined) steps.push({ label: "Total payments made", value: payments, kind: "info" });
  if (refund) steps.push({ label: "Refund", value: refund, kind: "end" });
  else if (owed) steps.push({ label: "Amount owed", value: owed, kind: "end" });
  return steps;
}
