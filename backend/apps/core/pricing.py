"""The pricing and tax engine. Pure functions on Decimals; no Django imports.

Order of operations for one line:

    gross    = quantity × unit price × proration factor
    net      = gross − discounts
    tax      = Σ (net × rate%)  for percentage taxes
             + Σ (quantity × amount) for fixed per-unit taxes
    total    = net + tax

Every intermediate amount is rounded half-up to the cent, per line.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from .money import ZERO, allocate, q


@dataclass(frozen=True)
class TaxRule:
    id: int | None
    name: str
    computation: str  # "PERCENT" | "FIXED"
    amount: Decimal


@dataclass
class LineResult:
    gross: Decimal
    discount: Decimal
    net: Decimal
    tax: Decimal
    total: Decimal
    tax_breakdown: list[dict] = field(default_factory=list)


def compute_line(
    quantity: Decimal,
    unit_price: Decimal,
    taxes: list[TaxRule],
    discount: Decimal = ZERO,
    factor: Decimal = Decimal(1),
) -> LineResult:
    gross = q(Decimal(quantity) * Decimal(unit_price) * Decimal(factor))
    discount = min(q(discount), gross) if gross > 0 else ZERO
    net = gross - discount
    breakdown = []
    tax_total = ZERO
    for rule in taxes:
        if rule.computation == "FIXED":
            amount = q(Decimal(quantity) * rule.amount * Decimal(factor))
        else:
            amount = q(net * rule.amount / Decimal(100))
        tax_total += amount
        breakdown.append(
            {
                "tax_id": rule.id,
                "name": rule.name,
                "computation": rule.computation,
                "rate": str(rule.amount),
                "amount": str(amount),
            }
        )
    return LineResult(gross, discount, net, tax_total, net + tax_total, breakdown)


@dataclass(frozen=True)
class DiscountRule:
    id: int
    name: str
    kind: str  # "PERCENT" | "FIXED"
    value: Decimal
    scope: str  # "PRODUCTS" | "SUBSCRIPTION"
    product_ids: frozenset[int]
    min_purchase: Decimal | None
    min_quantity: Decimal | None


@dataclass
class PricedLine:
    key: int
    product_id: int | None
    quantity: Decimal
    gross: Decimal
    discount: Decimal = ZERO

    @property
    def net(self) -> Decimal:
        return self.gross - self.discount


def apply_discounts(
    lines: list[PricedLine], rules: list[DiscountRule]
) -> list[tuple[DiscountRule, Decimal]]:
    """Apply every rule whose conditions hold, in order, mutating ``lines``.

    Returns ``[(rule, amount_applied), ...]`` for the rules that applied.
    Product rules touch only the matching product lines; subscription rules
    spread across all lines in proportion to their value. A fixed discount is
    capped at the value it applies to, so a total can never go negative.
    """
    applied: list[tuple[DiscountRule, Decimal]] = []
    for rule in rules:
        if rule.scope == "PRODUCTS":
            matching = [ln for ln in lines if ln.product_id in rule.product_ids]
        else:
            matching = list(lines)
        matching = [ln for ln in matching if ln.net > 0]
        if not matching:
            continue
        qty = sum((ln.quantity for ln in matching), Decimal(0))
        base = sum((ln.net for ln in matching), ZERO)
        if rule.min_quantity is not None and qty < rule.min_quantity:
            continue
        if rule.min_purchase is not None and base < rule.min_purchase:
            continue
        if rule.kind == "PERCENT":
            parts = [q(ln.net * min(rule.value, Decimal(100)) / Decimal(100)) for ln in matching]
        else:
            parts = allocate(min(q(rule.value), base), [ln.net for ln in matching])
        total = sum(parts, ZERO)
        if total <= 0:
            continue
        for ln, part in zip(matching, parts, strict=True):
            ln.discount += part
        applied.append((rule, total))
    return applied
