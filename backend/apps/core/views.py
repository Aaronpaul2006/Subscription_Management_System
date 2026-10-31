from django.conf import settings
from django.db.models import Q
from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Activity, OutboundEmail
from .permissions import IsAdmin, IsInternal
from .serializers import ActivitySerializer, OutboundEmailSerializer


class MetaView(APIView):
    """Company details and the choice lists the web app needs."""

    permission_classes = [AllowAny]

    def get(self, request):
        from apps.catalog.models import Product, RecurringPlan, Tax
        from apps.invoicing.models import Invoice, Payment
        from apps.subscriptions.models import Discount, Subscription

        def choices(enum):
            return [{"value": v, "label": label} for v, label in enum.choices]

        return Response(
            {
                "company": settings.COMPANY,
                "password_rules": "More than 8 characters, with an uppercase letter, a lowercase "
                "letter and a special character.",
                "choices": {
                    "product_type": choices(Product.Type),
                    "billing_period": choices(RecurringPlan.Period),
                    "tax_computation": choices(Tax.Computation),
                    "subscription_status": choices(Subscription.Status),
                    "invoice_status": choices(Invoice.Status),
                    "payment_method": choices(Payment.Method),
                    "discount_kind": choices(Discount.Kind),
                    "discount_scope": choices(Discount.Scope),
                },
            }
        )


class ActivityViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsInternal]
    serializer_class = ActivitySerializer
    filterset_fields = ["entity", "entity_id", "verb"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        return Activity.objects.select_related("actor")


class OutboxViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Every email the platform sent. Admin only."""

    permission_classes = [IsAdmin]
    serializer_class = OutboundEmailSerializer
    queryset = OutboundEmail.objects.all()
    filterset_fields = ["category", "status"]
    search_fields = ["to", "subject"]


class SearchView(APIView):
    """Global search behind the Ctrl+K command palette."""

    permission_classes = [IsInternal]

    def get(self, request):
        from apps.accounts.models import Customer
        from apps.catalog.models import Product, RecurringPlan
        from apps.invoicing.models import Invoice
        from apps.subscriptions.models import Subscription

        term = (request.query_params.get("q") or "").strip()
        if len(term) < 2:
            return Response([])
        results = []
        for s in Subscription.objects.select_related("customer").filter(
            Q(number__icontains=term)
            | Q(customer__name__icontains=term)
            | Q(customer__company__icontains=term)
        )[:6]:
            results.append(
                {
                    "type": "subscription",
                    "id": s.id,
                    "title": s.number,
                    "subtitle": f"{s.customer} · {s.get_status_display()}",
                }
            )
        for c in Customer.objects.filter(
            Q(name__icontains=term) | Q(company__icontains=term) | Q(email__icontains=term)
        )[:6]:
            results.append({"type": "customer", "id": c.id, "title": str(c), "subtitle": c.email})
        for i in Invoice.objects.select_related("customer").filter(
            Q(number__icontains=term)
            | Q(customer__name__icontains=term)
            | Q(customer__company__icontains=term)
        )[:6]:
            results.append(
                {
                    "type": "invoice",
                    "id": i.id,
                    "title": i.display_number,
                    "subtitle": f"{i.customer} · {i.get_status_display()} · {i.total}",
                }
            )
        for p in Product.objects.filter(name__icontains=term)[:4]:
            results.append(
                {
                    "type": "product",
                    "id": p.id,
                    "title": p.name,
                    "subtitle": p.get_product_type_display(),
                }
            )
        for p in RecurringPlan.objects.filter(name__icontains=term)[:4]:
            results.append(
                {"type": "plan", "id": p.id, "title": p.name, "subtitle": p.billing_label}
            )
        return Response(results)
