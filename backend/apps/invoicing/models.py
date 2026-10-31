from datetime import date

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Customer
from apps.catalog.models import MONEY, Product
from apps.subscriptions.models import QTY, Discount, Subscription


class BillingRun(models.Model):
    class Trigger(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        SCHEDULED = "SCHEDULED", "Scheduled"

    as_of = models.DateField()
    trigger = models.CharField(max_length=10, choices=Trigger.choices, default=Trigger.MANUAL)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    auto_confirm = models.BooleanField(default=True)
    auto_send = models.BooleanField(default=False)
    subscriptions_processed = models.PositiveIntegerField(default=0)
    invoices_created = models.PositiveIntegerField(default=0)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    errors = models.JSONField(default=list, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    duration_ms = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-started_at", "-id"]

    def __str__(self) -> str:
        return f"Billing run {self.as_of} ({self.invoices_created} invoices)"


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        CONFIRMED = "CONFIRMED", "Confirmed"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"

    number = models.CharField(max_length=30, unique=True, null=True, blank=True)
    subscription = models.ForeignKey(
        Subscription, null=True, blank=True, on_delete=models.PROTECT, related_name="invoices"
    )
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="invoices")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    invoice_date = models.DateField(default=date.today)
    due_date = models.DateField()
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    payment_term = models.CharField(max_length=80, blank=True)
    # Snapshot of who is billed, so later edits to the customer don't rewrite history.
    bill_to = models.JSONField(default=dict)

    untaxed_amount = models.DecimalField(**MONEY, default=0)  # before discounts
    discount_amount = models.DecimalField(**MONEY, default=0)
    tax_amount = models.DecimalField(**MONEY, default=0)
    total = models.DecimalField(**MONEY, default=0)
    amount_paid = models.DecimalField(**MONEY, default=0)
    amount_due = models.DecimalField(**MONEY, default=0)

    billing_run = models.ForeignKey(
        BillingRun, null=True, blank=True, on_delete=models.SET_NULL, related_name="invoices"
    )
    notes = models.TextField(blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=200, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    sent_count = models.PositiveSmallIntegerField(default=0)
    reminder_count = models.PositiveSmallIntegerField(default=0)
    last_reminder_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-invoice_date", "-id"]
        constraints = [
            # The heart of "nothing billed twice": one live invoice per period.
            models.UniqueConstraint(
                fields=["subscription", "period_start"],
                condition=Q(subscription__isnull=False) & ~Q(status="CANCELLED"),
                name="one_live_invoice_per_subscription_period",
            ),
            models.CheckConstraint(
                condition=Q(amount_paid__gte=0) & Q(amount_due__gte=0),
                name="invoice_amounts_not_negative",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "due_date"]),
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["-invoice_date"]),
            models.Index(fields=["subscription", "-period_start"]),
        ]

    def __str__(self) -> str:
        return self.number or f"Draft invoice #{self.pk}"

    @property
    def display_number(self) -> str:
        return self.number or f"Draft #{self.pk}"

    @property
    def is_overdue(self) -> bool:
        return (
            self.status == self.Status.CONFIRMED
            and self.amount_due > 0
            and self.due_date < date.today()
        )

    @property
    def days_overdue(self) -> int:
        return max((date.today() - self.due_date).days, 0) if self.is_overdue else 0


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.PROTECT)
    description = models.CharField(max_length=300)
    quantity = models.DecimalField(**QTY)
    unit_price = models.DecimalField(**MONEY)
    gross_amount = models.DecimalField(**MONEY, default=0)
    discount_amount = models.DecimalField(**MONEY, default=0)
    subtotal = models.DecimalField(**MONEY, default=0)  # after discount, before tax
    tax_amount = models.DecimalField(**MONEY, default=0)
    total = models.DecimalField(**MONEY, default=0)
    taxes = models.JSONField(default=list, blank=True)  # snapshot of the rules used
    sequence = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sequence", "id"]


class InvoiceDiscount(models.Model):
    """A discount applied to an invoice. Counts toward the rule's usage limit
    unless the invoice is cancelled."""

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="applied_discounts")
    discount = models.ForeignKey(Discount, on_delete=models.PROTECT, related_name="applications")
    name = models.CharField(max_length=120)
    amount = models.DecimalField(**MONEY)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["invoice", "discount"], name="discount_once_per_invoice")
        ]


class Payment(models.Model):
    class Method(models.TextChoices):
        BANK_TRANSFER = "BANK_TRANSFER", "Bank transfer"
        CARD = "CARD", "Card"
        UPI = "UPI", "UPI"
        CASH = "CASH", "Cash"
        CHEQUE = "CHEQUE", "Cheque"
        OTHER = "OTHER", "Other"

    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Recorded by staff"
        PORTAL = "PORTAL", "Customer portal"

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(max_length=15, choices=Method.choices)
    amount = models.DecimalField(**MONEY)
    payment_date = models.DateField(default=date.today)
    reference = models.CharField(max_length=100, blank=True)
    note = models.CharField(max_length=300, blank=True)
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.MANUAL)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-payment_date", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_amount_positive")
        ]
        indexes = [
            models.Index(fields=["-payment_date"]),
            models.Index(fields=["method", "payment_date"]),
            models.Index(fields=["customer", "-payment_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.amount} on {self.payment_date} for {self.invoice}"
