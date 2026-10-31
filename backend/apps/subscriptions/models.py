from datetime import date

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.accounts.models import Customer
from apps.catalog.models import (
    MONEY,
    PaymentTerm,
    Product,
    ProductVariant,
    RecurringPlan,
    Tax,
)

QTY = {"max_digits": 10, "decimal_places": 2}


class QuotationTemplate(models.Model):
    name = models.CharField(max_length=120, unique=True)
    validity_days = models.PositiveSmallIntegerField(default=30)
    plan = models.ForeignKey(RecurringPlan, on_delete=models.PROTECT, related_name="templates")
    payment_term = models.ForeignKey(
        PaymentTerm, null=True, blank=True, on_delete=models.SET_NULL
    )
    duration_months = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Default contract length; empty = open-ended."
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class QuotationTemplateLine(models.Model):
    template = models.ForeignKey(QuotationTemplate, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    variant = models.ForeignKey(ProductVariant, null=True, blank=True, on_delete=models.PROTECT)
    quantity = models.DecimalField(**QTY, default=1, validators=[MinValueValidator(0)])
    description = models.CharField(max_length=300, blank=True)
    sequence = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sequence", "id"]


class Subscription(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        QUOTATION = "QUOTATION", "Quotation"
        CONFIRMED = "CONFIRMED", "Confirmed"
        ACTIVE = "ACTIVE", "Active"
        PAUSED = "PAUSED", "Paused"
        CLOSED = "CLOSED", "Closed"

    number = models.CharField(max_length=30, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="subscriptions")
    plan = models.ForeignKey(RecurringPlan, on_delete=models.PROTECT, related_name="subscriptions")
    template = models.ForeignKey(
        QuotationTemplate, null=True, blank=True, on_delete=models.SET_NULL
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    start_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    payment_term = models.ForeignKey(PaymentTerm, null=True, blank=True, on_delete=models.PROTECT)
    quotation_valid_until = models.DateField(null=True, blank=True)
    next_invoice_date = models.DateField(null=True, blank=True)
    salesperson = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    notes = models.TextField(blank=True, help_text="Internal notes.")
    terms = models.TextField(blank=True, help_text="Shown to the customer on the quotation.")

    # Lifecycle bookkeeping
    quotation_sent_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    accepted_by_name = models.CharField(max_length=150, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    paused_at = models.DateField(null=True, blank=True)
    closed_at = models.DateField(null=True, blank=True)
    close_reason = models.CharField(max_length=200, blank=True)
    renewal_count = models.PositiveSmallIntegerField(default=0)

    # Stored totals for one billing period (kept in step with the lines).
    untaxed_amount = models.DecimalField(**MONEY, default=0)
    tax_amount = models.DecimalField(**MONEY, default=0)
    total = models.DecimalField(**MONEY, default=0)
    # Normalised monthly value of this subscription (for MRR without joins).
    mrr = models.DecimalField(**MONEY, default=0)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status", "next_invoice_date"]),
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["plan", "status"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["expiry_date"]),
        ]

    def __str__(self) -> str:
        return self.number

    @property
    def is_editable(self) -> bool:
        return self.status in (self.Status.DRAFT, self.Status.QUOTATION)

    @property
    def quotation_expired(self) -> bool:
        return (
            self.status == self.Status.QUOTATION
            and self.quotation_valid_until is not None
            and self.quotation_valid_until < date.today()
        )

    @property
    def is_expired(self) -> bool:
        return self.expiry_date is not None and self.expiry_date < date.today()


class SubscriptionLine(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.PROTECT,
                                help_text="Empty for the plan's base fee line.")
    variant = models.ForeignKey(ProductVariant, null=True, blank=True, on_delete=models.PROTECT)
    description = models.CharField(max_length=300)
    quantity = models.DecimalField(**QTY, validators=[MinValueValidator(0)])
    unit_price = models.DecimalField(**MONEY, validators=[MinValueValidator(0)])
    taxes = models.ManyToManyField(Tax, blank=True)
    subtotal = models.DecimalField(**MONEY, default=0)
    tax_amount = models.DecimalField(**MONEY, default=0)
    total = models.DecimalField(**MONEY, default=0)
    sequence = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sequence", "id"]

    def __str__(self) -> str:
        return self.description


class Discount(models.Model):
    """A discount rule. Only the admin creates them; billing applies them."""

    class Kind(models.TextChoices):
        PERCENT = "PERCENT", "Percentage"
        FIXED = "FIXED", "Fixed amount"

    class Scope(models.TextChoices):
        PRODUCTS = "PRODUCTS", "Specific products"
        SUBSCRIPTION = "SUBSCRIPTION", "Whole subscription"

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=40, blank=True)
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.PERCENT)
    value = models.DecimalField(**MONEY, validators=[MinValueValidator(0)])
    scope = models.CharField(max_length=12, choices=Scope.choices, default=Scope.SUBSCRIPTION)
    products = models.ManyToManyField(Product, blank=True, related_name="discounts")
    subscriptions = models.ManyToManyField(
        Subscription, blank=True, related_name="discounts",
        help_text="Limit to these subscriptions. Empty = every subscription.",
    )
    min_purchase = models.DecimalField(**MONEY, null=True, blank=True)
    min_quantity = models.DecimalField(**QTY, null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(
        null=True, blank=True, help_text="How many invoices it may apply to. Empty = unlimited."
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.name
