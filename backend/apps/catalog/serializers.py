from django.db import transaction
from rest_framework import serializers

from .models import PaymentTerm, Product, ProductVariant, RecurringPlan, Tax


class TaxSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tax
        fields = ["id", "name", "computation", "amount", "description", "is_active"]

    def validate(self, attrs):
        computation = attrs.get("computation", getattr(self.instance, "computation", None))
        amount = attrs.get("amount", getattr(self.instance, "amount", None))
        if computation == Tax.Computation.PERCENT and amount is not None and amount > 100:
            raise serializers.ValidationError({"amount": "A percentage cannot exceed 100."})
        return attrs


class VariantSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = ProductVariant
        fields = ["id", "attribute", "value", "extra_price", "price"]


class ProductSerializer(serializers.ModelSerializer):
    variants = VariantSerializer(many=True, required=False)
    taxes = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Tax.objects.all(), required=False
    )
    tax_names = serializers.SerializerMethodField()
    margin_percent = serializers.DecimalField(
        max_digits=6, decimal_places=1, read_only=True, allow_null=True
    )
    product_type_label = serializers.CharField(source="get_product_type_display", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "product_type", "product_type_label", "sales_price", "cost_price",
            "margin_percent", "notes", "taxes", "tax_names", "variants", "is_active", "created_at",
        ]  # fmt: skip
        read_only_fields = ["id", "created_at"]

    def get_tax_names(self, obj) -> list[str]:
        return [t.name for t in obj.taxes.all()]

    def validate_variants(self, variants):
        seen = set()
        for v in variants:
            key = (v["attribute"].strip().lower(), v["value"].strip().lower())
            if key in seen:
                raise serializers.ValidationError(
                    f"Variant {v['attribute']}: {v['value']} is listed twice."
                )
            seen.add(key)
        return variants

    @transaction.atomic
    def create(self, validated):
        variants = validated.pop("variants", [])
        taxes = validated.pop("taxes", [])
        product = Product.objects.create(**validated)
        product.taxes.set(taxes)
        for v in variants:
            v.pop("id", None)
            ProductVariant.objects.create(product=product, **v)
        return product

    @transaction.atomic
    def update(self, instance, validated):
        variants = validated.pop("variants", None)
        taxes = validated.pop("taxes", None)
        for key, value in validated.items():
            setattr(instance, key, value)
        instance.save()
        if taxes is not None:
            instance.taxes.set(taxes)
        if variants is not None:
            keep = []
            for v in variants:
                vid = v.pop("id", None)
                if vid and instance.variants.filter(pk=vid).exists():
                    instance.variants.filter(pk=vid).update(**v)
                    keep.append(vid)
                else:
                    keep.append(ProductVariant.objects.create(product=instance, **v).id)
            # Variants already on a subscription stay (PROTECT); unused ones go.
            for variant in instance.variants.exclude(pk__in=keep):
                if not variant.subscriptionline_set.exists():
                    variant.delete()
        return instance


class PaymentTermSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentTerm
        fields = ["id", "name", "due_days", "is_active"]


class RecurringPlanSerializer(serializers.ModelSerializer):
    taxes = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Tax.objects.all(), required=False
    )
    billing_label = serializers.CharField(read_only=True)
    billing_period_label = serializers.CharField(
        source="get_billing_period_display", read_only=True
    )
    active_subscriptions = serializers.IntegerField(read_only=True, required=False)
    is_available = serializers.SerializerMethodField()

    class Meta:
        model = RecurringPlan
        fields = [
            "id", "name", "description", "price", "billing_period", "billing_period_label",
            "billing_interval", "billing_label", "min_quantity", "start_date", "end_date",
            "auto_close", "closable", "pausable", "renewable", "taxes", "is_active",
            "is_available", "active_subscriptions", "created_at",
        ]  # fmt: skip
        read_only_fields = ["id", "created_at"]

    def get_is_available(self, obj) -> bool:
        from django.utils import timezone

        return obj.is_available_on(timezone.localdate())

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "Must be on or after the start date."})
        return attrs


class PlanLiteSerializer(serializers.ModelSerializer):
    billing_label = serializers.CharField(read_only=True)

    class Meta:
        model = RecurringPlan
        fields = [
            "id", "name", "price", "billing_period", "billing_interval", "billing_label",
            "min_quantity", "auto_close", "closable", "pausable", "renewable",
        ]  # fmt: skip
