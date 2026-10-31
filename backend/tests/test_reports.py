from datetime import timedelta
from decimal import Decimal

from apps.invoicing import services as billing
from apps.subscriptions import services as subs

from .conftest import make_plan


def test_dashboard_numbers(staff_api, make_active, today):
    monthly = make_active(qty=Decimal(2))  # 2,000/month
    yearly_plan = make_plan(name="Yearly", billing_period="YEARLY")
    make_active(plan=yearly_plan, qty=Decimal(12))  # 12,000/year = 1,000/month
    gone = make_active()
    subs.close(gone, reason="Budget")
    billing.run_billing(today)
    inv = monthly.invoices.get()
    billing.record_payment(inv, amount=Decimal("1000"), method="UPI", payment_date=today)

    data = staff_api.get("/api/reports/dashboard/").json()
    k = data["kpis"]
    assert k["active_subscriptions"] == 2
    assert k["mrr"] == "3000.00" and k["arr"] == "36000.00"
    assert k["churned_subscriptions"] == 1
    assert k["collected"] == "1000.00"
    assert k["invoiced"] == "16520.00"  # (2,000 + 12,000) × 1.18
    assert k["outstanding"] == "15520.00"
    assert {p["plan"] for p in data["mrr_by_plan"]} == {"Monthly", "Yearly"}
    assert len(data["trend"]) == 12
    assert data["payment_methods"][0]["method"] == "UPI"


def test_dashboard_plan_filter(staff_api, make_active, plan):
    make_active()
    other = make_plan(name="Other")
    make_active(plan=other)
    data = staff_api.get(f"/api/reports/dashboard/?plan={other.id}").json()
    assert data["kpis"]["active_subscriptions"] == 1


def test_portal_summary(customer_api, staff_api, make_active, today):
    make_active(start=today - timedelta(days=40))
    billing.run_billing(today)
    data = customer_api.get("/api/portal/summary/").json()
    assert data["active_subscriptions"] == 1
    assert data["overdue_count"] == 1
    assert data["next_invoice"]["date"] > str(today)
    assert staff_api.get("/api/portal/summary/").status_code == 403


def test_global_search(staff_api, make_active, customer_api):
    sub = make_active()
    results = staff_api.get("/api/search/?q=Shop").json()
    assert any(r["type"] == "customer" for r in results)
    assert any(r["title"] == sub.number for r in results)
    assert customer_api.get("/api/search/?q=Shop").status_code == 403
