import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CalendarClock, CreditCard, FileSignature, Receipt, Repeat } from "lucide-react";
import { Link } from "react-router";
import { Badge, Button, Card, Empty, formatDate, InvoiceBadge, Loading, Money, PageHeader, Stat, Table } from "../components/ui";
import { get } from "../lib/api";
import { useAuth } from "../lib/auth";
import { isZero } from "../lib/money";
import type { Invoice, Subscription } from "../lib/types";

interface Summary {
  customer: { id: number; name: string } | null;
  active_subscriptions: number;
  pending_quotations: number;
  amount_due: string;
  overdue: string;
  overdue_count: number;
  next_invoice: { date: string; subscription: string; subscription_id: number; estimate: string } | null;
  recent_invoices: Invoice[];
  subscriptions: Subscription[];
}

export function PortalHome() {
  const { user } = useAuth();
  const { data, isLoading } = useQuery({ queryKey: ["portal", "summary"], queryFn: () => get<Summary>("portal/summary/") });
  if (isLoading || !data) return <Loading />;
  const quotes = data.subscriptions.filter((s) => s.status === "QUOTATION" && !s.quotation_expired);

  return (
    <>
      <PageHeader title={`Hello, ${user?.name.split(" ")[0]}`} subtitle={data.customer ? `Your ${data.customer.name} account at a glance.` : "Your account at a glance."} />
      {quotes.map((q) => (
        <div key={q.id} className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-sky-200 bg-sky-50 px-5 py-4 dark:border-sky-900 dark:bg-sky-950/30">
          <div className="flex items-center gap-3 text-sky-900 dark:text-sky-200">
            <FileSignature className="size-6" />
            <div>
              <div className="font-medium">Quotation {q.number} is waiting for you</div>
              <div className="text-sm">{q.plan_name} · <Money value={q.total} /> {q.billing_label} · valid until {formatDate(q.quotation_valid_until)}</div>
            </div>
          </div>
          <Link to={`/portal/subscriptions/${q.id}`}><Button>Review & accept</Button></Link>
        </div>
      ))}
      {data.overdue_count > 0 && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 px-5 py-4 dark:border-rose-900 dark:bg-rose-950/30">
          <div className="flex items-center gap-3 text-rose-900 dark:text-rose-200">
            <AlertTriangle className="size-6" />
            <div>
              <div className="font-medium">{data.overdue_count} invoice{data.overdue_count > 1 ? "s are" : " is"} overdue</div>
              <div className="text-sm"><Money value={data.overdue} /> is past its due date.</div>
            </div>
          </div>
          <Link to="/portal/invoices?tab=OVERDUE"><Button variant="danger" icon={<CreditCard className="size-4" />}>Pay now</Button></Link>
        </div>
      )}
      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <Stat label="Active subscriptions" value={String(data.active_subscriptions)} icon={<Repeat className="size-5" />} to="/portal/subscriptions" />
        <Stat label="Amount due" value={<Money value={data.amount_due} />} icon={<Receipt className="size-5" />} tone={isZero(data.amount_due) ? "good" : "warn"} to="/portal/invoices?tab=CONFIRMED" hint={isZero(data.amount_due) ? "You're all paid up" : undefined} />
        <Stat
          label="Next invoice"
          value={data.next_invoice ? formatDate(data.next_invoice.date) : "—"}
          icon={<CalendarClock className="size-5" />}
          hint={data.next_invoice ? <>About <Money value={data.next_invoice.estimate} /> for {data.next_invoice.subscription}</> : "No upcoming invoices"}
        />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Your subscriptions" padded={false} actions={<Link to="/portal/subscriptions" className="text-xs font-medium text-brand-600 hover:underline">View all</Link>}>
          {data.subscriptions.length === 0 ? <Empty title="No subscriptions yet" /> : (
            <Table head={<><th className="th">Subscription</th><th className="th">Status</th><th className="th text-right">Per period</th></>}>
              {data.subscriptions.map((s) => (
                <tr key={s.id}>
                  <td className="td"><Link to={`/portal/subscriptions/${s.id}`} className="font-medium text-brand-600 hover:underline">{s.number}</Link><div className="text-xs text-slate-500">{s.plan_name} · {s.billing_label}</div></td>
                  <td className="td"><Badge status={s.status} /></td>
                  <td className="td text-right"><Money value={s.total} /></td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
        <Card title="Recent invoices" padded={false} actions={<Link to="/portal/invoices" className="text-xs font-medium text-brand-600 hover:underline">View all</Link>}>
          {data.recent_invoices.length === 0 ? <Empty title="No invoices yet" /> : (
            <Table head={<><th className="th">Invoice</th><th className="th">Status</th><th className="th text-right">Balance</th></>}>
              {data.recent_invoices.map((i) => (
                <tr key={i.id}>
                  <td className="td"><Link to={`/portal/invoices/${i.id}`} className="font-medium text-brand-600 hover:underline">{i.display_number}</Link><div className="text-xs text-slate-500">{formatDate(i.invoice_date)}</div></td>
                  <td className="td"><InvoiceBadge status={i.status} overdue={i.is_overdue} days={i.days_overdue} /></td>
                  <td className="td text-right font-medium"><Money value={i.amount_due} /></td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      </div>
    </>
  );
}
