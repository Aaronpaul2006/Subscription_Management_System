import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button, Card, Empty, ErrorBox, formatDate, Loading, Money, PageHeader, Select, Table } from "../components/ui";
import { get } from "../lib/api";
import { usePlans } from "../lib/hooks";
import { formatMoney, toChartNumber } from "../lib/money";
import { MoneyTooltip, monthLabel, periodRange, PERIODS, type DashboardData } from "./dashboard";

interface CustomerReport {
  top_by_mrr: { customer_id: number; customer: string; mrr: string }[];
  top_by_owed: { customer_id: number; customer: string; due: string; overdue: string; invoices: number }[];
}

export function ReportsPage() {
  const [period, setPeriod] = useState("12m");
  const [plan, setPlan] = useState("");
  const plans = usePlans().data?.results ?? [];
  const range = periodRange(period);
  const dash = useQuery({ queryKey: ["dashboard", range, plan], queryFn: () => get<DashboardData>("reports/dashboard/", { ...range, plan }) });
  const customers = useQuery({ queryKey: ["reports", "customers"], queryFn: () => get<CustomerReport>("reports/customers/") });
  const d = dash.data;
  const k = d?.kpis ?? {};
  const s = (key: string) => String(k[key] ?? "0");

  return (
    <>
      <PageHeader
        title="Reports"
        subtitle={d ? `Summary for ${formatDate(d.period.from)} – ${formatDate(d.period.to)}` : "Revenue, collections and receivables"}
        actions={
          <>
            <Select value={plan} onChange={(e) => setPlan(e.target.value)} className="w-44"><option value="">All plans</option>{plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select>
            <Select value={period} onChange={(e) => setPeriod(e.target.value)} className="w-40">{PERIODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}</Select>
            <a href={`/api/reports/invoices.csv?date_from=${range.date_from}&date_to=${range.date_to}${plan ? `&plan=${plan}` : ""}`}><Button variant="secondary" icon={<Download className="size-4" />}>Invoices CSV</Button></a>
          </>
        }
      />
      <ErrorBox error={dash.error} />
      {!d ? <Loading /> : (
        <div className="space-y-6">
          <Card title="Summary" padded={false}>
            <div className="grid divide-y divide-slate-100 sm:grid-cols-2 sm:divide-x lg:grid-cols-4 lg:divide-y-0 dark:divide-slate-800">
              {[
                ["Active subscriptions", Number(k.active_subscriptions).toLocaleString("en-IN"), `${k.paused_subscriptions} paused`],
                ["MRR", formatMoney(s("mrr")), `ARR ${formatMoney(s("arr"), { compact: true })}`],
                ["New / churned", `${k.new_subscriptions} / ${k.churned_subscriptions}`, `Churn ${k.churn_rate}%`],
                ["Open quotations", String(k.open_quotations), `Pipeline ${formatMoney(s("pipeline_mrr"), { compact: true })}/mo`],
                ["Invoiced", formatMoney(s("invoiced")), `${k.invoice_count} invoices`],
                ["Collected", formatMoney(s("collected")), `${k.payment_count} payments · ${k.collection_rate ?? "—"}% of invoiced`],
                ["Outstanding", formatMoney(s("outstanding")), `${k.outstanding_count} unpaid invoices`],
                ["Overdue", formatMoney(s("overdue")), `${k.overdue_count} invoices past due`],
              ].map(([label, value, hint]) => (
                <div key={label} className="px-5 py-4">
                  <div className="text-xs text-slate-500">{label}</div>
                  <div className="tabular mt-1 text-xl font-semibold">{value}</div>
                  <div className="text-xs text-slate-500">{hint}</div>
                </div>
              ))}
            </div>
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Monthly invoiced vs collected">
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={d.trend.map((t) => ({ month: monthLabel(t.month), invoiced: toChartNumber(t.invoiced), collected: toChartNumber(t.collected) }))}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                    <XAxis dataKey="month" tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                    <YAxis tickFormatter={(v: number) => formatMoney(String(Math.round(v)), { compact: true })} tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} width={64} />
                    <Tooltip content={<MoneyTooltip />} cursor={{ fill: "rgba(99,102,241,0.06)" }} />
                    <Bar dataKey="invoiced" fill="#6366f1" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="collected" fill="#10b981" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card title="Receivables ageing" padded={false}>
              <Table head={<><th className="th">Bucket</th><th className="th text-right">Amount</th></>}>
                {d.aging.map((a) => <tr key={a.bucket}><td className="td">{a.bucket}</td><td className="td text-right font-medium"><Money value={a.amount} /></td></tr>)}
                <tr className="bg-slate-50 dark:bg-slate-900/60"><td className="td font-semibold">Total outstanding</td><td className="td text-right font-semibold"><Money value={s("outstanding")} /></td></tr>
              </Table>
              <div className="px-5 py-3 text-right"><Link to="/invoices?tab=OVERDUE" className="text-sm font-medium text-brand-600 hover:underline">Chase overdue invoices →</Link></div>
            </Card>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <Card title="MRR by plan" padded={false}>
              <Table head={<><th className="th">Plan</th><th className="th text-right">Subs</th><th className="th text-right">MRR</th></>} empty={d.mrr_by_plan.length === 0 && <Empty title="No active subscriptions" />}>
                {d.mrr_by_plan.map((p) => <tr key={p.plan_id}><td className="td">{p.plan}</td><td className="td tabular text-right">{p.subscriptions}</td><td className="td text-right font-medium"><Money value={p.mrr} /></td></tr>)}
              </Table>
            </Card>
            <Card title="Top customers by MRR" padded={false}>
              {customers.isLoading ? <Loading /> : (
                <Table head={<><th className="th">Customer</th><th className="th text-right">MRR</th></>}>
                  {customers.data?.top_by_mrr.map((c) => <tr key={c.customer_id}><td className="td"><Link to={`/customers/${c.customer_id}`} className="hover:underline">{c.customer}</Link></td><td className="td text-right font-medium"><Money value={c.mrr} /></td></tr>)}
                </Table>
              )}
            </Card>
            <Card title="Who owes the most" padded={false}>
              {customers.isLoading ? <Loading /> : (
                <Table head={<><th className="th">Customer</th><th className="th text-right">Due</th><th className="th text-right">Overdue</th></>}>
                  {customers.data?.top_by_owed.map((c) => <tr key={c.customer_id}><td className="td"><Link to={`/customers/${c.customer_id}`} className="hover:underline">{c.customer}</Link><div className="text-xs text-slate-500">{c.invoices} invoices</div></td><td className="td text-right"><Money value={c.due} /></td><td className="td text-right text-rose-600"><Money value={c.overdue} /></td></tr>)}
                </Table>
              )}
            </Card>
          </div>

          <Card title="Payments by method" padded={false}>
            <Table head={<><th className="th">Method</th><th className="th text-right">Payments</th><th className="th text-right">Amount</th></>} empty={d.payment_methods.length === 0 && <Empty title="No payments in this period" />}>
              {d.payment_methods.map((m) => <tr key={m.method}><td className="td">{m.label}</td><td className="td tabular text-right">{m.count}</td><td className="td text-right font-medium"><Money value={m.amount} /></td></tr>)}
            </Table>
          </Card>
        </div>
      )}
    </>
  );
}
