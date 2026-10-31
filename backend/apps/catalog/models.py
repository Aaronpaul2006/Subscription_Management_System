from datetime import date

from django.core.validators import MinValueValidator
from django.db import models

MONEY = {"max_digits": 12, "decimal_places": 2}


class Tax(models.Model):
    """A tax rule set by the admin. Rates are data, never constants in code."""

    class Computation(models.TextChoices):
        PERCENT = "PERCENT", "Percentage of price"
        FIXED = "FIXED", "Fixed amount per unit"

    name = models.CharField(max_length=80, unique=True)
    computation = models.CharField(
        max_length=10, choices=Computation.choices, default=Computation.PERCENT
    )
    amount = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    description = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "taxes"

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    class Type(models.TextChoices):
        SERVICE = "SERVICE", "Service"
        SOFTWARE = "SOFTWARE", "Software licence"
        ADDON = "ADDON", "Add-on"
        GOODS = "GOODS", "Physical goods"

    name = models.CharField(max_length=200)
    product_type = models.CharField(max_length=10, choices=Type.choices, default=Type.SOFTWARE)
    sales_price = models.DecimalField(**MONEY, validators=[MinValueValidator(0)])
    cost_price = models.DecimalField(**MONEY, default=0, validators=[MinValueValidator(0)])
    notes = models.TextField(blank=True)
    taxes = models.ManyToManyField(Tax, blank=True, related_name="products")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def margin_percent(self):
        if not self.sales_price:
            return None
        return round((self.sales_price - self.cost_price) / self.sales_price * 100, 1)


class ProductVariant(models.Model):
    """One choice of an attribute, e.g. Brand = Odoo, which adds 560 to the price."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    attribute = models.CharField(max_length=80)
    value = models.CharField(max_length=80)
    extra_price = models.DecimalField(**MONEY, default=0)

    class Meta:
        ordering = ["attribute", "value"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "attribute", "value"], name="variant_unique_per_product"
            )
        ]

    def __str__(self) -> str:
        return f"{self.attribute}: {self.value}"

    @property
    def price(self):
        return self.product.sales_price + self.extra_price


class PaymentTerm(models.Model):
    name = models.CharField(max_length=80, unique=True)
    due_days = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["due_days", "name"]

    def __str__(self) -> str:
        return self.name


class RecurringPlan(models.Model):
    class Period(models.TextChoices):
        DAILY = "DAILY", "Daily"
        WEEKLY = "WEEKLY", "Weekly"
        MONTHLY = "MONTHLY", "Monthly"
        YEARLY = "YEARLY", "Yearly"

    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        **MONEY,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Base recurring fee per unit, per billing period.",
    )
    billing_period = models.CharField(max_length=8, choices=Period.choices, default=Period.MONTHLY)
    billing_interval = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1)], help_text="Bill every N periods."
    )
    min_quantity = models.DecimalField(
        max_digits=10, decimal_places=2, default=1, validators=[MinValueValidator(0)]
    )
    taxes = models.ManyToManyField(
        Tax, blank=True, related_name="plans", help_text="Taxes on the plan's base fee."
    )
    start_date = models.DateField(help_text="First day the plan can be sold.")
    end_date = models.DateField(null=True, blank=True, help_text="Last day the plan can be sold.")
    # Lifecycle options, decided plan by plan.
    auto_close = models.BooleanField(
        default=False, help_text="Close subscriptions automatically when they expire."
    )
    closable = models.BooleanField(default=True, help_text="Can be closed early.")
    pausable = models.BooleanField(default=False)
    renewable = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def is_available_on(self, day: date) -> bool:
        return (
            self.is_active
            and self.start_date <= day
            and (self.end_date is None or day <= self.end_date)
        )

    @property
    def billing_label(self) -> str:
        unit = {"DAILY": "day", "WEEKLY": "week", "MONTHLY": "month", "YEARLY": "year"}[
            self.billing_period
        ]
        return (
            f"every {unit}"
            if self.billing_interval == 1
            else (f"every {self.billing_interval} {unit}s")
        )
