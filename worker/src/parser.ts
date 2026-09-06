/**
 * Best-effort extraction of key line values from a Form 1040 PDF (plus
 * Schedules 1, 2, and 3). Ported from backend/parser.py — see that file's
 * module docstring for the full rationale; the short version: match each
 * row first by a distinctive label phrase (several variants per line, to
 * survive wording differences across tax years/software), then fall back to
 * a row simply starting with the line's own number, scoped to that
 * schedule's own pages so bare numbers don't collide across schedules.
 */
import { extractPdfPages } from "./pdfText";

const AMOUNT_RE = /^\(?\$?-?[\d,]+(?:\.\d{1,2})?\)?$/;

function parseAmount(token: string): number | null {
  const negative = token.startsWith("(") && token.endsWith(")");
  const cleaned = token.replace(/[()$]/g, "").replace(/,/g, "");
  if (!cleaned) return null;
  const value = Number(cleaned);
  if (Number.isNaN(value)) return null;
  return negative ? -value : value;
}

function lastAmountInLine(line: string): number | null {
  const tokens = line.split(/\s+/).filter(Boolean);
  for (let i = tokens.length - 1; i >= 0; i--) {
    if (AMOUNT_RE.test(tokens[i])) {
      const amount = parseAmount(tokens[i]);
      if (amount !== null) return amount;
    }
  }
  return null;
}

function startsWithNumber(rowLower: string, number: string): boolean {
  const tokens = rowLower.split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return false;
  return tokens[0].replace(/[.:]+$/, "") === number.toLowerCase();
}

export type LineDefinition = [id: string, label: string, phrases: string[], fallbackNumber: string];

export const LINE_DEFINITIONS: LineDefinition[] = [
  ["1z", "Total wages (Form W-2 box 1)",
    ["add lines 1a through 1h", "wages, salaries, tips", "total is your total wages"], "1z"],
  ["2b", "Taxable interest", ["taxable interest"], "2b"],
  ["3b", "Ordinary dividends", ["ordinary dividends"], "3b"],
  ["4b", "Taxable IRA distributions", ["ira distributions", "taxable amount"], "4b"],
  ["5b", "Taxable pensions and annuities", ["pensions and annuities"], "5b"],
  ["6b", "Taxable social security benefits", ["social security benefits"], "6b"],
  ["7", "Capital gain or (loss)", ["capital gain or", "capital gain (or loss)"], "7"],
  ["8", "Additional income (Schedule 1)",
    ["additional income from schedule 1", "other income from schedule 1"], "8"],
  ["9", "Total income", ["total income"], "9"],
  ["10", "Adjustments to income", ["adjustments to income"], "10"],
  ["11", "Adjusted gross income (AGI)", ["adjusted gross income"], "11"],
  ["12", "Standard deduction or itemized deductions",
    ["standard deduction or itemized", "itemized deductions (from schedule a)"], "12"],
  ["13", "Qualified business income deduction", ["qualified business income deduction"], "13"],
  ["14", "Total deductions", ["add lines 12 and 13"], "14"],
  ["15", "Taxable income", ["taxable income"], "15"],
  ["16", "Tax", ["tax (see instructions)", "check if any from form"], "16"],
  ["17", "Schedule 2, line 3 (AMT / excess APTC)", ["amount from schedule 2, line 3"], "17"],
  ["18", "Add lines 16 and 17", ["add lines 16 and 17"], "18"],
  ["19", "Child tax credit / credit for other dependents",
    ["child tax credit or credit for other dependents"], "19"],
  ["20", "Schedule 3, line 8", ["amount from schedule 3, line 8"], "20"],
  ["21", "Add lines 19 and 20", ["add lines 19 and 20"], "21"],
  ["22", "Subtract line 21 from line 18", ["subtract line 21 from line 18"], "22"],
  ["23", "Other taxes (Schedule 2)",
    ["other taxes, including self-employment tax", "amount from schedule 2, line 21"], "23"],
  ["24", "Total tax", ["total tax"], "24"],
  ["25d", "Federal income tax withheld",
    ["add lines 25a through 25c", "total is your total federal income tax withheld"], "25d"],
  ["26", "Estimated tax payments", ["estimated tax payments"], "26"],
  ["27", "Earned income credit (EIC)", ["earned income credit"], "27"],
  ["28", "Additional child tax credit", ["additional child tax credit"], "28"],
  ["31", "Schedule 3, line 13", ["amount from schedule 3, line 13"], "31"],
  ["32", "Total other payments and refundable credits",
    ["total other payments or refundable credits"], "32"],
  ["33", "Total payments", ["total payments"], "33"],
  ["34", "Overpayment (refund)", ["overpaid"], "34"],
  ["35a", "Refund amount", ["amount of line 34 you want refunded"], "35a"],
  ["37", "Amount you owe", ["subtract line 33 from line 24", "amount you owe"], "37"],
];

const SCHEDULE_TITLE_MARKERS: Record<"s1" | "s2" | "s3", string[]> = {
  s1: ["additional income and adjustments to income"],
  s2: ["additional taxes"],
  s3: ["additional credits and payments"],
};

export const SCHEDULE1_DEFINITIONS: LineDefinition[] = [
  ["s1_1", "Taxable refunds of state/local taxes", ["taxable refunds, credits"], "1"],
  ["s1_3", "Business income or (loss) (Schedule C)", ["business income or (loss)"], "3"],
  ["s1_7", "Unemployment compensation", ["unemployment compensation"], "7"],
  ["s1_9", "Total other income", ["add lines 1 through 8", "total other income"], "9"],
  ["s1_10", "Total additional income",
    ["combine lines 1 through 7 and 9", "add lines 1, 2c", "total additional income"], "10"],
  ["s1_11", "Educator expenses", ["educator expenses"], "11"],
  ["s1_13", "HSA deduction", ["health savings account deduction"], "13"],
  ["s1_15", "Deductible part of self-employment tax", ["deductible part of self-employment tax"], "15"],
  ["s1_20", "IRA deduction", ["ira deduction"], "20"],
  ["s1_21", "Student loan interest deduction", ["student loan interest deduction"], "21"],
  ["s1_25", "Total adjustments to income", ["add lines 11 through 23", "total adjustments"], "25"],
];

export const SCHEDULE2_DEFINITIONS: LineDefinition[] = [
  ["s2_1", "Alternative Minimum Tax (AMT)", ["alternative minimum tax"], "1"],
  ["s2_2", "Excess advance premium tax credit repayment", ["excess advance premium tax credit"], "2"],
  ["s2_3", "Total (Part I)", ["add lines 1 and 2", "amount from schedule 2, line 3"], "3"],
  ["s2_4", "Self-employment tax", ["self-employment tax"], "4"],
  ["s2_11", "Additional Medicare Tax", ["additional medicare tax"], "11"],
  ["s2_12", "Net investment income tax", ["net investment income tax"], "12"],
  ["s2_21", "Total other taxes (Part II)", ["add lines 4 through 18", "total other taxes"], "21"],
];

export const SCHEDULE3_DEFINITIONS: LineDefinition[] = [
  ["s3_1", "Foreign tax credit", ["foreign tax credit"], "1"],
  ["s3_2", "Child and dependent care credit", ["credit for child and dependent care"], "2"],
  ["s3_3", "Education credits", ["education credits"], "3"],
  ["s3_4", "Retirement savings contributions credit", ["retirement savings contributions credit"], "4"],
  ["s3_8", "Total nonrefundable credits (Part I)",
    ["add lines 1 through 4", "amount from schedule 3, line 8"], "8"],
  ["s3_9", "Net premium tax credit", ["net premium tax credit"], "9"],
  ["s3_13", "Total other payments/refundable credits (Part II)",
    ["add lines 9 through 12", "amount from schedule 3, line 13"], "13"],
];

const FILING_STATUS_PATTERNS: [string, RegExp][] = [
  ["single", /\bsingle\b/],
  ["mfj", /married filing jointly/],
  ["mfs", /married filing separately/],
  ["hoh", /head of household/],
  ["qss", /qualifying surviving spouse/],
];

const TAX_YEAR_RE = /\b(20[1-3][0-9])\b/;

export interface ExtractedLine {
  id: string;
  label: string;
  value: number | null;
  confidence: "matched" | "not_found";
  group: string;
}

export interface ExtractionResult {
  lines: ExtractedLine[];
  filingStatus: string | null;
  taxYear: number | null;
  rawText: string;
}

export function asValueMap(lines: ExtractedLine[]): Record<string, number> {
  const values: Record<string, number> = {};
  for (const ln of lines) if (ln.value !== null) values[ln.id] = ln.value;
  return values;
}

function detectFilingStatus(text: string): string | null {
  const lowered = text.toLowerCase();
  for (const [statusId, pattern] of FILING_STATUS_PATTERNS) {
    if (pattern.test(lowered)) return statusId;
  }
  return null;
}

function detectTaxYear(text: string): number | null {
  const header = text.slice(0, 600);
  const match = TAX_YEAR_RE.exec(header);
  return match ? parseInt(match[1], 10) : null;
}

function findSchedulePageStarts(pages: string[]): Record<"s1" | "s2" | "s3", number | null> {
  const starts: Record<"s1" | "s2" | "s3", number | null> = { s1: null, s2: null, s3: null };
  for (const key of Object.keys(SCHEDULE_TITLE_MARKERS) as ("s1" | "s2" | "s3")[]) {
    const markers = SCHEDULE_TITLE_MARKERS[key];
    for (let i = 0; i < pages.length; i++) {
      const pageLower = pages[i].toLowerCase();
      if (markers.some((marker) => pageLower.includes(marker))) {
        starts[key] = i;
        break;
      }
    }
  }
  return starts;
}

function matchByPhrase(lines: string[], phrases: string[]): number | null {
  for (const row of lines) {
    const rowLower = row.trim().toLowerCase();
    if (phrases.some((phrase) => rowLower.includes(phrase))) {
      const candidate = lastAmountInLine(row);
      if (candidate !== null) return candidate;
    }
  }
  return null;
}

function matchByNumber(lines: string[] | null, number: string): number | null {
  if (lines === null) return null;
  for (const row of lines) {
    const rowLower = row.trim().toLowerCase();
    if (startsWithNumber(rowLower, number)) {
      const candidate = lastAmountInLine(row);
      if (candidate !== null) return candidate;
    }
  }
  return null;
}

function extractGroup(
  phraseScope: string[],
  fallbackScope: string[] | null,
  definitions: LineDefinition[],
  group: string,
): ExtractedLine[] {
  return definitions.map(([id, label, phrases, fallbackNumber]) => {
    let value = matchByPhrase(phraseScope, phrases);
    if (value === null) value = matchByNumber(fallbackScope, fallbackNumber);
    return {
      id,
      label,
      value,
      confidence: value !== null ? "matched" : "not_found",
      group,
    } as ExtractedLine;
  });
}

export async function parse1040(bytes: Uint8Array): Promise<ExtractionResult> {
  const pageLines = await extractPdfPages(bytes);
  const pageTexts = pageLines.map((rows) => rows.join("\n"));
  const text = pageTexts.join("\n");

  const starts = findSchedulePageStarts(pageTexts);
  const totalPages = pageLines.length;
  const scheduleStarts = Object.values(starts).filter((s): s is number => s !== null);
  const firstSchedulePage = scheduleStarts.length > 0 ? Math.min(...scheduleStarts) : totalPages;

  const flatten = (a: number, b: number): string[] => pageLines.slice(a, b).flat();

  const scopeFor = (key: "s1" | "s2" | "s3"): string[] | null => {
    const start = starts[key];
    if (start === null) return null;
    const laterStarts = (Object.keys(starts) as ("s1" | "s2" | "s3")[])
      .filter((k) => k !== key && starts[k] !== null && (starts[k] as number) > start)
      .map((k) => starts[k] as number);
    const end = laterStarts.length > 0 ? Math.min(...laterStarts) : totalPages;
    return flatten(start, end);
  };

  const mainScope = flatten(0, firstSchedulePage);
  const allLines = flatten(0, totalPages);
  const s1Scope = scopeFor("s1");
  const s2Scope = scopeFor("s2");
  const s3Scope = scopeFor("s3");

  const lines: ExtractedLine[] = [
    ...extractGroup(mainScope, mainScope, LINE_DEFINITIONS, "Form 1040"),
    ...extractGroup(s1Scope ?? allLines, s1Scope, SCHEDULE1_DEFINITIONS,
      "Schedule 1 (Additional Income & Adjustments)"),
    ...extractGroup(s2Scope ?? allLines, s2Scope, SCHEDULE2_DEFINITIONS,
      "Schedule 2 (Additional Taxes)"),
    ...extractGroup(s3Scope ?? allLines, s3Scope, SCHEDULE3_DEFINITIONS,
      "Schedule 3 (Additional Credits & Payments)"),
  ];

  return {
    lines,
    filingStatus: detectFilingStatus(text),
    taxYear: detectTaxYear(text),
    rawText: text,
  };
}
