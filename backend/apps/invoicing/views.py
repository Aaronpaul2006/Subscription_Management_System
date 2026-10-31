from datetime import date

from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone
from django_filters import rest_framework as filters
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.errors import Forbidden, Invalid
from apps.core.models import Activity
from apps.core.permissions import IsAdmin, IsInternal, role_of
from apps.core.serializers import ActivitySerializer

from . import services
from .models import BillingRun, Invoice, Payment
from .pdf import invoice_pdf
from .serializers import (
    BillingRunSerializer,
    InvoiceDetailSerializer,
    InvoiceListSerializer,
    PaymentCreateSerializer,
    PaymentSerializer,
)

I = Invoice.Status  # noqa: E741
MONEY = DecimalField(max_digits=14, decimal_places=2)


def _overdue_q(today: date) -> Q:
    return Q(status=I.CONFIRMED, amount_due__gt=0, due_date__lt=today)


class InvoiceFilter(filters.FilterSet):
    status = filters.MultipleChoiceFilter(choices=Invoice.Status.choices)
    overdue = filters.BooleanFilter(method="filter_overdue")
    outstanding = filters.BooleanFilter(method="filter_outstanding")
    date_from = filters.DateFilter(field_name="invoice_date", lookup_expr="gte")
    date_to = filters.DateFilter(field_name="invoice_date", lookup_expr="lte")
    due_from = filters.DateFilter(field_name="due_date", lookup_expr="gte")
    due_to = filters.DateFilter(field_name="due_date", lookup_expr="lte")
    plan = filters.NumberFilter(field_name="subscription__plan")

    class Meta:
        model = Invoice
        fields = ["status", "customer", "subscription", "billing_run"]

    def filter_overdue(self, qs, name, value):
        q = _overdue_q(timezone.localdate())
        return qs.filter(q) if value else qs.exclude(q)

    def filter_outstanding(self, qs, name, value):
        q = Q(status=I.CONFIRMED, amount_due__gt=0)
        return qs.filter(q) if value else qs.exclude(q)


def scope_to_customer(qs, user):
    """Customers only ever see their own records; drafts stay internal."""
    if role_of(user) == "CUSTOMER":
        return qs.filter(customer=getattr(user, "customer", None)).exclude(status=I.DRAFT)
    return qs


class InvoiceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    filterset_class = InvoiceFilter
    search_fields = [
        "number",
        "customer__name",
        "customer__company",
        "customer__email",
        "subscription__number",
    ]
    ordering_fields = ["invoice_date", "due_date", "total", "amount_due", "number"]
    ordering = ["-invoice_date", "-id"]

    def get_queryset(self):
        qs = Invoice.objects.select_related("customer", "subscription")
        if self.action not in ("list", "stats", "export"):
            qs = qs.prefetch_related("lines", "applied_discounts", "payments__recorded_by")
        return scope_to_customer(qs, self.request.user)

    def get_serializer_class(self):
        return InvoiceListSerializer if self.action == "list" else InvoiceDetailSerializer

    def _detail(self, invoice, code=status.HTTP_200_OK):
        invoice = self.get_queryset().get(pk=invoice.pk)
        return Response(
            InvoiceDetailSerializer(invoice, context={"request": self.request}).data, status=code
        )

    def _internal_only(self):
        if role_of(self.request.user) not in ("ADMIN", "STAFF"):
            raise Forbidden("Only Brightloop staff can do this.")

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        self._internal_only()
        return self._detail(services.confirm_invoice(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        self._internal_only()
        reason = (request.data.get("reason") or "").strip()
        return self._detail(services.cancel_invoice(self.get_object(), request.user, reason))

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        self._internal_only()
        return self._detail(services.send_invoice(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def remind(self, request, pk=None):
        self._internal_only()
        invoice = self.get_object()
        if not invoice.is_overdue:
            raise Invalid("Only overdue invoices get payment reminders.")
        Invoice.objects.filter(pk=invoice.pk).update(last_reminder_at=None)
        services.send_overdue_reminders()
        return self._detail(invoice)

    @action(detail=True, methods=["post"])
    def rebill(self, request, pk=None):
        self._internal_only()
        new = services.rebill_period(self.get_object(), request.user)
        return self._detail(new, status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        """Customer portal checkout (demo gateway: the payment always succeeds)."""
        if role_of(request.user) != "CUSTOMER":
            raise Forbidden("Staff record payments with Register payment.")
        invoice = self.get_object()
        method = request.data.get("method") or Payment.Method.CARD
        if method not in (Payment.Method.CARD, Payment.Method.UPI, Payment.Method.BANK_TRANSFER):
            raise Invalid("Choose card, UPI or bank transfer.")
        services.record_payment(
            invoice,
            amount=invoice.amount_due,
            method=method,
            payment_date=timezone.localdate(),
            reference=f"PORTAL-{timezone.now():%Y%m%d%H%M%S}",
            note="Paid online through the customer portal",
            actor=request.user,
            source=Payment.Source.PORTAL,
        )
        return self._detail(invoice)

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        invoice = self.get_object()
        name = invoice.display_number.replace("/", "-").replace(" ", "-").replace("#", "")
        response = HttpResponse(invoice_pdf(invoice), content_type="application/pdf")
        disposition = "attachment" if request.query_params.get("download") else "inline"
        response["Content-Disposition"] = f'{disposition}; filename="{name}.pdf"'
        return response

    @action(detail=True, methods=["get"])
    def activity(self, request, pk=None):
        self._internal_only()
        invoice = self.get_object()
        qs = Activity.objects.filter(entity="invoice", entity_id=invoice.id).select_related(
            "actor"
        )[:100]
        return Response(ActivitySerializer(qs, many=True).data)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Counts and totals for the status tabs; honours other filters."""
        from rest_framework.filters import SearchFilter

        params = request.query_params.copy()
        for key in ("status", "overdue", "outstanding"):
            params.pop(key, None)
        qs = InvoiceFilter(params, queryset=self.get_queryset(), request=request).qs
        qs = SearchFilter().filter_queryset(request, qs, self).order_by()
        today = timezone.localdate()
        out = {
            r["status"]: {"count": r["count"], "total": str(r["total"]), "due": str(r["due"])}
            for r in qs.values("status").annotate(
                count=Count("id"),
                total=Coalesce(Sum("total"), Value(0), output_field=MONEY),
                due=Coalesce(Sum("amount_due"), Value(0), output_field=MONEY),
            )
        }
        overdue = qs.filter(_overdue_q(today)).aggregate(
            count=Count("id"), due=Coalesce(Sum("amount_due"), Value(0), output_field=MONEY)
        )
        out["OVERDUE"] = {
            "count": overdue["count"],
            "total": str(overdue["due"]),
            "due": str(overdue["due"]),
        }
        return Response(out)


class PaymentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentSerializer
    filterset_fields = {
        "method": ["exact"],
        "customer": ["exact"],
        "invoice": ["exact"],
        "source": ["exact"],
        "payment_date": ["gte", "lte"],
    }
    search_fields = ["invoice__number", "customer__name", "customer__company", "reference", "note"]
    ordering_fields = ["payment_date", "amount", "created_at"]
    ordering = ["-payment_date", "-id"]

    def get_queryset(self):
        qs = Payment.objects.select_related("invoice", "customer", "recorded_by")
        if role_of(self.request.user) == "CUSTOMER":
            qs = qs.filter(customer=getattr(self.request.user, "customer", None))
        return qs

    def create(self, request):
        if role_of(request.user) not in ("ADMIN", "STAFF"):
            raise Forbidden("Only Brightloop staff can record payments.")
        data = PaymentCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        payment = services.record_payment(
            v["invoice"],
            amount=v["amount"],
            method=v["method"],
            payment_date=v.get("payment_date"),
            note=v.get("note", ""),
            reference=v.get("reference", ""),
            actor=request.user,
        )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class BillingRunViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsInternal]
    serializer_class = BillingRunSerializer
    queryset = BillingRun.objects.select_related("triggered_by")

    @action(detail=False, methods=["get"])
    def preview(self, request):
        as_of = _date_param(request, "as_of")
        result = services.preview_billing(as_of)
        result["total"] = str(result["total"])
        for row in result["rows"]:
            row["total"] = str(row["total"])
            row["discount"] = str(row["discount"])
        return Response(result)

    @action(detail=False, methods=["post"])
    def run(self, request):
        as_of = _date_param(request, "as_of", body=True)
        if as_of > timezone.localdate():
            raise Invalid("A billing run cannot be dated in the future.")
        run = services.run_billing(
            as_of,
            actor=request.user,
            auto_confirm=bool(request.data.get("auto_confirm", True)),
            auto_send=bool(request.data.get("auto_send", False)),
        )
        return Response(BillingRunSerializer(run).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def gaps(self, request):
        gaps = services.billing_gaps()
        return Response({"healthy": not gaps, "gaps": gaps})

    @action(detail=False, methods=["post"], url_path="daily-jobs", permission_classes=[IsAdmin])
    def daily_jobs(self, request):
        return Response(services.run_daily_jobs(actor=request.user))

    @action(detail=False, methods=["post"], url_path="send-reminders")
    def send_reminders(self, request):
        return Response({"sent": services.send_overdue_reminders()})


def _date_param(request, name: str, body: bool = False) -> date:
    raw = (request.data if body else request.query_params).get(name)
    if not raw:
        return timezone.localdate()
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        raise Invalid(f"{name} must be a date like 2026-10-31.") from None


class InvoiceExportView(APIView):
    """CSV export of the filtered invoice list (for the finance lead)."""

    permission_classes = [IsInternal]

    def get(self, request):
        import csv

        view = InvoiceViewSet(request=request, format_kwarg=None, action="export")
        view.kwargs = {}
        qs = view.filter_queryset(view.get_queryset())
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="invoices.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "Number",
                "Customer",
                "Subscription",
                "Status",
                "Invoice date",
                "Due date",
                "Untaxed",
                "Discount",
                "Tax",
                "Total",
                "Paid",
                "Due",
                "Overdue days",
            ]
        )
        for inv in qs.iterator(chunk_size=2000):
            writer.writerow(
                [
                    inv.display_number,
                    str(inv.customer),
                    inv.subscription.number if inv.subscription else "",
                    inv.get_status_display(),
                    inv.invoice_date,
                    inv.due_date,
                    inv.untaxed_amount,
                    inv.discount_amount,
                    inv.tax_amount,
                    inv.total,
                    inv.amount_paid,
                    inv.amount_due,
                    inv.days_overdue,
                ]
            )
        return response
