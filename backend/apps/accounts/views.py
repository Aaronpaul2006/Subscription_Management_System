from decimal import Decimal

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.db.models import Count, DecimalField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.errors import Invalid
from apps.core.models import log_activity
from apps.core.permissions import IsAdmin, IsInternal

from . import services
from .models import Customer, Role, User
from .serializers import (
    ChangePasswordSerializer,
    CustomerSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    SignupSerializer,
    StaffSerializer,
    UserSerializer,
)


class AuthThrottled(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


@method_decorator(ensure_csrf_cookie, name="get")
class CsrfView(APIView):
    """Sets the CSRF cookie the web app sends back as ``X-CSRFToken``."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"ok": True})


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class LoginView(AuthThrottled):
    def post(self, request):
        data = LoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=data.validated_data["email"].strip().lower(),
            password=data.validated_data["password"],
        )
        if user is None:
            raise Invalid("Email or password is incorrect.", code="bad_credentials")
        login(request, user)
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SignupView(AuthThrottled):
    def post(self, request):
        data = SignupSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = services.sign_up(**data.validated_data)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class PasswordResetRequestView(AuthThrottled):
    def post(self, request):
        data = PasswordResetRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.request_password_reset(data.validated_data["email"])
        return Response(
            {"message": "If that email has an account, a reset link is on its way."},
            status=status.HTTP_202_ACCEPTED,
        )


class PasswordResetConfirmView(AuthThrottled):
    def post(self, request):
        data = PasswordResetConfirmSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.reset_password(**data.validated_data)
        return Response({"message": "Password updated. You can sign in now."})


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from django.contrib.auth import password_validation

        data = ChangePasswordSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(data.validated_data["current_password"]):
            raise Invalid("Current password is incorrect.", code="bad_credentials")
        password_validation.validate_password(data.validated_data["new_password"], user)
        user.set_password(data.validated_data["new_password"])
        user.save(update_fields=["password"])
        update_session_auth_hash(request, user)
        return Response({"message": "Password changed."})


class StaffViewSet(viewsets.ModelViewSet):
    """Team management. Only the admin can add or change staff."""

    permission_classes = [IsAdmin]
    serializer_class = StaffSerializer
    search_fields = ["name", "email"]
    filterset_fields = ["role", "is_active"]
    ordering = ["name"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return User.objects.filter(role__in=[Role.ADMIN, Role.STAFF]).order_by("name")

    def perform_create(self, serializer):
        user = serializer.save()
        log_activity(
            "user",
            user.id,
            "created",
            f"Added {user.name} as {user.get_role_display()}",
            self.request.user,
        )

    def perform_update(self, serializer):
        if serializer.instance == self.request.user and (
            serializer.validated_data.get("is_active") is False
            or serializer.validated_data.get("role", Role.ADMIN) != Role.ADMIN
        ):
            raise Invalid("You cannot deactivate or demote your own account.")
        serializer.save()


class CustomerViewSet(viewsets.ModelViewSet):
    permission_classes = [IsInternal]
    serializer_class = CustomerSerializer
    search_fields = ["name", "company", "email", "phone", "city"]
    ordering_fields = ["name", "created_at", "outstanding", "active_subscriptions"]
    ordering = ["name"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        from apps.invoicing.models import Invoice
        from apps.subscriptions.models import Subscription

        active = (
            Subscription.objects.filter(customer=OuterRef("pk"), status=Subscription.Status.ACTIVE)
            .values("customer")
            .annotate(c=Count("id"))
            .values("c")
        )
        due = (
            Invoice.objects.filter(customer=OuterRef("pk"), status=Invoice.Status.CONFIRMED)
            .values("customer")
            .annotate(s=Sum("amount_due"))
            .values("s")
        )
        money = DecimalField(max_digits=14, decimal_places=2)
        return Customer.objects.annotate(
            active_subscriptions=Coalesce(Subquery(active), Value(0)),
            outstanding=Coalesce(
                Subquery(due, output_field=money), Value(Decimal("0")), output_field=money
            ),
        )

    def perform_create(self, serializer):
        customer = serializer.save()
        log_activity(
            "customer", customer.id, "created", f"Customer {customer} created", self.request.user
        )


def customer_search_q(term: str) -> Q:
    return Q(name__icontains=term) | Q(company__icontains=term) | Q(email__icontains=term)
