"""Billing: invoices from subscriptions, billing runs, payments and reminders.

Guarantees
----------
* Nothing is billed twice: a partial unique index allows one live
  (non-cancelled) invoice per subscription period, and each subscription is
  billed under a row lock.
* Nothing is skipped: a run walks every period from ``next_invoice_date`` up to
  the run date, so a subscription that was missed for three months gets three
  invoices, and :func:`billing_gaps` audits the whole book for holes.
* Discounts apply themselves: every active rule whose conditions hold is put on
  the invoice, and stops once it expires or reaches its usage limit.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q
from django.utils import timezone

from apps.core.errors import Conflict, Invalid
from apps.core.mail import send_email
from apps.core.models import Sequence, log_activity
from apps.core.money import ZERO, q
from apps.core.periods import add_period
from apps.core.pricing import DiscountRule, PricedLine, apply_discounts, compute_line
from apps.subscriptions.models import Discount, Subscription
from apps.subscriptions.services import tax_rules

from .models import BillingRun, Invoice, InvoiceDiscount, InvoiceLine, Payment

logger = logging.getLogger(__name__)
I = Invoice.Status  # noqa: E741


# ---------------------------------------------------------------- periods


@dataclass
class Period:
    start: date
    end: date  # inclusive
    next_start: date
    factor: Decimal = Decimal(1)

    @property
    def prorated(self) -> bool:
        return self.factor != 1


def period_for(sub: Subscription, start: date) -> Period:
    plan = sub.plan
    next_start = add_period(
        start, plan.billing_period, plan.billing_interval, anchor_day=sub.start_date.day
    )
    end = next_start - timedelta(days=1)
    factor = Decimal(1)
    if sub.expiry_date and end > sub.expiry_date:
        full_days = (next_start - start).days
        used_days = (sub.expiry_date - start).days + 1
        factor = (Decimal(used_days) / Decimal(full_days)).quantize(Decimal("0.000001"))
        end = sub.expiry_date
    return Period(start, end, next_start, factor)


def is_billable(sub: Subscription, start: date | None) -> bool:
    return start is not None and (sub.expiry_date is None or start <= sub.expiry_date)


# ---------------------------------------------------------------- discounts


class DiscountBook:
    """Active discount rules and how often each has been used.

    Loaded once per billing run and updated in memory as invoices are made,
    so a run of thousands of invoices does not re-query usage each time.
    """

    def __init__(self, on: date):
        rules = (
            Discount.objects.filter(is_active=True)
            .filter(Q(start_date__isnull=True) | Q(start_date__lte=on))
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=on))
            .annotate(
                used=Count("applications", filter=~Q(applications__invoice__status=I.CANCELLED))
            )
            .prefetch_related("products", "subscriptions")
            .order_by("id")
        )
        self.on = on
        self.rules: list[tuple[Discount, DiscountRule, set[int]]] = []
        self.used: dict[int, int] = {}
        for d in rules:
            rule = DiscountRule(
                id=d.id,
                name=d.name,
                kind=d.kind,
                value=d.value,
                scope=d.scope,
                product_ids=frozenset(p.id for p in d.products.all()),
                min_purchase=d.min_purchase,
                min_quantity=d.min_quantity,
            )
            self.rules.append((d, rule, {s.id for s in d.subscriptions.all()}))
            self.used[d.id] = d.used

    def candidates(self, sub: Subscription) -> list[DiscountRule]:
        out = []
        for d, rule, sub_ids in self.rules:
            if sub_ids and sub.id not in sub_ids:
                continue
            if d.usage_limit is not None and self.used[d.id] >= d.usage_limit:
                continue
            out.append(rule)
        return out

    def record(self, rule_id: int) -> None:
        self.used[rule_id] += 1


# ---------------------------------------------------------------- pricing a period


@dataclass
class PricedInvoice:
    lines: list[dict] = field(default_factory=list)
    discounts: list[tuple[DiscountRule, Decimal]] = field(default_factory=list)
    untaxed: Decimal = ZERO
    discount: Decimal = ZERO
    tax: Decimal = ZERO
    total: Decimal = ZERO


def price_period(sub: Subscription, period: Period, book: DiscountBook) -> PricedInvoice:
    """Work out an invoice for one period without writing anything."""
    sub_lines = list(sub.lines.all())
    priced = [
        PricedLine(
            key=i,
            product_id=ln.product_id,
            quantity=ln.quantity,
            gross=q(ln.quantity * ln.unit_price * period.factor),
        )
        for i, ln in enumerate(sub_lines)
    ]
    applied = apply_discounts(priced, book.candidates(sub))
    result = PricedInvoice(discounts=applied)
    for ln, p in zip(sub_lines, priced, strict=True):
        calc = compute_line(
            ln.quantity,
            ln.unit_price,
            tax_rules(ln.taxes.all()),
            discount=p.discount,
            factor=period.factor,
        )
        description = ln.description
        if period.prorated:
            description += f" (prorated {period.factor * 100:.1f}%)"
        result.lines.append(
            {
                "product_id": ln.product_id,
                "description": description[:300],
                "quantity": ln.quantity,
                "unit_price": ln.unit_price,
                "gross_amount": calc.gross,
                "discount_amount": calc.discount,
                "subtotal": calc.net,
                "tax_amount": calc.tax,
                "total": calc.total,
                "taxes": calc.tax_breakdown,
            }
        )
        result.untaxed += calc.gross
        result.discount += calc.discount
        result.tax += calc.tax
        result.total += calc.total
    return result


def bill_to(customer) -> dict:
    return {
        "name": customer.name,
        "company": customer.company,
        "email": customer.email,
        "phone": customer.phone,
        "address": customer.address,
        "city": customer.city,
        "state": customer.state,
        "country": customer.country,
        "tax_id": customer.tax_id,
    }


def _create_invoice(sub, period, priced, run=None, actor=None) -> Invoice:
    term_days = sub.payment_term.due_days if sub.payment_term else 0
    invoice = Invoice.objects.create(
        subscription=sub,
        customer=sub.customer,
        invoice_date=period.start,
        due_date=period.start + timedelta(days=term_days),
        period_start=period.start,
        period_end=period.end,
        payment_term=sub.payment_term.name if sub.payment_term else "Immediate",
        bill_to=bill_to(sub.customer),
        untaxed_amount=priced.untaxed,
        discount_amount=priced.discount,
        tax_amount=priced.tax,
        total=priced.total,
        amount_due=priced.total,
        billing_run=run,
        created_by=actor,
    )
    InvoiceLine.objects.bulk_create(
        InvoiceLine(invoice=invoice, sequence=i, **line) for i, line in enumerate(priced.lines)
    )
    InvoiceDiscount.objects.bulk_create(
        InvoiceDiscount(invoice=invoice, discount_id=rule.id, name=rule.name, amount=amount)
        for rule, amount in priced.discounts
    )
    return invoice


def bill_next_period(
    sub: Subscription,
    book: DiscountBook | None = None,
    run=None,
    actor=None,
    confirm_now: bool = False,
) -> Invoice:
    """Invoice the subscription's next period and move its billing date on.

    Runs in its own transaction with the subscription row locked, so two
    billing runs (or a run and a click on "Invoice now") cannot both bill the
    same period; the partial unique index is the last line of defence.
    """
    with transaction.atomic():
        sub = (
            Subscription.objects.select_for_update()
            .select_related("plan", "customer", "payment_term")
            .get(pk=sub.pk)
        )
        if sub.status != Subscription.Status.ACTIVE:
            raise Conflict(
                f"{sub.number} is {sub.get_status_display()}, not active.", code="invalid_state"
            )
        if not is_billable(sub, sub.next_invoice_date):
            raise Conflict(f"{sub.number} is fully billed up to its end date.", code="fully_billed")
        sub = (
            Subscription.objects.prefetch_related("lines__taxes")
            .select_related("plan", "customer", "payment_term")
            .get(pk=sub.pk)
        )
        period = period_for(sub, sub.next_invoice_date)
        book = book or DiscountBook(period.start)
        priced = price_period(sub, period, book)
        try:
            with transaction.atomic():
                invoice = _create_invoice(sub, period, priced, run, actor)
        except IntegrityError:
            raise Conflict(
                f"{sub.number} already has an invoice for the period starting "
                f"{period.start:%d %b %Y}.",
                code="already_billed",
            ) from None
        for rule, _ in priced.discounts:
            book.record(rule.id)
        Subscription.objects.filter(pk=sub.pk).update(next_invoice_date=period.next_start)
        discounts = ", ".join(r.name for r, _ in priced.discounts)
        log_activity(
            "invoice",
            invoice.id,
            "created",
            f"Draft invoice for {sub.number}, {period.start:%d %b} – {period.end:%d %b %Y}"
            + (f"; discounts applied: {discounts}" if discounts else ""),
            actor,
            subscription=sub.id,
        )
        log_activity(
            "subscription",
            sub.id,
            "invoiced",
            f"Invoiced {period.start:%d %b} – {period.end:%d %b %Y}: {invoice.total}",
            actor,
            invoice=invoice.id,
        )
        if confirm_now:
            invoice = confirm_invoice(invoice, actor)
    return invoice


# ---------------------------------------------------------------- billing run


def due_subscriptions(as_of: date):
    return (
        Subscription.objects.filter(status=Subscription.Status.ACTIVE, next_invoice_date__lte=as_of)
        .filter(Q(expiry_date__isnull=True) | Q(next_invoice_date__lte=F("expiry_date")))
        .order_by("next_invoice_date", "id")
    )


def preview_billing(as_of: date, limit: int = 500) -> dict:
    """Dry run: what a billing run on ``as_of`` would invoice. Writes nothing."""
    book = DiscountBook(as_of)
    rows, total, count, subs = [], ZERO, 0, 0
    qs = (
        due_subscriptions(as_of).select_related("plan", "customer").prefetch_related("lines__taxes")
    )
    for sub in qs.iterator(chunk_size=500):
        subs += 1
        start = sub.next_invoice_date
        while is_billable(sub, start) and start <= as_of:
            period = period_for(sub, start)
            priced = price_period(sub, period, book)
            for rule, _ in priced.discounts:
                book.record(rule.id)
            count += 1
            total += priced.total
            if len(rows) < limit:
                rows.append(
                    {
                        "subscription_id": sub.id,
                        "subscription": sub.number,
                        "customer": str(sub.customer),
                        "plan": sub.plan.name,
                        "period_start": period.start,
                        "period_end": period.end,
                        "discount": priced.discount,
                        "total": priced.total,
                        "discounts": [r.name for r, _ in priced.discounts],
                        "prorated": period.prorated,
                    }
                )
            start = period.next_start
    return {
        "as_of": as_of,
        "subscriptions": subs,
        "invoices": count,
        "total": total,
        "rows": rows,
        "truncated": count > len(rows),
    }


def run_billing(
    as_of: date | None = None,
    *,
    actor=None,
    trigger=BillingRun.Trigger.MANUAL,
    auto_confirm: bool = True,
    auto_send: bool = False,
) -> BillingRun:
    """Invoice every active subscription that is due on or before ``as_of``."""
    as_of = as_of or timezone.localdate()
    started = time.perf_counter()
    run = BillingRun.objects.create(
        as_of=as_of,
        trigger=trigger,
        triggered_by=actor,
        auto_confirm=auto_confirm,
        auto_send=auto_send,
    )
    book = DiscountBook(as_of)
    processed, created, total, errors = 0, 0, ZERO, []
    for sub_id in list(due_subscriptions(as_of).values_list("id", flat=True)):
        processed += 1
        sub = Subscription(pk=sub_id)
        while True:
            current = Subscription.objects.only(
                "id", "status", "next_invoice_date", "expiry_date"
            ).get(pk=sub_id)
            if current.status != Subscription.Status.ACTIVE or not (
                is_billable(current, current.next_invoice_date)
                and current.next_invoice_date <= as_of
            ):
                break
            try:
                invoice = bill_next_period(sub, book, run, actor, confirm_now=auto_confirm)
            except Exception as exc:  # one bad subscription must not stop the run
                logger.exception("Billing failed for subscription %s", sub_id)
                errors.append({"subscription_id": sub_id, "error": str(exc)[:300]})
                break
            created += 1
            total += invoice.total
            if auto_send and invoice.status != I.DRAFT:
                try:
                    send_invoice(invoice, actor)
                except Exception as exc:
                    errors.append({"invoice_id": invoice.id, "error": f"send: {exc}"[:300]})
    run.subscriptions_processed = processed
    run.invoices_created = created
    run.total_amount = total
    run.errors = errors
    run.duration_ms = int((time.perf_counter() - started) * 1000)
    run.save()
    log_activity(
        "billing_run",
        run.id,
        "completed",
        f"Billing run for {as_of:%d %b %Y}: {created} invoices, {total}",
        actor,
    )
    return run


def billing_gaps(limit: int = 200) -> list[dict]:
    """Audit: periods between a subscription's start and its next billing date
    that have no live invoice. A healthy book returns an empty list.

    Periods that fell inside a pause are not gaps: billing restarts after a
    resume, so the walk jumps to the first period billed after the pause.
    """
    from apps.core.models import Activity

    live: dict[int, set[date]] = {}
    for sub_id, start in (
        Invoice.objects.filter(subscription__isnull=False)
        .exclude(status=I.CANCELLED)
        .values_list("subscription_id", "period_start")
    ):
        live.setdefault(sub_id, set()).add(start)
    pauses: dict[int, list[tuple[date, date]]] = {}
    for sub_id, data in Activity.objects.filter(entity="subscription", verb="resumed").values_list(
        "entity_id", "data"
    ):
        if data.get("paused_on") and data.get("resumed_on"):
            pauses.setdefault(sub_id, []).append(
                (date.fromisoformat(data["paused_on"]), date.fromisoformat(data["resumed_on"]))
            )

    gaps: list[dict] = []
    subs = Subscription.objects.filter(
        status__in=[
            Subscription.Status.ACTIVE,
            Subscription.Status.PAUSED,
            Subscription.Status.CLOSED,
        ],
        next_invoice_date__isnull=False,
    ).select_related("plan", "customer")
    for sub in subs.iterator(chunk_size=1000):
        billed = live.get(sub.id, set())
        start = sub.start_date
        while start < sub.next_invoice_date and is_billable(sub, start):
            if start in billed:
                start = period_for(sub, start).next_start
                continue
            window = next(
                (
                    w
                    for w in pauses.get(sub.id, [])
                    if w[0] <= period_for(sub, start).end and start < w[1]
                ),
                None,
            )
            if window:
                later = sorted(d for d in billed if d >= window[1])
                start = later[0] if later else sub.next_invoice_date
                continue
            period = period_for(sub, start)
            gaps.append(
                {
                    "subscription_id": sub.id,
                    "subscription": sub.number,
                    "customer": str(sub.customer),
                    "period_start": period.start,
                    "period_end": period.end,
                }
            )
            if len(gaps) >= limit:
                return gaps
            start = period.next_start
    return gaps


# ---------------------------------------------------------------- invoice actions


def _lock_invoice(invoice: Invoice) -> Invoice:
    return Invoice.objects.select_for_update().get(pk=invoice.pk)


@transaction.atomic
def confirm_invoice(invoice: Invoice, actor=None) -> Invoice:
    invoice = _lock_invoice(invoice)
    if invoice.status != I.DRAFT:
        raise Conflict(
            f"Only draft invoices can be confirmed ({invoice} is {invoice.get_status_display()}).",
            code="invalid_state",
        )
    year = invoice.invoice_date.year
    invoice.number = Sequence.next(f"invoice-{year}", f"INV/{year}/")
    invoice.status = I.CONFIRMED
    invoice.confirmed_at = timezone.now()
    if invoice.total <= 0:
        invoice.status = I.PAID
        invoice.paid_at = timezone.now()
    invoice.save()
    log_activity("invoice", invoice.id, "confirmed", f"Invoice {invoice.number} confirmed", actor)
    return invoice


@transaction.atomic
def cancel_invoice(invoice: Invoice, actor=None, reason: str = "") -> Invoice:
    invoice = _lock_invoice(invoice)
    if invoice.status not in (I.DRAFT, I.CONFIRMED):
        raise Conflict(
            f"{invoice.get_status_display()} invoices cannot be cancelled.", code="invalid_state"
        )
    if invoice.amount_paid > 0:
        raise Conflict(
            "This invoice has payments recorded against it; it cannot be cancelled.",
            code="has_payments",
        )
    invoice.status = I.CANCELLED
    invoice.cancelled_at = timezone.now()
    invoice.cancel_reason = reason[:200]
    invoice.amount_due = ZERO
    invoice.save()
    log_activity(
        "invoice",
        invoice.id,
        "cancelled",
        f"Invoice {invoice.display_number} cancelled" + (f": {reason}" if reason else ""),
        actor,
    )
    return invoice


@transaction.atomic
def rebill_period(invoice: Invoice, actor=None) -> Invoice:
    """Re-issue a cancelled subscription invoice for the same period, with the
    subscription's current lines (e.g. after correcting a quantity)."""
    if invoice.status != I.CANCELLED or invoice.subscription_id is None:
        raise Invalid("Only a cancelled subscription invoice can be re-billed.")
    sub = (
        Subscription.objects.select_for_update()
        .prefetch_related("lines__taxes")
        .select_related("plan", "customer", "payment_term")
        .get(pk=invoice.subscription_id)
    )
    period = period_for(sub, invoice.period_start)
    book = DiscountBook(period.start)
    priced = price_period(sub, period, book)
    try:
        with transaction.atomic():
            new = _create_invoice(sub, period, priced, actor=actor)
    except IntegrityError:
        raise Conflict("That period already has a live invoice.", code="already_billed") from None
    log_activity(
        "invoice",
        new.id,
        "created",
        f"Re-billed {period.start:%d %b} – {period.end:%d %b %Y} "
        f"(replaces {invoice.display_number})",
        actor,
    )
    return new


def _money(amount) -> str:
    return f"{settings.COMPANY['currency_symbol']}{amount:,.2f}"


def send_invoice(invoice: Invoice, actor=None) -> Invoice:
    from .pdf import invoice_pdf

    if invoice.status not in (I.CONFIRMED, I.PAID):
        raise Conflict("Confirm the invoice before sending it.", code="invalid_state")
    link = f"{settings.FRONTEND_URL}/portal/invoices/{invoice.id}"
    status_line = (
        "This invoice is paid in full — thank you!"
        if invoice.status == I.PAID
        else f"Amount due: {_money(invoice.amount_due)} by {invoice.due_date:%d %b %Y}."
    )
    send_email(
        invoice.customer.email,
        f"Invoice {invoice.number} from {settings.COMPANY['name']}",
        f"Hi {invoice.customer.name},\n\nPlease find invoice {invoice.number} attached.\n"
        f"{status_line}\n\nView and pay online: {link}\n",
        category="invoice",
        attachments=[
            (f"{invoice.number.replace('/', '-')}.pdf", invoice_pdf(invoice), "application/pdf")
        ],
    )
    Invoice.objects.filter(pk=invoice.pk).update(
        sent_at=timezone.now(), sent_count=F("sent_count") + 1
    )
    invoice.refresh_from_db()
    log_activity(
        "invoice",
        invoice.id,
        "sent",
        f"Invoice {invoice.number} emailed to {invoice.customer.email}",
        actor,
    )
    return invoice


# ---------------------------------------------------------------- payments


@transaction.atomic
def record_payment(
    invoice: Invoice,
    *,
    amount: Decimal,
    method: str,
    payment_date: date | None,
    note: str = "",
    reference: str = "",
    actor=None,
    source=Payment.Source.MANUAL,
) -> Payment:
    invoice = _lock_invoice(invoice)
    amount = q(amount)
    if invoice.status != I.CONFIRMED:
        raise Conflict(
            {
                I.DRAFT: "Confirm the invoice before recording a payment.",
                I.PAID: "This invoice is already paid in full.",
                I.CANCELLED: "Payments cannot be recorded on a cancelled invoice.",
            }[invoice.status],
            code="invalid_state",
        )
    if amount <= 0:
        raise Invalid("Payment amount must be more than zero.", fields={"amount": "Must be > 0"})
    if amount > invoice.amount_due:
        raise Invalid(
            f"Payment of {amount} is more than the {invoice.amount_due} still due.",
            code="overpayment",
            fields={"amount": "More than the amount due"},
        )
    payment_date = payment_date or timezone.localdate()
    if payment_date > timezone.localdate():
        raise Invalid("Payment date cannot be in the future.")
    if method not in Payment.Method.values:
        raise Invalid("Unknown payment method.", fields={"method": "Unknown"})
    payment = Payment.objects.create(
        invoice=invoice,
        customer_id=invoice.customer_id,
        method=method,
        amount=amount,
        payment_date=payment_date,
        note=note[:300],
        reference=reference[:100],
        recorded_by=actor,
        source=source,
    )
    invoice.amount_paid += amount
    invoice.amount_due = invoice.total - invoice.amount_paid
    if invoice.amount_due <= 0:
        invoice.amount_due = ZERO
        invoice.status = I.PAID
        invoice.paid_at = timezone.now()
    invoice.save()
    label = Payment.Method(method).label
    log_activity(
        "invoice",
        invoice.id,
        "payment",
        f"{_money(amount)} received by {label}"
        + (
            " — paid in full"
            if invoice.status == I.PAID
            else f"; {_money(invoice.amount_due)} still due"
        ),
        actor,
        payment=payment.id,
    )
    transaction.on_commit(lambda: _send_receipt(payment))
    return payment


def _send_receipt(payment: Payment) -> None:
    inv = payment.invoice
    send_email(
        inv.customer.email,
        f"Payment received for {inv.number}",
        f"Hi {inv.customer.name},\n\nWe received {_money(payment.amount)} by "
        f"{payment.get_method_display()} on {payment.payment_date:%d %b %Y} for invoice "
        f"{inv.number}.\n"
        + (
            "The invoice is now paid in full. Thank you!\n"
            if inv.status == I.PAID
            else f"Remaining balance: {_money(inv.amount_due)}.\n"
        ),
        category="receipt",
    )


# ---------------------------------------------------------------- dunning


def overdue_invoices(as_of: date | None = None):
    as_of = as_of or timezone.localdate()
    return Invoice.objects.filter(status=I.CONFIRMED, amount_due__gt=0, due_date__lt=as_of)


def send_overdue_reminders(as_of: date | None = None) -> int:
    """Email a reminder for each overdue invoice, at most once per interval."""
    as_of = as_of or timezone.localdate()
    cutoff = timezone.now() - timedelta(days=settings.DUNNING_INTERVAL_DAYS)
    qs = (
        overdue_invoices(as_of)
        .filter(Q(last_reminder_at__isnull=True) | Q(last_reminder_at__lt=cutoff))
        .select_related("customer")
    )
    sent = 0
    for inv in qs.iterator(chunk_size=500):
        days = (as_of - inv.due_date).days
        send_email(
            inv.customer.email,
            f"Reminder: invoice {inv.number} is {days} days overdue",
            f"Hi {inv.customer.name},\n\nInvoice {inv.number} for {_money(inv.total)} was due on "
            f"{inv.due_date:%d %b %Y}. {_money(inv.amount_due)} is still outstanding.\n\n"
            f"Pay online: {settings.FRONTEND_URL}/portal/invoices/{inv.id}\n",
            category="reminder",
        )
        Invoice.objects.filter(pk=inv.pk).update(
            reminder_count=F("reminder_count") + 1, last_reminder_at=timezone.now()
        )
        log_activity(
            "invoice",
            inv.id,
            "reminder",
            f"Overdue reminder #{inv.reminder_count + 1} sent ({days} days late)",
        )
        sent += 1
    return sent


def run_daily_jobs(as_of: date | None = None, actor=None) -> dict:
    """Everything that should happen every day, in order."""
    from apps.subscriptions.services import activate_due, close_expired

    as_of = as_of or timezone.localdate()
    activated = activate_due(as_of, actor)
    run = run_billing(
        as_of, actor=actor, trigger=BillingRun.Trigger.SCHEDULED, auto_confirm=True, auto_send=True
    )
    closed = close_expired(as_of)
    reminders = send_overdue_reminders(as_of)
    return {
        "activated": activated,
        "billing_run": run.id,
        "invoices": run.invoices_created,
        "closed": closed,
        "reminders": reminders,
    }
