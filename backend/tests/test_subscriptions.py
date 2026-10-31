from datetime import timedelta
from decimal import Decimal

import pytest

from apps.core.errors import Conflict, Forbidden, Invalid
from apps.subscriptions import services as subs
from apps.subscriptions.models import QuotationTemplate, QuotationTemplateLine, Subscription

from .conftest import make_plan

S = Subscription.Status


def test_full_lifecycle_through_the_api(staff_api, customer, plan, product, today):
    created = staff_api.post(
        "/api/subscriptions/",
        {
            "customer": customer.id,
            "plan": plan.id,
            "start_date": str(today),
            "lines": [
                {"product": product.id, "variant": product.variants.first().id, "quantity": "3"}
            ],
        },
        format="json",
    )
    assert created.status_code == 201, created.json()
    sub = created.json()
    assert sub["status"] == "DRAFT"
    assert sub["number"].startswith("SUB/")
    line = sub["lines"][0]
    assert line["unit_price"] == "1560.00"  # sales price + Odoo variant 560
    assert line["description"] == "CRM seat (Brand: Odoo)"
    assert sub["untaxed_amount"] == "4680.00" and sub["tax_amount"] == "842.40"

    url = f"/api/subscriptions/{sub['id']}"
    assert staff_api.post(f"{url}/confirm/").status_code == 409  # must be a quotation first
    sent = staff_api.post(f"{url}/send-quotation/").json()
    assert sent["status"] == "QUOTATION" and sent["quotation_valid_until"]
    confirmed = staff_api.post(f"{url}/confirm/").json()
    # Starting today, so confirmation activates it straight away.
    assert confirmed["status"] == "ACTIVE"
    assert confirmed["next_invoice_date"] == str(today)
    closed = staff_api.post(f"{url}/close/", {"reason": "Done"}).json()
    assert closed["status"] == "CLOSED"


def test_future_start_stays_confirmed_until_activated(make_active, today):
    sub = make_active(start=today + timedelta(days=5))
    assert sub.status == S.CONFIRMED
    assert subs.activate_due(today) == 0
    assert subs.activate_due(today + timedelta(days=5)) == 1
    sub.refresh_from_db()
    assert sub.status == S.ACTIVE


def test_template_prefills_quotation(customer, plan, product, addon, net15, today):
    template = QuotationTemplate.objects.create(
        name="Bundle",
        validity_days=10,
        plan=plan,
        payment_term=net15,
        duration_months=12,
        notes="Terms here",
    )
    QuotationTemplateLine.objects.create(template=template, product=product, quantity=5)
    QuotationTemplateLine.objects.create(template=template, product=addon, quantity=2)
    sub = subs.create_subscription(
        customer=customer, plan=plan, template=template, start_date=today
    )
    assert [ln.quantity for ln in sub.lines.all()] == [5, 2]
    assert sub.payment_term == net15
    assert sub.expiry_date == today.replace(year=today.year + 1) - timedelta(days=1)
    sent = subs.send_quotation(sub, email=False)
    assert sent.quotation_valid_until == today + timedelta(days=10)


def test_plan_fee_line_added_automatically(customer, product, today):
    plan = make_plan(name="Seats", price=Decimal("499"), min_quantity=Decimal("5"))
    sub = subs.create_subscription(
        customer=customer, plan=plan, start_date=today, lines=[{"product": product, "quantity": 1}]
    )
    first = sub.lines.first()
    assert first.product is None and first.unit_price == Decimal("499")
    assert first.quantity == Decimal("5")


def test_minimum_quantity_enforced(customer, product, today):
    plan = make_plan(name="Team", min_quantity=Decimal("10"))
    sub = subs.create_subscription(
        customer=customer, plan=plan, start_date=today, lines=[{"product": product, "quantity": 3}]
    )
    with pytest.raises(Invalid, match="minimum quantity"):
        subs.send_quotation(sub, email=False)


def test_plan_availability_window(customer, product, today):
    plan = make_plan(name="Festive", start_date=today + timedelta(days=30))
    sub = subs.create_subscription(
        customer=customer, plan=plan, start_date=today, lines=[{"product": product, "quantity": 1}]
    )
    with pytest.raises(Invalid, match="not available"):
        subs.send_quotation(sub, email=False)


def test_expired_quotation_cannot_be_confirmed(customer, plan, product, today):
    sub = subs.create_subscription(
        customer=customer, plan=plan, start_date=today, lines=[{"product": product, "quantity": 1}]
    )
    subs.send_quotation(sub, email=False)
    Subscription.objects.filter(pk=sub.pk).update(quotation_valid_until=today - timedelta(days=1))
    with pytest.raises(Conflict, match="expired"):
        subs.confirm(sub)


def test_plan_rules_for_pause_close_and_renew(make_active, today):
    strict = make_plan(name="Strict", pausable=False, closable=False, renewable=False)
    sub = make_active(plan=strict, expiry=today + timedelta(days=90))
    with pytest.raises(Forbidden):
        subs.pause(sub)
    with pytest.raises(Forbidden):
        subs.close(sub)
    with pytest.raises(Forbidden):
        subs.renew(sub)

    flexible = make_active(expiry=today + timedelta(days=29))
    subs.pause(flexible)
    flexible.refresh_from_db()
    assert flexible.status == S.PAUSED
    subs.resume(flexible)
    renewed = subs.renew(flexible)
    assert renewed.expiry_date == today + timedelta(days=59)
    assert renewed.renewal_count == 1


def test_auto_close_on_expiry(make_active, today):
    plan = make_plan(name="Pilot", auto_close=True)
    sub = make_active(plan=plan, start=today - timedelta(days=40), expiry=today - timedelta(days=1))
    assert subs.close_expired(today) == 1
    sub.refresh_from_db()
    assert sub.status == S.CLOSED and sub.close_reason == "Expired"


def test_confirmed_subscription_cannot_be_edited(staff_api, make_active):
    sub = make_active()
    response = staff_api.patch(f"/api/subscriptions/{sub.id}/", {"notes": "x"}, format="json")
    assert response.status_code == 409


def test_customer_sees_only_own_and_accepts_online(
    customer, other_customer, plan, product, customer_api, other_api, today
):
    sub = subs.create_subscription(
        customer=customer, plan=plan, start_date=today, lines=[{"product": product, "quantity": 1}]
    )
    # Drafts are internal.
    assert customer_api.get(f"/api/subscriptions/{sub.id}/").status_code == 404
    subs.send_quotation(sub, email=False)
    assert customer_api.get("/api/subscriptions/").json()["count"] == 1
    assert other_api.get("/api/subscriptions/").json()["count"] == 0
    # Another customer's record is a 404, never a 403.
    assert other_api.get(f"/api/subscriptions/{sub.id}/").status_code == 404
    assert (
        other_api.post(f"/api/subscriptions/{sub.id}/accept/", {"name": "Rival"}).status_code == 404
    )

    detail = customer_api.get(f"/api/subscriptions/{sub.id}/").json()
    assert "accept" in detail["allowed_actions"] and "notes" not in detail
    accepted = customer_api.post(f"/api/subscriptions/{sub.id}/accept/", {"name": "Buyer B"})
    assert accepted.status_code == 200
    assert accepted.json()["accepted_by_name"] == "Buyer B"
    assert accepted.json()["status"] == "ACTIVE"


def test_customer_cannot_create_or_confirm(customer_api, customer, plan, product, today):
    response = customer_api.post(
        "/api/subscriptions/",
        {
            "customer": customer.id,
            "plan": plan.id,
            "lines": [{"product": product.id, "quantity": "1"}],
        },
        format="json",
    )
    assert response.status_code == 403
    sub = subs.create_subscription(
        customer=customer, plan=plan, start_date=today, lines=[{"product": product, "quantity": 1}]
    )
    subs.send_quotation(sub, email=False)
    assert customer_api.post(f"/api/subscriptions/{sub.id}/confirm/").status_code == 403


def test_status_tab_counts(staff_api, make_active, customer, plan, product, today):
    make_active()
    make_active()
    subs.create_subscription(
        customer=customer, plan=plan, start_date=today, lines=[{"product": product, "quantity": 1}]
    )
    stats = staff_api.get("/api/subscriptions/stats/?status=DRAFT").json()
    assert stats["ACTIVE"]["count"] == 2 and stats["DRAFT"]["count"] == 1


def test_only_admin_manages_catalog_and_discounts(admin_api, staff_api, product):
    discount = {
        "name": "Seats",
        "kind": "PERCENT",
        "value": "10",
        "scope": "PRODUCTS",
        "products": [product.id],
        "min_quantity": "10",
    }
    assert staff_api.post("/api/discounts/", discount, format="json").status_code == 403
    assert staff_api.get("/api/discounts/").status_code == 200
    assert admin_api.post("/api/discounts/", discount, format="json").status_code == 201
    assert staff_api.patch(f"/api/products/{product.id}/", {"name": "X"}).status_code == 403
    assert admin_api.patch(f"/api/products/{product.id}/", {"name": "X"}).status_code == 200
    bad = admin_api.post("/api/discounts/", {**discount, "value": "120"}, format="json")
    assert bad.status_code == 400
