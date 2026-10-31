"""The finance lead's requirement: every page answers in under two seconds
with thousands of subscriptions on the books.

Loads ~3,000 subscriptions (about 15,000 invoices and 12,000 payments) with the
demo seeder, then times every list and dashboard endpoint the web app calls.
"""

import io
import time

import pytest
from django.core.management import call_command

from apps.accounts.models import User
from apps.subscriptions.models import Subscription

from .conftest import client_for

ENDPOINTS = [
    "/api/reports/dashboard/",
    "/api/reports/customers/",
    "/api/subscriptions/",
    "/api/subscriptions/?status=ACTIVE&search=a&ordering=-mrr",
    "/api/subscriptions/stats/",
    "/api/invoices/",
    "/api/invoices/?overdue=true",
    "/api/invoices/stats/",
    "/api/payments/",
    "/api/customers/?ordering=-outstanding",
    "/api/plans/",
    "/api/discounts/",
    "/api/search/?q=sun",
    "/api/billing/runs/preview/",
]


@pytest.mark.slow
def test_every_page_under_two_seconds():
    call_command("seed_demo", subscriptions=3000, yes=True, stdout=io.StringIO())
    assert Subscription.objects.count() > 3000
    client = client_for(User.objects.get(email="admin@brightloop.test"))
    slow = {}
    for url in ENDPOINTS:
        started = time.perf_counter()
        response = client.get(url)
        elapsed = time.perf_counter() - started
        assert response.status_code == 200, (url, response.content[:200])
        if elapsed >= 2:
            slow[url] = round(elapsed, 2)
    assert slow == {}, f"Slower than 2 s: {slow}"
