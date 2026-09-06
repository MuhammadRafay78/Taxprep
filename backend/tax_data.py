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
    2020: {"single": 12400, "mfs": 12400, "mfj": 24800, "qss": 24800, "hoh": 18650},
    2021: {"single": 12550, "mfs": 12550, "mfj": 25100, "qss": 25100, "hoh": 18800},
    2022: {"single": 12950, "mfs": 12950, "mfj": 25900, "qss": 25900, "hoh": 19400},
    2023: {"single": 13850, "mfs": 13850, "mfj": 27700, "qss": 27700, "hoh": 20800},
    2024: {"single": 14600, "mfs": 14600, "mfj": 29200, "qss": 29200, "hoh": 21900},
    2025: {"single": 15000, "mfs": 15000, "mfj": 30000, "qss": 30000, "hoh": 22500},
}

# {year: {status: [(bracket_ceiling_or_None, rate), ...]}}, ceilings in
# ascending order, last entry's ceiling is None (open-ended top bracket).
TAX_BRACKETS: dict[int, dict[str, list[tuple[float | None, float]]]] = {
    2020: {
        "single": [(9875, 0.10), (40125, 0.12), (85525, 0.22), (163300, 0.24),
                   (207350, 0.32), (518400, 0.35), (None, 0.37)],
        "mfs": [(9875, 0.10), (40125, 0.12), (85525, 0.22), (163300, 0.24),
                (207350, 0.32), (311025, 0.35), (None, 0.37)],
        "mfj": [(19750, 0.10), (80250, 0.12), (171050, 0.22), (326600, 0.24),
                (414700, 0.32), (622050, 0.35), (None, 0.37)],
        "qss": [(19750, 0.10), (80250, 0.12), (171050, 0.22), (326600, 0.24),
                (414700, 0.32), (622050, 0.35), (None, 0.37)],
        "hoh": [(14100, 0.10), (53700, 0.12), (85500, 0.22), (163300, 0.24),
                (207350, 0.32), (518400, 0.35), (None, 0.37)],
    },
    2021: {
        "single": [(9950, 0.10), (40525, 0.12), (86375, 0.22), (164925, 0.24),
                   (209425, 0.32), (523600, 0.35), (None, 0.37)],
        "mfs": [(9950, 0.10), (40525, 0.12), (86375, 0.22), (164925, 0.24),
                (209425, 0.32), (314150, 0.35), (None, 0.37)],
        "mfj": [(19900, 0.10), (81050, 0.12), (172750, 0.22), (329850, 0.24),
                (418850, 0.32), (628300, 0.35), (None, 0.37)],
        "qss": [(19900, 0.10), (81050, 0.12), (172750, 0.22), (329850, 0.24),
                (418850, 0.32), (628300, 0.35), (None, 0.37)],
        "hoh": [(14200, 0.10), (54200, 0.12), (86350, 0.22), (164900, 0.24),
                (209400, 0.32), (523600, 0.35), (None, 0.37)],
    },
    2022: {
        "single": [(10275, 0.10), (41775, 0.12), (89075, 0.22), (170050, 0.24),
                   (215950, 0.32), (539900, 0.35), (None, 0.37)],
        "mfs": [(10275, 0.10), (41775, 0.12), (89075, 0.22), (170050, 0.24),
                (215950, 0.32), (323925, 0.35), (None, 0.37)],
        "mfj": [(20550, 0.10), (83550, 0.12), (178150, 0.22), (340100, 0.24),
                (431900, 0.32), (647850, 0.35), (None, 0.37)],
        "qss": [(20550, 0.10), (83550, 0.12), (178150, 0.22), (340100, 0.24),
                (431900, 0.32), (647850, 0.35), (None, 0.37)],
        "hoh": [(14650, 0.10), (55900, 0.12), (89050, 0.22), (170050, 0.24),
                (215950, 0.32), (539900, 0.35), (None, 0.37)],
    },
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

# Thresholds for the 0%/15%/20% long-term capital gains & qualified dividend
# rates. Each ceiling is the top of that rate's bracket (income above the
# last ceiling is taxed at 20%). Mirrors the structure of TAX_BRACKETS.
CAPITAL_GAINS_BRACKETS: dict[int, dict[str, list[tuple[float | None, float]]]] = {
    2022: {
        "single": [(41675, 0.0), (459750, 0.15), (None, 0.20)],
        "mfs": [(41675, 0.0), (258600, 0.15), (None, 0.20)],
        "mfj": [(83350, 0.0), (517200, 0.15), (None, 0.20)],
        "qss": [(83350, 0.0), (517200, 0.15), (None, 0.20)],
        "hoh": [(55800, 0.0), (488500, 0.15), (None, 0.20)],
    },
    2023: {
        "single": [(44625, 0.0), (492300, 0.15), (None, 0.20)],
        "mfs": [(44625, 0.0), (276900, 0.15), (None, 0.20)],
        "mfj": [(89250, 0.0), (553850, 0.15), (None, 0.20)],
        "qss": [(89250, 0.0), (553850, 0.15), (None, 0.20)],
        "hoh": [(59750, 0.0), (523050, 0.15), (None, 0.20)],
    },
    2024: {
        "single": [(47025, 0.0), (518900, 0.15), (None, 0.20)],
        "mfs": [(47025, 0.0), (291850, 0.15), (None, 0.20)],
        "mfj": [(94050, 0.0), (583750, 0.15), (None, 0.20)],
        "qss": [(94050, 0.0), (583750, 0.15), (None, 0.20)],
        "hoh": [(63000, 0.0), (551350, 0.15), (None, 0.20)],
    },
    2025: {
        "single": [(48350, 0.0), (533400, 0.15), (None, 0.20)],
        "mfs": [(48350, 0.0), (300000, 0.15), (None, 0.20)],
        "mfj": [(96700, 0.0), (600050, 0.15), (None, 0.20)],
        "qss": [(96700, 0.0), (600050, 0.15), (None, 0.20)],
        "hoh": [(64750, 0.0), (566700, 0.15), (None, 0.20)],
    },
}

# AMT exemption and the income level where it starts phasing out (26%/28%
# AMT brackets aren't modeled here — this is only used for a rough
# "you're in AMT territory" proximity hint, not an actual AMT computation).
AMT_EXEMPTION: dict[int, dict[str, float]] = {
    2022: {"single": 75900, "hoh": 75900, "qss": 75900, "mfj": 118100, "mfs": 59050},
    2023: {"single": 81300, "hoh": 81300, "qss": 81300, "mfj": 126500, "mfs": 63250},
    2024: {"single": 85700, "hoh": 85700, "qss": 85700, "mfj": 133300, "mfs": 66650},
    2025: {"single": 88100, "hoh": 88100, "qss": 88100, "mfj": 137000, "mfs": 68500},
}
AMT_PHASEOUT_START: dict[int, dict[str, float]] = {
    2022: {"single": 539900, "hoh": 539900, "qss": 539900, "mfj": 1079800, "mfs": 539900},
    2023: {"single": 578150, "hoh": 578150, "qss": 578150, "mfj": 1156300, "mfs": 578150},
    2024: {"single": 609350, "hoh": 609350, "qss": 609350, "mfj": 1218700, "mfs": 609350},
    2025: {"single": 626350, "hoh": 626350, "qss": 626350, "mfj": 1252700, "mfs": 626350},
}

# Net Investment Income Tax (3.8%) MAGI thresholds — fixed by statute, not
# inflation-adjusted, so the same numbers apply across all tax years.
NIIT_THRESHOLD: dict[str, float] = {
    "single": 200000, "hoh": 200000, "qss": 200000, "mfj": 250000, "mfs": 125000,
}

# Additional Medicare Tax (0.9%) wage/SE-income thresholds — also fixed by
# statute.
ADDITIONAL_MEDICARE_THRESHOLD: dict[str, float] = {
    "single": 200000, "hoh": 200000, "qss": 200000, "mfj": 250000, "mfs": 125000,
}

# QBI (Section 199A) deduction phase-out range start — above this, the
# wage/UBIA limitations start to bite for specified service businesses.
QBI_PHASEOUT_START: dict[int, dict[str, float]] = {
    2022: {"single": 170050, "hoh": 170050, "qss": 170050, "mfj": 340100, "mfs": 170050},
    2023: {"single": 182100, "hoh": 182100, "qss": 182100, "mfj": 364200, "mfs": 182100},
    2024: {"single": 191950, "hoh": 191950, "qss": 191950, "mfj": 383900, "mfs": 191950},
    2025: {"single": 197300, "hoh": 197300, "qss": 197300, "mfj": 394600, "mfs": 197300},
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


def compute_qdcgt_tax(
    taxable_income: float,
    qualified_dividends: float,
    net_ltcg: float,
    ordinary_brackets: list[tuple[float | None, float]],
    capital_gains_brackets: list[tuple[float | None, float]],
) -> float:
    """Approximates the IRS "Qualified Dividends and Capital Gains Tax
    Worksheet": ordinary income is taxed through the regular brackets, and
    qualified dividends + net long-term capital gains are stacked on top of
    it and taxed at the 0/15/20% preferential rates instead, based on where
    that stacked income falls in the capital-gains bracket thresholds.

    This is a simplification — it doesn't model net capital losses limited
    to $3,000, the 28% collectibles rate, unrecaptured Section 1250 gain, or
    the exact worksheet's line-by-line rounding — so treat the result as a
    ballpark for a "does the reported tax look plausible" check, not as a
    recomputation of the actual liability.
    """
    if taxable_income <= 0:
        return 0.0

    preferential = max(0.0, qualified_dividends) + max(0.0, net_ltcg)
    preferential = min(preferential, taxable_income)
    ordinary = taxable_income - preferential

    tax = compute_bracket_tax(ordinary, ordinary_brackets)

    lower = ordinary
    for ceiling, rate in capital_gains_brackets:
        upper = ceiling if ceiling is not None else float("inf")
        if taxable_income <= lower:
            break
        band_top = min(taxable_income, max(upper, ordinary))
        taxed_at_this_rate = max(0.0, band_top - lower)
        tax += taxed_at_this_rate * rate
        lower = band_top

    return round(tax, 2)
