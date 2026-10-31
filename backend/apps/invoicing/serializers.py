from rest_framework import serializers

from .models import BillingRun, Invoice, InvoiceDiscount, InvoiceLine, Payment

I = Invoice.Status  # noqa: E741


def invoice_actions(invoice: Invoice, user) -> list[str]:
    role = getattr(user, "role", None)
    actions = ["pdf"]
    if role in ("ADMIN", "STAFF"):
        if invoice.status == I.DRAFT:
            actions += ["confirm", "cancel"]
        if invoice.status == I.CONFIRMED:
            actions += ["register_payment", "send", "remind"]
            if invoice.amount_paid == 0:
                actions.append("cancel")
        if invoice.status == I.PAID:
            actions.append("send")
        if invoice.status == I.CANCELLED and invoice.subscription_id:
            actions.append("rebill")
    elif invoice.status == I.CONFIRMED and invoice.amount_due > 0:
        actions.append("pay")
    return actions


class InvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLine
        fields = [
            "id",
            "product",
            "description",
            "quantity",
            "unit_price",
            "gross_amount",
            "discount_amount",
            "subtotal",
            "tax_amount",
            "total",
            "taxes",
        ]


class AppliedDiscountSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceDiscount
        fields = ["id", "discount", "name", "amount"]


class PaymentSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.display_number", read_only=True)
    customer_name = serializers.CharField(source="customer.__str__", read_only=True)
    method_label = serializers.CharField(source="get_method_display", read_only=True)
    recorded_by_name = serializers.CharField(
        source="recorded_by.name", read_only=True, default=None
    )

    class Meta:
        model = Payment
        fields = [
            "id",
            "invoice",
            "invoice_number",
            "customer",
            "customer_name",
            "method",
            "method_label",
            "amount",
            "payment_date",
            "reference",
            "note",
            "source",
            "recorded_by_name",
            "created_at",
        ]
        read_only_fields = ["id", "customer", "source", "created_at"]


class PaymentCreateSerializer(serializers.Serializer):
    invoice = serializers.PrimaryKeyRelatedField(queryset=Invoice.objects.all())
    method = serializers.ChoiceField(choices=Payment.Method.choices)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    payment_date = serializers.DateField(required=False)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    note = serializers.CharField(max_length=300, required=False, allow_blank=True)


class InvoiceListSerializer(serializers.ModelSerializer):
    display_number = serializers.CharField(read_only=True)
    customer_name = serializers.CharField(source="customer.__str__", read_only=True)
    subscription_number = serializers.CharField(
        source="subscription.number", read_only=True, default=None
    )
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    days_overdue = serializers.IntegerField(read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "number",
            "display_number",
            "customer",
            "customer_name",
            "subscription",
            "subscription_number",
            "status",
            "status_label",
            "invoice_date",
            "due_date",
            "period_start",
            "period_end",
            "untaxed_amount",
            "discount_amount",
            "tax_amount",
            "total",
            "amount_paid",
            "amount_due",
            "is_overdue",
            "days_overdue",
            "sent_at",
            "reminder_count",
        ]


class InvoiceDetailSerializer(InvoiceListSerializer):
    lines = InvoiceLineSerializer(many=True, read_only=True)
    applied_discounts = AppliedDiscountSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    allowed_actions = serializers.SerializerMethodField()

    class Meta(InvoiceListSerializer.Meta):
        fields = InvoiceListSerializer.Meta.fields + [
            "bill_to",
            "payment_term",
            "notes",
            "lines",
            "applied_discounts",
            "payments",
            "confirmed_at",
            "paid_at",
            "cancelled_at",
            "cancel_reason",
            "sent_count",
            "last_reminder_at",
            "billing_run",
            "created_at",
            "allowed_actions",
        ]

    def get_allowed_actions(self, obj) -> list[str]:
        return invoice_actions(obj, self.context["request"].user)


class BillingRunSerializer(serializers.ModelSerializer):
    triggered_by_name = serializers.CharField(
        source="triggered_by.name", read_only=True, default=None
    )

    class Meta:
        model = BillingRun
        fields = [
            "id",
            "as_of",
            "trigger",
            "triggered_by_name",
            "auto_confirm",
            "auto_send",
            "subscriptions_processed",
            "invoices_created",
            "total_amount",
            "errors",
            "started_at",
            "duration_ms",
        ]
