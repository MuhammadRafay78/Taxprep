/**
 * Best-effort extraction of key line values from a Form 1040 PDF (plus
 * Schedules 1, 2, 3, and any other attached form/schedule). Ported from
 * backend/parser.py — see that file's module docstring and inline comments
 * for the full rationale of each design choice; kept in lockstep here.
 */
import { extractPdfPages } from "./pdfText";

// Requires proper thousands-grouping (",ddd" in groups of exactly 3) when a
// comma is present, and allows 0-2 digits after a decimal point (real IRS
// forms print whole-dollar amounts as e.g. "1,200." with an empty cents
// spot). This is deliberately stricter than "any digits and commas" so it
// doesn't accidentally match a form/line cross-reference embedded in prose,
// like the "2441" in "...from Form 2441," or "line 11.".
const AMOUNT_RE = /^\(?\$?-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{0,2})?\)?$/;

function parseAmount(token: string): number | null {
  const negative = token.startsWith("(") && token.endsWith(")");
  const cleaned = token.replace(/[()$]/g, "").replace(/,/g, "");
  if (!cleaned || cleaned === ".") return null;
  const value = Number(cleaned);
  if (Number.isNaN(value)) return null;
  return negative ? -value : value;
}

function isBareInteger(token: string): boolean {
  const core = token.replace(/[()$]/g, "");
  return !core.includes(",") && !core.includes(".");
}

// A row's text can (rarely, in odd PDF exports) have a thousands-separator
// comma followed by a stray space, splitting a real amount like "51,808"
// into two tokens "51," and "808" — left unmerged, every amount check
// below would only ever see the trailing "808", silently truncating a
// real dollar figure. TOKENIZE_LEAD_RE matches the first group of a split
// number ("51,", "$1,", "(2,"); TOKENIZE_MID_RE a continuation group for
// numbers with more than one comma ("234,"); TOKENIZE_TAIL_RE the final
// group, with no trailing comma.
const TOKENIZE_LEAD_RE = /^\(?\$?-?\d{1,3},$/;
const TOKENIZE_MID_RE = /^\d{3},$/;
const TOKENIZE_TAIL_RE = /^\d{3}(?:\.\d{0,2})?\)?$/;

function tokenize(row: string): string[] {
  const raw = row.split(/\s+/).filter(Boolean);
  const tokens: string[] = [];
  let i = 0;
  while (i < raw.length) {
    if (TOKENIZE_LEAD_RE.test(raw[i])) {
      let j = i + 1;
      let combined = raw[i];
      while (j < raw.length && TOKENIZE_MID_RE.test(raw[j])) {
        combined += raw[j];
        j++;
      }
      if (j < raw.length && TOKENIZE_TAIL_RE.test(raw[j])) {
        combined += raw[j];
        tokens.push(combined);
        i = j + 1;
        continue;
      }
    }
    tokens.push(raw[i]);
    i++;
  }
  return tokens;
}

const LINE_NUMBER_START_RE = /^\d{1,2}[a-z]?$/i;

/**
 * True if this row looks like it opens with a different line's own number
 * (e.g. "9", "10", "1z") — a strong signal that the previous row's label
 * genuinely ended (however garbled its own trailing text), rather than
 * continuing to wrap onto this one. Checks the first two tokens, not just
 * the very first, in case a stray word got prepended to the row.
 */
function startsNewNumberedLine(row: string): boolean {
  const tokens = tokenize(row);
  return tokens.slice(0, 2).some((tok) => LINE_NUMBER_START_RE.test(tok.replace(/[.:]+$/, "")));
}

/**
 * Checks the anchor row at `idx`, then up to `lookahead` rows after it, for
 * a valid trailing amount — long labels often wrap, leaving the actual
 * entered value alone on a following row.
 *
 * We deliberately don't scan backward past other tokens on a row: a genuine
 * amount is always the very last thing printed on its row. Anything else
 * numeric-looking earlier is typically a form/line cross-reference embedded
 * in prose ("...from Form 2441, line 11.") that happens to satisfy a naive
 * number pattern but isn't in the amount column at all.
 *
 * A row's last token falls into exactly one of three buckets:
 *   - not amount-shaped at all (e.g. ends in "Attach") -> the label is
 *     still wrapping onto the next row, so keep looking ahead.
 *   - a bare integer equal to `rejectNumber` (e.g. "...taxes . . . 1" when
 *     the anchor row itself was line 1's own label) -> ambiguous. Most PDFs
 *     print this only when the line was left blank, with nothing else
 *     following. But some print the line number's own echo
 *     *unconditionally*, with the actual value (when there is one) printed
 *     alone on the very next row instead of the same row — so we peek once
 *     more: if the immediate next non-blank row is nothing but a single
 *     amount token, that's this line's real value; anything else (a
 *     different line's label, more prose, ...) means this line really was
 *     left blank. `rejectNumber` is derived from the anchor row's own
 *     leading number, not assumed from our line definitions, since a
 *     schedule's line numbering can shift between tax years.
 *   - anything else amount-shaped -> a real value; return it.
 */
function scanFromAnchor(lines: string[], idx: number, rejectNumber: string | null, lookahead = 2): number | null {
  for (let offset = 0; offset <= lookahead; offset++) {
    const j = idx + offset;
    if (j >= lines.length) break;
    if (offset > 0 && startsNewNumberedLine(lines[j])) {
      // The previous row's label didn't yield a value and this one opens
      // with what looks like a different line's own number - stop rather
      // than treating it as a wrapped continuation.
      break;
    }
    const tokens = tokenize(lines[j]);
    if (tokens.length === 0) continue;
    const last = tokens[tokens.length - 1];
    if (!AMOUNT_RE.test(last)) continue;
    if (rejectNumber !== null && isBareInteger(last) && last.replace(/[()$]/g, "") === rejectNumber) {
      for (let k = j + 1; k < Math.min(j + 1 + lookahead, lines.length); k++) {
        const nextTokens = tokenize(lines[k]);
        if (nextTokens.length === 0) continue;
        if (nextTokens.length === 1 && AMOUNT_RE.test(nextTokens[0])) {
          return parseAmount(nextTokens[0]);
        }
        break;
      }
      return null;
    }
    return parseAmount(last);
  }
  return null;
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
  // "matched" / "not_found": a curated line (Form 1040, Schedule 1/2/3) -
  // phrase-anchored, validated against real returns. "uncertain": a
  // generically-detected line on a form we have no curated definitions
  // for - position-based only, with no phrase anchor to confirm it's
  // reading the right cell.
  confidence: "matched" | "not_found" | "uncertain";
  group: string;
}

export interface ExtractionResult {
  lines: ExtractedLine[];
  filingStatus: string | null;
  taxYear: number | null;
  rawText: string;
  // 1-indexed page numbers with zero extractable text - almost always a
  // scanned/rasterized page. Nothing on that page could have been read.
  scannedPages: number[];
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

// Every official IRS form/schedule prints an "OMB No. 1545-nnnn" control
// number on its own first page, and not on continuation pages of the same
// form. That makes it a reliable, form-agnostic way to find where each
// attachment starts — Schedule D, Form 8949, Schedule E, Form 2441,
// Schedule 8812, and anything else, not just the schedules we have curated
// line definitions for. Bounding every section this way (rather than only
// looking for Schedule 1/2/3's own titles) prevents one schedule's scope
// from silently swallowing whatever comes after it in the PDF when there's
// no next *known* schedule to stop at.
const OMB_RE = /omb no\.?\s*1545/i;
const SCHEDULE_TITLE_RE = /^schedule\s+([a-z0-9]+)\b/i;
const BARE_FORM_NUMBER_RE = /^(\d{3,4}[a-z]{0,2})$/i;

export interface FormSection {
  title: string;
  startPage: number; // 0-indexed, inclusive
  endPage: number; // 0-indexed, exclusive
}

function splitBeforeOmb(text: string): string {
  return text.split(/omb no\.?/i)[0].trim();
}

function sectionTitle(pageLines: string[]): string {
  const nonBlank = pageLines.map((l) => l.trim()).filter(Boolean);
  for (let i = 0; i < Math.min(3, nonBlank.length); i++) {
    const line = nonBlank[i];
    const m = SCHEDULE_TITLE_RE.exec(line);
    if (m) {
      const rest = splitBeforeOmb(line.slice(m[0].length).trim());
      return `Schedule ${m[1].toUpperCase()}` + (rest ? ` — ${rest}` : "");
    }
    const firstToken = line.split(/\s+/)[0] ?? "";
    if (BARE_FORM_NUMBER_RE.test(firstToken)) {
      // The title may follow the number on this same line ("8889 Health
      // Savings Accounts (HSAs)") or sit alone on the next line ("2441"
      // then "Child and Dependent Care Expenses" below it).
      let rest = splitBeforeOmb(line.slice(firstToken.length).trim());
      if (!rest && i + 1 < nonBlank.length) {
        rest = splitBeforeOmb(nonBlank[i + 1]);
        // Some forms print a lone "Form" word ahead of the title's second
        // half on this line (the rest of the title having spilled onto the
        // line *before* the number, an unusual layout — e.g. Form 7203);
        // drop the redundant word rather than showing "Form 7203 — Form
        // Debt Basis Limitations".
        rest = rest.replace(/^form\s+/i, "");
      }
      return `Form ${firstToken.toUpperCase()}` + (rest ? ` — ${rest}` : "");
    }
  }
  return "Additional form";
}

function detectFormSections(pages: string[], pageLines: string[][]): FormSection[] {
  const boundaries: [number, string][] = [];
  for (let i = 0; i < pages.length; i++) {
    if (!OMB_RE.test(pages[i])) continue;
    boundaries.push([i, sectionTitle(pageLines[i])]);
  }

  // Consecutive pages with the same detected title (e.g. two properties on
  // separate Schedule E "page 1"s) are one logical section, not two.
  const merged: [number, string][] = [];
  for (const [start, title] of boundaries) {
    if (merged.length > 0 && merged[merged.length - 1][1] === title) continue;
    merged.push([start, title]);
  }

  return merged.map(([start, title], idx) => ({
    title,
    startPage: start,
    endPage: idx + 1 < merged.length ? merged[idx + 1][0] : pages.length,
  }));
}

/**
 * Locates a row by a distinctive label phrase, then reads the value off it
 * (or a wrapped continuation row). The "is this bare number actually just
 * this line's own echoed number" check is derived from the anchor row's
 * own leading token — not a hardcoded expectation of which number this
 * line "should" be — since a schedule's line numbering genuinely shifts
 * between tax years (e.g. Schedule 1's adjustments total moved from line
 * 25 to line 26 between recent years).
 */
function matchByPhrase(lines: string[], phrases: string[]): number | null {
  for (let i = 0; i < lines.length; i++) {
    const rowLower = lines[i].trim().toLowerCase();
    if (phrases.some((phrase) => rowLower.includes(phrase))) {
      const tokens = tokenize(lines[i]);
      const anchorNumber = tokens.length > 0 ? tokens[0].replace(/[.:]+$/, "").toLowerCase() : null;
      const value = scanFromAnchor(lines, i, anchorNumber);
      if (value !== null) return value;
    }
  }
  return null;
}

/**
 * Only used once phrase matching has already failed. Anchors strictly on
 * the number being the row's *first* token — a genuine "this is line N's
 * own label" signal — rather than the number appearing anywhere in the
 * row, which used to match a schedule's own title header (e.g. "SCHEDULE 1
 * ..." contains the token "1") and grab whatever was printed nearby.
 */
function matchByNumber(lines: string[] | null, number: string): number | null {
  if (lines === null) return null;
  const target = number.toLowerCase();
  for (let i = 0; i < lines.length; i++) {
    const tokens = tokenize(lines[i]);
    if (tokens.length > 0 && tokens[0].replace(/[.:]+$/, "").toLowerCase() === target) {
      const value = scanFromAnchor(lines, i, number);
      if (value !== null) return value;
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

const GENERIC_LINE_NUMBER_RE = /^\d{1,2}[a-z]?$/i;
const DOTTED_LEADER_RE = /(?:\.\s*){2,}/;

function slugify(title: string): string {
  const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  return slug || "form";
}

/**
 * For a form we don't have curated line definitions for: surface any row
 * that looks like its own numbered line and has a genuine trailing amount.
 * Unlike the curated groups, blank/not-entered lines aren't reported at
 * all here — without hand-written labels for every line on every possible
 * attachment, listing dozens of blank boxes would be noise rather than
 * useful detail.
 */
function extractGenericLines(lines: string[]): [string, string, number][] {
  const results: [string, string, number][] = [];
  const seenNumbers = new Set<string>();
  for (let i = 0; i < lines.length; i++) {
    const row = lines[i];
    const tokens = tokenize(row);
    if (tokens.length < 2) continue;
    const firstRaw = tokens[0].replace(/[.:]+$/, "");
    if (!GENERIC_LINE_NUMBER_RE.test(firstRaw)) continue;
    const number = firstRaw.toLowerCase();
    if (seenNumbers.has(number)) continue;
    const value = scanFromAnchor(lines, i, number);
    if (value === null) continue;
    let label = row.trim().split(DOTTED_LEADER_RE)[0];
    label = label.replace(/^\S+\s*/, "").trim();
    if (!label) label = `Line ${firstRaw}`;
    seenNumbers.add(number);
    results.push([firstRaw, label.slice(0, 120), value]);
  }
  return results;
}

const CURATED_SCHEDULES: Record<string, [LineDefinition[], string]> = {
  "schedule 1": [SCHEDULE1_DEFINITIONS, "Schedule 1 (Additional Income & Adjustments)"],
  "schedule 2": [SCHEDULE2_DEFINITIONS, "Schedule 2 (Additional Taxes)"],
  "schedule 3": [SCHEDULE3_DEFINITIONS, "Schedule 3 (Additional Credits & Payments)"],
};

export async function parse1040(bytes: Uint8Array): Promise<ExtractionResult> {
  const pageLines = await extractPdfPages(bytes);
  const pageTexts = pageLines.map((rows) => rows.join("\n"));
  const text = pageTexts.join("\n");
  const totalPages = pageLines.length;

  const scannedPages = pageLines
    .map((rows, i) => (rows.some((r) => r.trim().length > 0) ? -1 : i + 1))
    .filter((p) => p !== -1);

  const flatten = (a: number, b: number): string[] => pageLines.slice(a, b).flat();

  // Every attached form/schedule (curated or not) is bounded by the next
  // one's own first page, found generically via its OMB control number.
  const sections = detectFormSections(pageTexts, pageLines);
  const mainEnd = sections.length > 0 ? sections[0].startPage : totalPages;
  const mainScope = flatten(0, mainEnd);

  const lines: ExtractedLine[] = [...extractGroup(mainScope, mainScope, LINE_DEFINITIONS, "Form 1040")];

  const curatedFound = new Set<string>();
  for (const section of sections) {
    const scope = flatten(section.startPage, section.endPage);
    const curatedKey = Object.keys(CURATED_SCHEDULES).find((k) => section.title.toLowerCase().startsWith(k));
    if (curatedKey) {
      curatedFound.add(curatedKey);
      const [definitions, groupName] = CURATED_SCHEDULES[curatedKey];
      lines.push(...extractGroup(scope, scope, definitions, groupName));
    } else {
      // No hand-written line definitions for this form (Schedule D, Form
      // 8949, Schedule E, Form 2441, etc.) — surface whatever numbered
      // lines it actually has values on generically, under its own
      // detected title, rather than not showing it at all.
      for (const [number, label, value] of extractGenericLines(scope)) {
        lines.push({
          id: `${slugify(section.title)}_${number}`,
          label,
          value,
          confidence: "uncertain",
          group: section.title,
        });
      }
    }
  }

  // A curated schedule with no detected page at all is simply absent from
  // this return (e.g. no Schedule 2 needed this year) — report its lines
  // as not_found rather than silently omitting them.
  for (const [key, [definitions, groupName]] of Object.entries(CURATED_SCHEDULES)) {
    if (!curatedFound.has(key)) {
      lines.push(...extractGroup([], null, definitions, groupName));
    }
  }

  return {
    lines,
    filingStatus: detectFilingStatus(text),
    taxYear: detectTaxYear(text),
    rawText: text,
    scannedPages,
  };
}
