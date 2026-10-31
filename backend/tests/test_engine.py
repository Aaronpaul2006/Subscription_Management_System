"""Pure engine tests: money, periods, taxes and discounts (no database)."""

from datetime import date
from decimal import Decimal as D

import pytest

from apps.core.money import allocate, q
from apps.core.periods import add_months, add_period, monthly_factor
from apps.core.pricing import DiscountRule, PricedLine, TaxRule, apply_discounts, compute_line

GST = TaxRule(1, "GST 18%", "PERCENT", D("18"))


def test_round_half_up():
    assert q("2.345") == D("2.35")
    assert q("2.344") == D("2.34")


def test_allocate_never_loses_a_cent():
    parts = allocate(D("100"), [D("1"), D("1"), D("1")])
    assert sum(parts) == D("100.00")
    assert sorted(parts) == [D("33.33"), D("33.33"), D("33.34")]


def test_month_end_clamps_and_keeps_anchor():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    # Anchored on the 31st: back to the 31st in March, not stuck on the 28th.
    assert add_months(date(2026, 2, 28), 1, anchor_day=31) == date(2026, 3, 31)
    assert add_months(date(2024, 2, 29), 12) == date(2025, 2, 28)


@pytest.mark.parametrize(
    ("period", "interval", "expected"),
    [
        ("DAILY", 1, date(2026, 1, 2)),
        ("WEEKLY", 2, date(2026, 1, 15)),
        ("MONTHLY", 3, date(2026, 4, 1)),
        ("YEARLY", 1, date(2027, 1, 1)),
    ],
)
def test_add_period(period, interval, expected):
    assert add_period(date(2026, 1, 1), period, interval) == expected


def test_monthly_factor():
    assert monthly_factor("YEARLY") == D(1) / D(12)
    assert monthly_factor("MONTHLY", 3) == D(1) / D(3)


def test_line_with_percent_and_fixed_tax():
    fixed = TaxRule(2, "Cess", "FIXED", D("2"))
    r = compute_line(D("3"), D("100"), [GST, fixed])
    assert r.gross == D("300.00")
    assert r.tax == D("54.00") + D("6.00")
    assert r.total == D("360.00")
    assert [t["amount"] for t in r.tax_breakdown] == ["54.00", "6.00"]


def test_tax_is_on_price_after_discount():
    r = compute_line(D("1"), D("1000"), [GST], discount=D("100"))
    assert r.net == D("900.00")
    assert r.tax == D("162.00")


def test_proration_factor():
    r = compute_line(D("1"), D("3000"), [GST], factor=D("0.5"))
    assert r.gross == D("1500.00")


def rule(**kw):
    base = dict(
        id=1,
        name="R",
        kind="PERCENT",
        value=D("10"),
        scope="SUBSCRIPTION",
        product_ids=frozenset(),
        min_purchase=None,
        min_quantity=None,
    )
    base.update(kw)
    return DiscountRule(**base)


def lines():
    return [PricedLine(0, 1, D("20"), D("2000")), PricedLine(1, 2, D("1"), D("500"))]


def test_product_discount_needs_minimum_quantity():
    ls = lines()
    applied = apply_discounts(
        ls, [rule(scope="PRODUCTS", product_ids=frozenset({1}), min_quantity=D("25"))]
    )
    assert applied == []
    applied = apply_discounts(
        ls, [rule(scope="PRODUCTS", product_ids=frozenset({1}), min_quantity=D("20"))]
    )
    assert applied[0][1] == D("200.00")
    assert ls[0].discount == D("200.00") and ls[1].discount == 0


def test_fixed_subscription_discount_is_spread_and_capped():
    ls = lines()
    applied = apply_discounts(ls, [rule(kind="FIXED", value=D("250"))])
    assert applied[0][1] == D("250.00")
    assert ls[0].discount == D("200.00") and ls[1].discount == D("50.00")
    ls = lines()
    applied = apply_discounts(ls, [rule(kind="FIXED", value=D("99999"))])
    assert applied[0][1] == D("2500.00")
    assert all(line.net == 0 for line in ls)


def test_minimum_purchase():
    assert apply_discounts(lines(), [rule(min_purchase=D("3000"))]) == []
    assert apply_discounts(lines(), [rule(min_purchase=D("2500"))])
