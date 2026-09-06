import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.explain import build_flags  # noqa: E402
from backend import tax_data  # noqa: E402


def messages(flags):
    return [f.message for f in flags]


def test_bracket_mismatch_is_flagged_for_ordinary_income_only_return():
    # $60,000 taxable income, single, 2023: bracket tax is well-defined and
    # a wildly different reported tax (with no cap gains/dividends to
    # explain it) should surface as worth a look.
    values = {"15": 60000, "16": 40000, "9": 60000}
    flags = build_flags(values, "single", 2023)
    assert any("bracket calculation" in m for m in messages(flags))


def test_bracket_mismatch_suppressed_when_capital_gains_present():
    values = {"15": 60000, "16": 5000, "9": 60000, "7": 40000}
    flags = build_flags(values, "single", 2023)
    assert not any("bracket calculation" in m for m in messages(flags))


def test_eic_hint_for_low_agi_with_no_credit_claimed():
    values = {"11": 15000, "9": 15000}
    flags = build_flags(values, "single", 2023)
    assert any("Earned Income Credit" in m for m in messages(flags))


def test_no_eic_hint_when_credit_already_claimed():
    values = {"11": 15000, "9": 15000, "27": 500}
    flags = build_flags(values, "single", 2023)
    assert not any("Earned Income Credit" in m for m in messages(flags))


def test_no_eic_hint_for_mfs():
    values = {"11": 15000, "9": 15000}
    flags = build_flags(values, "mfs", 2023)
    assert not any("Earned Income Credit" in m for m in messages(flags))


def test_self_employment_tax_note():
    values = {"9": 50000, "s2_4": 1500}
    flags = build_flags(values, "single", 2023)
    assert any("Self-employment tax" in m for m in messages(flags))


def test_compute_bracket_tax_matches_known_single_2023_bracket():
    # $50,000 taxable income, single, 2023 brackets:
    # 10% up to 11,000 + 12% up to 44,725 + 22% of remainder
    brackets = tax_data.TAX_BRACKETS[2023]["single"]
    expected = 11000 * 0.10 + (44725 - 11000) * 0.12 + (50000 - 44725) * 0.22
    assert tax_data.compute_bracket_tax(50000, brackets) == round(expected, 2)
