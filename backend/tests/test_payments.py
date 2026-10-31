from datetime import timedelta
from decimal import Decimal

import pytest

from apps.core.errors import Conflict, Invalid
from apps.core.models import OutboundEmail
from apps.invoicing import services as billing
from apps.invoicing.models import Invoice

I = Invoice.Status  # noqa: E741


@pytest.fixture
def invoice(make_active, today):
    sub = make_active()
    return billing.bill_next_period(sub, confirm_now=True)  # total 2,360.00


def test_partial_then_full_payment(staff_api, invoice, today, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        first = staff_api.post(
            "/api/payments/",
            {
                "invoice": invoice.id,
                "method": "BANK_TRANSFER",
                "amount": "1000.00",
                "payment_date": str(today),
                "note": "NEFT part 1",
            },
            format="json",
        )
    assert first.status_code == 201, first.json()
    detail = staff_api.get(f"/api/invoices/{invoice.id}/").json()
    assert detail["status"] == "CONFIRMED"
    assert detail["amount_paid"] == "1000.00" and detail["amount_due"] == "1360.00"

    with django_capture_on_commit_callbacks(execute=True):
        staff_api.post(
            "/api/payments/",
            {"invoice": invoice.id, "method": "UPI", "amount": "1360.00"},
            format="json",
        )
    detail = staff_api.get(f"/api/invoices/{invoice.id}/").json()
    assert detail["status"] == "PAID" and detail["amount_due"] == "0.00"
    assert [p["method"] for p in detail["payments"]] == ["UPI", "BANK_TRANSFER"]
    assert OutboundEmail.objects.filter(category="receipt").count() == 2


def test_payment_validation(invoice, make_active, today):
    with pytest.raises(Invalid, match="more than"):
        billing.record_payment(invoice, amount=Decimal("9999"), method="CASH", payment_date=today)
    with pytest.raises(Invalid):
        billing.record_payment(invoice, amount=Decimal("0"), method="CASH", payment_date=today)
    with pytest.raises(Invalid, match="future"):
        billing.record_payment(
            invoice, amount=Decimal("1"), method="CASH", payment_date=today + timedelta(days=1)
        )
    draft = billing.bill_next_period(make_active())
    with pytest.raises(Conflict, match="Confirm"):
        billing.record_payment(draft, amount=Decimal("1"), method="CASH", payment_date=today)


def test_paid_invoice_cannot_be_cancelled(invoice, today):
    billing.record_payment(invoice, amount=Decimal("10"), method="CASH", payment_date=today)
    with pytest.raises(Conflict):
        billing.cancel_invoice(invoice)


def test_money_is_a_string_and_floats_never_appear(staff_api, invoice):
    data = staff_api.get(f"/api/invoices/{invoice.id}/").json()
    assert isinstance(data["total"], str) and data["total"] == "2360.00"


def test_overdue_and_outstanding_filters(staff_api, make_active, today):
    late = make_active(start=today - timedelta(days=40))
    billing.run_billing(today)
    overdue = staff_api.get("/api/invoices/?overdue=true").json()
    assert overdue["count"] == 1  # the period that started 40 days ago, net 15
    assert overdue["results"][0]["days_overdue"] > 0
    assert overdue["results"][0]["subscription"] == late.id
    outstanding = staff_api.get("/api/invoices/?outstanding=true").json()
    assert outstanding["count"] == 2
    stats = staff_api.get("/api/invoices/stats/").json()
    assert stats["OVERDUE"]["count"] == 1 and stats["CONFIRMED"]["count"] == 2


def test_overdue_reminders_are_spaced_out(make_active, today):
    make_active(start=today - timedelta(days=40))
    billing.run_billing(today)
    assert billing.send_overdue_reminders(today) == 1
    assert billing.send_overdue_reminders(today) == 0  # not again within the interval
    assert Invoice.objects.get(reminder_count=1).last_reminder_at is not None


def test_customer_pays_own_invoice_in_portal(customer_api, other_api, invoice):
    url = f"/api/invoices/{invoice.id}"
    assert other_api.post(f"{url}/pay/", {"method": "CARD"}).status_code == 404
    paid = customer_api.post(f"{url}/pay/", {"method": "UPI"})
    assert paid.status_code == 200
    assert paid.json()["status"] == "PAID"
    assert paid.json()["payments"][0]["source"] == "PORTAL"
    assert customer_api.get("/api/payments/").json()["count"] == 1
    assert other_api.get("/api/payments/").json()["count"] == 0


def test_customer_cannot_record_payments_or_see_drafts(customer_api, make_active, invoice):
    response = customer_api.post(
        "/api/payments/", {"invoice": invoice.id, "method": "CASH", "amount": "1"}
    )
    assert response.status_code == 403
    draft = billing.bill_next_period(make_active())
    assert customer_api.get(f"/api/invoices/{draft.id}/").status_code == 404


def test_csv_export(staff_api, invoice):
    response = staff_api.get("/api/reports/invoices.csv?status=CONFIRMED")
    body = response.content.decode()
    assert response.status_code == 200 and invoice.number in body
