from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Customer, Role, User
from apps.catalog.models import PaymentTerm, Product, ProductVariant, RecurringPlan, Tax
from apps.subscriptions import services as subs

PASSWORD = "Strong@Pass1"


@pytest.fixture(autouse=True)
def _db(db, settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    settings.MAILERS = {
        "default": {"BACKEND": "apps.core.mail.OutboxEmailBackend"},
        "delivery": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"},
    }
    from django.core.cache import cache

    cache.clear()  # login throttling counts live in the cache


@pytest.fixture
def today() -> date:
    return timezone.localdate()


def make_user(email, role, name="Test User"):
    return User.objects.create_user(email=email, password=PASSWORD, name=name, role=role)


@pytest.fixture
def admin_user():
    return make_user("admin@test.local", Role.ADMIN, "Admin")


@pytest.fixture
def staff_user():
    return make_user("staff@test.local", Role.STAFF, "Staff")


@pytest.fixture
def customer(db):
    user = make_user("buyer@shop.test", Role.CUSTOMER, "Buyer")
    return Customer.objects.create(
        name="Buyer", company="Shop One", email="buyer@shop.test", user=user
    )


@pytest.fixture
def other_customer(db):
    user = make_user("rival@other.test", Role.CUSTOMER, "Rival")
    return Customer.objects.create(
        name="Rival", company="Other Co", email="rival@other.test", user=user
    )


def client_for(user):
    client = APIClient()
    if user is not None:
        client.force_login(user)
    return client


@pytest.fixture
def admin_api(admin_user):
    return client_for(admin_user)


@pytest.fixture
def staff_api(staff_user):
    return client_for(staff_user)


@pytest.fixture
def customer_api(customer):
    return client_for(customer.user)


@pytest.fixture
def other_api(other_customer):
    return client_for(other_customer.user)


@pytest.fixture
def gst():
    return Tax.objects.create(name="GST 18%", amount=Decimal("18"))


@pytest.fixture
def net15():
    return PaymentTerm.objects.create(name="Net 15", due_days=15)


@pytest.fixture
def product(gst):
    p = Product.objects.create(
        name="CRM seat", sales_price=Decimal("1000"), cost_price=Decimal("200")
    )
    p.taxes.set([gst])
    ProductVariant.objects.create(
        product=p, attribute="Brand", value="Odoo", extra_price=Decimal("560")
    )
    return p


@pytest.fixture
def addon(gst):
    p = Product.objects.create(
        name="Storage", product_type=Product.Type.ADDON, sales_price=Decimal("250")
    )
    p.taxes.set([gst])
    return p


def make_plan(**kw):
    defaults = dict(
        name="Monthly",
        billing_period="MONTHLY",
        price=Decimal("0"),
        min_quantity=Decimal("1"),
        start_date=date(2020, 1, 1),
        pausable=True,
    )
    defaults.update(kw)
    return RecurringPlan.objects.create(**defaults)


@pytest.fixture
def plan():
    return make_plan()


def active_subscription(
    customer, plan, product, start, qty=Decimal(2), term=None, actor=None, expiry=None
):
    sub = subs.create_subscription(
        customer=customer,
        plan=plan,
        start_date=start,
        expiry_date=expiry,
        payment_term=term,
        lines=[{"product": product, "quantity": qty}],
        actor=actor,
    )
    subs.send_quotation(sub, actor, email=False)
    subs.confirm(sub, actor)
    sub.refresh_from_db()
    return sub


@pytest.fixture
def make_active(customer, plan, product, net15, staff_user, today):
    def _make(start=None, **kw):
        kw.setdefault("term", net15)
        kw.setdefault("actor", staff_user)
        return active_subscription(
            kw.pop("customer", customer),
            kw.pop("plan", plan),
            kw.pop("product", product),
            start or today,
            **kw,
        )

    return _make


def days_ago(n: int) -> date:
    return timezone.localdate() - timedelta(days=n)
