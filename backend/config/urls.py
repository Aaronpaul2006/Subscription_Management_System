from django.conf import settings
from django.contrib import admin
from django.http import FileResponse, Http404
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from apps.accounts import views as accounts
from apps.catalog import views as catalog
from apps.core import views as core
from apps.invoicing import views as invoicing
from apps.reports import views as reports
from apps.subscriptions import views as subscriptions

router = DefaultRouter()
router.register("customers", accounts.CustomerViewSet, basename="customer")
router.register("team", accounts.StaffViewSet, basename="team")
router.register("taxes", catalog.TaxViewSet, basename="tax")
router.register("payment-terms", catalog.PaymentTermViewSet, basename="payment-term")
router.register("products", catalog.ProductViewSet, basename="product")
router.register("plans", catalog.RecurringPlanViewSet, basename="plan")
router.register(
    "quotation-templates", subscriptions.QuotationTemplateViewSet, basename="quotation-template"
)
router.register("subscriptions", subscriptions.SubscriptionViewSet, basename="subscription")
router.register("discounts", subscriptions.DiscountViewSet, basename="discount")
router.register("invoices", invoicing.InvoiceViewSet, basename="invoice")
router.register("payments", invoicing.PaymentViewSet, basename="payment")
router.register("billing/runs", invoicing.BillingRunViewSet, basename="billing-run")
router.register("activity", core.ActivityViewSet, basename="activity")
router.register("outbox", core.OutboxViewSet, basename="outbox")

auth_urls = [
    path("csrf/", accounts.CsrfView.as_view()),
    path("me/", accounts.MeView.as_view()),
    path("login/", accounts.LoginView.as_view()),
    path("logout/", accounts.LogoutView.as_view()),
    path("signup/", accounts.SignupView.as_view()),
    path("password-reset/", accounts.PasswordResetRequestView.as_view()),
    path("password-reset/confirm/", accounts.PasswordResetConfirmView.as_view()),
    path("change-password/", accounts.ChangePasswordView.as_view()),
]

api = [
    path("auth/", include(auth_urls)),
    path("meta/", core.MetaView.as_view()),
    path("search/", core.SearchView.as_view()),
    path("reports/dashboard/", reports.DashboardView.as_view()),
    path("reports/customers/", reports.CustomerReportView.as_view()),
    path("reports/invoices.csv", invoicing.InvoiceExportView.as_view()),
    path("portal/summary/", reports.PortalSummaryView.as_view()),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema")),
    path("", include(router.urls)),
]


def spa(request, path=""):
    """Serve the built web app; client-side routes all get index.html."""
    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        raise Http404("Web app not built. Run `npm run build` in frontend/.")
    return FileResponse(index.open("rb"), content_type="text/html")


urlpatterns = [
    path("api/", include(api)),
    path("django-admin/", admin.site.urls),
    re_path(r"^(?!api/|django-admin/|static/).*$", spa),
]
