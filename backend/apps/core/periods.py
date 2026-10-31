"""Calendar arithmetic for billing periods (pure Python, no Django imports)."""

import calendar
from datetime import date, timedelta
from decimal import Decimal

# Average month length, used to normalise any billing period to monthly revenue.
DAYS_PER_MONTH = Decimal("30.436875")


def add_months(day: date, months: int, anchor_day: int | None = None) -> date:
    """Add months, clamping to the month's last day (Jan 31 + 1 month = Feb 28).

    ``anchor_day`` keeps a subscription that started on the 31st billing on the
    31st again in months that have one, instead of drifting to the 28th.
    """
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    wanted = anchor_day or day.day
    return date(year, month, min(wanted, calendar.monthrange(year, month)[1]))


def add_period(day: date, period: str, interval: int = 1, anchor_day: int | None = None) -> date:
    if period == "DAILY":
        return day + timedelta(days=interval)
    if period == "WEEKLY":
        return day + timedelta(weeks=interval)
    if period == "MONTHLY":
        return add_months(day, interval, anchor_day)
    if period == "YEARLY":
        return add_months(day, 12 * interval, anchor_day)
    raise ValueError(f"Unknown billing period {period!r}")


def monthly_factor(period: str, interval: int = 1) -> Decimal:
    """Multiplier that turns one period's amount into monthly recurring revenue."""
    per_period = {
        "DAILY": DAYS_PER_MONTH,
        "WEEKLY": DAYS_PER_MONTH / Decimal(7),
        "MONTHLY": Decimal(1),
        "YEARLY": Decimal(1) / Decimal(12),
    }[period]
    return per_period / Decimal(interval)
