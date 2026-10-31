import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { BadgePercent, Boxes, CalendarClock, Check, FileStack, Lock, Pencil, Plus, Trash2, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Badge, Button, Card, Empty, ErrorBox, Field, formatDate, Input, Loading, Modal, Money, PageHeader, Select, Table, Textarea, Toggle } from "../components/ui";
import { ApiError, get, patch, post, type Page } from "../lib/api";
import { useRole } from "../lib/auth";
import { useAction, useChoices, usePaymentTerms, usePlans, useProducts, useTaxes, useTemplates } from "../lib/hooks";
import type { Discount, PaymentTerm, Plan, Product, QuotationTemplate, Subscription, Tax, TemplateLine, Variant } from "../lib/types";

function ReadOnlyNote() {
  const { isAdmin } = useRole();
  if (isAdmin) return null;
  return (
    <div className="mb-4 flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-4 py-2 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
      <Lock className="size-4" /> Only an administrator can change this. You can view it.
    </div>
  );
}

function useSaver<T>(path: string, id: number | undefined, keys: string[][], close: () => void, label: (r: T) => string) {
  return useAction((body: unknown) => (id ? patch<T>(`${path}/${id}/`, body) : post<T>(`${path}/`, body)), { invalidate: keys, success: (r) => `${label(r)} saved`, onSuccess: close });
}

const fieldErr = (e: unknown, name: string) => (e instanceof ApiError ? e.fieldError(name) : undefined);

// ===================================================================== products

export function ProductsPage() {
  const { isAdmin } = useRole();
  const { data, isLoading } = useProducts();
  const [editing, setEditing] = useState<Product | "new" | null>(null);
  return (
    <>
      <PageHeader title="Products" subtitle="What Brightloop sells, with variants that change the price." actions={isAdmin && <Button icon={<Plus className="size-4" />} onClick={() => setEditing("new")}>New product</Button>} />
      <ReadOnlyNote />
      <div className="card overflow-hidden">
        {isLoading ? <Loading /> : (
          <Table head={<><th className="th">Product</th><th className="th">Type</th><th className="th text-right">Sales price</th><th className="th text-right">Cost</th><th className="th text-right">Margin</th><th className="th">Variants</th><th className="th">Taxes</th><th className="th" /></>}
            empty={data?.results.length === 0 && <Empty icon={<Boxes className="size-5" />} title="No products yet" />}>
            {data?.results.map((p) => (
              <tr key={p.id} className={clsx(!p.is_active && "opacity-50")}>
                <td className="td"><div className="font-medium">{p.name}</div>{p.notes && <div className="max-w-xs truncate text-xs text-slate-500">{p.notes}</div>}</td>
                <td className="td"><Badge status="CONFIRMED">{p.product_type_label}</Badge>{!p.is_active && <Badge status="CLOSED" className="ml-1">Archived</Badge>}</td>
                <td className="td text-right font-medium"><Money value={p.sales_price} /></td>
                <td className="td text-right text-slate-500"><Money value={p.cost_price} /></td>
                <td className="td tabular text-right text-sm">{p.margin_percent !== null ? `${p.margin_percent}%` : "—"}</td>
                <td className="td text-xs">
                  {p.variants.length ? p.variants.map((v) => (
                    <span key={v.id} className="mr-1 mb-1 inline-block rounded bg-slate-100 px-1.5 py-0.5 dark:bg-slate-800">{v.attribute}: {v.value}{Number(v.extra_price) ? ` +${v.extra_price}` : ""}</span>
                  )) : <span className="text-slate-400">—</span>}
                </td>
                <td className="td text-xs text-slate-500">{p.tax_names.join(", ") || "—"}</td>
                <td className="td text-right">{isAdmin && <Button size="sm" variant="ghost" icon={<Pencil className="size-3.5" />} onClick={() => setEditing(p)}>Edit</Button>}</td>
              </tr>
            ))}
          </Table>
        )}
      </div>
      {editing && <ProductModal product={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
    </>
  );
}

function ProductModal({ product, onClose }: { product?: Product; onClose: () => void }) {
  const types = useChoices("product_type");
  const taxes = useTaxes().data ?? [];
  const [form, setForm] = useState({
    name: product?.name ?? "",
    product_type: product?.product_type ?? "SOFTWARE",
    sales_price: product?.sales_price ?? "",
    cost_price: product?.cost_price ?? "0.00",
    notes: product?.notes ?? "",
    taxes: product?.taxes ?? [],
    is_active: product?.is_active ?? true,
  });
  const [variants, setVariants] = useState<Variant[]>(product?.variants ?? []);
  const save = useSaver<Product>("products", product?.id, [["products"]], onClose, (p) => p.name);
  const err = save.error;
  return (
    <Modal open onClose={onClose} wide title={product ? `Edit ${product.name}` : "New product"}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate({ ...form, variants })}>Save product</Button></>}>
      {err && <ErrorBox error={err} />}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name" error={fieldErr(err, "name")}><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
        <Field label="Type"><Select value={form.product_type} onChange={(e) => setForm({ ...form, product_type: e.target.value })}>{types.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</Select></Field>
        <Field label="Sales price" error={fieldErr(err, "sales_price")}><Input inputMode="decimal" value={form.sales_price} onChange={(e) => setForm({ ...form, sales_price: e.target.value })} /></Field>
        <Field label="Cost price" error={fieldErr(err, "cost_price")}><Input inputMode="decimal" value={form.cost_price} onChange={(e) => setForm({ ...form, cost_price: e.target.value })} /></Field>
        <Field label="Default taxes" className="sm:col-span-2">
          <div className="flex flex-wrap gap-2">
            {taxes.filter((t) => t.is_active).map((t) => {
              const on = form.taxes.includes(t.id);
              return <button key={t.id} type="button" onClick={() => setForm({ ...form, taxes: on ? form.taxes.filter((x) => x !== t.id) : [...form.taxes, t.id] })} className={clsx("rounded-full border px-3 py-1 text-xs font-medium", on ? "border-brand-600 bg-brand-50 text-brand-700 dark:bg-brand-900/40" : "border-slate-300 dark:border-slate-700")}>{on && <Check className="mr-1 inline size-3" />}{t.name}</button>;
            })}
          </div>
        </Field>
        <Field label="Notes" className="sm:col-span-2"><Textarea rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field>
      </div>
      <div className="mt-5">
        <div className="mb-2 flex items-center justify-between">
          <span className="label mb-0">Variants</span>
          <Button size="sm" variant="secondary" icon={<Plus className="size-3.5" />} onClick={() => setVariants([...variants, { attribute: variants[0]?.attribute ?? "Brand", value: "", extra_price: "0.00" }])}>Add variant</Button>
        </div>
        {variants.length === 0 ? <p className="text-xs text-slate-500">No variants. Example: attribute “Brand”, value “Odoo”, extra price 560.</p> : (
          <div className="space-y-2">
            {variants.map((v, i) => (
              <div key={i} className="grid grid-cols-12 gap-2">
                <Input className="col-span-4" placeholder="Attribute" value={v.attribute} onChange={(e) => setVariants(variants.map((x, j) => (j === i ? { ...x, attribute: e.target.value } : x)))} />
                <Input className="col-span-4" placeholder="Value" value={v.value} onChange={(e) => setVariants(variants.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} />
                <Input className="col-span-3" placeholder="Extra price" inputMode="decimal" value={v.extra_price} onChange={(e) => setVariants(variants.map((x, j) => (j === i ? { ...x, extra_price: e.target.value } : x)))} />
                <button className="col-span-1 text-slate-400 hover:text-rose-600" onClick={() => setVariants(variants.filter((_, j) => j !== i))} aria-label="Remove variant"><Trash2 className="mx-auto size-4" /></button>
              </div>
            ))}
          </div>
        )}
      </div>
      {product && <div className="mt-5 border-t border-slate-100 pt-4 dark:border-slate-800"><Toggle checked={form.is_active} onChange={(v) => setForm({ ...form, is_active: v })} label="Available for sale" hint="Archived products stay on existing subscriptions and invoices." /></div>}
    </Modal>
  );
}

// ===================================================================== plans

function Rule({ on, children }: { on: boolean; children: ReactNode }) {
  return <li className={clsx("flex items-center gap-1.5 text-xs", on ? "text-slate-700 dark:text-slate-300" : "text-slate-400 line-through")}>{on ? <Check className="size-3.5 text-emerald-600" /> : <X className="size-3.5" />}{children}</li>;
}

export function PlansPage() {
  const { isAdmin } = useRole();
  const { data, isLoading } = usePlans();
  const [editing, setEditing] = useState<Plan | "new" | null>(null);
  return (
    <>
      <PageHeader title="Recurring plans" subtitle="How often each plan bills and what customers may do with it." actions={isAdmin && <Button icon={<Plus className="size-4" />} onClick={() => setEditing("new")}>New plan</Button>} />
      <ReadOnlyNote />
      {isLoading ? <Loading /> : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data?.results.map((p) => (
            <div key={p.id} className={clsx("card flex flex-col p-5", !p.is_active && "opacity-60")}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="font-semibold">{p.name}</h3>
                  <p className="text-xs text-slate-500">{p.billing_label}</p>
                </div>
                {p.is_available ? <Badge status="ACTIVE">On sale</Badge> : <Badge status="CLOSED">{p.is_active ? "Not on sale" : "Archived"}</Badge>}
              </div>
              <div className="mt-3"><Money value={p.price} className="text-2xl font-semibold" /><span className="text-xs text-slate-500"> per unit {p.billing_label}</span></div>
              {p.description && <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{p.description}</p>}
              <ul className="mt-3 grid grid-cols-2 gap-1">
                <Rule on={p.auto_close}>Auto-closes at end</Rule>
                <Rule on={p.closable}>Close early</Rule>
                <Rule on={p.pausable}>Pause</Rule>
                <Rule on={p.renewable}>Renew</Rule>
              </ul>
              <div className="mt-auto flex items-center justify-between border-t border-slate-100 pt-3 text-xs text-slate-500 dark:border-slate-800">
                <span>Min qty {Number(p.min_quantity)} · {formatDate(p.start_date)}{p.end_date ? ` – ${formatDate(p.end_date)}` : " onwards"}</span>
                <span className="font-medium text-slate-700 dark:text-slate-300">{p.active_subscriptions} active</span>
              </div>
              {isAdmin && <Button size="sm" variant="secondary" className="mt-3" icon={<Pencil className="size-3.5" />} onClick={() => setEditing(p)}>Edit plan</Button>}
            </div>
          ))}
          {data?.results.length === 0 && <div className="card"><Empty icon={<CalendarClock className="size-5" />} title="No plans yet" /></div>}
        </div>
      )}
      {editing && <PlanModal plan={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
    </>
  );
}

function PlanModal({ plan, onClose }: { plan?: Plan; onClose: () => void }) {
  const periods = useChoices("billing_period");
  const taxes = useTaxes().data ?? [];
  const [form, setForm] = useState({
    name: plan?.name ?? "",
    description: plan?.description ?? "",
    price: plan?.price ?? "0.00",
    billing_period: plan?.billing_period ?? "MONTHLY",
    billing_interval: plan?.billing_interval ?? 1,
    min_quantity: plan?.min_quantity ?? "1",
    start_date: plan?.start_date ?? new Date().toISOString().slice(0, 10),
    end_date: plan?.end_date ?? "",
    auto_close: plan?.auto_close ?? false,
    closable: plan?.closable ?? true,
    pausable: plan?.pausable ?? false,
    renewable: plan?.renewable ?? true,
    taxes: plan?.taxes ?? taxes.filter((t) => t.is_active).slice(0, 1).map((t) => t.id),
    is_active: plan?.is_active ?? true,
  });
  const save = useSaver<Plan>("plans", plan?.id, [["plans"]], onClose, (p) => p.name);
  const err = save.error;
  return (
    <Modal open onClose={onClose} wide title={plan ? `Edit ${plan.name}` : "New recurring plan"}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate({ ...form, end_date: form.end_date || null })}>Save plan</Button></>}>
      {err && <ErrorBox error={err} />}
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Name" className="sm:col-span-2"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
        <Field label="Price per unit" hint="Base fee per billing period; 0 for product-only plans"><Input inputMode="decimal" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} /></Field>
        <Field label="Bills every"><Input type="number" min={1} value={form.billing_interval} onChange={(e) => setForm({ ...form, billing_interval: Number(e.target.value) })} /></Field>
        <Field label="Period"><Select value={form.billing_period} onChange={(e) => setForm({ ...form, billing_period: e.target.value })}>{periods.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}</Select></Field>
        <Field label="Minimum quantity"><Input inputMode="decimal" value={form.min_quantity} onChange={(e) => setForm({ ...form, min_quantity: e.target.value })} /></Field>
        <Field label="Available from"><Input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></Field>
        <Field label="Available until" error={fieldErr(err, "end_date")} hint="Empty = no end"><Input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></Field>
        <Field label="Tax on the plan fee">
          <Select value={form.taxes[0] ?? ""} onChange={(e) => setForm({ ...form, taxes: e.target.value ? [Number(e.target.value)] : [] })}>
            <option value="">No tax</option>
            {taxes.filter((t) => t.is_active).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </Select>
        </Field>
        <Field label="Description" className="sm:col-span-3"><Textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
      </div>
      <div className="mt-5 grid gap-4 border-t border-slate-100 pt-4 sm:grid-cols-2 dark:border-slate-800">
        <Toggle checked={form.auto_close} onChange={(v) => setForm({ ...form, auto_close: v })} label="Close automatically" hint="When a subscription reaches its end date" />
        <Toggle checked={form.closable} onChange={(v) => setForm({ ...form, closable: v })} label="Can be closed early" />
        <Toggle checked={form.pausable} onChange={(v) => setForm({ ...form, pausable: v })} label="Can be paused" hint="Billing stops while paused" />
        <Toggle checked={form.renewable} onChange={(v) => setForm({ ...form, renewable: v })} label="Can be renewed" />
        {plan && <Toggle checked={form.is_active} onChange={(v) => setForm({ ...form, is_active: v })} label="Active" hint="Archived plans keep their existing subscriptions" />}
      </div>
    </Modal>
  );
}

// ===================================================================== quotation templates

export function TemplatesPage() {
  const { data, isLoading } = useTemplates();
  const [editing, setEditing] = useState<QuotationTemplate | "new" | null>(null);
  return (
    <>
      <PageHeader title="Quotation templates" subtitle="Ready-made offers: a plan, product lines and how long the quotation stays valid." actions={<Button icon={<Plus className="size-4" />} onClick={() => setEditing("new")}>New template</Button>} />
      {isLoading ? <Loading /> : (
        <div className="grid gap-4 md:grid-cols-2">
          {data?.map((t) => (
            <div key={t.id} className={clsx("card p-5", !t.is_active && "opacity-60")}>
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-semibold">{t.name}</h3>
                  <p className="text-xs text-slate-500">{t.plan_name} · valid {t.validity_days} days{t.duration_months ? ` · ${t.duration_months}-month contract` : ""}{t.payment_term_name ? ` · ${t.payment_term_name}` : ""}</p>
                </div>
                <Button size="sm" variant="ghost" icon={<Pencil className="size-3.5" />} onClick={() => setEditing(t)}>Edit</Button>
              </div>
              <ul className="mt-3 divide-y divide-slate-100 text-sm dark:divide-slate-800">
                {t.lines.map((l) => <li key={l.id} className="flex justify-between py-1.5"><span>{l.product_name}{l.variant_label && <span className="text-slate-500"> · {l.variant_label}</span>}</span><span className="tabular text-slate-500">× {Number(l.quantity)}</span></li>)}
              </ul>
              {t.notes && <p className="mt-2 text-xs text-slate-500">{t.notes}</p>}
            </div>
          ))}
          {data?.length === 0 && <div className="card"><Empty icon={<FileStack className="size-5" />} title="No templates yet" /></div>}
        </div>
      )}
      {editing && <TemplateModal template={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
    </>
  );
}

function TemplateModal({ template, onClose }: { template?: QuotationTemplate; onClose: () => void }) {
  const plans = (usePlans().data?.results ?? []).filter((p) => p.is_active);
  const products = (useProducts().data?.results ?? []).filter((p) => p.is_active);
  const terms = usePaymentTerms().data ?? [];
  const [form, setForm] = useState({
    name: template?.name ?? "",
    validity_days: template?.validity_days ?? 30,
    plan: template?.plan ?? "",
    payment_term: template?.payment_term ?? "",
    duration_months: template?.duration_months ?? "",
    notes: template?.notes ?? "",
    is_active: template?.is_active ?? true,
  });
  const [lines, setLines] = useState<TemplateLine[]>(template?.lines ?? []);
  const save = useSaver<QuotationTemplate>("quotation-templates", template?.id, [["quotation-templates"]], onClose, (t) => t.name);
  return (
    <Modal open onClose={onClose} wide title={template ? `Edit ${template.name}` : "New quotation template"}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate({ ...form, plan: Number(form.plan), payment_term: form.payment_term || null, duration_months: form.duration_months || null, lines: lines.map((l) => ({ product: l.product, variant: l.variant, quantity: l.quantity, description: l.description })) })}>Save template</Button></>}>
      <ErrorBox error={save.error} />
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Name" className="sm:col-span-2"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
        <Field label="Valid for (days)"><Input type="number" min={1} value={form.validity_days} onChange={(e) => setForm({ ...form, validity_days: Number(e.target.value) })} /></Field>
        <Field label="Recurring plan"><Select value={form.plan} onChange={(e) => setForm({ ...form, plan: e.target.value })}><option value="">Choose…</option>{plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>
        <Field label="Payment terms"><Select value={form.payment_term} onChange={(e) => setForm({ ...form, payment_term: e.target.value })}><option value="">Immediate</option>{terms.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select></Field>
        <Field label="Contract length (months)" hint="Empty = open-ended"><Input type="number" min={1} value={form.duration_months} onChange={(e) => setForm({ ...form, duration_months: e.target.value })} /></Field>
        <Field label="Notes shown on the quotation" className="sm:col-span-3"><Textarea rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field>
      </div>
      <div className="mt-5">
        <div className="mb-2 flex items-center justify-between">
          <span className="label mb-0">Product lines</span>
          <Button size="sm" variant="secondary" icon={<Plus className="size-3.5" />} onClick={() => setLines([...lines, { product: products[0]?.id ?? 0, variant: null, quantity: "1", description: "" }])}>Add line</Button>
        </div>
        <div className="space-y-2">
          {lines.map((l, i) => {
            const product = products.find((p) => p.id === l.product);
            const upd = (d: Partial<TemplateLine>) => setLines(lines.map((x, j) => (j === i ? { ...x, ...d } : x)));
            return (
              <div key={i} className="grid grid-cols-12 gap-2">
                <Select className="col-span-5" value={l.product} onChange={(e) => upd({ product: Number(e.target.value), variant: null })}>{products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select>
                <Select className="col-span-4" value={l.variant ?? ""} disabled={!product?.variants.length} onChange={(e) => upd({ variant: e.target.value ? Number(e.target.value) : null })}><option value="">No variant</option>{product?.variants.map((v) => <option key={v.id} value={v.id}>{v.attribute}: {v.value}</option>)}</Select>
                <Input className="col-span-2" inputMode="decimal" value={l.quantity} onChange={(e) => upd({ quantity: e.target.value })} />
                <button className="col-span-1 text-slate-400 hover:text-rose-600" onClick={() => setLines(lines.filter((_, j) => j !== i))} aria-label="Remove line"><Trash2 className="mx-auto size-4" /></button>
              </div>
            );
          })}
        </div>
      </div>
      {template && <div className="mt-5 border-t border-slate-100 pt-4 dark:border-slate-800"><Toggle checked={form.is_active} onChange={(v) => setForm({ ...form, is_active: v })} label="Active" /></div>}
    </Modal>
  );
}

// ===================================================================== discounts

export function DiscountsPage() {
  const { isAdmin } = useRole();
  const { data, isLoading } = useQuery({ queryKey: ["discounts"], queryFn: () => get<Page<Discount>>("discounts/", { page_size: 200 }) });
  const [editing, setEditing] = useState<Discount | "new" | null>(null);
  return (
    <>
      <PageHeader title="Discounts" subtitle="Rules that apply themselves to the next invoice, and stop when they expire or run out." actions={isAdmin && <Button icon={<Plus className="size-4" />} onClick={() => setEditing("new")}>New discount rule</Button>} />
      <ReadOnlyNote />
      <div className="card overflow-hidden">
        {isLoading ? <Loading /> : (
          <Table head={<><th className="th">Rule</th><th className="th">Value</th><th className="th">Applies to</th><th className="th">Conditions</th><th className="th">Valid</th><th className="th text-right">Used</th><th className="th text-right">Given</th><th className="th">State</th><th className="th" /></>}
            empty={data?.results.length === 0 && <Empty icon={<BadgePercent className="size-5" />} title="No discount rules" />}>
            {data?.results.map((d) => (
              <tr key={d.id}>
                <td className="td"><div className="font-medium">{d.name}</div>{d.code && <code className="text-xs text-slate-500">{d.code}</code>}</td>
                <td className="td font-medium">{d.kind === "PERCENT" ? `${Number(d.value)}%` : <Money value={d.value} />}</td>
                <td className="td text-xs">{d.scope === "PRODUCTS" ? d.product_names.join(", ") : d.subscription_numbers.length ? d.subscription_numbers.join(", ") : "Every subscription"}</td>
                <td className="td text-xs text-slate-500">
                  {d.min_quantity && <div>Qty ≥ {Number(d.min_quantity)}</div>}
                  {d.min_purchase && <div>Purchase ≥ <Money value={d.min_purchase} /></div>}
                  {!d.min_quantity && !d.min_purchase && "None"}
                </td>
                <td className="td text-xs">{d.start_date || d.end_date ? `${formatDate(d.start_date)} – ${formatDate(d.end_date)}` : "Always"}</td>
                <td className="td tabular text-right text-sm">{d.times_used}{d.usage_limit !== null && <span className="text-slate-400"> / {d.usage_limit}</span>}</td>
                <td className="td text-right text-sm"><Money value={d.total_discounted} /></td>
                <td className="td"><Badge status={d.state} /></td>
                <td className="td text-right">{isAdmin && <Button size="sm" variant="ghost" icon={<Pencil className="size-3.5" />} onClick={() => setEditing(d)}>Edit</Button>}</td>
              </tr>
            ))}
          </Table>
        )}
      </div>
      {editing && <DiscountModal discount={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
    </>
  );
}

function DiscountModal({ discount, onClose }: { discount?: Discount; onClose: () => void }) {
  const products = (useProducts().data?.results ?? []).filter((p) => p.is_active);
  const [subSearch, setSubSearch] = useState("");
  const subs = useQuery({ queryKey: ["subscriptions", "pick", subSearch], queryFn: () => get<Page<Subscription>>("subscriptions/", { search: subSearch, status: ["ACTIVE", "CONFIRMED", "QUOTATION"], page_size: 10 }), enabled: subSearch.length > 1 });
  const [form, setForm] = useState({
    name: discount?.name ?? "",
    code: discount?.code ?? "",
    kind: discount?.kind ?? "PERCENT",
    value: discount?.value ?? "",
    scope: discount?.scope ?? "PRODUCTS",
    products: discount?.products ?? [],
    subscriptions: discount?.subscriptions ?? [],
    min_purchase: discount?.min_purchase ?? "",
    min_quantity: discount?.min_quantity ?? "",
    start_date: discount?.start_date ?? "",
    end_date: discount?.end_date ?? "",
    usage_limit: discount?.usage_limit ?? "",
    is_active: discount?.is_active ?? true,
  });
  const [subLabels, setSubLabels] = useState<Record<number, string>>(Object.fromEntries((discount?.subscriptions ?? []).map((id, i) => [id, discount!.subscription_numbers[i]])));
  const save = useSaver<Discount>("discounts", discount?.id, [["discounts"]], onClose, (d) => d.name);
  const err = save.error;
  const n = (v: string | number) => (v === "" ? null : v);
  return (
    <Modal open onClose={onClose} wide title={discount ? `Edit ${discount.name}` : "New discount rule"}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate({ ...form, min_purchase: n(form.min_purchase), min_quantity: n(form.min_quantity), start_date: n(form.start_date), end_date: n(form.end_date), usage_limit: n(form.usage_limit) })}>Save rule</Button></>}>
      {err && <ErrorBox error={err} />}
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Name" className="sm:col-span-2"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Volume: 10% off 20+ seats" /></Field>
        <Field label="Code (optional)"><Input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} /></Field>
        <Field label="Type">
          <div className="flex rounded-lg border border-slate-300 p-0.5 dark:border-slate-700">
            {(["PERCENT", "FIXED"] as const).map((k) => <button key={k} type="button" onClick={() => setForm({ ...form, kind: k })} className={clsx("flex-1 rounded-md py-1.5 text-sm font-medium", form.kind === k ? "bg-brand-600 text-white" : "text-slate-600 dark:text-slate-300")}>{k === "PERCENT" ? "Percentage" : "Fixed amount"}</button>)}
          </div>
        </Field>
        <Field label={form.kind === "PERCENT" ? "Percent off" : "Amount off"} error={fieldErr(err, "value")}><Input inputMode="decimal" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} /></Field>
        <Field label="Applies to">
          <Select value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value as Discount["scope"] })}><option value="PRODUCTS">Specific products</option><option value="SUBSCRIPTION">Whole subscription</option></Select>
        </Field>
        {form.scope === "PRODUCTS" && (
          <Field label="Products" className="sm:col-span-3" error={fieldErr(err, "products")}>
            <div className="flex flex-wrap gap-2">
              {products.map((p) => {
                const on = form.products.includes(p.id);
                return <button key={p.id} type="button" onClick={() => setForm({ ...form, products: on ? form.products.filter((x) => x !== p.id) : [...form.products, p.id] })} className={clsx("rounded-full border px-3 py-1 text-xs font-medium", on ? "border-brand-600 bg-brand-50 text-brand-700 dark:bg-brand-900/40" : "border-slate-300 dark:border-slate-700")}>{on && <Check className="mr-1 inline size-3" />}{p.name}</button>;
              })}
            </div>
          </Field>
        )}
        <Field label="Only for these subscriptions" className="sm:col-span-3" hint="Leave empty to apply to every subscription that meets the conditions.">
          <div className="mb-2 flex flex-wrap gap-2">
            {form.subscriptions.map((id) => <span key={id} className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-xs dark:bg-slate-800">{subLabels[id] ?? `#${id}`}<button onClick={() => setForm({ ...form, subscriptions: form.subscriptions.filter((x) => x !== id) })} aria-label="Remove"><X className="size-3" /></button></span>)}
          </div>
          <div className="relative">
            <Input value={subSearch} onChange={(e) => setSubSearch(e.target.value)} placeholder="Search a subscription or customer to add…" />
            {subs.data && subSearch.length > 1 && (
              <ul className="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded-lg border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
                {subs.data.results.map((s) => <li key={s.id}><button className="w-full px-3 py-2 text-left text-sm hover:bg-slate-50 dark:hover:bg-slate-800" onClick={() => { setForm({ ...form, subscriptions: [...new Set([...form.subscriptions, s.id])] }); setSubLabels({ ...subLabels, [s.id]: s.number }); setSubSearch(""); }}>{s.number} <span className="text-slate-500">· {s.customer_name}</span></button></li>)}
              </ul>
            )}
          </div>
        </Field>
        <Field label="Minimum quantity" hint="Of the matching lines"><Input inputMode="decimal" value={form.min_quantity} onChange={(e) => setForm({ ...form, min_quantity: e.target.value })} /></Field>
        <Field label="Minimum purchase" hint="Value of the matching lines"><Input inputMode="decimal" value={form.min_purchase} onChange={(e) => setForm({ ...form, min_purchase: e.target.value })} /></Field>
        <Field label="Usage limit" hint="Invoices it may apply to"><Input type="number" min={1} value={form.usage_limit} onChange={(e) => setForm({ ...form, usage_limit: e.target.value })} /></Field>
        <Field label="Starts"><Input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></Field>
        <Field label="Ends" error={fieldErr(err, "end_date")}><Input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></Field>
        <div className="flex items-end pb-1"><Toggle checked={form.is_active} onChange={(v) => setForm({ ...form, is_active: v })} label="Active" /></div>
      </div>
    </Modal>
  );
}

// ===================================================================== taxes & payment terms

export function TaxesPage() {
  const { isAdmin } = useRole();
  const taxes = useTaxes();
  const terms = usePaymentTerms();
  const [tax, setTax] = useState<Tax | "new" | null>(null);
  const [term, setTerm] = useState<PaymentTerm | "new" | null>(null);
  return (
    <>
      <PageHeader title="Taxes & payment terms" subtitle="Tax rules are applied automatically to every invoice line. Rates are data, never hard-coded." />
      <ReadOnlyNote />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Taxes" padded={false} actions={isAdmin && <Button size="sm" icon={<Plus className="size-3.5" />} onClick={() => setTax("new")}>New tax</Button>}>
          {taxes.isLoading ? <Loading /> : (
            <Table head={<><th className="th">Name</th><th className="th">Computation</th><th className="th text-right">Rate</th><th className="th" /></>}>
              {taxes.data?.map((t) => (
                <tr key={t.id} className={clsx(!t.is_active && "opacity-50")}>
                  <td className="td"><div className="font-medium">{t.name}</div>{t.description && <div className="text-xs text-slate-500">{t.description}</div>}</td>
                  <td className="td text-sm">{t.computation === "PERCENT" ? "% of price" : "Fixed per unit"}</td>
                  <td className="td tabular text-right font-medium">{t.computation === "PERCENT" ? `${Number(t.amount)}%` : <Money value={t.amount} />}</td>
                  <td className="td text-right">{isAdmin && <Button size="sm" variant="ghost" icon={<Pencil className="size-3.5" />} onClick={() => setTax(t)} />}</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
        <Card title="Payment terms" padded={false} actions={isAdmin && <Button size="sm" icon={<Plus className="size-3.5" />} onClick={() => setTerm("new")}>New term</Button>}>
          {terms.isLoading ? <Loading /> : (
            <Table head={<><th className="th">Name</th><th className="th text-right">Due after</th><th className="th" /></>}>
              {terms.data?.map((t) => (
                <tr key={t.id} className={clsx(!t.is_active && "opacity-50")}>
                  <td className="td font-medium">{t.name}</td>
                  <td className="td tabular text-right">{t.due_days ? `${t.due_days} days` : "Immediately"}</td>
                  <td className="td text-right">{isAdmin && <Button size="sm" variant="ghost" icon={<Pencil className="size-3.5" />} onClick={() => setTerm(t)} />}</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      </div>
      {tax && <TaxModal tax={tax === "new" ? undefined : tax} onClose={() => setTax(null)} />}
      {term && <TermModal term={term === "new" ? undefined : term} onClose={() => setTerm(null)} />}
    </>
  );
}

function TaxModal({ tax, onClose }: { tax?: Tax; onClose: () => void }) {
  const [form, setForm] = useState({ name: tax?.name ?? "", computation: tax?.computation ?? "PERCENT", amount: tax?.amount ?? "", description: tax?.description ?? "", is_active: tax?.is_active ?? true });
  const save = useSaver<Tax>("taxes", tax?.id, [["taxes"]], onClose, (t) => t.name);
  return (
    <Modal open onClose={onClose} title={tax ? `Edit ${tax.name}` : "New tax"} footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate(form)}>Save</Button></>}>
      <ErrorBox error={save.error} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name" className="sm:col-span-2"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="GST 18%" /></Field>
        <Field label="Computation"><Select value={form.computation} onChange={(e) => setForm({ ...form, computation: e.target.value as Tax["computation"] })}><option value="PERCENT">Percentage of price</option><option value="FIXED">Fixed amount per unit</option></Select></Field>
        <Field label={form.computation === "PERCENT" ? "Rate (%)" : "Amount per unit"}><Input inputMode="decimal" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></Field>
        <Field label="Description" className="sm:col-span-2"><Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
        <div className="sm:col-span-2"><Toggle checked={form.is_active} onChange={(v) => setForm({ ...form, is_active: v })} label="Active" /></div>
      </div>
    </Modal>
  );
}

function TermModal({ term, onClose }: { term?: PaymentTerm; onClose: () => void }) {
  const [form, setForm] = useState({ name: term?.name ?? "", due_days: term?.due_days ?? 30, is_active: term?.is_active ?? true });
  const save = useSaver<PaymentTerm>("payment-terms", term?.id, [["payment-terms"]], onClose, (t) => t.name);
  return (
    <Modal open onClose={onClose} title={term ? `Edit ${term.name}` : "New payment term"} footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate(form)}>Save</Button></>}>
      <ErrorBox error={save.error} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Net 30" /></Field>
        <Field label="Due after (days)"><Input type="number" min={0} value={form.due_days} onChange={(e) => setForm({ ...form, due_days: Number(e.target.value) })} /></Field>
        <div className="sm:col-span-2"><Toggle checked={form.is_active} onChange={(v) => setForm({ ...form, is_active: v })} label="Active" /></div>
      </div>
    </Modal>
  );
}
