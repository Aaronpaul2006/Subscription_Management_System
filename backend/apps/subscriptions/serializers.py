from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import Customer, User
from apps.accounts.serializers import CustomerLiteSerializer
from apps.catalog.models import PaymentTerm, Product, ProductVariant, RecurringPlan, Tax
from apps.catalog.serializers import PlanLiteSerializer

from .models import Discount, QuotationTemplate, QuotationTemplateLine, Subscription

S = Subscription.Status


def allowed_actions(sub: Subscription, user) -> list[str]:
    """Which buttons the UI should show. The services enforce the same rules."""
    role = getattr(user, "role", None)
    plan = sub.plan
    actions: list[str] = []
    if role in ("ADMIN", "STAFF"):
        if sub.status in (S.DRAFT, S.QUOTATION):
            actions += ["edit", "send_quotation"]
        if sub.status == S.QUOTATION and not sub.quotation_expired:
            actions.append("confirm")
        if sub.status == S.CONFIRMED:
            actions.append("activate")
        if sub.status == S.ACTIVE and (
            sub.next_invoice_date
            and (sub.expiry_date is None or sub.next_invoice_date <= sub.expiry_date)
        ):
            actions.append("invoice_now")
        actions.append("duplicate")
    elif sub.status == S.QUOTATION and not sub.quotation_expired:
        actions.append("accept")
    if sub.status == S.ACTIVE and plan.pausable:
        actions.append("pause")
    if sub.status == S.PAUSED:
        actions.append("resume")
    if sub.status in (S.ACTIVE, S.PAUSED) and sub.expiry_date and plan.renewable:
        actions.append("renew")
    if sub.status == S.CLOSED and sub.close_reason == "Expired" and plan.renewable:
        actions.append("renew")
    can_close_early = plan.closable or sub.is_expired
    if sub.status in (S.ACTIVE, S.PAUSED, S.CONFIRMED) and can_close_early:
        actions.append("close")
    if sub.status in (S.DRAFT, S.QUOTATION) and role in ("ADMIN", "STAFF"):
        actions.append("close")
    return actions


class SubscriptionLineSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), allow_null=True, required=False
    )
    product_name = serializers.CharField(source="product.name", read_only=True, default=None)
    variant = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.all(), allow_null=True, required=False
    )
    variant_label = serializers.SerializerMethodField()
    description = serializers.CharField(max_length=300, required=False, allow_blank=True)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2)
    unit_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    taxes = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Tax.objects.all(), required=False
    )
    tax_names = serializers.SerializerMethodField()
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    tax_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    def get_variant_label(self, obj) -> str | None:
        variant = obj.variant if hasattr(obj, "variant") else None
        return f"{variant.attribute}: {variant.value}" if variant else None

    def get_tax_names(self, obj) -> list[str]:
        return [t.name for t in obj.taxes.all()] if hasattr(obj, "taxes") else []


class SubscriptionListSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.__str__", read_only=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    billing_label = serializers.CharField(source="plan.billing_label", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    quotation_expired = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id", "number", "customer", "customer_name", "plan", "plan_name", "billing_label",
            "status", "status_label", "start_date", "expiry_date", "next_invoice_date",
            "quotation_valid_until", "quotation_expired", "is_expired", "untaxed_amount",
            "tax_amount", "total", "mrr", "created_at",
        ]  # fmt: skip


class SubscriptionDetailSerializer(SubscriptionListSerializer):
    customer_detail = CustomerLiteSerializer(source="customer", read_only=True)
    plan_detail = PlanLiteSerializer(source="plan", read_only=True)
    lines = SubscriptionLineSerializer(many=True, read_only=True)
    payment_term_name = serializers.CharField(
        source="payment_term.name", read_only=True, default=None
    )
    template_name = serializers.CharField(source="template.name", read_only=True, default=None)
    salesperson_name = serializers.CharField(
        source="salesperson.name", read_only=True, default=None
    )
    allowed_actions = serializers.SerializerMethodField()

    class Meta(SubscriptionListSerializer.Meta):
        fields = SubscriptionListSerializer.Meta.fields + [
            "customer_detail", "plan_detail", "lines", "payment_term", "payment_term_name",
            "template", "template_name", "salesperson", "salesperson_name", "notes", "terms",
            "quotation_sent_at", "confirmed_at", "accepted_by_name", "accepted_at",
            "activated_at", "paused_at", "closed_at", "close_reason", "renewal_count",
            "allowed_actions",
        ]  # fmt: skip

    def get_allowed_actions(self, obj) -> list[str]:
        return allowed_actions(obj, self.context["request"].user)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if getattr(self.context["request"].user, "role", None) == "CUSTOMER":
            data.pop("notes", None)  # internal notes stay internal
        return data


class SubscriptionWriteSerializer(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())
    plan = serializers.PrimaryKeyRelatedField(queryset=RecurringPlan.objects.all(), required=False)
    template = serializers.PrimaryKeyRelatedField(
        queryset=QuotationTemplate.objects.filter(is_active=True), required=False, allow_null=True
    )
    start_date = serializers.DateField(required=False)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    payment_term = serializers.PrimaryKeyRelatedField(
        queryset=PaymentTerm.objects.all(), required=False, allow_null=True
    )
    salesperson = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role__in=["ADMIN", "STAFF"]), required=False, allow_null=True
    )
    notes = serializers.CharField(required=False, allow_blank=True)
    terms = serializers.CharField(required=False, allow_blank=True)
    lines = SubscriptionLineSerializer(many=True, required=False)

    def validate(self, attrs):
        if self.partial:
            return attrs
        if not attrs.get("plan") and not attrs.get("template"):
            raise serializers.ValidationError({"plan": "Choose a plan or a quotation template."})
        attrs.setdefault("start_date", timezone.localdate())
        return attrs


class TemplateLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    variant_label = serializers.SerializerMethodField()

    class Meta:
        model = QuotationTemplateLine
        fields = [
            "id",
            "product",
            "product_name",
            "variant",
            "variant_label",
            "quantity",
            "description",
        ]
        read_only_fields = ["id"]

    def get_variant_label(self, obj) -> str | None:
        return f"{obj.variant.attribute}: {obj.variant.value}" if obj.variant else None

    def validate(self, attrs):
        variant = attrs.get("variant")
        if variant and variant.product_id != attrs["product"].id:
            raise serializers.ValidationError({"variant": "Belongs to a different product."})
        return attrs


class QuotationTemplateSerializer(serializers.ModelSerializer):
    lines = TemplateLineSerializer(many=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    payment_term_name = serializers.CharField(
        source="payment_term.name", read_only=True, default=None
    )

    class Meta:
        model = QuotationTemplate
        fields = [
            "id", "name", "validity_days", "plan", "plan_name", "payment_term",
            "payment_term_name", "duration_months", "notes", "is_active", "lines", "created_at",
        ]  # fmt: skip
        read_only_fields = ["id", "created_at"]

    def validate_validity_days(self, value):
        if value < 1:
            raise serializers.ValidationError("A quotation must stay valid at least one day.")
        return value

    @transaction.atomic
    def create(self, validated):
        lines = validated.pop("lines")
        template = QuotationTemplate.objects.create(**validated)
        for i, line in enumerate(lines):
            QuotationTemplateLine.objects.create(template=template, sequence=i, **line)
        return template

    @transaction.atomic
    def update(self, instance, validated):
        lines = validated.pop("lines", None)
        for key, value in validated.items():
            setattr(instance, key, value)
        instance.save()
        if lines is not None:
            instance.lines.all().delete()
            for i, line in enumerate(lines):
                QuotationTemplateLine.objects.create(template=instance, sequence=i, **line)
        return instance


class DiscountSerializer(serializers.ModelSerializer):
    products = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Product.objects.all(), required=False
    )
    subscriptions = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Subscription.objects.all(), required=False
    )
    product_names = serializers.SerializerMethodField()
    subscription_numbers = serializers.SerializerMethodField()
    times_used = serializers.IntegerField(read_only=True, required=False)
    total_discounted = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, required=False
    )
    state = serializers.SerializerMethodField()

    class Meta:
        model = Discount
        fields = [
            "id", "name", "code", "kind", "value", "scope", "products", "product_names",
            "subscriptions", "subscription_numbers", "min_purchase", "min_quantity",
            "start_date", "end_date", "usage_limit", "times_used", "total_discounted",
            "is_active", "state", "created_at",
        ]  # fmt: skip
        read_only_fields = ["id", "created_at"]

    def get_product_names(self, obj) -> list[str]:
        return [p.name for p in obj.products.all()]

    def get_subscription_numbers(self, obj) -> list[str]:
        return [s.number for s in obj.subscriptions.all()]

    def get_state(self, obj) -> str:
        today = timezone.localdate()
        if not obj.is_active:
            return "inactive"
        if obj.start_date and obj.start_date > today:
            return "scheduled"
        if obj.end_date and obj.end_date < today:
            return "expired"
        used = getattr(obj, "times_used", None)
        if obj.usage_limit is not None and used is not None and used >= obj.usage_limit:
            return "exhausted"
        return "active"

    def validate(self, attrs):
        def get(name):
            return attrs.get(name, getattr(self.instance, name, None) if self.instance else None)

        if get("kind") == Discount.Kind.PERCENT and get("value") is not None and get("value") > 100:
            raise serializers.ValidationError({"value": "A percentage cannot exceed 100."})
        if get("value") is not None and get("value") <= 0:
            raise serializers.ValidationError({"value": "Must be more than zero."})
        start, end = get("start_date"), get("end_date")
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "Must be on or after the start date."})
        if get("scope") == Discount.Scope.PRODUCTS:
            products = attrs.get("products")
            if products is None and self.instance:
                products = list(self.instance.products.all())
            if not products:
                raise serializers.ValidationError(
                    {"products": "Choose the products this discount applies to."}
                )
        return attrs
