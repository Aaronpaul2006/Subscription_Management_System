import re

import pytest

from apps.accounts.models import Customer, User
from apps.core.models import OutboundEmail

from .conftest import PASSWORD, client_for

SIGNUP = "/api/auth/signup/"


def signup(client, **kw):
    data = {"name": "New Owner", "email": "owner@newshop.test", "password": "Brightloop#26"}
    data.update(kw)
    return client.post(SIGNUP, data, format="json")


@pytest.mark.parametrize(
    ("password", "problem"),
    [
        ("Abcdef!1", "more than 8"),  # exactly 8 is not "more than eight"
        ("abcdefgh!1", "uppercase"),
        ("ABCDEFGH!1", "lowercase"),
        ("Abcdefghi1", "special"),
    ],
)
def test_signup_password_rules(password, problem):
    response = signup(client_for(None), password=password)
    assert response.status_code == 400
    assert problem in str(response.json()).lower()


def test_signup_creates_customer_account_and_logs_in():
    client = client_for(None)
    response = signup(client, password="Abcdefg!1")  # nine characters is enough
    assert response.status_code == 201, response.json()
    assert response.json()["role"] == "CUSTOMER"
    assert Customer.objects.get(email="owner@newshop.test").user.email == "owner@newshop.test"
    assert client.get("/api/auth/me/").json()["email"] == "owner@newshop.test"


def test_one_account_per_email_case_insensitive():
    assert signup(client_for(None)).status_code == 201
    again = signup(client_for(None), email="OWNER@NewShop.test")
    assert again.status_code == 400
    assert "already exists" in again.json()["error"]["message"]


def test_signup_claims_customer_created_by_staff():
    existing = Customer.objects.create(name="Pre", company="Pre Co", email="owner@newshop.test")
    assert signup(client_for(None)).status_code == 201
    existing.refresh_from_db()
    assert existing.user is not None
    assert Customer.objects.filter(email="owner@newshop.test").count() == 1


def test_login_and_wrong_password(customer):
    client = client_for(None)
    bad = client.post("/api/auth/login/", {"email": customer.email, "password": "nope"})
    assert bad.status_code == 400
    ok = client.post("/api/auth/login/", {"email": customer.email.upper(), "password": PASSWORD})
    assert ok.status_code == 200


def test_password_reset_flow(customer):
    client = client_for(None)
    unknown = client.post("/api/auth/password-reset/", {"email": "nobody@x.test"})
    assert unknown.status_code == 202  # same answer: no account discovery
    assert OutboundEmail.objects.count() == 0

    client.post("/api/auth/password-reset/", {"email": customer.email})
    mail = OutboundEmail.objects.get(category="password_reset")
    assert mail.to == customer.email
    uid, token = re.search(r"/reset-password/([^/]+)/(\S+)", mail.body).groups()

    weak = client.post(
        "/api/auth/password-reset/confirm/", {"uid": uid, "token": token, "password": "weak"}
    )
    assert weak.status_code == 400
    done = client.post(
        "/api/auth/password-reset/confirm/",
        {"uid": uid, "token": token, "password": "Fresh&Strong9"},
    )
    assert done.status_code == 200
    reused = client.post(
        "/api/auth/password-reset/confirm/",
        {"uid": uid, "token": token, "password": "Another&Strong9"},
    )
    assert reused.status_code == 400  # a link works once
    assert (
        client.post(
            "/api/auth/login/", {"email": customer.email, "password": "Fresh&Strong9"}
        ).status_code
        == 200
    )


def test_only_admin_adds_staff(admin_api, staff_api, customer_api):
    member = {
        "name": "New Rep",
        "email": "rep@brightloop.test",
        "role": "STAFF",
        "password": "Rep&Strong99",
    }
    assert staff_api.post("/api/team/", member).status_code == 403
    assert customer_api.post("/api/team/", member).status_code == 403
    created = admin_api.post("/api/team/", member)
    assert created.status_code == 201
    assert User.objects.get(email="rep@brightloop.test").role == "STAFF"
    customer_role = admin_api.post(
        "/api/team/", {**member, "email": "x@y.test", "role": "CUSTOMER"}
    )
    assert customer_role.status_code == 400


def test_staff_password_rules_apply(admin_api):
    response = admin_api.post(
        "/api/team/",
        {"name": "Weak", "email": "weak@b.test", "role": "STAFF", "password": "password"},
    )
    assert response.status_code == 400


def test_roles_see_different_areas(staff_api, customer_api, admin_api):
    assert staff_api.get("/api/customers/").status_code == 200
    assert customer_api.get("/api/customers/").status_code == 403
    assert customer_api.get("/api/reports/dashboard/").status_code == 403
    assert staff_api.get("/api/outbox/").status_code == 403
    assert admin_api.get("/api/outbox/").status_code == 200
    assert client_for(None).get("/api/subscriptions/").status_code == 403
