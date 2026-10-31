import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Check, Copy, FilePlus2, Pause, Play, Plus, Receipt, RefreshCw, Search, Send, Trash2, X, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorBox,
  Field,
  formatDate,
  formatDateTime,
  Input,
  InvoiceBadge,
  KeyValue,
  Loading,
  Modal,
  Money,
  PageHeader,
  Pagination,
  Select,
  Table,
  Tabs,
  Textarea,
  timeAgo,
  useDebounced,
} from "../components/ui";
import { get, patch, post, type Page } from "../lib/api";
import { useRole } from "../lib/auth";
import { useAction, useCustomerSearch, useListParams, usePaymentTerms, usePlans, useProducts, useTaxes, useTeam, useTemplates } from "../lib/hooks";
import type { Activity, Invoice, Product, SubscriptionDetail as SubDetail, Subscription, SubscriptionLine } from "../lib/types";

const STATUS_TABS = ["ALL", "DRAFT", "QUOTATION", "CONFIRMED", "ACTIVE", "PAUSED", "CLOSED"] as const;
const label = (s: string) => (s === "ALL" ? "All" : s.charAt(0) + s.slice(1).toLowerCase());

// ===================================================================== list

export function SubscriptionsPage({ portal = false }: { portal?: boolean }) {
  const { value, set, page } = useListParams({ tab: "ALL" });
  const tab = value("tab");
  const [search, setSearch] = useState(value("search"));
  const debounced = useDebounced(search);
  useEffect(() => {
    if (debounced !== value("search")) set({ search: debounced });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);
  const plans = usePlans().data?.results ?? [];
  const filters = { search: value("search"), plan: value("plan"), ordering: value("ordering") || undefined, expiring_within: value("expiring") };
  const { data, isLoading, error } = useQuery({
    queryKey: ["subscriptions", "list", tab, page, filters],
    queryFn: () => get<Page<Subscription>>("subscriptions/", { ...filters, page, status: tab === "ALL" ? undefined : tab }),
    placeholderData: (prev) => prev,
  });
  const { data: stats } = useQuery({
    queryKey: ["subscriptions", "stats", filters],
    queryFn: () => get<Record<string, { count: number; mrr: string }>>("subscriptions/stats/", filters),
    enabled: !portal,
  });
  const total = stats ? Object.values(stats).reduce((a, b) => a + b.count, 0) : undefined;
  const base = portal ? "/portal/subscriptions" : "/subscriptions";

  return (
    <>
      <PageHeader
        title={portal ? "My subscriptions" : "Subscriptions"}
        subtitle={portal ? "Everything you subscribe to, and where each one stands." : "From first quotation to closed — every subscription and where it stands."}
        actions={!portal && <Link to="/subscriptions/new"><Button icon={<Plus className="size-4" />}>New subscription</Button></Link>}
      />
      <div className="card overflow-hidden">
        {!portal && (
          <div className="px-4 pt-2">
            <Tabs value={tab} onChange={(t) => set({ tab: t })} tabs={STATUS_TABS.map((s) => ({ value: s, label: label(s), count: s === "ALL" ? total : (stats?.[s]?.count ?? 0) }))} />
          </div>
        )}
        {!portal && (
          <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-3 dark:border-slate-800">
            <div className="relative min-w-60 flex-1">
              <Search className="absolute top-2.5 left-3 size-4 text-slate-400" />
              <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search number, customer, plan…" className="pl-9" />
            </div>
            <Select value={value("plan")} onChange={(e) => set({ plan: e.target.value })} className="w-44">
              <option value="">All plans</option>
              {plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
            <Select value={value("expiring")} onChange={(e) => set({ expiring: e.target.value })} className="w-44">
              <option value="">Any end date</option>
              <option value="30">Ending in 30 days</option>
              <option value="90">Ending in 90 days</option>
            </Select>
            <Select value={value("ordering")} onChange={(e) => set({ ordering: e.target.value })} className="w-44">
              <option value="">Newest first</option>
              <option value="-mrr">Highest MRR</option>
              <option value="next_invoice_date">Next invoice soonest</option>
              <option value="expiry_date">Ending soonest</option>
              <option value="number">Number</option>
            </Select>
          </div>
        )}
        <ErrorBox error={error} />
        {isLoading ? (
          <Loading />
        ) : (
          <Table
            head={
              <>
                <th className="th">Number</th>
                {!portal && <th className="th">Customer</th>}
                <th className="th">Plan</th>
                <th className="th">Status</th>
                <th className="th">Start</th>
                <th className="th">Next invoice</th>
                <th className="th">Ends</th>
                <th className="th text-right">Per period</th>
                {!portal && <th className="th text-right">MRR</th>}
              </>
            }
            empty={data?.results.length === 0 && <Empty icon={<Receipt className="size-5" />} title="No subscriptions here">{portal ? "When Brightloop sends you a quotation it will appear here." : "Try another tab or clear the filters."}</Empty>}
          >
            {data?.results.map((s) => (
              <tr key={s.id} className="cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/40">
                <td className="td font-medium"><Link to={`${base}/${s.id}`} className="text-brand-600 hover:underline">{s.number}</Link></td>
                {!portal && <td className="td max-w-56 truncate">{s.customer_name}</td>}
                <td className="td">
                  <div>{s.plan_name}</div>
                  <div className="text-xs text-slate-500">{s.billing_label}</div>
                </td>
                <td className="td">
                  <Badge status={s.status} />
                  {s.quotation_expired && <span className="ml-1 text-xs text-rose-600">expired</span>}
                  {s.is_expired && s.status === "ACTIVE" && <span className="ml-1 text-xs text-amber-600">ended</span>}
                </td>
                <td className="td tabular">{formatDate(s.start_date)}</td>
                <td className="td tabular">{s.status === "ACTIVE" ? formatDate(s.next_invoice_date) : "—"}</td>
                <td className="td tabular">{s.expiry_date ? formatDate(s.expiry_date) : <span className="text-slate-400">Open-ended</span>}</td>
                <td className="td text-right"><Money value={s.total} /></td>
                {!portal && <td className="td text-right text-slate-500"><Money value={s.mrr} /></td>}
              </tr>
            ))}
          </Table>
        )}
        {data && <Pagination page={page} count={data.count} onPage={(p) => set({ page: p })} />}
      </div>
    </>
  );
}

// ===================================================================== detail

const STEPS = ["DRAFT", "QUOTATION", "CONFIRMED", "ACTIVE", "CLOSED"] as const;

function Stepper({ sub }: { sub: SubDetail }) {
  const current = sub.status === "PAUSED" ? "ACTIVE" : sub.status;
  const index = STEPS.indexOf(current as (typeof STEPS)[number]);
  const dates: Record<string, string | null> = {
    DRAFT: sub.created_at,
    QUOTATION: sub.quotation_sent_at,
    CONFIRMED: sub.confirmed_at,
    ACTIVE: sub.activated_at,
    CLOSED: sub.closed_at,
  };
  return (
    <ol className="flex items-center">
      {STEPS.map((step, i) => {
        const done = i < index || (i === index && step === "CLOSED");
        const here = i === index;
        return (
          <li key={step} className="flex flex-1 items-center last:flex-none">
            <div className="flex flex-col items-center gap-1">
              <span
                className={clsx(
                  "flex size-8 items-center justify-center rounded-full border-2 text-xs font-semibold",
                  done && "border-brand-600 bg-brand-600 text-white",
                  here && !done && (sub.status === "PAUSED" ? "border-amber-500 bg-amber-50 text-amber-600" : "border-brand-600 bg-brand-50 text-brand-700 dark:bg-brand-900/40"),
                  !done && !here && "border-slate-200 text-slate-400 dark:border-slate-700",
                )}
              >
                {done ? <Check className="size-4" /> : here && sub.status === "PAUSED" ? <Pause className="size-3.5" /> : i + 1}
              </span>
              <span className={clsx("text-xs font-medium", here ? "text-slate-900 dark:text-white" : "text-slate-500")}>{here && sub.status === "PAUSED" ? "Paused" : label(step)}</span>
              <span className="h-4 text-[10px] text-slate-400">{dates[step] && i <= index ? formatDate(dates[step], false) : ""}</span>
            </div>
            {i < STEPS.length - 1 && <div className={clsx("mx-2 mb-8 h-0.5 flex-1", i < index ? "bg-brand-600" : "bg-slate-200 dark:bg-slate-700")} />}
          </li>
        );
      })}
    </ol>
  );
}

interface Upcoming {
  period_start: string;
  period_end: string;
  prorated: boolean;
  lines: { description: string; quantity: string; unit_price: string; discount_amount: string; tax_amount: string; total: string }[];
  discounts: { name: string; amount: string }[];
  untaxed_amount: string;
  discount_amount: string;
  tax_amount: string;
  total: string;
}

export function SubscriptionDetail({ portal = false }: { portal?: boolean }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const { isInternal } = useRole();
  const key = ["subscription", id];
  const { data: sub, isLoading, error } = useQuery({ queryKey: key, queryFn: () => get<SubDetail>(`subscriptions/${id}/`) });
  const { data: invoices } = useQuery({
    queryKey: ["invoices", "for-sub", id],
    queryFn: () => get<Page<Invoice>>("invoices/", { subscription: id, page_size: 50 }),
    enabled: !!sub,
  });
  const { data: upcoming } = useQuery({
    queryKey: ["subscription", id, "upcoming"],
    queryFn: () => get<Upcoming | null>(`subscriptions/${id}/upcoming-invoice/`),
    enabled: !!sub && ["ACTIVE", "CONFIRMED", "QUOTATION", "DRAFT", "PAUSED"].includes(sub.status),
  });
  const { data: activity } = useQuery({
    queryKey: ["subscription", id, "activity"],
    queryFn: () => get<Activity[]>(`subscriptions/${id}/activity/`),
    enabled: !!sub && isInternal,
  });
  const [modal, setModal] = useState<"" | "close" | "accept" | "invoice">("");
  const [reason, setReason] = useState("");
  const [signer, setSigner] = useState("");
  const invalidate = [key, ["subscriptions"], ["invoices"], ["dashboard"], ["portal"]];
  const act = useAction(({ action, body }: { action: string; body?: unknown }) => post<SubDetail>(`subscriptions/${id}/${action}/`, body), {
    invalidate,
    success: (s) => `${s.number} is now ${s.status_label.toLowerCase()}`,
    onSuccess: () => setModal(""),
  });
  const dup = useAction(() => post<SubDetail>(`subscriptions/${id}/duplicate/`), {
    invalidate,
    success: (s) => `Copied to ${s.number}`,
    onSuccess: (s) => navigate(`/subscriptions/${s.id}`),
  });
  const invoiceNow = useAction((confirm: boolean) => post<Invoice>(`subscriptions/${id}/invoice-now/`, { confirm }), {
    invalidate,
    success: (inv) => `Invoice ${inv.display_number} created`,
    onSuccess: (inv) => navigate(`/invoices/${inv.id}`),
  });

  if (isLoading) return <Loading />;
  if (error || !sub) return <ErrorBox error={error ?? "Not found"} />;
  const can = (a: string) => sub.allowed_actions.includes(a);
  const run = (action: string, body?: unknown) => act.mutate({ action, body });
  const plan = sub.plan_detail;
  const busy = act.isPending;

  return (
    <>
      <PageHeader
        back={portal ? "/portal/subscriptions" : "/subscriptions"}
        title={
          <span className="flex items-center gap-3">
            {sub.number} <Badge status={sub.status} />
          </span>
        }
        subtitle={
          <>
            {portal ? sub.plan_name : <Link to={`/customers/${sub.customer}`} className="hover:underline">{sub.customer_name}</Link>} · {sub.plan_name} · {sub.billing_label}
          </>
        }
        actions={
          <>
            {can("edit") && <Link to={`/subscriptions/${sub.id}/edit`}><Button variant="secondary">Edit</Button></Link>}
            {can("send_quotation") && (
              <Button variant={sub.status === "DRAFT" ? "primary" : "secondary"} icon={<Send className="size-4" />} loading={busy} onClick={() => run("send-quotation")}>
                {sub.status === "QUOTATION" ? "Resend quotation" : "Send quotation"}
              </Button>
            )}
            {can("confirm") && <Button icon={<Check className="size-4" />} loading={busy} onClick={() => run("confirm")}>Confirm</Button>}
            {can("accept") && <Button variant="success" icon={<Check className="size-4" />} onClick={() => setModal("accept")}>Accept quotation</Button>}
            {can("activate") && <Button icon={<Play className="size-4" />} loading={busy} onClick={() => run("activate")}>Activate now</Button>}
            {can("invoice_now") && <Button variant="secondary" icon={<FilePlus2 className="size-4" />} onClick={() => setModal("invoice")}>Invoice now</Button>}
            {can("pause") && <Button variant="secondary" icon={<Pause className="size-4" />} loading={busy} onClick={() => run("pause")}>Pause</Button>}
            {can("resume") && <Button icon={<Play className="size-4" />} loading={busy} onClick={() => run("resume")}>Resume</Button>}
            {can("renew") && <Button variant="secondary" icon={<RefreshCw className="size-4" />} loading={busy} onClick={() => run("renew")}>Renew</Button>}
            {can("duplicate") && <Button variant="ghost" icon={<Copy className="size-4" />} loading={dup.isPending} onClick={() => dup.mutate(undefined)}>Duplicate</Button>}
            {can("close") && <Button variant="ghost" className="text-rose-600" icon={<XCircle className="size-4" />} onClick={() => setModal("close")}>Close</Button>}
          </>
        }
      />

      <div className="card mb-6 px-6 pt-6 pb-2">
        <Stepper sub={sub} />
      </div>

      {sub.status === "QUOTATION" && (
        <div className={clsx("mb-6 rounded-xl border px-5 py-4 text-sm", sub.quotation_expired ? "border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-300" : "border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-300")}>
          {sub.quotation_expired
            ? `This quotation expired on ${formatDate(sub.quotation_valid_until)}. ${isInternal ? "Resend it to give the customer a fresh validity period." : "Please contact Brightloop for an updated offer."}`
            : `Quotation valid until ${formatDate(sub.quotation_valid_until)}. ${portal ? "Review the lines below and accept online when you are ready." : "The customer can accept it from their portal."}`}
        </div>
      )}
      {sub.status === "ACTIVE" && sub.is_expired && (
        <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300">
          This subscription reached its end date on {formatDate(sub.expiry_date)} and is no longer billed. {plan.renewable ? "Renew it to continue, or close it." : "Close it to finish."}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card title="Lines" padded={false}>
            <Table
              head={
                <>
                  <th className="th">Product</th>
                  <th className="th text-right">Qty</th>
                  <th className="th text-right">Unit price</th>
                  <th className="th">Taxes</th>
                  <th className="th text-right">Amount</th>
                </>
              }
            >
              {sub.lines.map((l) => (
                <tr key={l.id}>
                  <td className="td">
                    <div className="font-medium">{l.description}</div>
                    {!l.product && <div className="text-xs text-slate-500">Plan fee</div>}
                  </td>
                  <td className="td tabular text-right">{Number(l.quantity).toLocaleString("en-IN")}</td>
                  <td className="td text-right"><Money value={l.unit_price} /></td>
                  <td className="td text-xs text-slate-500">{l.tax_names?.join(", ") || "—"}</td>
                  <td className="td text-right font-medium"><Money value={l.subtotal} /></td>
                </tr>
              ))}
            </Table>
            <div className="flex justify-end border-t border-slate-100 px-5 py-4 dark:border-slate-800">
              <dl className="w-64 space-y-1 text-sm">
                <div className="flex justify-between"><dt className="text-slate-500">Untaxed</dt><dd><Money value={sub.untaxed_amount} /></dd></div>
                <div className="flex justify-between"><dt className="text-slate-500">Taxes</dt><dd><Money value={sub.tax_amount} /></dd></div>
                <div className="flex justify-between border-t border-slate-200 pt-1 text-base font-semibold dark:border-slate-700"><dt>Total {plan.billing_label}</dt><dd><Money value={sub.total} /></dd></div>
              </dl>
            </div>
          </Card>

          {upcoming && (
            <Card
              title={sub.status === "ACTIVE" ? "Next invoice preview" : "First invoice preview"}
              actions={<span className="text-xs text-slate-500">{formatDate(upcoming.period_start)} – {formatDate(upcoming.period_end)}{upcoming.prorated && " · prorated"}</span>}
            >
              <div className="flex flex-wrap items-end justify-between gap-4">
                <div className="space-y-1 text-sm">
                  {upcoming.discounts.length > 0 ? (
                    upcoming.discounts.map((d) => (
                      <div key={d.name} className="flex items-center gap-2 text-emerald-700 dark:text-emerald-400">
                        <Check className="size-4" /> {d.name} applies automatically: −<Money value={d.amount} />
                      </div>
                    ))
                  ) : (
                    <div className="text-slate-500">No discount rules apply to the next period.</div>
                  )}
                  <div className="text-slate-500">Untaxed <Money value={upcoming.untaxed_amount} /> · discount <Money value={upcoming.discount_amount} /> · tax <Money value={upcoming.tax_amount} /></div>
                </div>
                <div className="text-right">
                  <div className="text-xs text-slate-500">Estimated total</div>
                  <Money value={upcoming.total} className="text-2xl font-semibold" />
                </div>
              </div>
            </Card>
          )}

          <Card title="Invoices" padded={false}>
            {!invoices || invoices.results.length === 0 ? (
              <Empty title="No invoices yet">{sub.status === "ACTIVE" ? `The next one is due on ${formatDate(sub.next_invoice_date)}.` : "Invoices start once the subscription is active."}</Empty>
            ) : (
              <Table
                head={
                  <>
                    <th className="th">Invoice</th>
                    <th className="th">Period</th>
                    <th className="th">Status</th>
                    <th className="th text-right">Total</th>
                    <th className="th text-right">Due</th>
                  </>
                }
              >
                {invoices.results.map((inv) => (
                  <tr key={inv.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                    <td className="td font-medium"><Link className="text-brand-600 hover:underline" to={`${portal ? "/portal" : ""}/invoices/${inv.id}`}>{inv.display_number}</Link></td>
                    <td className="td text-xs text-slate-500">{formatDate(inv.period_start, false)} – {formatDate(inv.period_end)}</td>
                    <td className="td"><InvoiceBadge status={inv.status} overdue={inv.is_overdue} days={inv.days_overdue} /></td>
                    <td className="td text-right"><Money value={inv.total} /></td>
                    <td className="td text-right"><Money value={inv.amount_due} /></td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="Details">
            <KeyValue
              items={[
                ["Customer", sub.customer_detail.company || sub.customer_detail.name],
                ["Plan", sub.plan_name],
                ["Start date", formatDate(sub.start_date)],
                ["Expiry date", sub.expiry_date ? formatDate(sub.expiry_date) : "Open-ended"],
                ["Next invoice", sub.status === "ACTIVE" && !sub.is_expired ? formatDate(sub.next_invoice_date) : "—"],
                ["Payment terms", sub.payment_term_name ?? "Immediate"],
                ...(portal ? [] : ([["Salesperson", sub.salesperson_name ?? "—"], ["Template", sub.template_name ?? "—"], ["MRR", <Money key="m" value={sub.mrr} />]] as [string, React.ReactNode][])),
                ...(sub.renewal_count ? ([["Renewals", String(sub.renewal_count)]] as [string, string][]) : []),
                ...(sub.accepted_by_name ? ([["Accepted online by", `${sub.accepted_by_name}, ${formatDate(sub.accepted_at)}`]] as [string, string][]) : []),
                ...(sub.close_reason ? ([["Closed", `${formatDate(sub.closed_at)} · ${sub.close_reason}`]] as [string, string][]) : []),
              ]}
            />
          </Card>
          <Card title="Plan rules">
            <ul className="space-y-1.5 text-sm">
              {[
                [plan.auto_close, "Closes automatically when it ends"],
                [plan.closable, "Can be closed early"],
                [plan.pausable, "Can be paused"],
                [plan.renewable, "Can be renewed"],
              ].map(([ok, text]) => (
                <li key={String(text)} className={clsx("flex items-center gap-2", ok ? "" : "text-slate-400 line-through")}>
                  {ok ? <Check className="size-4 text-emerald-600" /> : <X className="size-4" />} {text}
                </li>
              ))}
              <li className="pt-1 text-xs text-slate-500">Minimum quantity {Number(plan.min_quantity)}</li>
            </ul>
          </Card>
          {sub.terms && (
            <Card title="Terms">
              <p className="text-sm whitespace-pre-line text-slate-600 dark:text-slate-300">{sub.terms}</p>
            </Card>
          )}
          {!portal && sub.notes && (
            <Card title="Internal notes">
              <p className="text-sm whitespace-pre-line text-slate-600 dark:text-slate-300">{sub.notes}</p>
            </Card>
          )}
          {activity && (
            <Card title="Timeline" padded={false}>
              <ol className="max-h-96 space-y-0 overflow-y-auto px-5 py-3">
                {activity.map((a) => (
                  <li key={a.id} className="relative border-l border-slate-200 pb-4 pl-4 last:pb-0 dark:border-slate-700">
                    <span className="absolute top-1 -left-[5px] size-2.5 rounded-full border-2 border-white bg-brand-500 dark:border-slate-900" />
                    <div className="text-sm">{a.message}</div>
                    <div className="text-xs text-slate-500" title={formatDateTime(a.created_at)}>{a.actor_name ?? "System"} · {timeAgo(a.created_at)}</div>
                  </li>
                ))}
              </ol>
            </Card>
          )}
        </div>
      </div>

      <Modal
        open={modal === "close"}
        onClose={() => setModal("")}
        title={`Close ${sub.number}?`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setModal("")}>Keep it</Button>
            <Button variant="danger" loading={busy} onClick={() => run("close", { reason })}>Close subscription</Button>
          </>
        }
      >
        <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">Billing stops. Invoices already issued stay as they are.</p>
        <Field label="Reason (optional)">
          <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Moved to annual plan" />
        </Field>
      </Modal>
      <Modal
        open={modal === "accept"}
        onClose={() => setModal("")}
        title="Accept quotation"
        footer={
          <>
            <Button variant="secondary" onClick={() => setModal("")}>Cancel</Button>
            <Button variant="success" disabled={signer.trim().length < 2} loading={busy} onClick={() => run("accept", { name: signer })}>I accept</Button>
          </>
        }
      >
        <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">
          You are accepting <strong>{sub.number}</strong> for <Money value={sub.total} /> {plan.billing_label}, starting {formatDate(sub.start_date)}. Type your full name to sign.
        </p>
        <Field label="Full name">
          <Input value={signer} onChange={(e) => setSigner(e.target.value)} autoFocus />
        </Field>
      </Modal>
      <Modal
        open={modal === "invoice"}
        onClose={() => setModal("")}
        title="Invoice the next period now"
        footer={
          <>
            <Button variant="secondary" loading={invoiceNow.isPending} onClick={() => invoiceNow.mutate(false)}>Create draft</Button>
            <Button loading={invoiceNow.isPending} onClick={() => invoiceNow.mutate(true)}>Create and confirm</Button>
          </>
        }
      >
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Bills {upcoming ? `${formatDate(upcoming.period_start)} – ${formatDate(upcoming.period_end)}` : "the next period"} ahead of the billing run. The billing run will not bill this period again.
        </p>
      </Modal>
    </>
  );
}

// ===================================================================== form

type LineForm = SubscriptionLine & { key: number };
let lineKey = 1;

function productPrice(p: Product | undefined, variantId: number | null): string {
  if (!p) return "";
  const v = p.variants.find((x) => x.id === variantId);
  if (!v) return p.sales_price;
  // Both are 2-decimal strings: add as integer paise, no floats.
  const paise = (s: string) => BigInt(s.replace(".", "").replace(/^(-?)0+(?=\d)/, "$1"));
  const total = paise(p.sales_price) + paise(v.extra_price);
  const str = total.toString().padStart(3, "0");
  return `${str.slice(0, -2)}.${str.slice(-2)}`;
}

export function SubscriptionForm() {
  const { id } = useParams();
  const editing = !!id;
  const navigate = useNavigate();
  const plans = (usePlans().data?.results ?? []).filter((p) => p.is_active);
  const products = (useProducts().data?.results ?? []).filter((p) => p.is_active);
  const taxes = useTaxes().data ?? [];
  const terms = usePaymentTerms().data ?? [];
  const templates = (useTemplates().data ?? []).filter((t) => t.is_active);
  const team = useTeam().data?.results ?? [];
  const existing = useQuery({ queryKey: ["subscription", id], queryFn: () => get<SubDetail>(`subscriptions/${id}/`), enabled: editing });

  const [customerSearch, setCustomerSearch] = useState("");
  const customers = useCustomerSearch(useDebounced(customerSearch)).data?.results ?? [];
  const [form, setForm] = useState({
    customer: "",
    customer_label: "",
    template: "",
    plan: "",
    start_date: new Date().toISOString().slice(0, 10),
    expiry_date: "",
    payment_term: "",
    salesperson: "",
    notes: "",
    terms: "",
  });
  const [lines, setLines] = useState<LineForm[]>([]);

  useEffect(() => {
    const s = existing.data;
    if (!s) return;
    setForm({
      customer: String(s.customer),
      customer_label: s.customer_name,
      template: "",
      plan: String(s.plan),
      start_date: s.start_date,
      expiry_date: s.expiry_date ?? "",
      payment_term: s.payment_term ? String(s.payment_term) : "",
      salesperson: s.salesperson ? String(s.salesperson) : "",
      notes: s.notes ?? "",
      terms: s.terms,
    });
    setLines(s.lines.map((l) => ({ ...l, key: lineKey++ })));
  }, [existing.data]);

  const template = templates.find((t) => String(t.id) === form.template);
  const plan = plans.find((p) => String(p.id) === (template ? String(template.plan) : form.plan));
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const setLine = (key: number, patchData: Partial<LineForm>) => setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...patchData } : l)));

  const save = useAction(
    () => {
      const body = {
        customer: Number(form.customer),
        plan: plan?.id,
        template: form.template ? Number(form.template) : null,
        start_date: form.start_date,
        expiry_date: form.expiry_date || null,
        payment_term: form.payment_term ? Number(form.payment_term) : null,
        salesperson: form.salesperson ? Number(form.salesperson) : null,
        notes: form.notes,
        terms: form.terms,
        ...(lines.length || editing
          ? {
              lines: lines.map((l) => ({
                product: l.product,
                variant: l.variant,
                description: l.description,
                quantity: l.quantity,
                unit_price: l.unit_price || null,
                taxes: l.taxes,
              })),
            }
          : {}),
      };
      return editing ? patch<SubDetail>(`subscriptions/${id}/`, body) : post<SubDetail>("subscriptions/", body);
    },
    { success: (s) => `${s.number} saved`, invalidate: [["subscriptions"], ["subscription", id ?? ""]], onSuccess: (s) => navigate(`/subscriptions/${s.id}`) },
  );

  const totalQty = useMemo(() => lines.reduce((a, l) => a + Number(l.quantity || 0), 0), [lines]);
  if (editing && existing.isLoading) return <Loading />;

  return (
    <>
      <PageHeader back="/subscriptions" title={editing ? `Edit ${existing.data?.number}` : "New subscription"} subtitle="Start from a quotation template, or build the lines yourself." />
      <ErrorBox error={save.error} />
      <div className="mt-4 grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card title="Customer & plan">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Customer" className="sm:col-span-2">
                {form.customer ? (
                  <div className="flex items-center justify-between rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700">
                    <span className="font-medium">{form.customer_label}</span>
                    {!editing || existing.data?.status === "DRAFT" ? (
                      <button className="text-xs text-brand-600" onClick={() => setForm((f) => ({ ...f, customer: "", customer_label: "" }))}>Change</button>
                    ) : null}
                  </div>
                ) : (
                  <div className="relative">
                    <Input value={customerSearch} onChange={(e) => setCustomerSearch(e.target.value)} placeholder="Search customers by name, company or email…" />
                    {customers.length > 0 && (
                      <ul className="absolute z-10 mt-1 max-h-60 w-full overflow-y-auto rounded-lg border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
                        {customers.map((c) => (
                          <li key={c.id}>
                            <button
                              className="w-full px-3 py-2 text-left text-sm hover:bg-slate-50 dark:hover:bg-slate-800"
                              onClick={() => setForm((f) => ({ ...f, customer: String(c.id), customer_label: c.company ? `${c.company} (${c.name})` : c.name }))}
                            >
                              <div className="font-medium">{c.company || c.name}</div>
                              <div className="text-xs text-slate-500">{c.email}</div>
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </Field>
              {!editing && (
                <Field label="Quotation template" hint={template ? `Valid ${template.validity_days} days · ${template.lines.length} lines · ${template.plan_name}` : "Optional — fills in the plan, lines and terms"}>
                  <Select value={form.template} onChange={set("template")}>
                    <option value="">No template</option>
                    {templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </Select>
                </Field>
              )}
              <Field label="Recurring plan" hint={plan ? `${plan.billing_label} · min qty ${Number(plan.min_quantity)}${Number(plan.price) ? ` · base fee per unit` : ""}` : undefined}>
                <Select value={template ? String(template.plan) : form.plan} onChange={set("plan")} disabled={!!template}>
                  <option value="">Choose a plan…</option>
                  {plans.map((p) => <option key={p.id} value={p.id} disabled={!p.is_available}>{p.name}{!p.is_available ? " (not on sale)" : ""}</option>)}
                </Select>
              </Field>
              <Field label="Start date">
                <Input type="date" value={form.start_date} onChange={set("start_date")} />
              </Field>
              <Field label="Expiry date" hint={template?.duration_months ? `Template default: ${template.duration_months} months` : "Leave empty for open-ended"}>
                <Input type="date" value={form.expiry_date} onChange={set("expiry_date")} min={form.start_date} />
              </Field>
              <Field label="Payment terms">
                <Select value={form.payment_term} onChange={set("payment_term")}>
                  <option value="">{template?.payment_term_name ? `${template.payment_term_name} (template)` : "Immediate"}</option>
                  {terms.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </Select>
              </Field>
              <Field label="Salesperson">
                <Select value={form.salesperson} onChange={set("salesperson")}>
                  <option value="">Me</option>
                  {team.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                </Select>
              </Field>
            </div>
          </Card>

          <Card
            title="Lines"
            actions={
              <Button size="sm" variant="secondary" icon={<Plus className="size-3.5" />} onClick={() => setLines((ls) => [...ls, { key: lineKey++, product: null, variant: null, description: "", quantity: "1", unit_price: "", taxes: undefined }])}>
                Add line
              </Button>
            }
            padded={false}
          >
            {lines.length === 0 ? (
              <Empty title={template ? `Lines come from “${template.name}”` : "No lines yet"}>
                {template ? "You can edit them after the draft is created." : plan && Number(plan.price) ? "The plan's base fee is added automatically. Add products for anything else." : "Add the products this customer subscribes to."}
              </Empty>
            ) : (
              <div className="divide-y divide-slate-100 dark:divide-slate-800">
                {lines.map((line) => {
                  const product = products.find((p) => p.id === line.product);
                  return (
                    <div key={line.key} className="grid grid-cols-12 items-end gap-2 px-5 py-3">
                      <Field label="Product" className="col-span-12 sm:col-span-4">
                        <Select
                          value={line.product ?? ""}
                          onChange={(e) => {
                            const p = products.find((x) => x.id === Number(e.target.value));
                            setLine(line.key, { product: p ? p.id : null, variant: null, unit_price: p ? p.sales_price : line.unit_price, taxes: p ? p.taxes : line.taxes, description: p ? p.name : line.description });
                          }}
                        >
                          <option value="">Plan fee / custom</option>
                          {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                        </Select>
                      </Field>
                      <Field label="Variant" className="col-span-6 sm:col-span-2">
                        <Select
                          value={line.variant ?? ""}
                          disabled={!product?.variants.length}
                          onChange={(e) => {
                            const v = e.target.value ? Number(e.target.value) : null;
                            const variant = product?.variants.find((x) => x.id === v);
                            setLine(line.key, { variant: v, unit_price: productPrice(product, v), description: product ? product.name + (variant ? ` (${variant.attribute}: ${variant.value})` : "") : line.description });
                          }}
                        >
                          <option value="">—</option>
                          {product?.variants.map((v) => <option key={v.id} value={v.id}>{v.value}{Number(v.extra_price) ? ` +${v.extra_price}` : ""}</option>)}
                        </Select>
                      </Field>
                      <Field label="Qty" className="col-span-6 sm:col-span-1">
                        <Input inputMode="decimal" value={line.quantity} onChange={(e) => setLine(line.key, { quantity: e.target.value })} />
                      </Field>
                      <Field label="Unit price" className="col-span-6 sm:col-span-2">
                        <Input inputMode="decimal" value={line.unit_price ?? ""} onChange={(e) => setLine(line.key, { unit_price: e.target.value })} placeholder={product?.sales_price} />
                      </Field>
                      <Field label="Tax" className="col-span-5 sm:col-span-2">
                        <Select value={line.taxes?.[0] ?? ""} onChange={(e) => setLine(line.key, { taxes: e.target.value ? [Number(e.target.value)] : [] })}>
                          <option value="">No tax</option>
                          {taxes.filter((t) => t.is_active).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                        </Select>
                      </Field>
                      <div className="col-span-1 flex justify-end pb-1">
                        <button onClick={() => setLines((ls) => ls.filter((l) => l.key !== line.key))} className="rounded p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600" aria-label="Remove line">
                          <Trash2 className="size-4" />
                        </button>
                      </div>
                      <Field className="col-span-12" label="">
                        <Input value={line.description} onChange={(e) => setLine(line.key, { description: e.target.value })} placeholder="Description" className="text-xs" />
                      </Field>
                    </div>
                  );
                })}
              </div>
            )}
            {plan && lines.length > 0 && totalQty < Number(plan.min_quantity) && (
              <div className="border-t border-amber-200 bg-amber-50 px-5 py-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300">
                The {plan.name} plan needs a total quantity of at least {Number(plan.min_quantity)} before it can be sent.
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="Notes">
            <div className="space-y-4">
              <Field label="Terms shown to the customer">
                <Textarea value={form.terms} onChange={set("terms")} rows={4} placeholder={template?.notes} />
              </Field>
              <Field label="Internal notes">
                <Textarea value={form.notes} onChange={set("notes")} rows={3} />
              </Field>
            </div>
          </Card>
          <div className="card space-y-2 p-5">
            <Button className="w-full" loading={save.isPending} disabled={!form.customer || (!plan && !template)} onClick={() => save.mutate(undefined)}>
              {editing ? "Save changes" : "Create draft"}
            </Button>
            <p className="text-center text-xs text-slate-500">Totals and taxes are calculated by the server when you save.</p>
          </div>
        </div>
      </div>
    </>
  );
}
