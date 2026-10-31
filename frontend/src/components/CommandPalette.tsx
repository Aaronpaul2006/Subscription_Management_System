import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Boxes, CalendarClock, CornerDownLeft, Plus, Receipt, Repeat, Search, Users } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { get } from "../lib/api";
import { useDebounced } from "./ui";

interface Result {
  type: string;
  id: number;
  title: string;
  subtitle: string;
}

const ICONS: Record<string, ReactNode> = {
  subscription: <Repeat className="size-4" />,
  customer: <Users className="size-4" />,
  invoice: <Receipt className="size-4" />,
  product: <Boxes className="size-4" />,
  plan: <CalendarClock className="size-4" />,
};
const ROUTES: Record<string, (id: number) => string> = {
  subscription: (id) => `/subscriptions/${id}`,
  customer: (id) => `/customers/${id}`,
  invoice: (id) => `/invoices/${id}`,
  product: () => `/products`,
  plan: () => `/plans`,
};

const QUICK = [
  { title: "New subscription", subtitle: "Start a quotation", to: "/subscriptions/new" },
  { title: "Run billing", subtitle: "Preview and generate due invoices", to: "/billing" },
  { title: "Overdue invoices", subtitle: "Chase what is late", to: "/invoices?tab=OVERDUE" },
  { title: "New customer", subtitle: "Add a customer record", to: "/customers?new=1" },
];

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [term, setTerm] = useState("");
  const [index, setIndex] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const q = useDebounced(term, 200);
  const { data = [], isFetching } = useQuery({
    queryKey: ["search", q],
    queryFn: () => get<Result[]>("search/", { q }),
    enabled: open && q.trim().length >= 2,
  });

  const items = useMemo(
    () =>
      q.trim().length >= 2
        ? data.map((r) => ({ key: `${r.type}-${r.id}`, icon: ICONS[r.type], title: r.title, subtitle: r.subtitle, tag: r.type, to: ROUTES[r.type](r.id) }))
        : QUICK.map((r) => ({ key: r.to, icon: <Plus className="size-4" />, title: r.title, subtitle: r.subtitle, tag: "action", to: r.to })),
    [data, q],
  );

  useEffect(() => {
    if (open) {
      setTerm("");
      setIndex(0);
      setTimeout(() => input.current?.focus(), 10);
    }
  }, [open]);
  useEffect(() => setIndex(0), [q]);

  if (!open) return null;
  const go = (to: string) => {
    onClose();
    navigate(to);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-slate-900/50 p-4 pt-[12vh] backdrop-blur-sm" onMouseDown={onClose}>
      <div className="card w-full max-w-xl overflow-hidden shadow-2xl" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3 border-b border-slate-100 px-4 dark:border-slate-800">
          <Search className="size-4 text-slate-400" />
          <input
            ref={input}
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setIndex((i) => Math.min(i + 1, items.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setIndex((i) => Math.max(i - 1, 0));
              } else if (e.key === "Enter" && items[index]) go(items[index].to);
              else if (e.key === "Escape") onClose();
            }}
            placeholder="Search by number, customer, product…"
            className="h-12 flex-1 bg-transparent text-sm outline-none"
          />
          {isFetching && <span className="text-xs text-slate-400">Searching…</span>}
        </div>
        <ul className="max-h-96 overflow-y-auto p-2">
          {q.trim().length < 2 && <li className="px-3 pt-1 pb-2 text-[11px] font-semibold tracking-wider text-slate-400 uppercase">Quick actions</li>}
          {items.map((item, i) => (
            <li key={item.key}>
              <button
                onMouseEnter={() => setIndex(i)}
                onClick={() => go(item.to)}
                className={clsx("flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left", i === index && "bg-brand-50 dark:bg-brand-900/30")}
              >
                <span className="text-slate-400">{item.icon}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{item.title}</span>
                  <span className="block truncate text-xs text-slate-500">{item.subtitle}</span>
                </span>
                <span className="text-[10px] tracking-wide text-slate-400 uppercase">{item.tag}</span>
                {i === index && <CornerDownLeft className="size-3.5 text-slate-400" />}
              </button>
            </li>
          ))}
          {q.trim().length >= 2 && !isFetching && items.length === 0 && <li className="px-3 py-6 text-center text-sm text-slate-500">Nothing matches “{q}”.</li>}
        </ul>
      </div>
    </div>
  );
}
