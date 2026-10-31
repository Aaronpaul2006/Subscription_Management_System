import { useQuery } from "@tanstack/react-query";
import { CalendarCheck, CheckCircle2, Eye, Play, ShieldAlert, ShieldCheck, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { Badge, Button, Card, Empty, ErrorBox, Field, formatDate, formatDateTime, Input, Loading, Modal, Money, PageHeader, Table, Toggle } from "../components/ui";
import { get, post, type Page } from "../lib/api";
import { useRole } from "../lib/auth";
import { useAction } from "../lib/hooks";
import type { BillingRun } from "../lib/types";

interface Preview {
  as_of: string;
  subscriptions: number;
  invoices: number;
  total: string;
  truncated: boolean;
  rows: { subscription_id: number; subscription: string; customer: string; plan: string; period_start: string; period_end: string; discount: string; total: string; discounts: string[]; prorated: boolean }[];
}

interface Gaps {
  healthy: boolean;
  gaps: { subscription_id: number; subscription: string; customer: string; period_start: string; period_end: string }[];
}

const today = () => new Date().toISOString().slice(0, 10);

export function BillingPage() {
  const { isAdmin } = useRole();
  const [asOf, setAsOf] = useState(today());
  const [autoConfirm, setAutoConfirm] = useState(true);
  const [autoSend, setAutoSend] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [lastRun, setLastRun] = useState<BillingRun | null>(null);
  const preview = useQuery({ queryKey: ["billing", "preview", asOf], queryFn: () => get<Preview>("billing/runs/preview/", { as_of: asOf }) });
  const runs = useQuery({ queryKey: ["billing", "runs"], queryFn: () => get<Page<BillingRun>>("billing/runs/") });
  const gaps = useQuery({ queryKey: ["billing", "gaps"], queryFn: () => get<Gaps>("billing/runs/gaps/") });
  const invalidate = [["billing"], ["invoices"], ["dashboard"], ["subscriptions"]];
  const run = useAction(() => post<BillingRun>("billing/runs/run/", { as_of: asOf, auto_confirm: autoConfirm, auto_send: autoSend }), {
    invalidate,
    success: (r) => `Billing run done: ${r.invoices_created} invoices in ${(r.duration_ms / 1000).toFixed(1)} s`,
    onSuccess: (r) => {
      setConfirmOpen(false);
      setLastRun(r);
    },
  });
  const daily = useAction(() => post<Record<string, number>>("billing/runs/daily-jobs/"), {
    invalidate,
    success: (r) => `Daily jobs: ${r.activated} activated, ${r.invoices} invoiced, ${r.closed} closed, ${r.reminders} reminders`,
  });
  const p = preview.data;

  return (
    <>
      <PageHeader
        title="Billing runs"
        subtitle="Billing day, automated. Preview exactly what will be invoiced, then run it — nothing is billed twice, nothing is skipped."
        actions={isAdmin && <Button variant="secondary" icon={<Sparkles className="size-4" />} loading={daily.isPending} onClick={() => daily.mutate(undefined)}>Run all daily jobs</Button>}
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card
            title="Preview"
            actions={
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500">Bill everything due on or before</span>
                <Input type="date" value={asOf} max={today()} onChange={(e) => setAsOf(e.target.value)} className="w-40" />
              </div>
            }
            padded={false}
          >
            {preview.isLoading || !p ? (
              <Loading />
            ) : p.invoices === 0 ? (
              <Empty icon={<CheckCircle2 className="size-5" />} title="Nothing to bill">Every active subscription is billed up to {formatDate(asOf)}.</Empty>
            ) : (
              <>
                <div className="grid grid-cols-3 divide-x divide-slate-100 border-b border-slate-100 dark:divide-slate-800 dark:border-slate-800">
                  <div className="px-5 py-4"><div className="text-xs text-slate-500">Subscriptions due</div><div className="tabular text-2xl font-semibold">{p.subscriptions.toLocaleString("en-IN")}</div></div>
                  <div className="px-5 py-4"><div className="text-xs text-slate-500">Invoices to create</div><div className="tabular text-2xl font-semibold">{p.invoices.toLocaleString("en-IN")}</div></div>
                  <div className="px-5 py-4"><div className="text-xs text-slate-500">Total to bill</div><Money value={p.total} className="text-2xl font-semibold" /></div>
                </div>
                <div className="max-h-[28rem] overflow-y-auto">
                  <Table head={<><th className="th">Subscription</th><th className="th">Customer</th><th className="th">Period</th><th className="th">Discounts</th><th className="th text-right">Total</th></>}>
                    {p.rows.map((r, i) => (
                      <tr key={`${r.subscription_id}-${r.period_start}-${i}`}>
                        <td className="td"><Link to={`/subscriptions/${r.subscription_id}`} className="font-medium text-brand-600 hover:underline">{r.subscription}</Link><div className="text-xs text-slate-500">{r.plan}</div></td>
                        <td className="td max-w-48 truncate">{r.customer}</td>
                        <td className="td text-xs">{formatDate(r.period_start, false)} – {formatDate(r.period_end)}{r.prorated && <Badge status="PAUSED" className="ml-1">prorated</Badge>}</td>
                        <td className="td text-xs text-emerald-600">{r.discounts.join(", ") || <span className="text-slate-400">—</span>}</td>
                        <td className="td text-right font-medium"><Money value={r.total} /></td>
                      </tr>
                    ))}
                  </Table>
                  {p.truncated && <div className="px-5 py-3 text-xs text-slate-500">Showing the first {p.rows.length} of {p.invoices} invoices.</div>}
                </div>
              </>
            )}
            <div className="flex flex-wrap items-center justify-between gap-4 border-t border-slate-100 px-5 py-4 dark:border-slate-800">
              <div className="flex flex-wrap gap-6">
                <Toggle checked={autoConfirm} onChange={setAutoConfirm} label="Confirm invoices" hint="Assign numbers straight away" />
                <Toggle checked={autoSend} onChange={(v) => { setAutoSend(v); if (v) setAutoConfirm(true); }} label="Email to customers" hint="With the PDF attached" />
              </div>
              <Button icon={<Play className="size-4" />} disabled={!p || p.invoices === 0} onClick={() => setConfirmOpen(true)}>Run billing</Button>
            </div>
          </Card>

          {lastRun && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5 dark:border-emerald-900 dark:bg-emerald-950/30">
              <div className="flex items-center gap-2 font-medium text-emerald-800 dark:text-emerald-300"><CalendarCheck className="size-5" /> Run #{lastRun.id} complete</div>
              <p className="mt-1 text-sm text-emerald-700 dark:text-emerald-400">
                {lastRun.invoices_created} invoices for <Money value={lastRun.total_amount} /> across {lastRun.subscriptions_processed} subscriptions in {(lastRun.duration_ms / 1000).toFixed(1)} s.
                {lastRun.errors.length > 0 && ` ${lastRun.errors.length} subscriptions need attention.`}
              </p>
              <Link to={`/invoices?tab=${lastRun.auto_confirm ? "CONFIRMED" : "DRAFT"}`} className="mt-2 inline-block text-sm font-medium text-emerald-700 underline">View the new invoices</Link>
            </div>
          )}

          <Card title="History" padded={false}>
            {runs.isLoading ? (
              <Loading />
            ) : (
              <Table head={<><th className="th">Run</th><th className="th">Billed up to</th><th className="th">By</th><th className="th text-right">Subscriptions</th><th className="th text-right">Invoices</th><th className="th text-right">Amount</th><th className="th text-right">Time</th></>}
                empty={runs.data?.results.length === 0 && <Empty title="No billing runs yet" />}>
                {runs.data?.results.map((r) => (
                  <tr key={r.id}>
                    <td className="td"><span className="font-medium">#{r.id}</span><div className="text-xs text-slate-500">{formatDateTime(r.started_at)}</div></td>
                    <td className="td tabular">{formatDate(r.as_of)}</td>
                    <td className="td text-sm">{r.trigger === "SCHEDULED" ? <Badge status="CONFIRMED">Scheduled</Badge> : r.triggered_by_name}</td>
                    <td className="td tabular text-right">{r.subscriptions_processed}</td>
                    <td className="td tabular text-right">{r.invoices_created}{r.errors.length > 0 && <span className="ml-1 text-xs text-rose-600">({r.errors.length} errors)</span>}</td>
                    <td className="td text-right"><Money value={r.total_amount} /></td>
                    <td className="td tabular text-right text-xs text-slate-500">{(r.duration_ms / 1000).toFixed(1)} s</td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="Billing health check">
            {gaps.isLoading || !gaps.data ? (
              <Loading />
            ) : gaps.data.healthy ? (
              <div className="flex gap-3">
                <ShieldCheck className="size-8 shrink-0 text-emerald-500" />
                <div className="text-sm">
                  <div className="font-medium">No missed periods</div>
                  <p className="text-slate-500">Every billed period of every subscription has exactly one live invoice.</p>
                </div>
              </div>
            ) : (
              <div>
                <div className="flex gap-3">
                  <ShieldAlert className="size-8 shrink-0 text-rose-500" />
                  <div className="text-sm">
                    <div className="font-medium">{gaps.data.gaps.length} periods have no live invoice</div>
                    <p className="text-slate-500">Usually a cancelled invoice that was not re-billed.</p>
                  </div>
                </div>
                <ul className="mt-3 max-h-64 divide-y divide-slate-100 overflow-y-auto text-sm dark:divide-slate-800">
                  {gaps.data.gaps.map((g) => (
                    <li key={`${g.subscription_id}-${g.period_start}`} className="py-2">
                      <Link to={`/subscriptions/${g.subscription_id}`} className="font-medium text-brand-600 hover:underline">{g.subscription}</Link>
                      <div className="text-xs text-slate-500">{g.customer} · {formatDate(g.period_start, false)} – {formatDate(g.period_end)}</div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Card>
          <Card title="How billing works">
            <ol className="list-decimal space-y-2 pl-4 text-sm text-slate-600 dark:text-slate-300">
              <li>Every active subscription has a <strong>next invoice date</strong>. On or after it, the next period is billed in advance.</li>
              <li>Lines, quantities, prices and taxes come from the subscription; the customer's details are copied onto the invoice.</li>
              <li>Discount rules that apply are added automatically and stop when they expire or run out.</li>
              <li>A subscription missed for a while gets one invoice per missed period. A short final period is prorated.</li>
              <li>The database allows only one live invoice per subscription period, so a period can never be billed twice.</li>
              <li>The scheduler runs this every morning; overdue invoices get a reminder every 7 days.</li>
            </ol>
            <div className="mt-3 flex items-center gap-1 text-xs text-slate-500"><Eye className="size-3.5" /> The preview above is a dry run and never writes anything.</div>
          </Card>
        </div>
      </div>

      <Modal
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Run billing now?"
        footer={<><Button variant="secondary" onClick={() => setConfirmOpen(false)}>Cancel</Button><Button loading={run.isPending} onClick={() => run.mutate(undefined)}>Create {p?.invoices} invoices</Button></>}
      >
        <ErrorBox error={run.error} />
        <Field label="">
          <p className="text-sm text-slate-600 dark:text-slate-300">
            This creates <strong>{p?.invoices}</strong> invoices for <Money value={p?.total} /> {autoConfirm ? "and confirms them" : "as drafts"}{autoSend ? ", then emails each customer their invoice." : "."}
          </p>
        </Field>
      </Modal>
    </>
  );
}
