import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation, useParams } from "react-router";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { useAuth } from "./lib/auth";
import { useMeta } from "./lib/hooks";
import type { Role } from "./lib/types";
import { ForgotPassword, Login, ResetPassword, Signup } from "./pages/auth";
import { BillingPage } from "./pages/billing";
import { DiscountsPage, PlansPage, ProductsPage, TaxesPage, TemplatesPage } from "./pages/catalog";
import { CustomerDetail, CustomersPage } from "./pages/customers";
import { Dashboard } from "./pages/dashboard";
import { InvoiceDetail, InvoicePrint, InvoicesPage } from "./pages/invoices";
import { OutboxPage, TeamPage } from "./pages/admin";
import { PaymentsPage } from "./pages/payments";
import { PortalHome } from "./pages/portal";
import { ProfilePage } from "./pages/profile";
import { ReportsPage } from "./pages/reports";
import { SubscriptionDetail, SubscriptionForm, SubscriptionsPage } from "./pages/subscriptions";

const INTERNAL: Role[] = ["ADMIN", "STAFF"];

function RequireAuth({ roles, children }: { roles?: Role[]; children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" state={{ from: location.pathname + location.search }} replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to={user.role === "CUSTOMER" ? "/portal" : "/"} replace />;
  return <>{children}</>;
}

/** Email links point at the portal; staff opening one land on the office page. */
function PortalOrOffice({ portal, office }: { portal: ReactNode; office: (id: string) => string }) {
  const { user } = useAuth();
  const { id } = useParams();
  if (user && user.role !== "CUSTOMER") return <Navigate to={office(id!)} replace />;
  return <>{portal}</>;
}

export function App() {
  useMeta();
  const { user } = useAuth();
  const home = user?.role === "CUSTOMER" ? "/portal" : "/";
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to={home} replace /> : <Login />} />
      <Route path="/signup" element={user ? <Navigate to={home} replace /> : <Signup />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password/:uid/:token" element={<ResetPassword />} />
      <Route path="/invoices/:id/print" element={<RequireAuth><InvoicePrint /></RequireAuth>} />
      <Route path="/portal/invoices/:id/print" element={<RequireAuth><InvoicePrint /></RequireAuth>} />

      <Route element={<RequireAuth><Layout /></RequireAuth>}>
        <Route path="/profile" element={<ProfilePage />} />

        {/* Office */}
        <Route path="/" element={<RequireAuth roles={INTERNAL}><Dashboard /></RequireAuth>} />
        <Route path="/subscriptions" element={<RequireAuth roles={INTERNAL}><SubscriptionsPage /></RequireAuth>} />
        <Route path="/subscriptions/new" element={<RequireAuth roles={INTERNAL}><SubscriptionForm /></RequireAuth>} />
        <Route path="/subscriptions/:id" element={<RequireAuth roles={INTERNAL}><SubscriptionDetail /></RequireAuth>} />
        <Route path="/subscriptions/:id/edit" element={<RequireAuth roles={INTERNAL}><SubscriptionForm /></RequireAuth>} />
        <Route path="/invoices" element={<RequireAuth roles={INTERNAL}><InvoicesPage /></RequireAuth>} />
        <Route path="/invoices/:id" element={<RequireAuth roles={INTERNAL}><InvoiceDetail /></RequireAuth>} />
        <Route path="/payments" element={<RequireAuth roles={INTERNAL}><PaymentsPage /></RequireAuth>} />
        <Route path="/billing" element={<RequireAuth roles={INTERNAL}><BillingPage /></RequireAuth>} />
        <Route path="/customers" element={<RequireAuth roles={INTERNAL}><CustomersPage /></RequireAuth>} />
        <Route path="/customers/:id" element={<RequireAuth roles={INTERNAL}><CustomerDetail /></RequireAuth>} />
        <Route path="/reports" element={<RequireAuth roles={INTERNAL}><ReportsPage /></RequireAuth>} />
        <Route path="/products" element={<RequireAuth roles={INTERNAL}><ProductsPage /></RequireAuth>} />
        <Route path="/plans" element={<RequireAuth roles={INTERNAL}><PlansPage /></RequireAuth>} />
        <Route path="/templates" element={<RequireAuth roles={INTERNAL}><TemplatesPage /></RequireAuth>} />
        <Route path="/discounts" element={<RequireAuth roles={INTERNAL}><DiscountsPage /></RequireAuth>} />
        <Route path="/taxes" element={<RequireAuth roles={INTERNAL}><TaxesPage /></RequireAuth>} />
        <Route path="/team" element={<RequireAuth roles={["ADMIN"]}><TeamPage /></RequireAuth>} />
        <Route path="/outbox" element={<RequireAuth roles={["ADMIN"]}><OutboxPage /></RequireAuth>} />

        {/* Customer portal */}
        <Route path="/portal" element={<RequireAuth roles={["CUSTOMER"]}><PortalHome /></RequireAuth>} />
        <Route path="/portal/subscriptions" element={<RequireAuth roles={["CUSTOMER"]}><SubscriptionsPage portal /></RequireAuth>} />
        <Route path="/portal/subscriptions/:id" element={<PortalOrOffice office={(id) => `/subscriptions/${id}`} portal={<SubscriptionDetail portal />} />} />
        <Route path="/portal/invoices" element={<RequireAuth roles={["CUSTOMER"]}><InvoicesPage portal /></RequireAuth>} />
        <Route path="/portal/invoices/:id" element={<PortalOrOffice office={(id) => `/invoices/${id}`} portal={<InvoiceDetail portal />} />} />
        <Route path="/portal/payments" element={<RequireAuth roles={["CUSTOMER"]}><PaymentsPage portal /></RequireAuth>} />
      </Route>
      <Route path="*" element={<Navigate to={home} replace />} />
    </Routes>
  );
}
