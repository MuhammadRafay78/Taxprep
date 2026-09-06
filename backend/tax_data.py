"""Reference tax figures used for sanity checks — not a source of truth.

These are the published federal numbers for a handful of recent tax years,
used only to power rough "does this look right" checks (an expected tax
range, a plausible EIC eligibility hint, a plausible standard deduction).
None of this should be treated as authoritative for filing — always defer to
the IRS's own numbers for the actual tax year in question.
"""
from __future__ import annotations

FILING_STATUSES = ("single", "mfj", "mfs", "hoh", "qss")

# {year: {status: (amount,)}}
STANDARD_DEDUCTIONS: dict[int, dict[str, float]] = {
    2023: {"single": 13850, "mfs": 13850, "mfj": 27700, "qss": 27700, "hoh": 20800},
    2024: {"single": 14600, "mfs": 14600, "mfj": 29200, "qss": 29200, "hoh": 21900},
    2025: {"single": 15000, "mfs": 15000, "mfj": 30000, "qss": 30000, "hoh": 22500},
}

# {year: {status: [(bracket_ceiling_or_None, rate), ...]}}, ceilings in
# ascending order, last entry's ceiling is None (open-ended top bracket).
TAX_BRACKETS: dict[int, dict[str, list[tuple[float | None, float]]]] = {
    2023: {
        "single": [(11000, 0.10), (44725, 0.12), (95375, 0.22), (182100, 0.24),
                   (231250, 0.32), (578125, 0.35), (None, 0.37)],
        "mfs": [(11000, 0.10), (44725, 0.12), (95375, 0.22), (182100, 0.24),
                (231250, 0.32), (346875, 0.35), (None, 0.37)],
        "mfj": [(22000, 0.10), (89450, 0.12), (190750, 0.22), (364200, 0.24),
                (462500, 0.32), (693750, 0.35), (None, 0.37)],
        "qss": [(22000, 0.10), (89450, 0.12), (190750, 0.22), (364200, 0.24),
                (462500, 0.32), (693750, 0.35), (None, 0.37)],
        "hoh": [(15700, 0.10), (59850, 0.12), (95350, 0.22), (182100, 0.24),
                (231250, 0.32), (578100, 0.35), (None, 0.37)],
    },
    2024: {
        "single": [(11600, 0.10), (47150, 0.12), (100525, 0.22), (191950, 0.24),
                   (243725, 0.32), (609350, 0.35), (None, 0.37)],
        "mfs": [(11600, 0.10), (47150, 0.12), (100525, 0.22), (191950, 0.24),
                (243725, 0.32), (365600, 0.35), (None, 0.37)],
        "mfj": [(23200, 0.10), (94300, 0.12), (201050, 0.22), (383900, 0.24),
                (487450, 0.32), (731200, 0.35), (None, 0.37)],
        "qss": [(23200, 0.10), (94300, 0.12), (201050, 0.22), (383900, 0.24),
                (487450, 0.32), (731200, 0.35), (None, 0.37)],
        "hoh": [(16550, 0.10), (63100, 0.12), (100500, 0.22), (191950, 0.24),
                (243700, 0.32), (609350, 0.35), (None, 0.37)],
    },
}

# Max AGI to qualify for the Earned Income Credit with *no* qualifying
# children — the most conservative case. Actual limits are higher with
# qualifying children, so this only ever under-flags, never over-flags.
EIC_MAX_AGI_NO_CHILDREN: dict[int, dict[str, float]] = {
    2023: {"single": 17640, "hoh": 17640, "qss": 17640, "mfj": 24210},
    2024: {"single": 18591, "hoh": 18591, "qss": 18591, "mfj": 25511},
}


def compute_bracket_tax(taxable_income: float, brackets: list[tuple[float | None, float]]) -> float:
    """Progressive tax on ordinary income only — ignores preferential rates
    on qualified dividends / long-term capital gains, so it will run high
    for returns with significant investment income. Callers should account
    for that before treating a mismatch as meaningful."""
    if taxable_income <= 0:
        return 0.0
    tax = 0.0
    lower = 0.0
    for ceiling, rate in brackets:
        upper = ceiling if ceiling is not None else float("inf")
        if taxable_income <= lower:
            break
        taxed_at_this_rate = min(taxable_income, upper) - lower
        tax += taxed_at_this_rate * rate
        lower = upper
    return round(tax, 2)
