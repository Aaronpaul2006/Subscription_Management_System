import { useQuery } from "@tanstack/react-query";
import { Search, Wallet } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { Badge, Empty, ErrorBox, formatDate, Input, Loading, Money, PageHeader, Pagination, Select, Table, useDebounced } from "../components/ui";
import { get, type Page } from "../lib/api";
import { useChoices, useListParams } from "../lib/hooks";
import type { Payment } from "../lib/types";

export function PaymentsPage({ portal = false }: { portal?: boolean }) {
  const { value, set, page } = useListParams();
  const methods = useChoices("payment_method");
  const [search, setSearch] = useState(value("search"));
  const debounced = useDebounced(search);
  useEffect(() => {
    if (debounced !== value("search")) set({ search: debounced });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);
  const filters = { search: value("search"), method: value("method"), payment_date__gte: value("from"), payment_date__lte: value("to"), page };
  const { data, isLoading, error } = useQuery({
    queryKey: ["payments", filters],
    queryFn: () => get<Page<Payment>>("payments/", filters),
    placeholderData: (prev) => prev,
  });
  const invoiceBase = portal ? "/portal/invoices" : "/invoices";

  return (
    <>
      <PageHeader title={portal ? "Payment history" : "Payments"} subtitle={portal ? "Every payment we have received from you." : "Every payment received, by method, date and invoice."} />
      <div className="card overflow-hidden">
        {!portal && (
          <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-3 dark:border-slate-800">
            <div className="relative min-w-60 flex-1">
              <Search className="absolute top-2.5 left-3 size-4 text-slate-400" />
              <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search invoice, customer, reference…" className="pl-9" />
            </div>
            <Select value={value("method")} onChange={(e) => set({ method: e.target.value })} className="w-44">
              <option value="">All methods</option>
              {methods.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </Select>
            <Input type="date" value={value("from")} onChange={(e) => set({ from: e.target.value })} className="w-40" aria-label="From" />
            <span className="text-slate-400">–</span>
            <Input type="date" value={value("to")} onChange={(e) => set({ to: e.target.value })} className="w-40" aria-label="To" />
          </div>
        )}
        <ErrorBox error={error} />
        {isLoading ? (
          <Loading />
        ) : (
          <Table
            head={
              <>
                <th className="th">Date</th>
                <th className="th">Invoice</th>
                {!portal && <th className="th">Customer</th>}
                <th className="th">Method</th>
                <th className="th">Reference</th>
                {!portal && <th className="th">Recorded by</th>}
                <th className="th text-right">Amount</th>
              </>
            }
            empty={data?.results.length === 0 && <Empty icon={<Wallet className="size-5" />} title="No payments found" />}
          >
            {data?.results.map((p) => (
              <tr key={p.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                <td className="td tabular">{formatDate(p.payment_date)}</td>
                <td className="td"><Link to={`${invoiceBase}/${p.invoice}`} className="font-medium text-brand-600 hover:underline">{p.invoice_number}</Link></td>
                {!portal && <td className="td max-w-52 truncate">{p.customer_name}</td>}
                <td className="td">{p.method_label}{p.source === "PORTAL" && <Badge status="QUOTATION" className="ml-2">Online</Badge>}</td>
                <td className="td text-xs text-slate-500">{p.reference || "—"}{p.note && <div className="truncate">{p.note}</div>}</td>
                {!portal && <td className="td text-xs text-slate-500">{p.recorded_by_name ?? "Customer"}</td>}
                <td className="td text-right font-medium"><Money value={p.amount} /></td>
              </tr>
            ))}
          </Table>
        )}
        {data && <Pagination page={page} count={data.count} onPage={(n) => set({ page: n })} />}
      </div>
    </>
  );
}
