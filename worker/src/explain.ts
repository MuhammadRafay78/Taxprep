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

// Short display names for the computation-walkthrough tables — distinct
// from LINE_EXPLANATIONS, which is full plain-language prose for a
// different part of the UI. Ported from backend/explain.py's ITEM_LABELS.
const ITEM_LABELS: Record<string, string> = {
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
};

const FILING_STATUS_LABELS: Record<string, string> = {
  single: "Single", mfj: "Married filing jointly", mfs: "Married filing separately",
  hoh: "Head of household", qss: "Qualifying surviving spouse",
};

const INCOME_LINE_IDS = ["1z", "2b", "3b", "4b", "5b", "6b", "7", "8"];
const OUTCOME_LINE_IDS = ["16", "17", "18", "19", "20", "21", "22", "23", "24",
  "25d", "26", "27", "28", "31", "32", "33"];

export interface ComputationRow {
  line: string;
  item: string;
  amount: number;
  note: string | null;
}

export interface Computation {
  header: {
    filingStatus: string | null;
    taxYear: number | null;
    resultType: "refund" | "owed" | null;
    resultAmount: number | null;
  };
  incomeToAgi: ComputationRow[];
  agiToTaxable: {
    agi: number | null;
    deduction: number | null;
    deductionNote: string | null;
    qbi: number | null;
    taxableIncome: number | null;
  };
  taxComputation: {
    method: "qdcgt" | "brackets";
    ordinaryIncome?: number;
    ordinaryTax?: number;
    ordinaryBracketRows?: { range: string; rate: number; amount: number; tax: number }[];
    preferentialIncome?: number;
    preferentialRows?: { rate: number; amount: number; tax: number }[];
    bracketRows?: { range: string; rate: number; amount: number; tax: number }[];
    reconstructedTax: number;
    reportedTax: number | undefined;
    tiesOut: boolean;
  } | null;
  taxToOutcome: ComputationRow[];
  otherTaxRows: { line: string; item: string; amount: number }[];
  reviewerNotes: Flag[];
}

// Short display labels for Schedule 2's "other taxes" (line 23) components —
// shown as their own breakdown in the walkthrough instead of a single lumped
// number, the same way credits/income already break down into their parts.
const OTHER_TAX_LINE_IDS = ["s2_4", "s2_11", "s2_12", "s2_1", "s2_2"];
const OTHER_TAX_LABELS: Record<string, string> = {
  s2_4: "Self-employment tax",
  s2_11: "Additional Medicare Tax",
  s2_12: "Net Investment Income Tax",
  s2_1: "Alternative Minimum Tax (AMT)",
  s2_2: "Excess advance premium tax credit repayment",
};

/** The bracket-by-bracket breakdown of tax on `amount` under a progressive
 * schedule — one row per bracket actually reached, each with the dollar
 * range, rate, amount taxed at that rate, and the tax it produced. Shared
 * by both the plain-brackets and QDCGT computation methods below, since
 * ordinary income is taxed the same progressive way in either case — QDCGT
 * just taxes a preferential slice on top of it separately instead of
 * running the whole taxable income through this. */
function bracketRowsFor(
  amount: number,
  brackets: [number | null, number][],
): { range: string; rate: number; amount: number; tax: number }[] {
  const rows: { range: string; rate: number; amount: number; tax: number }[] = [];
  let lower = 0;
  for (const [ceiling, rate] of brackets) {
    const upper = ceiling ?? Infinity;
    if (amount <= lower) break;
    const taxed = Math.min(amount, upper) - lower;
    if (taxed > 0) {
      rows.push({
        range: ceiling !== null ? `$${lower.toLocaleString()}–$${upper.toLocaleString()}` : `$${lower.toLocaleString()}+`,
        rate, amount: taxed, tax: Math.round(taxed * rate * 100) / 100,
      });
    }
    lower = upper;
  }
  return rows;
}

/** A table-driven walkthrough of how this return's numbers were computed,
 * in the order Form 1040 stacks up: income -> AGI -> taxable income -> tax
 * (reconstructed via the bracket schedule or the Qualified Dividends &
 * Capital Gain Tax Worksheet, whichever applies, checked against line 16)
 * -> total tax -> refund/amount owed. Ported from backend/explain.py's
 * build_computation(). */
export function buildComputation(
  values: Record<string, number>,
  filingStatus: string | null,
  taxYear: number | null,
): Computation {
  const v = (id: string): number | undefined => values[id];

  const refund = v("34");
  const owed = v("37");
  const header = {
    filingStatus: filingStatus ? (FILING_STATUS_LABELS[filingStatus] ?? filingStatus) : null,
    taxYear,
    resultType: refund ? ("refund" as const) : owed ? ("owed" as const) : null,
    resultAmount: refund ? refund : owed ? owed : null,
  };

  const incomeToAgi: ComputationRow[] = [];
  for (const lineId of INCOME_LINE_IDS) {
    const amount = v(lineId);
    if (!amount) continue;
    let note: string | null = null;
    if (lineId === "3b" && v("3a")) note = `of which $${v("3a")!.toLocaleString()} is qualified`;
    incomeToAgi.push({ line: lineId, item: ITEM_LABELS[lineId], amount, note });
  }
  const totalIncome = v("9");
  if (totalIncome !== undefined) incomeToAgi.push({ line: "9", item: "Total income", amount: totalIncome, note: null });
  const adjustments = v("10");
  if (adjustments) incomeToAgi.push({ line: "10", item: "Adjustments to income", amount: -adjustments, note: null });
  const agi = v("11");
  if (agi !== undefined) incomeToAgi.push({ line: "11", item: "Adjusted gross income (AGI)", amount: agi, note: null });

  const deduction = v("12");
  const qbi = v("13");
  const taxableIncome = v("15");
  let deductionNote: string | null = null;
  if (deduction !== undefined && filingStatus && taxYear !== null && taxData.STANDARD_DEDUCTIONS[taxYear]) {
    const standard = taxData.STANDARD_DEDUCTIONS[taxYear][filingStatus as FilingStatus];
    if (standard !== undefined) {
      deductionNote = Math.abs(deduction - standard) <= 1 ? "standard deduction" : "itemized (Schedule A)";
    }
  }
  const agiToTaxable = {
    agi: agi ?? null, deduction: deduction ?? null, deductionNote,
    qbi: qbi ?? null, taxableIncome: taxableIncome ?? null,
  };

  let taxComputation: Computation["taxComputation"] = null;
  const reportedTax = v("16");
  const capitalGains = v("7");
  const qualifiedDividends = v("3a");
  if (taxableIncome && filingStatus && taxYear !== null && taxData.TAX_BRACKETS[taxYear]) {
    const brackets = taxData.TAX_BRACKETS[taxYear][filingStatus as FilingStatus];
    const hasPreferential = !!(capitalGains && capitalGains > 0) || !!qualifiedDividends;
    const cgBrackets = taxData.CAPITAL_GAINS_BRACKETS[taxYear]?.[filingStatus as FilingStatus];
    if (brackets && hasPreferential && cgBrackets) {
      let preferential = Math.max(0, qualifiedDividends || 0) + Math.max(0, capitalGains || 0);
      preferential = Math.min(preferential, taxableIncome);
      const ordinary = taxableIncome - preferential;
      const ordinaryBracketRows = bracketRowsFor(ordinary, brackets);
      const ordinaryTax = Math.round(ordinaryBracketRows.reduce((s, r) => s + r.tax, 0) * 100) / 100;
      const preferentialRows: { rate: number; amount: number; tax: number }[] = [];
      let lower = ordinary;
      for (const [ceiling, rate] of cgBrackets) {
        const upper = ceiling ?? Infinity;
        if (taxableIncome <= lower) break;
        const bandTop = Math.min(taxableIncome, Math.max(upper, ordinary));
        const taxed = Math.max(0, bandTop - lower);
        if (taxed > 0) preferentialRows.push({ rate, amount: taxed, tax: Math.round(taxed * rate * 100) / 100 });
        lower = bandTop;
      }
      const reconstructed = Math.round((ordinaryTax + preferentialRows.reduce((s, r) => s + r.tax, 0)) * 100) / 100;
      taxComputation = {
        method: "qdcgt", ordinaryIncome: ordinary, ordinaryTax, ordinaryBracketRows, preferentialIncome: preferential,
        preferentialRows, reconstructedTax: reconstructed, reportedTax,
        tiesOut: reportedTax !== undefined && Math.abs(reportedTax - reconstructed) <= Math.max(75, reconstructed * 0.08),
      };
    } else if (brackets) {
      const bracketRows = bracketRowsFor(taxableIncome, brackets);
      const reconstructed = Math.round(bracketRows.reduce((s, r) => s + r.tax, 0) * 100) / 100;
      taxComputation = {
        method: "brackets", bracketRows, reconstructedTax: reconstructed, reportedTax,
        tiesOut: reportedTax !== undefined && Math.abs(reportedTax - reconstructed) <= Math.max(75, reconstructed * 0.08),
      };
    }
  }

  const hasOtherTax = OTHER_TAX_LINE_IDS.some((id) => v(id));
  const taxToOutcome: ComputationRow[] = [];
  for (const lineId of OUTCOME_LINE_IDS) {
    const amount = v(lineId);
    if (amount === undefined) continue;
    const note = lineId === "23" && hasOtherTax ? "see the breakdown below" : null;
    taxToOutcome.push({ line: lineId, item: ITEM_LABELS[lineId], amount, note });
  }
  if (refund) taxToOutcome.push({ line: "34", item: "Overpayment (refund)", amount: refund, note: null });
  else if (owed) taxToOutcome.push({ line: "37", item: "Amount you owe", amount: owed, note: null });

  // Line 23 ("other taxes") is itself a sum of very different things — SE
  // tax, AMT, NIIT, Additional Medicare Tax — that a single lumped number
  // doesn't distinguish. Broken out here the same way credits/income
  // already are.
  const otherTaxRows = OTHER_TAX_LINE_IDS
    .filter((id) => v(id))
    .map((id) => ({ line: id.replace("s2_", ""), item: OTHER_TAX_LABELS[id], amount: v(id)! }));

  const reviewerNotes = buildFlags(values, filingStatus, taxYear);

  return { header, incomeToAgi, agiToTaxable, taxComputation, taxToOutcome, otherTaxRows, reviewerNotes };
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
