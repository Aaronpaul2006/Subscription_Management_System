"""Money helpers. Money is always Decimal, rounded half-up to two places."""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def q(value) -> Decimal:
    """Quantize any number-like value to money precision."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def allocate(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Split ``total`` across ``weights`` proportionally without losing a cent.

    The rounding remainder goes to the largest share, so the parts always add
    up to exactly ``total``.
    """
    total = q(total)
    weight_sum = sum(weights, Decimal(0))
    if not weights:
        return []
    if weight_sum == 0:
        return [ZERO for _ in weights]
    parts = [q(total * w / weight_sum) for w in weights]
    diff = total - sum(parts, ZERO)
    if diff:
        largest = max(range(len(weights)), key=lambda i: weights[i])
        parts[largest] += diff
    return parts
