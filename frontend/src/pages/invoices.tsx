import { useQuery } from "@tanstack/react-query";
import { BellRing, Check, CreditCard, Download, FileDown, Printer, RotateCcw, Search, Send, Wallet, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
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
import { get, post, qs, type Page } from "../lib/api";
import { useRole } from "../lib/auth";
import { useAction, useChoices, useListParams, useMeta } from "../lib/hooks";
import { formatMoney } from "../lib/money";
import type { Activity, InvoiceDetail as InvDetail, Invoice } from "../lib/types";

const TABS = ["ALL", "DRAFT", "CONFIRMED", "OVERDUE", "PAID", "CANCELLED"] as const;
const tabLabel: Record<string, string> = { ALL: "All", DRAFT: "Draft", CONFIRMED: "Unpaid", OVERDUE: "Overdue", PAID: "Paid", CANCELLED: "Cancelled" };

function tabQuery(tab: string) {
  if (tab === "ALL") return {};
  if (tab === "OVERDUE") return { overdue: true };
  return { status: tab };
}

export function InvoicesPage({ portal = false }: { portal?: boolean }) {
  const { value, set, page } = useListParams({ tab: "ALL" });
  const tab = value("tab");
  const [search, setSearch] = useState(value("search"));
  const debounced = useDebounced(search);
  useEffect(() => {
    if (debounced !== value("search")) set({ search: debounced });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);
  const filters = { search: value("search"), date_from: value("from"), date_to: value("to"), ordering: value("ordering") || undefined };
  const { data, isLoading, error } = useQuery({
    queryKey: ["invoices", "list", tab, page, filters],
    queryFn: () => get<Page<Invoice>>("invoices/", { ...filters, ...tabQuery(tab), page }),
    placeholderData: (prev) => prev,
  });
  const { data: stats } = useQuery({
    queryKey: ["invoices", "stats", filters],
    queryFn: () => get<Record<string, { count: number; total: string; due: string }>>("invoices/stats/", filters),
  });
  const total = stats ? ["DRAFT", "CONFIRMED", "PAID", "CANCELLED"].reduce((a, k) => a + (stats[k]?.count ?? 0), 0) : undefined;
  const base = portal ? "/portal/invoices" : "/invoices";
  const exportUrl = `/api/reports/invoices.csv${qs({ ...filters, ...tabQuery(tab) })}`;

  return (
    <>
      <PageHeader
        title={portal ? "My invoices" : "Invoices"}
        subtitle={portal ? "Download, print or pay your invoices." : "Created from subscriptions on billing day — confirm, send, print and collect."}
        actions={!portal && <a href={exportUrl}><Button variant="secondary" icon={<Download className="size-4" />}>Export CSV</Button></a>}
      />
      {stats && (
        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          <div className="card px-5 py-3">
            <div className="text-xs text-slate-500">Outstanding</div>
            <Money value={stats.CONFIRMED?.due ?? "0"} className="text-xl font-semibold" />
            <div className="text-xs text-slate-500">{stats.CONFIRMED?.count ?? 0} unpaid invoices</div>
          </div>
          <div className="card px-5 py-3">
            <div className="text-xs text-slate-500">Overdue</div>
            <Money value={stats.OVERDUE?.due ?? "0"} className="text-xl font-semibold text-rose-600" />
            <div className="text-xs text-slate-500">{stats.OVERDUE?.count ?? 0} past their due date</div>
          </div>
          <div className="card px-5 py-3">
            <div className="text-xs text-slate-500">Paid</div>
            <Money value={stats.PAID?.total ?? "0"} className="text-xl font-semibold text-emerald-600" />
            <div className="text-xs text-slate-500">{stats.PAID?.count ?? 0} settled in full</div>
          </div>
        </div>
      )}
      <div className="card overflow-hidden">
        <div className="px-4 pt-2">
          <Tabs value={tab} onChange={(t) => set({ tab: t })} tabs={TABS.filter((t) => !portal || t !== "DRAFT").map((t) => ({ value: t, label: tabLabel[t], count: t === "ALL" ? total : (stats?.[t]?.count ?? 0) }))} />
        </div>
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-3 dark:border-slate-800">
          <div className="relative min-w-60 flex-1">
            <Search className="absolute top-2.5 left-3 size-4 text-slate-400" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={portal ? "Search invoice number…" : "Search number, customer, subscription…"} className="pl-9" />
          </div>
          <Input type="date" value={value("from")} onChange={(e) => set({ from: e.target.value })} className="w-40" aria-label="From date" />
          <span className="text-slate-400">–</span>
          <Input type="date" value={value("to")} onChange={(e) => set({ to: e.target.value })} className="w-40" aria-label="To date" />
          <Select value={value("ordering")} onChange={(e) => set({ ordering: e.target.value })} className="w-44">
            <option value="">Newest first</option>
            <option value="due_date">Due soonest</option>
            <option value="-amount_due">Largest balance</option>
            <option value="-total">Largest total</option>
          </Select>
        </div>
        <ErrorBox error={error} />
        {isLoading ? (
          <Loading />
        ) : (
          <Table
            head={
              <>
                <th className="th">Invoice</th>
                {!portal && <th className="th">Customer</th>}
                <th className="th">Date</th>
                <th className="th">Due</th>
                <th className="th">Status</th>
                <th className="th text-right">Total</th>
                <th className="th text-right">Balance</th>
              </>
            }
            empty={data?.results.length === 0 && <Empty title="No invoices here">Try another tab or clear the filters.</Empty>}
          >
            {data?.results.map((inv) => (
              <tr key={inv.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                <td className="td">
                  <Link to={`${base}/${inv.id}`} className="font-medium text-brand-600 hover:underline">{inv.display_number}</Link>
                  {inv.subscription_number && <div className="text-xs text-slate-500">{inv.subscription_number}</div>}
                </td>
                {!portal && <td className="td max-w-56 truncate">{inv.customer_name}</td>}
                <td className="td tabular">{formatDate(inv.invoice_date)}</td>
                <td className="td tabular">{formatDate(inv.due_date)}</td>
                <td className="td">
                  <InvoiceBadge status={inv.status} overdue={inv.is_overdue} days={inv.days_overdue} />
                  {inv.reminder_count > 0 && <BellRing className="ml-1 inline size-3.5 text-amber-500" aria-label={`${inv.reminder_count} reminders sent`} />}
                </td>
                <td className="td text-right"><Money value={inv.total} /></td>
                <td className="td text-right font-medium"><Money value={inv.amount_due} /></td>
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

export function InvoiceDetail({ portal = false }: { portal?: boolean }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const { isInternal } = useRole();
  const methods = useChoices("payment_method");
  const key = ["invoice", id];
  const { data: inv, isLoading, error } = useQuery({ queryKey: key, queryFn: () => get<InvDetail>(`invoices/${id}/`) });
  const { data: activity } = useQuery({ queryKey: ["invoice", id, "activity"], queryFn: () => get<Activity[]>(`invoices/${id}/activity/`), enabled: isInternal && !!inv });
  const [modal, setModal] = useState<"" | "pay" | "cancel" | "checkout">("");
  const [payment, setPayment] = useState({ amount: "", method: "BANK_TRANSFER", payment_date: new Date().toISOString().slice(0, 10), reference: "", note: "" });
  const [cancelReason, setCancelReason] = useState("");
  const [checkoutMethod, setCheckoutMethod] = useState("CARD");
  const invalidate = [key, ["invoices"], ["payments"], ["dashboard"], ["subscription"], ["portal"]];
  const act = useAction(({ action, body }: { action: string; body?: unknown }) => post<InvDetail>(`invoices/${id}/${action}/`, body), {
    invalidate,
    success: (r) => `${r.display_number}: ${r.status_label.toLowerCase()}`,
    onSuccess: (r) => {
      setModal("");
      if (String(r.id) !== id) navigate(`/invoices/${r.id}`);
    },
  });
  const record = useAction(() => post("payments/", { invoice: Number(id), ...payment }), {
    invalidate,
    success: "Payment recorded",
    onSuccess: () => setModal(""),
  });

  if (isLoading) return <Loading />;
  if (error || !inv) return <ErrorBox error={error ?? "Not found"} />;
  const can = (a: string) => inv.allowed_actions.includes(a);
  const run = (action: string, body?: unknown) => act.mutate({ action, body });
  const b = inv.bill_to;
  const printPath = `${portal ? "/portal" : ""}/invoices/${inv.id}/print`;

  return (
    <>
      <PageHeader
        back={portal ? "/portal/invoices" : "/invoices"}
        title={
          <span className="flex items-center gap-3">
            {inv.display_number} <InvoiceBadge status={inv.status} overdue={inv.is_overdue} days={inv.days_overdue} />
          </span>
        }
        subtitle={
          <>
            {portal ? "" : <><Link to={`/customers/${inv.customer}`} className="hover:underline">{inv.customer_name}</Link> · </>}
            {inv.subscription_number && <Link to={`${portal ? "/portal" : ""}/subscriptions/${inv.subscription}`} className="hover:underline">{inv.subscription_number}</Link>}
            {inv.period_start && ` · ${formatDate(inv.period_start, false)} – ${formatDate(inv.period_end)}`}
          </>
        }
        actions={
          <>
            {can("confirm") && <Button icon={<Check className="size-4" />} loading={act.isPending} onClick={() => run("confirm")}>Confirm</Button>}
            {can("register_payment") && (
              <Button variant="success" icon={<Wallet className="size-4" />} onClick={() => { setPayment((p) => ({ ...p, amount: inv.amount_due })); setModal("pay"); }}>
                Register payment
              </Button>
            )}
            {can("pay") && <Button variant="success" icon={<CreditCard className="size-4" />} onClick={() => setModal("checkout")}>Pay <Money value={inv.amount_due} /></Button>}
            {can("send") && <Button variant="secondary" icon={<Send className="size-4" />} loading={act.isPending} onClick={() => run("send")}>{inv.sent_at ? "Resend" : "Send"}</Button>}
            {can("remind") && inv.is_overdue && <Button variant="secondary" icon={<BellRing className="size-4" />} loading={act.isPending} onClick={() => run("remind")}>Send reminder</Button>}
            <Link to={printPath}><Button variant="secondary" icon={<Printer className="size-4" />}>Print</Button></Link>
            <a href={`/api/invoices/${inv.id}/pdf/?download=1`}><Button variant="secondary" icon={<FileDown className="size-4" />}>PDF</Button></a>
            {can("rebill") && <Button variant="secondary" icon={<RotateCcw className="size-4" />} loading={act.isPending} onClick={() => run("rebill")}>Re-bill period</Button>}
            {can("cancel") && <Button variant="ghost" className="text-rose-600" icon={<XCircle className="size-4" />} onClick={() => setModal("cancel")}>Cancel</Button>}
          </>
        }
      />
      {inv.status === "CANCELLED" && (
        <div className="mb-6 rounded-xl border border-slate-200 bg-slate-50 px-5 py-3 text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-900">
          Cancelled {formatDateTime(inv.cancelled_at)}{inv.cancel_reason && `: ${inv.cancel_reason}`}. {isInternal && inv.subscription && "Re-bill the period to issue a corrected invoice."}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card padded={false}>
            <div className="grid gap-6 border-b border-slate-100 p-5 sm:grid-cols-2 dark:border-slate-800">
              <div>
                <div className="text-xs font-semibold tracking-wide text-slate-400 uppercase">Bill to</div>
                <div className="mt-1 font-medium">{b.company || b.name}</div>
                <div className="text-sm text-slate-500">
                  {b.company && <div>{b.name}</div>}
                  {[b.address, b.city, b.state].filter(Boolean).join(", ")}
                  <div>{b.email}</div>
                  {b.tax_id && <div>Tax ID {b.tax_id}</div>}
                </div>
              </div>
              <dl className="grid grid-cols-2 gap-2 text-sm sm:text-right">
                <dt className="text-slate-500">Invoice date</dt><dd className="font-medium">{formatDate(inv.invoice_date)}</dd>
                <dt className="text-slate-500">Due date</dt><dd className={inv.is_overdue ? "font-medium text-rose-600" : "font-medium"}>{formatDate(inv.due_date)}</dd>
                <dt className="text-slate-500">Terms</dt><dd className="font-medium">{inv.payment_term}</dd>
                {inv.sent_at && <><dt className="text-slate-500">Sent</dt><dd className="font-medium">{timeAgo(inv.sent_at)}</dd></>}
              </dl>
            </div>
            <Table
              head={
                <>
                  <th className="th">Description</th>
                  <th className="th text-right">Qty</th>
                  <th className="th text-right">Price</th>
                  <th className="th text-right">Discount</th>
                  <th className="th text-right">Tax</th>
                  <th className="th text-right">Amount</th>
                </>
              }
            >
              {inv.lines.map((l) => (
                <tr key={l.id}>
                  <td className="td">{l.description}</td>
                  <td className="td tabular text-right">{Number(l.quantity).toLocaleString("en-IN")}</td>
                  <td className="td text-right"><Money value={l.unit_price} /></td>
                  <td className="td text-right text-emerald-600">{Number(l.discount_amount) ? <>−<Money value={l.discount_amount} /></> : "—"}</td>
                  <td className="td text-right">
                    <Money value={l.tax_amount} />
                    <div className="text-[10px] text-slate-400">{l.taxes.map((t) => t.name).join(", ")}</div>
                  </td>
                  <td className="td text-right font-medium"><Money value={l.total} /></td>
                </tr>
              ))}
            </Table>
            <div className="flex justify-end border-t border-slate-100 px-5 py-4 dark:border-slate-800">
              <dl className="w-72 space-y-1 text-sm">
                <div className="flex justify-between"><dt className="text-slate-500">Subtotal</dt><dd><Money value={inv.untaxed_amount} /></dd></div>
                {inv.applied_discounts.map((d) => (
                  <div key={d.id} className="flex justify-between text-emerald-600"><dt>{d.name}</dt><dd>−<Money value={d.amount} /></dd></div>
                ))}
                <div className="flex justify-between"><dt className="text-slate-500">Tax</dt><dd><Money value={inv.tax_amount} /></dd></div>
                <div className="flex justify-between border-t border-slate-200 pt-1 font-semibold dark:border-slate-700"><dt>Total</dt><dd><Money value={inv.total} /></dd></div>
                <div className="flex justify-between"><dt className="text-slate-500">Paid</dt><dd><Money value={inv.amount_paid} /></dd></div>
                <div className="flex justify-between text-base font-semibold text-brand-700 dark:text-brand-400"><dt>Balance due</dt><dd><Money value={inv.amount_due} /></dd></div>
              </dl>
            </div>
          </Card>

          <Card title="Payments" padded={false}>
            {inv.payments.length === 0 ? (
              <Empty title="No payments yet">{inv.status === "CONFIRMED" ? `Due ${formatDate(inv.due_date)}.` : inv.status === "DRAFT" ? "Confirm the invoice to start collecting." : ""}</Empty>
            ) : (
              <Table head={<><th className="th">Date</th><th className="th">Method</th><th className="th">Reference</th><th className="th">Note</th><th className="th text-right">Amount</th></>}>
                {inv.payments.map((p) => (
                  <tr key={p.id}>
                    <td className="td tabular">{formatDate(p.payment_date)}</td>
                    <td className="td">{p.method_label}{p.source === "PORTAL" && <Badge status="QUOTATION" className="ml-2">Online</Badge>}</td>
                    <td className="td text-xs text-slate-500">{p.reference || "—"}</td>
                    <td className="td text-xs text-slate-500">{p.note || "—"}{p.recorded_by_name && !portal && <div>by {p.recorded_by_name}</div>}</td>
                    <td className="td text-right font-medium"><Money value={p.amount} /></td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="Summary">
            <div className="text-xs text-slate-500">Balance due</div>
            <Money value={inv.amount_due} className="text-3xl font-semibold" />
            <div className="mt-3 h-2 rounded-full bg-slate-100 dark:bg-slate-800">
              <div className="h-2 rounded-full bg-emerald-500" style={{ width: `${Number(inv.total) ? (Number(inv.amount_paid) / Number(inv.total)) * 100 : 100}%` }} />
            </div>
            <div className="mt-1 text-xs text-slate-500"><Money value={inv.amount_paid} /> of <Money value={inv.total} /> paid</div>
            {inv.reminder_count > 0 && <div className="mt-3 text-xs text-amber-600">{inv.reminder_count} payment reminder{inv.reminder_count > 1 ? "s" : ""} sent · last {timeAgo(inv.last_reminder_at!)}</div>}
          </Card>
          {activity && (
            <Card title="Timeline" padded={false}>
              <ol className="max-h-96 overflow-y-auto px-5 py-3">
                {activity.map((a) => (
                  <li key={a.id} className="relative border-l border-slate-200 pb-4 pl-4 last:pb-0 dark:border-slate-700">
                    <span className="absolute top-1 -left-[5px] size-2.5 rounded-full border-2 border-white bg-brand-500 dark:border-slate-900" />
                    <div className="text-sm">{a.message}</div>
                    <div className="text-xs text-slate-500">{a.actor_name ?? "System"} · {timeAgo(a.created_at)}</div>
                  </li>
                ))}
              </ol>
            </Card>
          )}
        </div>
      </div>

      <Modal
        open={modal === "pay"}
        onClose={() => setModal("")}
        title={`Register payment for ${inv.display_number}`}
        footer={<><Button variant="secondary" onClick={() => setModal("")}>Cancel</Button><Button variant="success" loading={record.isPending} onClick={() => record.mutate(undefined)}>Record payment</Button></>}
      >
        <ErrorBox error={record.error} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Amount" hint={<>Balance due <Money value={inv.amount_due} /></>}>
            <Input inputMode="decimal" value={payment.amount} onChange={(e) => setPayment({ ...payment, amount: e.target.value })} />
          </Field>
          <Field label="Method">
            <Select value={payment.method} onChange={(e) => setPayment({ ...payment, method: e.target.value })}>
              {methods.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </Select>
          </Field>
          <Field label="Payment date">
            <Input type="date" value={payment.payment_date} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setPayment({ ...payment, payment_date: e.target.value })} />
          </Field>
          <Field label="Reference">
            <Input value={payment.reference} onChange={(e) => setPayment({ ...payment, reference: e.target.value })} placeholder="UTR / cheque no." />
          </Field>
          <Field label="Note" className="sm:col-span-2">
            <Textarea rows={2} value={payment.note} onChange={(e) => setPayment({ ...payment, note: e.target.value })} />
          </Field>
        </div>
      </Modal>
      <Modal
        open={modal === "cancel"}
        onClose={() => setModal("")}
        title={`Cancel ${inv.display_number}?`}
        footer={<><Button variant="secondary" onClick={() => setModal("")}>Keep it</Button><Button variant="danger" loading={act.isPending} onClick={() => run("cancel", { reason: cancelReason })}>Cancel invoice</Button></>}
      >
        <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">The invoice stays on record as cancelled{inv.number ? ` and keeps its number ${inv.number}` : ""}. Its period can be re-billed afterwards.</p>
        <Field label="Reason">
          <Input value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} placeholder="e.g. Wrong quantity" />
        </Field>
      </Modal>
      <Modal
        open={modal === "checkout"}
        onClose={() => setModal("")}
        title="Pay online"
        footer={<><Button variant="secondary" onClick={() => setModal("")}>Cancel</Button><Button variant="success" loading={act.isPending} onClick={() => run("pay", { method: checkoutMethod })}>Pay {formatMoney(inv.amount_due)}</Button></>}
      >
        <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">Paying invoice <strong>{inv.display_number}</strong> in full.</p>
        <div className="grid grid-cols-3 gap-2">
          {[["CARD", "Card"], ["UPI", "UPI"], ["BANK_TRANSFER", "Net banking"]].map(([value, text]) => (
            <button key={value} onClick={() => setCheckoutMethod(value)} className={`rounded-lg border px-3 py-3 text-sm font-medium ${checkoutMethod === value ? "border-brand-600 bg-brand-50 text-brand-700 dark:bg-brand-900/40 dark:text-brand-200" : "border-slate-200 dark:border-slate-700"}`}>
              {text}
            </button>
          ))}
        </div>
        <p className="mt-4 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800">Demo payment gateway: no card details are collected and the payment always succeeds.</p>
      </Modal>
    </>
  );
}

// ===================================================================== print

export function InvoicePrint() {
  const { id } = useParams();
  const { data: meta } = useMeta();
  const { data: inv, isLoading } = useQuery({ queryKey: ["invoice", id], queryFn: () => get<InvDetail>(`invoices/${id}/`) });
  useEffect(() => {
    if (inv) setTimeout(() => window.print(), 400);
  }, [inv]);
  if (isLoading || !inv || !meta) return <Loading />;
  const b = inv.bill_to;
  const c = meta.company;
  return (
    <div className="min-h-screen bg-slate-100 py-8 print:bg-white print:py-0">
      <div className="no-print mx-auto mb-4 flex max-w-3xl justify-between px-4">
        <Button variant="secondary" onClick={() => history.back()}>Back</Button>
        <Button icon={<Printer className="size-4" />} onClick={() => window.print()}>Print</Button>
      </div>
      <article className="print-sheet mx-auto max-w-3xl bg-white p-10 text-slate-900 shadow-lg">
        <header className="flex justify-between">
          <div>
            <div className="flex items-center gap-2">
              <img src="/favicon.svg" alt="" className="size-8" />
              <span className="text-lg font-semibold">{c.name}</span>
            </div>
            <p className="mt-2 text-xs text-slate-500">{c.address}<br />{c.email} · Tax ID {c.tax_id}</p>
          </div>
          <div className="text-right">
            <div className="text-3xl font-bold text-brand-600">INVOICE</div>
            <div className="mt-1 font-semibold">{inv.display_number}</div>
            <div className="text-xs text-slate-500 uppercase">{inv.is_overdue ? `Overdue · ${inv.days_overdue} days` : inv.status_label}</div>
          </div>
        </header>
        <section className="mt-8 grid grid-cols-2 gap-6 text-sm">
          <div>
            <div className="text-xs font-semibold text-slate-400 uppercase">Bill to</div>
            <div className="mt-1 font-medium">{b.company || b.name}</div>
            {b.company && <div>{b.name}</div>}
            <div className="text-slate-600">{[b.address, b.city, b.state, b.country].filter(Boolean).join(", ")}</div>
            <div className="text-slate-600">{b.email}</div>
            {b.tax_id && <div className="text-slate-600">Tax ID {b.tax_id}</div>}
          </div>
          <dl className="grid grid-cols-2 gap-1 text-right">
            <dt className="text-slate-500">Invoice date</dt><dd>{formatDate(inv.invoice_date)}</dd>
            <dt className="text-slate-500">Due date</dt><dd>{formatDate(inv.due_date)}</dd>
            <dt className="text-slate-500">Terms</dt><dd>{inv.payment_term}</dd>
            {inv.period_start && <><dt className="text-slate-500">Period</dt><dd>{formatDate(inv.period_start, false)} – {formatDate(inv.period_end)}</dd></>}
            {inv.subscription_number && <><dt className="text-slate-500">Subscription</dt><dd>{inv.subscription_number}</dd></>}
          </dl>
        </section>
        <table className="mt-8 w-full text-sm">
          <thead>
            <tr className="border-b-2 border-slate-900 text-left text-xs text-slate-500 uppercase">
              <th className="py-2">Description</th><th className="py-2 text-right">Qty</th><th className="py-2 text-right">Price</th><th className="py-2 text-right">Discount</th><th className="py-2 text-right">Tax</th><th className="py-2 text-right">Amount</th>
            </tr>
          </thead>
          <tbody>
            {inv.lines.map((l) => (
              <tr key={l.id} className="border-b border-slate-200">
                <td className="py-2">{l.description}</td>
                <td className="tabular py-2 text-right">{Number(l.quantity)}</td>
                <td className="py-2 text-right"><Money value={l.unit_price} /></td>
                <td className="py-2 text-right">{Number(l.discount_amount) ? <Money value={l.discount_amount} /> : "—"}</td>
                <td className="py-2 text-right"><Money value={l.tax_amount} /></td>
                <td className="py-2 text-right"><Money value={l.total} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-4 flex justify-end">
          <dl className="w-64 space-y-1 text-sm">
            <div className="flex justify-between"><dt>Subtotal</dt><dd><Money value={inv.untaxed_amount} /></dd></div>
            {inv.applied_discounts.map((d) => <div key={d.id} className="flex justify-between"><dt>{d.name}</dt><dd>−<Money value={d.amount} /></dd></div>)}
            <div className="flex justify-between"><dt>Tax</dt><dd><Money value={inv.tax_amount} /></dd></div>
            <div className="flex justify-between border-t border-slate-900 pt-1 font-semibold"><dt>Total ({c.currency})</dt><dd><Money value={inv.total} /></dd></div>
            <div className="flex justify-between"><dt>Paid</dt><dd><Money value={inv.amount_paid} /></dd></div>
            <div className="flex justify-between text-base font-bold text-brand-700"><dt>Amount due</dt><dd><Money value={inv.amount_due} /></dd></div>
          </dl>
        </div>
        <footer className="mt-12 border-t border-slate-200 pt-4 text-xs text-slate-500">Thank you for your business. Questions? Write to {c.email}.</footer>
      </article>
    </div>
  );
}
