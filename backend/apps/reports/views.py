"""The finance lead's view: one request returns the whole dashboard.

Every number is a database aggregate over indexed columns, so the dashboard
stays well under two seconds with tens of thousands of subscriptions
(see tests/test_performance.py).
"""

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.errors import Forbidden, Invalid
from apps.core.models import Activity
from apps.core.money import q
from apps.core.permissions import IsInternal, role_of
from apps.core.serializers import ActivitySerializer
from apps.invoicing.models import Invoice, Payment
from apps.invoicing.serializers import InvoiceListSerializer
from apps.subscriptions.models import Subscription
from apps.subscriptions.serializers import SubscriptionListSerializer

MONEY = DecimalField(max_digits=16, decimal_places=2)
ZERO = Value(Decimal("0"), output_field=MONEY)
I = Invoice.Status  # noqa: E741
S = Subscription.Status


def _sum(field, **filter_kw):
    return Coalesce(
        Sum(field, filter=Q(**filter_kw) if filter_kw else None), ZERO, output_field=MONEY
    )


def _parse(request, name, default: date) -> date:
    raw = request.query_params.get(name)
    if not raw:
        return default
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise Invalid(f"{name} must be a date like 2026-10-31.") from None


def _month_start(day: date, back: int = 0) -> date:
    month = day.month - 1 - back
    return date(day.year + month // 12, month % 12 + 1, 1)


class DashboardView(APIView):
    permission_classes = [IsInternal]

    def get(self, request):
        today = timezone.localdate()
        date_from = _parse(request, "date_from", today.replace(day=1))
        date_to = _parse(request, "date_to", today)
        if date_to < date_from:
            raise Invalid("date_to must be on or after date_from.")
        plan = request.query_params.get("plan")

        subs = Subscription.objects.all()
        invoices = Invoice.objects.all()
        payments = Payment.objects.all()
        if plan:
            subs = subs.filter(plan_id=plan)
            invoices = invoices.filter(subscription__plan_id=plan)
            payments = payments.filter(invoice__subscription__plan_id=plan)

        # --- subscriptions
        sub_kpis = subs.aggregate(
            active=Count("id", filter=Q(status=S.ACTIVE)),
            paused=Count("id", filter=Q(status=S.PAUSED)),
            active_mrr=_sum("mrr", status=S.ACTIVE),
            active_customers=Count("customer", filter=Q(status=S.ACTIVE), distinct=True),
            new=Count(
                "id", filter=Q(activated_at__date__gte=date_from, activated_at__date__lte=date_to)
            ),
            churned=Count(
                "id",
                filter=Q(
                    status=S.CLOSED,
                    activated_at__isnull=False,
                    closed_at__gte=date_from,
                    closed_at__lte=date_to,
                ),
            ),
            churned_mrr=_sum(
                "mrr",
                status=S.CLOSED,
                activated_at__isnull=False,
                closed_at__gte=date_from,
                closed_at__lte=date_to,
            ),
            open_quotations=Count("id", filter=Q(status__in=[S.DRAFT, S.QUOTATION])),
            pipeline=_sum("mrr", status__in=[S.QUOTATION, S.CONFIRMED]),
        )
        by_status = {
            r["status"]: r["n"] for r in subs.order_by().values("status").annotate(n=Count("id"))
        }

        # --- invoices & payments in the period
        live = invoices.filter(status__in=[I.CONFIRMED, I.PAID])
        inv_kpis = live.aggregate(
            invoiced=_sum("total", invoice_date__gte=date_from, invoice_date__lte=date_to),
            invoice_count=Count(
                "id", filter=Q(invoice_date__gte=date_from, invoice_date__lte=date_to)
            ),
            outstanding=_sum("amount_due", status=I.CONFIRMED),
            outstanding_count=Count("id", filter=Q(status=I.CONFIRMED, amount_due__gt=0)),
            overdue=_sum("amount_due", status=I.CONFIRMED, due_date__lt=today),
            overdue_count=Count(
                "id", filter=Q(status=I.CONFIRMED, amount_due__gt=0, due_date__lt=today)
            ),
        )
        draft_count = invoices.filter(status=I.DRAFT).count()
        period_payments = payments.filter(payment_date__gte=date_from, payment_date__lte=date_to)
        pay_kpis = period_payments.aggregate(collected=_sum("amount"), count=Count("id"))

        mrr = sub_kpis["active_mrr"]
        active = sub_kpis["active"]
        base = active + sub_kpis["churned"]
        kpis = {
            "active_subscriptions": active,
            "paused_subscriptions": sub_kpis["paused"],
            "active_customers": sub_kpis["active_customers"],
            "mrr": q(mrr),
            "arr": q(mrr * 12),
            "arpa": q(mrr / sub_kpis["active_customers"] if sub_kpis["active_customers"] else 0),
            "new_subscriptions": sub_kpis["new"],
            "churned_subscriptions": sub_kpis["churned"],
            "churned_mrr": q(sub_kpis["churned_mrr"]),
            "churn_rate": round(sub_kpis["churned"] * 100 / base, 1) if base else 0,
            "open_quotations": sub_kpis["open_quotations"],
            "pipeline_mrr": q(sub_kpis["pipeline"]),
            "invoiced": q(inv_kpis["invoiced"]),
            "invoice_count": inv_kpis["invoice_count"],
            "collected": q(pay_kpis["collected"]),
            "payment_count": pay_kpis["count"],
            "collection_rate": (
                round(pay_kpis["collected"] * 100 / inv_kpis["invoiced"], 1)
                if inv_kpis["invoiced"]
                else None
            ),
            "outstanding": q(inv_kpis["outstanding"]),
            "outstanding_count": inv_kpis["outstanding_count"],
            "overdue": q(inv_kpis["overdue"]),
            "overdue_count": inv_kpis["overdue_count"],
            "draft_invoices": draft_count,
        }

        # Money (and rates) travel as strings, never floats.
        kpis = {k: str(v) if isinstance(v, Decimal) else v for k, v in kpis.items()}

        # --- 12-month trend: invoiced vs collected
        trend_from = _month_start(today, 11)
        invoiced_by_month = {
            r["m"]: r["v"]
            for r in live.filter(invoice_date__gte=trend_from)
            .annotate(m=TruncMonth("invoice_date"))
            .values("m")
            .annotate(v=Sum("total"))
        }
        collected_by_month = {
            r["m"]: r["v"]
            for r in payments.filter(payment_date__gte=trend_from)
            .annotate(m=TruncMonth("payment_date"))
            .values("m")
            .annotate(v=Sum("amount"))
        }
        trend = []
        for back in range(11, -1, -1):
            m = _month_start(today, back)
            trend.append(
                {
                    "month": m.isoformat(),
                    "invoiced": str(q(_lookup(invoiced_by_month, m))),
                    "collected": str(q(_lookup(collected_by_month, m))),
                }
            )

        # --- MRR by plan
        by_plan = [
            {
                "plan_id": r["plan_id"],
                "plan": r["plan__name"],
                "subscriptions": r["n"],
                "mrr": str(q(r["plan_mrr"])),
            }
            for r in subs.filter(status=S.ACTIVE)
            .order_by()
            .values("plan_id", "plan__name")
            .annotate(n=Count("id"), plan_mrr=Sum("mrr"))
            .order_by("-plan_mrr")
        ]

        # --- receivables ageing
        aging_rows = invoices.filter(status=I.CONFIRMED, amount_due__gt=0).aggregate(
            current=_sum("amount_due", due_date__gte=today),
            d30=_sum("amount_due", due_date__lt=today, due_date__gte=today - timedelta(days=30)),
            d60=_sum(
                "amount_due",
                due_date__lt=today - timedelta(days=30),
                due_date__gte=today - timedelta(days=60),
            ),
            d90=_sum(
                "amount_due",
                due_date__lt=today - timedelta(days=60),
                due_date__gte=today - timedelta(days=90),
            ),
            older=_sum("amount_due", due_date__lt=today - timedelta(days=90)),
        )
        aging = [
            {"bucket": label, "amount": str(q(aging_rows[key]))}
            for key, label in [
                ("current", "Not yet due"),
                ("d30", "1–30 days"),
                ("d60", "31–60 days"),
                ("d90", "61–90 days"),
                ("older", "90+ days"),
            ]
        ]

        # --- payment methods in the period
        methods = [
            {
                "method": r["method"],
                "label": Payment.Method(r["method"]).label,
                "count": r["n"],
                "amount": str(q(r["v"])),
            }
            for r in period_payments.order_by()
            .values("method")
            .annotate(n=Count("id"), v=Sum("amount"))
            .order_by("-v")
        ]

        ctx = {"request": request}
        overdue_list = (
            invoices.filter(status=I.CONFIRMED, amount_due__gt=0, due_date__lt=today)
            .select_related("customer", "subscription")
            .order_by("due_date")[:8]
        )
        renewals = (
            subs.filter(
                status__in=[S.ACTIVE, S.PAUSED],
                expiry_date__gte=today,
                expiry_date__lte=today + timedelta(days=30),
            )
            .select_related("customer", "plan")
            .order_by("expiry_date")[:8]
        )
        activity = Activity.objects.select_related("actor")[:12]

        return Response(
            {
                "period": {"from": date_from, "to": date_to},
                "kpis": kpis,
                "subscriptions_by_status": by_status,
                "trend": trend,
                "mrr_by_plan": by_plan,
                "aging": aging,
                "payment_methods": methods,
                "overdue_invoices": InvoiceListSerializer(
                    overdue_list, many=True, context=ctx
                ).data,
                "upcoming_renewals": SubscriptionListSerializer(
                    renewals, many=True, context=ctx
                ).data,
                "recent_activity": ActivitySerializer(activity, many=True).data,
            }
        )


def _lookup(by_month: dict, month: date):
    for key, value in by_month.items():
        key_date = key.date() if hasattr(key, "date") and callable(key.date) else key
        if key_date == month:
            return value or 0
    return 0


class CustomerReportView(APIView):
    """Top customers by recurring value and by amount owed."""

    permission_classes = [IsInternal]

    def get(self, request):
        from apps.accounts.models import Customer

        today = timezone.localdate()
        rows = (
            Customer.objects.annotate(
                active_mrr=_sum("subscriptions__mrr", subscriptions__status=S.ACTIVE),
            )
            .filter(active_mrr__gt=0)
            .order_by("-active_mrr")[:10]
        )
        owed = (
            Invoice.objects.filter(status=I.CONFIRMED, amount_due__gt=0)
            .values("customer_id", "customer__name", "customer__company")
            .annotate(
                due=Sum("amount_due"),
                overdue=_sum("amount_due", due_date__lt=today),
                invoices=Count("id"),
            )
            .order_by("-due")[:10]
        )
        return Response(
            {
                "top_by_mrr": [
                    {"customer_id": c.id, "customer": str(c), "mrr": str(q(c.active_mrr))}
                    for c in rows
                ],
                "top_by_owed": [
                    {
                        "customer_id": r["customer_id"],
                        "customer": r["customer__company"] or r["customer__name"],
                        "due": str(q(r["due"])),
                        "overdue": str(q(r["overdue"])),
                        "invoices": r["invoices"],
                    }
                    for r in owed
                ],
            }
        )


class PortalSummaryView(APIView):
    """The customer's own home page."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if role_of(request.user) != "CUSTOMER":
            raise Forbidden("The portal summary is for customers.")
        customer = getattr(request.user, "customer", None)
        today = timezone.localdate()
        subs = Subscription.objects.filter(customer=customer).exclude(status=S.DRAFT)
        invoices = Invoice.objects.filter(customer=customer).exclude(status=I.DRAFT)
        due = invoices.filter(status=I.CONFIRMED).aggregate(
            due=_sum("amount_due"),
            overdue=_sum("amount_due", due_date__lt=today),
            overdue_count=Count("id", filter=Q(due_date__lt=today, amount_due__gt=0)),
        )
        next_sub = (
            subs.filter(status=S.ACTIVE, next_invoice_date__isnull=False)
            .filter(Q(expiry_date__isnull=True) | Q(next_invoice_date__lte=F("expiry_date")))
            .order_by("next_invoice_date")
            .select_related("plan")
            .first()
        )
        ctx = {"request": request}
        return Response(
            {
                "customer": {"id": customer.id, "name": str(customer)} if customer else None,
                "active_subscriptions": subs.filter(status=S.ACTIVE).count(),
                "pending_quotations": subs.filter(status=S.QUOTATION).count(),
                "amount_due": str(q(due["due"])),
                "overdue": str(q(due["overdue"])),
                "overdue_count": due["overdue_count"],
                "next_invoice": {
                    "date": next_sub.next_invoice_date,
                    "subscription": next_sub.number,
                    "subscription_id": next_sub.id,
                    "estimate": str(next_sub.total),
                }
                if next_sub
                else None,
                "recent_invoices": InvoiceListSerializer(
                    invoices.select_related("customer", "subscription")[:5], many=True, context=ctx
                ).data,
                "subscriptions": SubscriptionListSerializer(
                    subs.select_related("customer", "plan")[:10], many=True, context=ctx
                ).data,
            }
        )
