import { useQuery } from "@tanstack/react-query";
import { Plus, Search, UserCheck, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { Badge, Button, Card, Empty, ErrorBox, Field, formatDate, Input, InvoiceBadge, KeyValue, Loading, Modal, Money, PageHeader, Pagination, Select, Stat, Table, Textarea, useDebounced } from "../components/ui";
import { ApiError, get, patch, post, type Page } from "../lib/api";
import { useAction, useListParams } from "../lib/hooks";
import type { Customer, Invoice, Subscription } from "../lib/types";

const EMPTY = { name: "", company: "", email: "", phone: "", address: "", city: "", state: "", country: "India", tax_id: "", notes: "" };

function CustomerModal({ open, onClose, customer }: { open: boolean; onClose: () => void; customer?: Customer }) {
  const [form, setForm] = useState(EMPTY);
  useEffect(() => {
    if (open) setForm(customer ? { ...EMPTY, ...Object.fromEntries(Object.keys(EMPTY).map((k) => [k, (customer as unknown as Record<string, string>)[k] ?? ""])) } : EMPTY);
  }, [open, customer]);
  const save = useAction(() => (customer ? patch<Customer>(`customers/${customer.id}/`, form) : post<Customer>("customers/", form)), {
    invalidate: [["customers"], ["customer"]],
    success: (c) => `${c.company || c.name} saved`,
    onSuccess: onClose,
  });
  const err = save.error as ApiError | null;
  const set = (k: keyof typeof EMPTY) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  return (
    <Modal open={open} onClose={onClose} title={customer ? "Edit customer" : "New customer"} wide footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate(undefined)}>Save</Button></>}>
      {err && !err.fields?.email && <ErrorBox error={err} />}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Contact name"><Input value={form.name} onChange={set("name")} /></Field>
        <Field label="Company"><Input value={form.company} onChange={set("company")} /></Field>
        <Field label="Email" error={err?.fieldError("email")} hint="One customer per email. They can sign up with it to use the portal."><Input type="email" value={form.email} onChange={set("email")} /></Field>
        <Field label="Phone"><Input value={form.phone} onChange={set("phone")} /></Field>
        <Field label="Address" className="sm:col-span-2"><Input value={form.address} onChange={set("address")} /></Field>
        <Field label="City"><Input value={form.city} onChange={set("city")} /></Field>
        <Field label="State"><Input value={form.state} onChange={set("state")} /></Field>
        <Field label="Country"><Input value={form.country} onChange={set("country")} /></Field>
        <Field label="GSTIN / tax ID"><Input value={form.tax_id} onChange={set("tax_id")} /></Field>
        <Field label="Notes" className="sm:col-span-2"><Textarea value={form.notes} onChange={set("notes")} rows={2} /></Field>
      </div>
    </Modal>
  );
}

export function CustomersPage() {
  const { value, set, page } = useListParams();
  const [params, setParams] = useSearchParams();
  const [creating, setCreating] = useState(params.get("new") === "1");
  const [search, setSearch] = useState(value("search"));
  const debounced = useDebounced(search);
  useEffect(() => {
    if (debounced !== value("search")) set({ search: debounced });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);
  const filters = { search: value("search"), ordering: value("ordering") || undefined, page };
  const { data, isLoading, error } = useQuery({ queryKey: ["customers", filters], queryFn: () => get<Page<Customer>>("customers/", filters), placeholderData: (p) => p });

  return (
    <>
      <PageHeader title="Customers" subtitle="Everyone Brightloop bills, with what they subscribe to and what they owe." actions={<Button icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>New customer</Button>} />
      <div className="card overflow-hidden">
        <div className="flex flex-wrap gap-2 border-b border-slate-100 px-4 py-3 dark:border-slate-800">
          <div className="relative min-w-60 flex-1">
            <Search className="absolute top-2.5 left-3 size-4 text-slate-400" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search name, company, email, city…" className="pl-9" />
          </div>
          <Select value={value("ordering")} onChange={(e) => set({ ordering: e.target.value })} className="w-48">
            <option value="">Name A–Z</option>
            <option value="-outstanding">Most outstanding</option>
            <option value="-active_subscriptions">Most subscriptions</option>
            <option value="-created_at">Newest</option>
          </Select>
        </div>
        <ErrorBox error={error} />
        {isLoading ? <Loading /> : (
          <Table
            head={<><th className="th">Customer</th><th className="th">Email</th><th className="th">City</th><th className="th">Portal</th><th className="th text-right">Active subs</th><th className="th text-right">Outstanding</th></>}
            empty={data?.results.length === 0 && <Empty icon={<Users className="size-5" />} title="No customers found" />}
          >
            {data?.results.map((c) => (
              <tr key={c.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                <td className="td"><Link to={`/customers/${c.id}`} className="font-medium text-brand-600 hover:underline">{c.company || c.name}</Link>{c.company && <div className="text-xs text-slate-500">{c.name}</div>}</td>
                <td className="td text-sm text-slate-600 dark:text-slate-300">{c.email}</td>
                <td className="td text-sm">{c.city || "—"}</td>
                <td className="td">{c.has_portal_access ? <UserCheck className="size-4 text-emerald-600" aria-label="Has portal access" /> : <span className="text-slate-300">—</span>}</td>
                <td className="td tabular text-right">{c.active_subscriptions}</td>
                <td className="td text-right font-medium"><Money value={c.outstanding} /></td>
              </tr>
            ))}
          </Table>
        )}
        {data && <Pagination page={page} count={data.count} onPage={(p) => set({ page: p })} />}
      </div>
      <CustomerModal open={creating} onClose={() => { setCreating(false); if (params.get("new")) setParams({}); }} />
    </>
  );
}

export function CustomerDetail() {
  const { id } = useParams();
  const [editing, setEditing] = useState(false);
  const { data: c, isLoading, error } = useQuery({ queryKey: ["customer", id], queryFn: () => get<Customer>(`customers/${id}/`) });
  const subs = useQuery({ queryKey: ["subscriptions", "customer", id], queryFn: () => get<Page<Subscription>>("subscriptions/", { customer: id, page_size: 100 }) });
  const invoices = useQuery({ queryKey: ["invoices", "customer", id], queryFn: () => get<Page<Invoice>>("invoices/", { customer: id, page_size: 50 }) });
  if (isLoading) return <Loading />;
  if (error || !c) return <ErrorBox error={error ?? "Not found"} />;
  const overdue = invoices.data?.results.filter((i) => i.is_overdue) ?? [];
  const mrr = (subs.data?.results ?? []).filter((s) => s.status === "ACTIVE");

  return (
    <>
      <PageHeader
        back="/customers"
        title={c.company || c.name}
        subtitle={<>{c.company && `${c.name} · `}{c.email}{c.phone && ` · ${c.phone}`}</>}
        actions={<><Button variant="secondary" onClick={() => setEditing(true)}>Edit</Button><Link to="/subscriptions/new"><Button icon={<Plus className="size-4" />}>New subscription</Button></Link></>}
      />
      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <Stat label="Active subscriptions" value={String(c.active_subscriptions ?? 0)} hint={`${mrr.length ? mrr.map((s) => s.plan_name).filter((v, i, a) => a.indexOf(v) === i).join(", ") : "None"}`} />
        <Stat label="Outstanding" value={<Money value={c.outstanding} />} tone={overdue.length ? "bad" : "default"} hint={overdue.length ? `${overdue.length} overdue invoices` : "Nothing overdue"} />
        <Stat label="Portal access" value={c.has_portal_access ? "Yes" : "Not yet"} tone={c.has_portal_access ? "good" : "warn"} hint={c.has_portal_access ? "Can self-serve online" : "They can sign up with this email"} />
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card title="Subscriptions" padded={false}>
            <Table head={<><th className="th">Number</th><th className="th">Plan</th><th className="th">Status</th><th className="th">Next invoice</th><th className="th text-right">Per period</th></>} empty={subs.data?.results.length === 0 && <Empty title="No subscriptions yet" />}>
              {subs.data?.results.map((s) => (
                <tr key={s.id}>
                  <td className="td"><Link to={`/subscriptions/${s.id}`} className="font-medium text-brand-600 hover:underline">{s.number}</Link></td>
                  <td className="td">{s.plan_name}</td>
                  <td className="td"><Badge status={s.status} /></td>
                  <td className="td tabular">{s.status === "ACTIVE" ? formatDate(s.next_invoice_date) : "—"}</td>
                  <td className="td text-right"><Money value={s.total} /></td>
                </tr>
              ))}
            </Table>
          </Card>
          <Card title="Invoices" padded={false}>
            <Table head={<><th className="th">Invoice</th><th className="th">Date</th><th className="th">Status</th><th className="th text-right">Total</th><th className="th text-right">Balance</th></>} empty={invoices.data?.results.length === 0 && <Empty title="No invoices yet" />}>
              {invoices.data?.results.map((i) => (
                <tr key={i.id}>
                  <td className="td"><Link to={`/invoices/${i.id}`} className="font-medium text-brand-600 hover:underline">{i.display_number}</Link></td>
                  <td className="td tabular">{formatDate(i.invoice_date)}</td>
                  <td className="td"><InvoiceBadge status={i.status} overdue={i.is_overdue} days={i.days_overdue} /></td>
                  <td className="td text-right"><Money value={i.total} /></td>
                  <td className="td text-right font-medium"><Money value={i.amount_due} /></td>
                </tr>
              ))}
            </Table>
          </Card>
        </div>
        <Card title="Details">
          <KeyValue items={[["Contact", c.name], ["Email", c.email], ["Phone", c.phone || "—"], ["GSTIN", c.tax_id || "—"], ["Address", [c.address, c.city, c.state, c.country].filter(Boolean).join(", ") || "—"], ["Customer since", formatDate(c.created_at)]]} />
          {c.notes && <p className="mt-4 border-t border-slate-100 pt-3 text-sm whitespace-pre-line text-slate-600 dark:border-slate-800 dark:text-slate-300">{c.notes}</p>}
        </Card>
      </div>
      <CustomerModal open={editing} onClose={() => setEditing(false)} customer={c} />
    </>
  );
}
