"""Role-based access.

* ADMIN    – everything, including catalog, taxes, discounts and staff.
* STAFF    – day-to-day work: customers, subscriptions, invoices, payments.
             Catalog configuration is read-only for staff.
* CUSTOMER – the portal only; querysets are scoped to their own records, so
             another customer's record is a 404, never a 403.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission


def role_of(user) -> str | None:
    return getattr(user, "role", None) if user and user.is_authenticated else None


class IsAdmin(BasePermission):
    message = "Only an administrator can do this."

    def has_permission(self, request, view):
        return role_of(request.user) == "ADMIN"


class IsInternal(BasePermission):
    """Admin or staff."""

    message = "This area is for Brightloop staff."

    def has_permission(self, request, view):
        return role_of(request.user) in ("ADMIN", "STAFF")


class AdminWritesInternalReads(BasePermission):
    """Catalog configuration: staff may read, only the admin may change it."""

    message = "Only an administrator can change this."

    def has_permission(self, request, view):
        role = role_of(request.user)
        if request.method in SAFE_METHODS:
            return role in ("ADMIN", "STAFF")
        return role == "ADMIN"


class AdminWritesEveryoneReads(BasePermission):
    """Configuration customers also need to read (e.g. plan options)."""

    def has_permission(self, request, view):
        role = role_of(request.user)
        if request.method in SAFE_METHODS:
            return role is not None
        return role == "ADMIN"
