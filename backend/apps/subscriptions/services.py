"""Subscription lifecycle: Draft → Quotation → Confirmed → Active (⇄ Paused) → Closed.

Every transition is a function here. Each one locks the row, checks the
current state and the plan's rules, writes, and records an Activity entry.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Customer
from apps.catalog.models import PaymentTerm, Product, ProductVariant, RecurringPlan, Tax
from apps.core.errors import Conflict, Forbidden, Invalid
from apps.core.mail import send_email
from apps.core.models import Sequence, log_activity
from apps.core.money import ZERO, q
from apps.core.periods import add_months, monthly_factor
from apps.core.pricing import TaxRule, compute_line

from .models import QuotationTemplate, Subscription, SubscriptionLine

S = Subscription.Status


def tax_rules(taxes) -> list[TaxRule]:
    return [TaxRule(t.id, t.name, t.computation, t.amount) for t in taxes]


def _lock(sub: Subscription) -> Subscription:
    return (
        Subscription.objects.select_for_update().select_related("plan", "customer").get(pk=sub.pk)
    )


def _require(sub: Subscription, *allowed: str, action: str) -> None:
    if sub.status not in allowed:
        labels = ", ".join(S(a).label for a in allowed)
        raise Conflict(
            f"Cannot {action} a subscription that is {sub.get_status_display()} "
            f"(must be {labels}).",
            code="invalid_state",
        )


# ---------------------------------------------------------------- lines & totals


def recompute_totals(sub: Subscription) -> None:
    untaxed = tax = ZERO
    for line in sub.lines.prefetch_related("taxes"):
        result = compute_line(line.quantity, line.unit_price, tax_rules(line.taxes.all()))
        line.subtotal, line.tax_amount, line.total = result.net, result.tax, result.total
        line.save(update_fields=["subtotal", "tax_amount", "total"])
        untaxed += result.net
        tax += result.tax
    sub.untaxed_amount, sub.tax_amount, sub.total = untaxed, tax, untaxed + tax
    sub.mrr = q(untaxed * monthly_factor(sub.plan.billing_period, sub.plan.billing_interval))
    sub.save(update_fields=["untaxed_amount", "tax_amount", "total", "mrr", "updated_at"])


def _plan_fee_line(plan: RecurringPlan, quantity: Decimal | None = None) -> dict:
    return {
        "product": None,
        "variant": None,
        "description": f"{plan.name} plan ({plan.billing_label})",
        "quantity": quantity if quantity is not None else max(plan.min_quantity, Decimal(1)),
        "unit_price": plan.price,
        "taxes": list(plan.taxes.filter(is_active=True)),
    }


def _normalise_line(raw: dict) -> dict:
    """Fill in defaults from the product / variant and validate a line."""
    product = raw.get("product")
    variant = raw.get("variant")
    if isinstance(product, int):
        product = Product.objects.filter(pk=product).first()
    if isinstance(variant, int):
        variant = ProductVariant.objects.filter(pk=variant).first()
    quantity = Decimal(raw.get("quantity") or 0)
    if quantity <= 0:
        raise Invalid("Quantity must be more than zero.", fields={"quantity": "Must be > 0"})
    if variant is not None and (product is None or variant.product_id != product.id):
        raise Invalid("The variant does not belong to this product.")
    if product is not None and not product.is_active:
        raise Invalid(f"{product.name} is archived and cannot be sold.")

    unit_price = raw.get("unit_price")
    if unit_price in (None, ""):
        if product is None:
            raise Invalid("A line without a product needs a unit price.")
        unit_price = product.sales_price + (variant.extra_price if variant else ZERO)
    unit_price = q(unit_price)
    if unit_price < 0:
        raise Invalid("Unit price cannot be negative.")

    taxes = raw.get("taxes")
    if taxes is None:
        taxes = list(product.taxes.filter(is_active=True)) if product else []
    else:
        taxes = [t if isinstance(t, Tax) else Tax.objects.get(pk=t) for t in taxes]

    description = (raw.get("description") or "").strip()
    if not description:
        description = product.name if product else "Service"
        if variant:
            description += f" ({variant.attribute}: {variant.value})"
    return {
        "product": product,
        "variant": variant,
        "description": description[:300],
        "quantity": quantity,
        "unit_price": unit_price,
        "taxes": taxes,
    }


def replace_lines(sub: Subscription, raw_lines: list[dict]) -> None:
    lines = [_normalise_line(raw) for raw in raw_lines]
    sub.lines.all().delete()
    for i, data in enumerate(lines):
        taxes = data.pop("taxes")
        line = SubscriptionLine.objects.create(subscription=sub, sequence=i, **data)
        line.taxes.set(taxes)
    recompute_totals(sub)


# ---------------------------------------------------------------- create / edit


@transaction.atomic
def create_subscription(
    *,
    customer: Customer,
    plan: RecurringPlan,
    start_date: date,
    lines: list[dict] | None = None,
    template: QuotationTemplate | None = None,
    expiry_date: date | None = None,
    payment_term: PaymentTerm | None = None,
    salesperson=None,
    notes: str = "",
    terms: str = "",
    actor=None,
) -> Subscription:
    """Create a draft. Starting from a quotation template copies its plan
    lines, payment terms, validity and default contract length."""
    raw_lines: list[dict] = list(lines or [])
    if template is not None:
        plan = template.plan
        payment_term = payment_term or template.payment_term
        if expiry_date is None and template.duration_months:
            expiry_date = add_months(start_date, template.duration_months) - timedelta(days=1)
        terms = terms or template.notes
        if not raw_lines:
            raw_lines = [
                {
                    "product": tl.product,
                    "variant": tl.variant,
                    "quantity": tl.quantity,
                    "description": tl.description,
                }
                for tl in template.lines.select_related("product", "variant")
            ]
    if expiry_date is not None and expiry_date < start_date:
        raise Invalid(
            "Expiry date must be on or after the start date.",
            fields={"expiry_date": "Before start date"},
        )
    if not plan.is_active:
        raise Invalid(f"Plan {plan.name} is archived.")

    has_plan_line = any(raw.get("product") in (None, "") for raw in raw_lines)
    if plan.price > 0 and not has_plan_line:
        raw_lines.insert(0, _plan_fee_line(plan))

    sub = Subscription.objects.create(
        number=Sequence.next("subscription", "SUB/"),
        customer=customer,
        plan=plan,
        template=template,
        start_date=start_date,
        expiry_date=expiry_date,
        payment_term=payment_term,
        salesperson=salesperson or (actor if getattr(actor, "is_internal", False) else None),
        notes=notes,
        terms=terms,
        created_by=actor,
    )
    replace_lines(sub, raw_lines)
    origin = f" from template {template.name}" if template else ""
    log_activity("subscription", sub.id, "created", f"{sub.number} created as draft{origin}", actor)
    return sub


@transaction.atomic
def update_subscription(sub: Subscription, data: dict, lines: list[dict] | None, actor=None):
    sub = _lock(sub)
    if not sub.is_editable:
        raise Conflict(
            "Only draft and quotation subscriptions can be edited. Confirmed "
            "subscriptions change through pause, renew or close.",
            code="not_editable",
        )
    for field in (
        "customer",
        "plan",
        "start_date",
        "expiry_date",
        "payment_term",
        "salesperson",
        "notes",
        "terms",
    ):
        if field in data:
            setattr(sub, field, data[field])
    if sub.expiry_date and sub.expiry_date < sub.start_date:
        raise Invalid("Expiry date must be on or after the start date.")
    sub.save()
    if lines is not None:
        replace_lines(sub, lines)
    else:
        recompute_totals(sub)
    log_activity("subscription", sub.id, "updated", f"{sub.number} updated", actor)
    return sub


# ---------------------------------------------------------------- transitions


def _check_ready_to_confirm(sub: Subscription) -> None:
    plan = sub.plan
    lines = list(sub.lines.all())
    if not lines:
        raise Invalid("Add at least one line before confirming.")
    total_qty = sum((ln.quantity for ln in lines), Decimal(0))
    if total_qty < plan.min_quantity:
        raise Invalid(
            f"The {plan.name} plan needs a minimum quantity of {plan.min_quantity:g} "
            f"(this subscription has {total_qty:g}).",
            code="below_min_quantity",
        )
    if not plan.is_available_on(sub.start_date):
        window = f"{plan.start_date:%d %b %Y}" + (
            f" – {plan.end_date:%d %b %Y}" if plan.end_date else " onwards"
        )
        raise Invalid(
            f"The {plan.name} plan is not available on {sub.start_date:%d %b %Y} "
            f"(available {window}).",
            code="plan_unavailable",
        )


@transaction.atomic
def send_quotation(sub: Subscription, actor=None, email: bool = True) -> Subscription:
    sub = _lock(sub)
    _require(sub, S.DRAFT, S.QUOTATION, action="send a quotation for")
    _check_ready_to_confirm(sub)
    validity = sub.template.validity_days if sub.template else 30
    sub.status = S.QUOTATION
    sub.quotation_sent_at = timezone.now()
    sub.quotation_valid_until = timezone.localdate() + timedelta(days=validity)
    sub.save()
    if email:
        link = f"{settings.FRONTEND_URL}/portal/subscriptions/{sub.id}"
        send_email(
            sub.customer.email,
            f"Quotation {sub.number} from {settings.COMPANY['name']}",
            f"Hi {sub.customer.name},\n\nYour quotation {sub.number} for the {sub.plan.name} "
            f"plan is ready: {sub.total} {settings.COMPANY['currency']} {sub.plan.billing_label}."
            f"\nIt is valid until {sub.quotation_valid_until:%d %b %Y}.\n\n"
            f"Review and accept it online: {link}\n",
            category="quotation",
        )
    log_activity(
        "subscription",
        sub.id,
        "quotation_sent",
        f"Quotation sent, valid until {sub.quotation_valid_until:%d %b %Y}",
        actor,
    )
    return sub


def _activate(sub: Subscription, actor=None) -> None:
    sub.status = S.ACTIVE
    sub.activated_at = timezone.now()
    if sub.next_invoice_date is None:
        sub.next_invoice_date = sub.start_date
    sub.save()
    log_activity("subscription", sub.id, "activated", f"{sub.number} is now active", actor)


@transaction.atomic
def confirm(sub: Subscription, actor=None, accepted_by_name: str = "") -> Subscription:
    sub = _lock(sub)
    _require(sub, S.QUOTATION, action="confirm")
    if sub.quotation_expired:
        raise Conflict(
            "This quotation has expired. Send a fresh quotation first.", code="quotation_expired"
        )
    _check_ready_to_confirm(sub)
    sub.status = S.CONFIRMED
    sub.confirmed_at = timezone.now()
    if accepted_by_name:
        sub.accepted_by_name = accepted_by_name[:150]
        sub.accepted_at = timezone.now()
    sub.save()
    who = f" (accepted online by {accepted_by_name})" if accepted_by_name else ""
    log_activity("subscription", sub.id, "confirmed", f"{sub.number} confirmed{who}", actor)
    if sub.start_date <= timezone.localdate():
        _activate(sub, actor)
    return sub


@transaction.atomic
def activate(sub: Subscription, actor=None) -> Subscription:
    sub = _lock(sub)
    _require(sub, S.CONFIRMED, action="activate")
    _activate(sub, actor)
    return sub


@transaction.atomic
def pause(sub: Subscription, actor=None) -> Subscription:
    from apps.invoicing.services import bill_owed_periods

    sub = _lock(sub)
    _require(sub, S.ACTIVE, action="pause")
    if not sub.plan.pausable:
        raise Forbidden(f"The {sub.plan.name} plan cannot be paused.", code="plan_not_pausable")
    # Periods that started before the pause are owed: bill them now, so that a
    # resume only skips time actually spent paused.
    bill_owed_periods(sub, timezone.localdate(), actor)
    sub = _lock(sub)
    sub.status = S.PAUSED
    sub.paused_at = timezone.localdate()
    sub.save()
    log_activity("subscription", sub.id, "paused", f"{sub.number} paused; billing stops", actor)
    return sub


@transaction.atomic
def resume(sub: Subscription, actor=None) -> Subscription:
    sub = _lock(sub)
    _require(sub, S.PAUSED, action="resume")
    today = timezone.localdate()
    sub.status = S.ACTIVE
    paused_on = sub.paused_at or today
    # Periods while paused are not billed; billing picks up from today.
    if sub.next_invoice_date is None or sub.next_invoice_date < today:
        sub.next_invoice_date = today
    sub.paused_at = None
    sub.save()
    log_activity(
        "subscription",
        sub.id,
        "resumed",
        f"{sub.number} resumed; next invoice {sub.next_invoice_date:%d %b %Y}",
        actor,
        paused_on=paused_on.isoformat(),
        resumed_on=today.isoformat(),
    )
    return sub


@transaction.atomic
def close(sub: Subscription, actor=None, reason: str = "", automatic: bool = False):
    sub = _lock(sub)
    _require(sub, S.DRAFT, S.QUOTATION, S.CONFIRMED, S.ACTIVE, S.PAUSED, action="close")
    early = sub.status in (S.ACTIVE, S.PAUSED, S.CONFIRMED) and not sub.is_expired
    if early and not automatic and not sub.plan.closable:
        raise Forbidden(
            f"The {sub.plan.name} plan cannot be closed before it ends"
            + (f" on {sub.expiry_date:%d %b %Y}." if sub.expiry_date else "."),
            code="plan_not_closable",
        )
    sub.status = S.CLOSED
    sub.closed_at = timezone.localdate()
    sub.close_reason = (reason or ("Expired" if automatic else "Closed"))[:200]
    sub.save()
    log_activity(
        "subscription", sub.id, "closed", f"{sub.number} closed: {sub.close_reason}", actor
    )
    return sub


@transaction.atomic
def renew(sub: Subscription, actor=None) -> Subscription:
    """Extend the contract by its original length and keep billing."""
    sub = _lock(sub)
    reopened = sub.status == S.CLOSED and sub.close_reason == "Expired"
    if not reopened:
        _require(sub, S.ACTIVE, S.PAUSED, action="renew")
    if not sub.plan.renewable:
        raise Forbidden(f"The {sub.plan.name} plan cannot be renewed.", code="plan_not_renewable")
    if sub.expiry_date is None:
        raise Invalid("This subscription has no end date, so it renews by itself.")
    term = (sub.expiry_date - sub.start_date).days + 1
    old = sub.expiry_date
    sub.expiry_date = old + timedelta(days=term)
    sub.renewal_count += 1
    if reopened:
        sub.status = S.ACTIVE
        sub.closed_at = None
        sub.close_reason = ""
    sub.save()
    log_activity(
        "subscription",
        sub.id,
        "renewed",
        f"{sub.number} renewed until {sub.expiry_date:%d %b %Y}",
        actor,
    )
    return sub


@transaction.atomic
def duplicate(sub: Subscription, actor=None) -> Subscription:
    lines = [
        {
            "product": ln.product,
            "variant": ln.variant,
            "description": ln.description,
            "quantity": ln.quantity,
            "unit_price": ln.unit_price,
            "taxes": list(ln.taxes.all()),
        }
        for ln in sub.lines.select_related("product", "variant").prefetch_related("taxes")
    ]
    today = timezone.localdate()
    return create_subscription(
        customer=sub.customer,
        plan=sub.plan,
        start_date=max(today, sub.start_date),
        lines=lines,
        payment_term=sub.payment_term,
        notes=f"Copied from {sub.number}",
        terms=sub.terms,
        actor=actor,
    )


# ---------------------------------------------------------------- daily housekeeping


def activate_due(as_of: date, actor=None) -> int:
    count = 0
    for sub in Subscription.objects.filter(status=S.CONFIRMED, start_date__lte=as_of):
        activate(sub, actor)
        count += 1
    return count


def close_expired(as_of: date) -> int:
    """Close subscriptions on auto-close plans once their last period is billed."""
    count = 0
    candidates = Subscription.objects.filter(
        status__in=[S.ACTIVE, S.PAUSED], plan__auto_close=True, expiry_date__lt=as_of
    )
    for sub in candidates:
        close(sub, reason="Expired", automatic=True)
        count += 1
    return count
