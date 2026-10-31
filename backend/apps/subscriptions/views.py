from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django_filters import rest_framework as filters
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.errors import Forbidden, Invalid
from apps.core.models import Activity, log_activity
from apps.core.permissions import AdminWritesInternalReads, IsInternal, role_of
from apps.core.serializers import ActivitySerializer

from . import services
from .models import Discount, QuotationTemplate, Subscription
from .serializers import (
    DiscountSerializer,
    QuotationTemplateSerializer,
    SubscriptionDetailSerializer,
    SubscriptionListSerializer,
    SubscriptionWriteSerializer,
)


class SubscriptionFilter(filters.FilterSet):
    status = filters.MultipleChoiceFilter(choices=Subscription.Status.choices)
    start_from = filters.DateFilter(field_name="start_date", lookup_expr="gte")
    start_to = filters.DateFilter(field_name="start_date", lookup_expr="lte")
    expiring_within = filters.NumberFilter(method="filter_expiring")
    due_for_billing = filters.BooleanFilter(method="filter_due")

    class Meta:
        model = Subscription
        fields = ["status", "plan", "customer", "salesperson"]

    def filter_expiring(self, qs, name, value):
        today = timezone.localdate()
        return qs.filter(
            status__in=["ACTIVE", "PAUSED"],
            expiry_date__gte=today,
            expiry_date__lte=today + timezone.timedelta(days=int(value)),
        )

    def filter_due(self, qs, name, value):
        today = timezone.localdate()
        due = Q(status="ACTIVE", next_invoice_date__lte=today) & (
            Q(expiry_date__isnull=True) | Q(next_invoice_date__lte=F("expiry_date"))
        )
        return qs.filter(due) if value else qs.exclude(due)


class SubscriptionViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Subscriptions. Customers see only their own (others are 404)."""

    permission_classes = [IsAuthenticated]
    filterset_class = SubscriptionFilter
    search_fields = [
        "number",
        "customer__name",
        "customer__company",
        "customer__email",
        "plan__name",
    ]
    ordering_fields = [
        "number",
        "created_at",
        "start_date",
        "expiry_date",
        "next_invoice_date",
        "total",
        "mrr",
    ]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        qs = Subscription.objects.select_related("customer", "plan")
        if self.action not in ("list", "stats"):
            qs = qs.select_related("payment_term", "template", "salesperson").prefetch_related(
                "lines__taxes", "lines__product", "lines__variant"
            )
        if role_of(self.request.user) == "CUSTOMER":
            customer = getattr(self.request.user, "customer", None)
            qs = qs.filter(customer=customer).exclude(status=Subscription.Status.DRAFT)
        return qs

    def get_serializer_class(self):
        return (
            SubscriptionListSerializer if self.action == "list" else (SubscriptionDetailSerializer)
        )

    def _detail(self, sub, code=status.HTTP_200_OK):
        sub = self.get_queryset().get(pk=sub.pk)
        return Response(
            SubscriptionDetailSerializer(sub, context={"request": self.request}).data, status=code
        )

    def _internal_only(self):
        if role_of(self.request.user) not in ("ADMIN", "STAFF"):
            raise Forbidden("Only Brightloop staff can do this.")

    # ------------------------------------------------------------ create / edit

    def create(self, request):
        self._internal_only()
        data = SubscriptionWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        lines = [dict(line) for line in v.pop("lines", [])] or None
        sub = services.create_subscription(
            customer=v["customer"],
            plan=v.get("plan") or v["template"].plan,
            start_date=v["start_date"],
            lines=lines,
            template=v.get("template"),
            expiry_date=v.get("expiry_date"),
            payment_term=v.get("payment_term"),
            salesperson=v.get("salesperson"),
            notes=v.get("notes", ""),
            terms=v.get("terms", ""),
            actor=request.user,
        )
        return self._detail(sub, status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        self._internal_only()
        sub = self.get_object()
        data = SubscriptionWriteSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        v = dict(data.validated_data)
        lines = v.pop("lines", None)
        lines = [dict(line) for line in lines] if lines is not None else None
        v.pop("template", None)
        services.update_subscription(sub, v, lines, request.user)
        return self._detail(sub)

    # ------------------------------------------------------------ transitions

    def _transition(self, fn, internal=True, **kwargs):
        if internal:
            self._internal_only()
        sub = self.get_object()
        fn(sub, actor=self.request.user, **kwargs)
        return self._detail(sub)

    @action(detail=True, methods=["post"], url_path="send-quotation")
    def send_quotation(self, request, pk=None):
        return self._transition(
            services.send_quotation, email=bool(request.data.get("email", True))
        )

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        return self._transition(services.confirm)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        """The customer accepts a quotation online by typing their name."""
        name = (request.data.get("name") or "").strip()
        if len(name) < 2:
            raise Invalid(
                "Type your full name to accept the quotation.", fields={"name": "Required"}
            )
        return self._transition(services.confirm, internal=False, accepted_by_name=name)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        return self._transition(services.activate)

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        return self._transition(services.pause, internal=False)

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        return self._transition(services.resume, internal=False)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        return self._transition(
            services.close, internal=False, reason=(request.data.get("reason") or "")[:200]
        )

    @action(detail=True, methods=["post"])
    def renew(self, request, pk=None):
        return self._transition(services.renew, internal=False)

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        self._internal_only()
        new = services.duplicate(self.get_object(), request.user)
        return self._detail(new, status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="invoice-now")
    def invoice_now(self, request, pk=None):
        """Bill the next period immediately (ahead of the billing run)."""
        from apps.invoicing.serializers import InvoiceDetailSerializer
        from apps.invoicing.services import bill_next_period

        self._internal_only()
        invoice = bill_next_period(
            self.get_object(),
            actor=request.user,
            confirm_now=bool(request.data.get("confirm", False)),
        )
        return Response(
            InvoiceDetailSerializer(invoice, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    # ------------------------------------------------------------ read helpers

    @action(detail=True, methods=["get"], url_path="upcoming-invoice")
    def upcoming_invoice(self, request, pk=None):
        """Preview the next invoice, discounts and proration included."""
        from apps.invoicing.services import DiscountBook, is_billable, period_for, price_period

        sub = self.get_object()
        start = sub.next_invoice_date or sub.start_date
        if not is_billable(sub, start) or sub.status == Subscription.Status.CLOSED:
            return Response(None)
        period = period_for(sub, start)
        priced = price_period(sub, period, DiscountBook(period.start))
        return Response(
            {
                "period_start": period.start,
                "period_end": period.end,
                "prorated": period.prorated,
                "lines": [
                    {
                        k: (str(v) if not isinstance(v, list | type(None)) else v)
                        for k, v in line.items()
                    }
                    for line in priced.lines
                ],
                "discounts": [{"name": r.name, "amount": str(a)} for r, a in priced.discounts],
                "untaxed_amount": str(priced.untaxed),
                "discount_amount": str(priced.discount),
                "tax_amount": str(priced.tax),
                "total": str(priced.total),
            }
        )

    @action(detail=True, methods=["get"])
    def activity(self, request, pk=None):
        sub = self.get_object()
        invoice_ids = list(sub.invoices.values_list("id", flat=True))
        qs = Activity.objects.filter(
            Q(entity="subscription", entity_id=sub.id)
            | Q(entity="invoice", entity_id__in=invoice_ids)
        ).select_related("actor")[:100]
        return Response(ActivitySerializer(qs, many=True).data)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Counts per status for the list tabs. Honours every filter except
        ``status`` itself, so each tab shows its own count."""
        from rest_framework.filters import SearchFilter

        params = request.query_params.copy()
        params.pop("status", None)
        qs = SubscriptionFilter(params, queryset=self.get_queryset(), request=request).qs
        qs = SearchFilter().filter_queryset(request, qs, self).order_by()
        money = DecimalField(max_digits=14, decimal_places=2)
        rows = qs.values("status").annotate(
            count=Count("id"), mrr_total=Coalesce(Sum("mrr"), Value(0), output_field=money)
        )
        return Response(
            {r["status"]: {"count": r["count"], "mrr": str(r["mrr_total"])} for r in rows}
        )


class QuotationTemplateViewSet(viewsets.ModelViewSet):
    permission_classes = [IsInternal]
    serializer_class = QuotationTemplateSerializer
    filterset_fields = ["is_active", "plan"]
    search_fields = ["name"]
    pagination_class = None
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return QuotationTemplate.objects.select_related("plan", "payment_term").prefetch_related(
            "lines__product", "lines__variant"
        )


class DiscountViewSet(viewsets.ModelViewSet):
    """Discount rules: only the admin creates or changes them."""

    permission_classes = [AdminWritesInternalReads]
    serializer_class = DiscountSerializer
    filterset_fields = ["is_active", "kind", "scope"]
    search_fields = ["name", "code"]
    ordering = ["-created_at", "-id"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        live = ~Q(applications__invoice__status="CANCELLED")
        return Discount.objects.prefetch_related("products", "subscriptions").annotate(
            times_used=Count("applications", filter=live),
            total_discounted=Coalesce(
                Sum("applications__amount", filter=live),
                Value(0),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
        )

    def perform_create(self, serializer):
        discount = serializer.save(created_by=self.request.user)
        log_activity(
            "discount", discount.id, "created", f"Discount {discount} created", self.request.user
        )

    def perform_update(self, serializer):
        discount = serializer.save()
        log_activity(
            "discount", discount.id, "updated", f"Discount {discount} updated", self.request.user
        )
