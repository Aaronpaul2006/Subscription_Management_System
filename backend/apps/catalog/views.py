from django.db.models import Count, Q
from rest_framework import viewsets

from apps.core.models import log_activity
from apps.core.permissions import AdminWritesInternalReads

from .models import PaymentTerm, Product, RecurringPlan, Tax
from .serializers import (
    PaymentTermSerializer,
    ProductSerializer,
    RecurringPlanSerializer,
    TaxSerializer,
)

# Catalog records are archived (is_active = false), never deleted: invoices
# and subscriptions keep pointing at them.
NO_DELETE = ["get", "post", "patch", "head", "options"]


class AuditedViewSet(viewsets.ModelViewSet):
    entity = ""
    http_method_names = NO_DELETE
    permission_classes = [AdminWritesInternalReads]

    def perform_create(self, serializer):
        obj = serializer.save()
        log_activity(
            self.entity,
            obj.id,
            "created",
            f"{self.entity.title()} {obj} created",
            self.request.user,
        )

    def perform_update(self, serializer):
        obj = serializer.save()
        log_activity(
            self.entity,
            obj.id,
            "updated",
            f"{self.entity.title()} {obj} updated",
            self.request.user,
        )


class TaxViewSet(AuditedViewSet):
    entity = "tax"
    queryset = Tax.objects.all()
    serializer_class = TaxSerializer
    filterset_fields = ["is_active", "computation"]
    search_fields = ["name"]
    pagination_class = None


class PaymentTermViewSet(AuditedViewSet):
    entity = "payment_term"
    queryset = PaymentTerm.objects.all()
    serializer_class = PaymentTermSerializer
    filterset_fields = ["is_active"]
    pagination_class = None


class ProductViewSet(AuditedViewSet):
    entity = "product"
    serializer_class = ProductSerializer
    filterset_fields = ["is_active", "product_type"]
    search_fields = ["name", "notes", "variants__value"]
    ordering_fields = ["name", "sales_price", "created_at"]
    ordering = ["name"]

    def get_queryset(self):
        return Product.objects.prefetch_related("variants", "taxes").distinct()


class RecurringPlanViewSet(AuditedViewSet):
    entity = "plan"
    serializer_class = RecurringPlanSerializer
    filterset_fields = ["is_active", "billing_period"]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "price", "created_at"]
    ordering = ["name"]

    def get_queryset(self):
        return RecurringPlan.objects.prefetch_related("taxes").annotate(
            active_subscriptions=Count("subscriptions", filter=Q(subscriptions__status="ACTIVE"))
        )
