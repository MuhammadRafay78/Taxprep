/**
 * Reference tax figures used for sanity checks — not a source of truth.
 * Ported from backend/tax_data.py (see that file for the same caveats).
 */

export type FilingStatus = "single" | "mfj" | "mfs" | "hoh" | "qss";

export const STANDARD_DEDUCTIONS: Record<number, Partial<Record<FilingStatus, number>>> = {
  2023: { single: 13850, mfs: 13850, mfj: 27700, qss: 27700, hoh: 20800 },
  2024: { single: 14600, mfs: 14600, mfj: 29200, qss: 29200, hoh: 21900 },
  2025: { single: 15000, mfs: 15000, mfj: 30000, qss: 30000, hoh: 22500 },
};

// [ceiling-or-null, rate] pairs, ascending; last entry's ceiling is null
// (open-ended top bracket).
export type Bracket = [number | null, number];

export const TAX_BRACKETS: Record<number, Partial<Record<FilingStatus, Bracket[]>>> = {
  2023: {
    single: [[11000, 0.10], [44725, 0.12], [95375, 0.22], [182100, 0.24],
             [231250, 0.32], [578125, 0.35], [null, 0.37]],
    mfs: [[11000, 0.10], [44725, 0.12], [95375, 0.22], [182100, 0.24],
          [231250, 0.32], [346875, 0.35], [null, 0.37]],
    mfj: [[22000, 0.10], [89450, 0.12], [190750, 0.22], [364200, 0.24],
          [462500, 0.32], [693750, 0.35], [null, 0.37]],
    qss: [[22000, 0.10], [89450, 0.12], [190750, 0.22], [364200, 0.24],
          [462500, 0.32], [693750, 0.35], [null, 0.37]],
    hoh: [[15700, 0.10], [59850, 0.12], [95350, 0.22], [182100, 0.24],
          [231250, 0.32], [578100, 0.35], [null, 0.37]],
  },
  2024: {
    single: [[11600, 0.10], [47150, 0.12], [100525, 0.22], [191950, 0.24],
             [243725, 0.32], [609350, 0.35], [null, 0.37]],
    mfs: [[11600, 0.10], [47150, 0.12], [100525, 0.22], [191950, 0.24],
          [243725, 0.32], [365600, 0.35], [null, 0.37]],
    mfj: [[23200, 0.10], [94300, 0.12], [201050, 0.22], [383900, 0.24],
          [487450, 0.32], [731200, 0.35], [null, 0.37]],
    qss: [[23200, 0.10], [94300, 0.12], [201050, 0.22], [383900, 0.24],
          [487450, 0.32], [731200, 0.35], [null, 0.37]],
    hoh: [[16550, 0.10], [63100, 0.12], [100500, 0.22], [191950, 0.24],
          [243700, 0.32], [609350, 0.35], [null, 0.37]],
  },
};

// Max AGI to qualify for the Earned Income Credit with *no* qualifying
// children — the most conservative case. Actual limits are higher with
// qualifying children, so this only ever under-flags, never over-flags.
export const EIC_MAX_AGI_NO_CHILDREN: Record<number, Partial<Record<FilingStatus, number>>> = {
  2023: { single: 17640, hoh: 17640, qss: 17640, mfj: 24210 },
  2024: { single: 18591, hoh: 18591, qss: 18591, mfj: 25511 },
};

/**
 * Progressive tax on ordinary income only — ignores preferential rates on
 * qualified dividends / long-term capital gains, so it will run high for
 * returns with significant investment income. Callers should account for
 * that before treating a mismatch as meaningful.
 */
export function computeBracketTax(taxableIncome: number, brackets: Bracket[]): number {
  if (taxableIncome <= 0) return 0;
  let tax = 0;
  let lower = 0;
  for (const [ceiling, rate] of brackets) {
    const upper = ceiling ?? Infinity;
    if (taxableIncome <= lower) break;
    const taxedAtThisRate = Math.min(taxableIncome, upper) - lower;
    tax += taxedAtThisRate * rate;
    lower = upper;
  }
  return Math.round(tax * 100) / 100;
}
