import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowDownRight, ArrowUpRight, Banknote, CalendarClock, CircleDollarSign, FileWarning, Hourglass, Repeat, TrendingUp, Users } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Card, Empty, ErrorBox, formatDate, Loading, Money, PageHeader, Select, Stat, timeAgo } from "../components/ui";
import { get } from "../lib/api";
import { usePlans } from "../lib/hooks";
import { formatMoney, isZero, toChartNumber } from "../lib/money";
import type { Activity, Invoice, Subscription } from "../lib/types";

export interface DashboardData {
  period: { from: string; to: string };
  kpis: Record<string, string | number | null>;
  subscriptions_by_status: Record<string, number>;
  trend: { month: string; invoiced: string; collected: string }[];
  mrr_by_plan: { plan_id: number; plan: string; subscriptions: number; mrr: string }[];
  aging: { bucket: string; amount: string }[];
  payment_methods: { method: string; label: string; count: number; amount: string }[];
  overdue_invoices: Invoice[];
  upcoming_renewals: Subscription[];
  recent_activity: Activity[];
}

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export function periodRange(key: string): { date_from: string; date_to: string } {
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth();
  switch (key) {
    case "last_month":
      return { date_from: iso(new Date(y, m - 1, 1)), date_to: iso(new Date(y, m, 0)) };
    case "quarter": {
      const q = Math.floor(m / 3) * 3;
      return { date_from: iso(new Date(y, q, 1)), date_to: iso(now) };
    }
    case "ytd":
      return { date_from: iso(new Date(y, 0, 1)), date_to: iso(now) };
    case "12m":
      return { date_from: iso(new Date(y, m - 11, 1)), date_to: iso(now) };
    default:
      return { date_from: iso(new Date(y, m, 1)), date_to: iso(now) };
  }
}

export const PERIODS = [
  { value: "month", label: "This month" },
  { value: "last_month", label: "Last month" },
  { value: "quarter", label: "This quarter" },
  { value: "ytd", label: "Year to date" },
  { value: "12m", label: "Last 12 months" },
];

const AGING_COLORS = ["#10b981", "#f59e0b", "#f97316", "#ef4444", "#b91c1c"];

export function MoneyTooltip({ active, payload, label }: { active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg dark:border-slate-700 dark:bg-slate-900">
      {label && <div className="mb-1 font-medium">{label}</div>}
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2">
          <span className="size-2 rounded-full" style={{ background: p.color }} />
          <span className="text-slate-500 capitalize">{p.name}</span>
          <span className="tabular ml-auto font-medium">{formatMoney(p.value.toFixed(2))}</span>
        </div>
      ))}
    </div>
  );
}

export const monthLabel = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { month: "short", year: "2-digit" });
const axisMoney = (v: number) => formatMoney(String(Math.round(v)), { compact: true });

export function Dashboard() {
  const [period, setPeriod] = useState("month");
  const [plan, setPlan] = useState("");
  const plans = usePlans().data?.results ?? [];
  const range = periodRange(period);
  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard", range, plan],
    queryFn: () => get<DashboardData>("reports/dashboard/", { ...range, plan }),
  });

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle={data ? `${formatDate(data.period.from)} – ${formatDate(data.period.to)}` : "Revenue, subscriptions and collections"}
        actions={
          <>
            <Select value={plan} onChange={(e) => setPlan(e.target.value)} className="w-44" aria-label="Plan">
              <option value="">All plans</option>
              {plans.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
            <Select value={period} onChange={(e) => setPeriod(e.target.value)} className="w-40" aria-label="Period">
              {PERIODS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </Select>
          </>
        }
      />
      <ErrorBox error={error} />
      {isLoading || !data ? <Loading /> : <DashboardBody data={data} />}
    </>
  );
}

function DashboardBody({ data }: { data: DashboardData }) {
  const k = data.kpis;
  const s = (key: string) => String(k[key] ?? "0");
  const trend = data.trend.map((t) => ({ month: monthLabel(t.month), invoiced: toChartNumber(t.invoiced), collected: toChartNumber(t.collected) }));
  const aging = data.aging.map((a) => ({ bucket: a.bucket, amount: toChartNumber(a.amount) }));
  const plans = data.mrr_by_plan.map((p) => ({ ...p, value: toChartNumber(p.mrr) }));

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Active subscriptions"
          value={Number(k.active_subscriptions).toLocaleString("en-IN")}
          icon={<Repeat className="size-5" />}
          to="/subscriptions?tab=ACTIVE"
          hint={
            <span className="flex items-center gap-2">
              <span className="flex items-center text-emerald-600"><ArrowUpRight className="size-3" />{k.new_subscriptions} new</span>
              <span className="flex items-center text-rose-600"><ArrowDownRight className="size-3" />{k.churned_subscriptions} churned</span>
            </span>
          }
        />
        <Stat label="Monthly recurring revenue" value={<Money value={s("mrr")} compact />} icon={<TrendingUp className="size-5" />} hint={<>ARR <Money value={s("arr")} compact /> · ARPA <Money value={s("arpa")} compact /></>} />
        <Stat
          label="Collected"
          value={<Money value={s("collected")} compact />}
          icon={<Banknote className="size-5" />}
          tone="good"
          to="/payments"
          hint={<>of <Money value={s("invoiced")} compact /> invoiced{k.collection_rate !== null && ` · ${k.collection_rate}%`}</>}
        />
        <Stat
          label="Overdue"
          value={<Money value={s("overdue")} compact />}
          icon={<AlertTriangle className="size-5" />}
          tone={isZero(s("overdue")) ? "good" : "bad"}
          to="/invoices?tab=OVERDUE"
          hint={<>{k.overdue_count} invoices · <Money value={s("outstanding")} compact /> outstanding in total</>}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Invoiced vs collected — last 12 months" className="lg:col-span-2">
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trend} margin={{ left: 8, right: 8, top: 8 }}>
                <defs>
                  <linearGradient id="inv" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#6366f1" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="col" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#10b981" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-slate-200 dark:text-slate-800" vertical={false} />
                <XAxis dataKey="month" tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                <YAxis tickFormatter={axisMoney} tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} width={64} />
                <Tooltip content={<MoneyTooltip />} />
                <Area type="monotone" dataKey="invoiced" stroke="#6366f1" strokeWidth={2} fill="url(#inv)" />
                <Area type="monotone" dataKey="collected" stroke="#10b981" strokeWidth={2} fill="url(#col)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex gap-4 text-xs text-slate-500">
            <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-brand-500" />Invoiced</span>
            <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-emerald-500" />Collected</span>
          </div>
        </Card>

        <Card title="Receivables ageing">
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={aging} layout="vertical" margin={{ left: 0, right: 8 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="bucket" width={84} tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                <Tooltip content={<MoneyTooltip />} cursor={{ fill: "transparent" }} />
                <Bar dataKey="amount" radius={[0, 4, 4, 0]} barSize={18}>
                  {aging.map((_, i) => (
                    <Cell key={i} fill={AGING_COLORS[i]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-3 text-sm dark:border-slate-800">
            <span className="text-slate-500">Outstanding</span>
            <Money value={s("outstanding")} className="font-semibold" />
          </div>
        </Card>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Active customers" value={Number(k.active_customers).toLocaleString("en-IN")} icon={<Users className="size-5" />} to="/customers" />
        <Stat label="Churn this period" value={`${k.churn_rate}%`} icon={<ArrowDownRight className="size-5" />} tone={Number(k.churn_rate) > 5 ? "warn" : "default"} hint={<>Lost MRR <Money value={s("churned_mrr")} compact /></>} />
        <Stat label="Open quotations" value={String(k.open_quotations)} icon={<Hourglass className="size-5" />} to="/subscriptions?tab=QUOTATION" hint={<>Pipeline MRR <Money value={s("pipeline_mrr")} compact /></>} />
        <Stat label="Draft invoices to review" value={String(k.draft_invoices)} icon={<FileWarning className="size-5" />} tone={Number(k.draft_invoices) ? "warn" : "good"} to="/invoices?tab=DRAFT" />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="MRR by plan">
          {plans.length === 0 ? (
            <Empty title="No active subscriptions" />
          ) : (
            <ul className="space-y-3">
              {plans.map((p) => {
                const max = Math.max(...plans.map((x) => x.value), 1);
                return (
                  <li key={p.plan_id}>
                    <div className="flex justify-between text-sm">
                      <span className="font-medium">{p.plan}</span>
                      <Money value={p.mrr} className="font-medium" />
                    </div>
                    <div className="mt-1 h-2 rounded-full bg-slate-100 dark:bg-slate-800">
                      <div className="h-2 rounded-full bg-brand-500" style={{ width: `${(p.value / max) * 100}%` }} />
                    </div>
                    <div className="mt-0.5 text-xs text-slate-500">{p.subscriptions.toLocaleString("en-IN")} subscriptions</div>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card title="Overdue — chase these first" padded={false} actions={<Link to="/invoices?tab=OVERDUE" className="text-xs font-medium text-brand-600 hover:underline">View all</Link>}>
          {data.overdue_invoices.length === 0 ? (
            <Empty icon={<CircleDollarSign className="size-5" />} title="Nothing overdue">Every confirmed invoice is within its terms.</Empty>
          ) : (
            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
              {data.overdue_invoices.map((inv) => (
                <li key={inv.id}>
                  <Link to={`/invoices/${inv.id}`} className="flex items-center justify-between gap-3 px-5 py-2.5 hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">{inv.customer_name}</div>
                      <div className="text-xs text-slate-500">{inv.display_number} · due {formatDate(inv.due_date, false)}</div>
                    </div>
                    <div className="text-right">
                      <Money value={inv.amount_due} className="text-sm font-semibold" />
                      <div className="text-xs text-rose-600">{inv.days_overdue} days late</div>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Renewals in the next 30 days" padded={false}>
          {data.upcoming_renewals.length === 0 ? (
            <Empty icon={<CalendarClock className="size-5" />} title="No contracts ending soon" />
          ) : (
            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
              {data.upcoming_renewals.map((sub) => (
                <li key={sub.id}>
                  <Link to={`/subscriptions/${sub.id}`} className="flex items-center justify-between gap-3 px-5 py-2.5 hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">{sub.customer_name}</div>
                      <div className="text-xs text-slate-500">
                        {sub.number} · {sub.plan_name}
                      </div>
                    </div>
                    <div className="text-right text-xs">
                      <div className="font-medium">{formatDate(sub.expiry_date, false)}</div>
                      <Money value={sub.mrr} className="text-slate-500" />/mo
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Payments by method">
          {data.payment_methods.length === 0 ? (
            <Empty title="No payments in this period" />
          ) : (
            <ul className="space-y-2">
              {data.payment_methods.map((m) => (
                <li key={m.method} className="flex items-center justify-between text-sm">
                  <span>
                    {m.label} <span className="text-xs text-slate-500">· {m.count}</span>
                  </span>
                  <Money value={m.amount} className="font-medium" />
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Subscriptions by status">
          <div className="flex flex-wrap gap-2">
            {["DRAFT", "QUOTATION", "CONFIRMED", "ACTIVE", "PAUSED", "CLOSED"].map((st) => (
              <Link key={st} to={`/subscriptions?tab=${st}`} className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 hover:border-brand-300 dark:border-slate-700">
                <Badge status={st} />
                <span className="tabular text-sm font-semibold">{(data.subscriptions_by_status[st] ?? 0).toLocaleString("en-IN")}</span>
              </Link>
            ))}
          </div>
        </Card>
        <Card title="Recent activity" padded={false}>
          <ActivityFeed items={data.recent_activity} />
        </Card>
      </div>
    </div>
  );
}

export function ActivityFeed({ items }: { items: Activity[] }) {
  if (!items.length) return <Empty title="No activity yet" />;
  return (
    <ul className="max-h-80 divide-y divide-slate-100 overflow-y-auto dark:divide-slate-800">
      {items.map((a) => (
        <li key={a.id} className="px-5 py-2.5 text-sm">
          <div>{a.message}</div>
          <div className="text-xs text-slate-500">
            {a.actor_name ?? "System"} · {timeAgo(a.created_at)}
          </div>
        </li>
      ))}
    </ul>
  );
}
