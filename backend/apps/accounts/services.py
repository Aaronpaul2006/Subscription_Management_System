from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.core.errors import Invalid
from apps.core.mail import send_email
from apps.core.models import log_activity

from .models import Customer, Role, User


@transaction.atomic
def sign_up(name: str, email: str, password: str, company: str = "", phone: str = "") -> User:
    """Create a portal account. If staff already created a customer record for
    this email, the account claims it instead of creating a duplicate."""
    email = email.strip().lower()
    user = User.objects.create_user(email=email, password=password, name=name, phone=phone)
    customer = Customer.objects.select_for_update().filter(email__iexact=email).first()
    if customer is None:
        customer = Customer.objects.create(
            name=name, email=email, company=company, phone=phone, user=user
        )
    else:
        customer.user = user
        customer.save(update_fields=["user"])
    log_activity("customer", customer.id, "signed_up", f"{name} created a portal account", user)
    send_email(
        email,
        f"Welcome to {settings.COMPANY['name']}",
        f"Hi {name},\n\nYour account is ready. Sign in at {settings.FRONTEND_URL}/login "
        "to see your subscriptions and invoices.\n",
        category="welcome",
    )
    return user


def request_password_reset(email: str) -> None:
    """Send a reset link. Silently does nothing for unknown emails so the
    endpoint cannot be used to discover who has an account."""
    user = User.objects.filter(email__iexact=email.strip(), is_active=True).first()
    if user is None:
        return
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f"{settings.FRONTEND_URL}/reset-password/{uid}/{token}"
    send_email(
        user.email,
        "Reset your password",
        f"Hi {user.name},\n\nUse this link to choose a new password (valid for 24 hours):\n"
        f"{link}\n\nIf you did not ask for this, you can ignore this email.\n",
        html=(
            f"<p>Hi {user.name},</p><p>Use the button below to choose a new password. "
            f"The link is valid for 24 hours.</p><p><a href='{link}' style='background:#4f46e5;"
            "color:#fff;padding:10px 16px;border-radius:8px;text-decoration:none'>Reset password"
            "</a></p><p>If you did not ask for this, you can ignore this email.</p>"
        ),
        category="password_reset",
    )


def reset_password(uid: str, token: str, password: str) -> User:
    from django.contrib.auth import password_validation

    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)), is_active=True)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        raise Invalid(
            "This reset link is invalid or has expired.", code="reset_link_invalid"
        ) from None
    if not default_token_generator.check_token(user, token):
        raise Invalid("This reset link is invalid or has expired.", code="reset_link_invalid")
    password_validation.validate_password(password, user)
    user.set_password(password)
    user.save(update_fields=["password"])
    log_activity("user", user.id, "password_reset", f"{user.name} reset their password", user)
    return user


def is_admin(user) -> bool:
    return getattr(user, "role", None) == Role.ADMIN
