from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.core.errors import Conflict
from apps.core.models import OutboundEmail
from apps.invoicing import services as billing
from apps.invoicing.models import Invoice, InvoiceLine
from apps.subscriptions import services as subs
from apps.subscriptions.models import Discount

from .conftest import make_plan

I = Invoice.Status  # noqa: E741


def test_invoice_is_filled_in_from_the_subscription(make_active, customer, today, net15):
    sub = make_active(qty=Decimal(3))
    run = billing.run_billing(today)
    assert run.invoices_created == 1
    inv = Invoice.objects.get(subscription=sub)
    assert inv.status == I.CONFIRMED and inv.number.startswith(f"INV/{today.year}/")
    assert inv.bill_to["email"] == customer.email
    assert inv.period_start == today
    assert inv.due_date == today + timedelta(days=net15.due_days)
    line = inv.lines.get()
    assert line.quantity == 3 and line.unit_price == Decimal("1000")
    assert line.taxes[0]["name"] == "GST 18%"
    assert inv.untaxed_amount == Decimal("3000") and inv.tax_amount == Decimal("540")
    assert inv.total == inv.amount_due == Decimal("3540")


def test_nothing_billed_twice(make_active, today):
    make_active()
    assert billing.run_billing(today).invoices_created == 1
    assert billing.run_billing(today).invoices_created == 0
    assert Invoice.objects.count() == 1


def test_database_refuses_a_second_live_invoice_for_a_period(make_active, today):
    sub = make_active()
    billing.run_billing(today)
    inv = Invoice.objects.get()
    with pytest.raises(IntegrityError), transaction.atomic():
        Invoice.objects.create(
            subscription=sub, customer=sub.customer, due_date=today, period_start=inv.period_start
        )


def test_nothing_skipped_when_billing_catches_up(make_active, today):
    sub = make_active(start=today - timedelta(days=95))
    run = billing.run_billing(today)
    assert run.invoices_created == 4  # four monthly periods have started
    starts = sorted(Invoice.objects.filter(subscription=sub).values_list("period_start", flat=True))
    for previous, current in zip(starts, starts[1:], strict=False):
        assert current > previous
    assert billing.billing_gaps() == []


def test_numbers_are_sequential(make_active, today):
    for _ in range(3):
        make_active()
    billing.run_billing(today)
    numbers = sorted(Invoice.objects.values_list("number", flat=True))
    assert [n[-5:] for n in numbers] == ["00001", "00002", "00003"]


def test_last_period_is_prorated_at_expiry(make_active, today):
    start = today.replace(day=1) - timedelta(days=1)
    start = start.replace(day=1)  # first day of last month
    sub = make_active(start=start, expiry=start + timedelta(days=44))
    billing.run_billing(today)
    invoices = list(Invoice.objects.filter(subscription=sub).order_by("period_start"))
    assert len(invoices) == 2
    second = invoices[1]
    assert second.period_end == sub.expiry_date
    assert "prorated" in second.lines.get().description
    assert second.untaxed_amount < invoices[0].untaxed_amount
    # Fully billed: nothing more to do.
    assert billing.run_billing(today + timedelta(days=60)).invoices_created == 0


def test_paused_subscription_is_not_billed(make_active, today):
    sub = make_active()
    subs.pause(sub)
    assert billing.run_billing(today + timedelta(days=40)).invoices_created == 0


def test_discount_applies_by_itself_and_respects_usage_limit(
    make_active, product, admin_user, today
):
    rule = Discount.objects.create(
        name="Volume 10%",
        kind="PERCENT",
        value=Decimal("10"),
        scope="PRODUCTS",
        min_quantity=Decimal("20"),
        usage_limit=2,
        created_by=admin_user,
    )
    rule.products.set([product])
    small = make_active(qty=Decimal(5))
    big = make_active(qty=Decimal(25), start=today - timedelta(days=70))
    billing.run_billing(today)
    assert not Invoice.objects.get(subscription=small).applied_discounts.exists()
    big_invoices = list(Invoice.objects.filter(subscription=big).order_by("period_start"))
    assert len(big_invoices) == 3
    discounted = [inv for inv in big_invoices if inv.applied_discounts.exists()]
    assert len(discounted) == 2  # usage limit reached; third invoice is full price
    first = discounted[0]
    assert first.discount_amount == Decimal("2500.00")
    assert first.tax_amount == Decimal("4050.00")  # tax on 22,500 after discount


def test_discount_stops_after_end_date(make_active, product, today):
    rule = Discount.objects.create(
        name="Old promo",
        kind="FIXED",
        value=Decimal("100"),
        scope="SUBSCRIPTION",
        end_date=today - timedelta(days=1),
    )
    make_active()
    billing.run_billing(today)
    assert not Invoice.objects.get().applied_discounts.filter(discount=rule).exists()


def test_discount_limited_to_chosen_subscriptions(make_active, today):
    target = make_active()
    other = make_active()
    rule = Discount.objects.create(
        name="Loyalty", kind="PERCENT", value=Decimal("5"), scope="SUBSCRIPTION"
    )
    rule.subscriptions.set([target])
    billing.run_billing(today)
    assert Invoice.objects.get(subscription=target).discount_amount == Decimal("100.00")
    assert Invoice.objects.get(subscription=other).discount_amount == 0


def test_cancelled_invoice_frees_the_period_and_its_discount(make_active, today):
    sub = make_active()
    rule = Discount.objects.create(
        name="Once", kind="FIXED", value=Decimal("100"), scope="SUBSCRIPTION", usage_limit=1
    )
    inv = billing.bill_next_period(sub)
    assert inv.discount_amount == Decimal("100.00")
    billing.cancel_invoice(inv, reason="Wrong quantity")
    again = billing.rebill_period(inv)
    assert again.period_start == inv.period_start and again.status == I.DRAFT
    assert again.applied_discounts.get().discount == rule  # usage was released
    with pytest.raises(Conflict):
        billing.rebill_period(inv)


def test_invoice_actions(staff_api, make_active, today):
    sub = make_active()
    created = staff_api.post(f"/api/subscriptions/{sub.id}/invoice-now/").json()
    assert created["status"] == "DRAFT" and created["number"] is None
    url = f"/api/invoices/{created['id']}"
    confirmed = staff_api.post(f"{url}/confirm/").json()
    assert confirmed["status"] == "CONFIRMED" and confirmed["number"]
    sent = staff_api.post(f"{url}/send/").json()
    assert sent["sent_at"]
    mail = OutboundEmail.objects.get(category="invoice")
    assert mail.attachments == [f"{confirmed['number'].replace('/', '-')}.pdf"]
    pdf = staff_api.get(f"{url}/pdf/")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert staff_api.post(f"{url}/confirm/").status_code == 409


def test_billing_preview_writes_nothing(staff_api, make_active, today):
    make_active(start=today - timedelta(days=40))
    preview = staff_api.get(f"/api/billing/runs/preview/?as_of={today}").json()
    assert preview["invoices"] == 2 and len(preview["rows"]) == 2
    assert Invoice.objects.count() == 0
    run = staff_api.post("/api/billing/runs/run/", {"as_of": str(today)}).json()
    assert run["invoices_created"] == 2
    assert staff_api.get("/api/billing/runs/gaps/").json()["healthy"] is True


def test_gap_audit_finds_a_missing_period(make_active, today):
    sub = make_active(start=today - timedelta(days=40))
    billing.run_billing(today)
    first = Invoice.objects.filter(subscription=sub).order_by("period_start").first()
    InvoiceLine.objects.filter(invoice=first).delete()
    Invoice.objects.filter(pk=first.pk).update(status=I.CANCELLED)
    gaps = billing.billing_gaps()
    assert [g["period_start"] for g in gaps] == [first.period_start]


def test_resume_after_pause_is_not_a_gap(make_active, today):
    sub = make_active(start=today - timedelta(days=70))
    billing.run_billing(today - timedelta(days=65))
    subs.pause(sub)
    subs.resume(sub)
    billing.run_billing(today)
    assert billing.billing_gaps() == []


def test_daily_jobs(make_active, today):
    pilot = make_plan(name="Pilot", auto_close=True)
    make_active(plan=pilot, start=today - timedelta(days=10), expiry=today - timedelta(days=1))
    result = billing.run_daily_jobs(today)
    assert result["invoices"] == 1 and result["closed"] == 1
