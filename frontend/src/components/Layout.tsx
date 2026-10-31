import clsx from "clsx";
import {
  BadgePercent,
  Banknote,
  BarChart3,
  Boxes,
  CalendarClock,
  FileStack,
  FileText,
  Gauge,
  Home,
  LogOut,
  Mail,
  Menu,
  Moon,
  Receipt,
  Repeat,
  Search,
  Sun,
  Timer,
  UserCog,
  Users,
  WalletCards,
  X,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { onServerTiming } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useMeta } from "../lib/hooks";
import type { Role } from "../lib/types";
import { CommandPalette } from "./CommandPalette";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  roles: Role[];
  end?: boolean;
}
interface NavGroup {
  title?: string;
  items: NavItem[];
}

const I = "size-4";
const INTERNAL: Role[] = ["ADMIN", "STAFF"];
const NAV: NavGroup[] = [
  {
    items: [
      { to: "/", label: "Dashboard", icon: <Gauge className={I} />, roles: INTERNAL, end: true },
      { to: "/portal", label: "Home", icon: <Home className={I} />, roles: ["CUSTOMER"], end: true },
      { to: "/portal/subscriptions", label: "My subscriptions", icon: <Repeat className={I} />, roles: ["CUSTOMER"] },
      { to: "/portal/invoices", label: "My invoices", icon: <Receipt className={I} />, roles: ["CUSTOMER"] },
      { to: "/portal/payments", label: "Payment history", icon: <WalletCards className={I} />, roles: ["CUSTOMER"] },
    ],
  },
  {
    title: "Sales & billing",
    items: [
      { to: "/subscriptions", label: "Subscriptions", icon: <Repeat className={I} />, roles: INTERNAL },
      { to: "/invoices", label: "Invoices", icon: <Receipt className={I} />, roles: INTERNAL },
      { to: "/payments", label: "Payments", icon: <Banknote className={I} />, roles: INTERNAL },
      { to: "/billing", label: "Billing runs", icon: <CalendarClock className={I} />, roles: INTERNAL },
      { to: "/customers", label: "Customers", icon: <Users className={I} />, roles: INTERNAL },
      { to: "/reports", label: "Reports", icon: <BarChart3 className={I} />, roles: INTERNAL },
    ],
  },
  {
    title: "Configuration",
    items: [
      { to: "/products", label: "Products", icon: <Boxes className={I} />, roles: INTERNAL },
      { to: "/plans", label: "Recurring plans", icon: <CalendarClock className={I} />, roles: INTERNAL },
      { to: "/templates", label: "Quotation templates", icon: <FileStack className={I} />, roles: INTERNAL },
      { to: "/discounts", label: "Discounts", icon: <BadgePercent className={I} />, roles: INTERNAL },
      { to: "/taxes", label: "Taxes & terms", icon: <FileText className={I} />, roles: INTERNAL },
    ],
  },
  {
    title: "Admin",
    items: [
      { to: "/team", label: "Team", icon: <UserCog className={I} />, roles: ["ADMIN"] },
      { to: "/outbox", label: "Email outbox", icon: <Mail className={I} />, roles: ["ADMIN"] },
    ],
  },
];

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("theme", dark ? "dark" : "light");
    } catch {
      /* private mode */
    }
  }, [dark]);
  return [dark, () => setDark((d) => !d)] as const;
}

export function Layout() {
  const { user, logout } = useAuth();
  const { data: meta } = useMeta();
  const [dark, toggleTheme] = useTheme();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [timing, setTiming] = useState("");
  const location = useLocation();
  const navigate = useNavigate();
  const role = user!.role;
  const internal = role !== "CUSTOMER";

  useEffect(() => onServerTiming(setTiming), []);
  useEffect(() => setMobileOpen(false), [location.pathname]);
  useEffect(() => {
    if (!internal) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [internal]);

  const nav = (
    <nav className="flex flex-1 flex-col gap-5 overflow-y-auto px-3 py-4">
      {NAV.map((group, i) => {
        const items = group.items.filter((item) => item.roles.includes(role));
        if (!items.length) return null;
        return (
          <div key={i}>
            {group.title && <div className="mb-1 px-3 text-[11px] font-semibold tracking-wider text-slate-400 uppercase">{group.title}</div>}
            <ul className="space-y-0.5">
              {items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) =>
                      clsx(
                        "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                        isActive
                          ? "bg-brand-50 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300"
                          : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100",
                      )
                    }
                  >
                    {item.icon}
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </nav>
  );

  const brand = (
    <Link to={internal ? "/" : "/portal"} className="flex items-center gap-2.5 px-5 py-4">
      <img src="/favicon.svg" alt="" className="size-8" />
      <div className="leading-tight">
        <div className="text-sm font-semibold">{meta?.company.name ?? "Brightloop"}</div>
        <div className="text-[11px] text-slate-500">{internal ? "Billing workspace" : "Customer portal"}</div>
      </div>
    </Link>
  );

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="no-print fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-slate-200 bg-white lg:flex dark:border-slate-800 dark:bg-slate-900">
        {brand}
        {nav}
      </aside>
      {mobileOpen && (
        <div className="no-print fixed inset-0 z-40 lg:hidden" onClick={() => setMobileOpen(false)}>
          <div className="absolute inset-0 bg-slate-900/40" />
          <aside className="absolute inset-y-0 left-0 flex w-72 flex-col bg-white dark:bg-slate-900" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between pr-3">
              {brand}
              <button onClick={() => setMobileOpen(false)} aria-label="Close menu">
                <X className="size-5" />
              </button>
            </div>
            {nav}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col lg:pl-64">
        {/* Top bar */}
        <header className="no-print sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-slate-200 bg-white/80 px-4 backdrop-blur sm:px-6 dark:border-slate-800 dark:bg-slate-900/80">
          <button className="lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open menu">
            <Menu className="size-5" />
          </button>
          {internal ? (
            <button
              onClick={() => setPaletteOpen(true)}
              className="flex w-full max-w-md items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm text-slate-400 hover:border-slate-300 dark:border-slate-700 dark:bg-slate-800"
            >
              <Search className="size-4" />
              <span className="flex-1 text-left">Search subscriptions, customers, invoices…</span>
              <kbd className="hidden rounded border border-slate-200 bg-white px-1.5 text-[10px] font-medium sm:block dark:border-slate-600 dark:bg-slate-700">Ctrl K</kbd>
            </button>
          ) : (
            <div className="flex-1" />
          )}
          <div className="ml-auto flex items-center gap-1">
            <button onClick={toggleTheme} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Toggle dark mode">
              {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </button>
            <Link to="/profile" className="flex items-center gap-2 rounded-lg px-2 py-1 hover:bg-slate-100 dark:hover:bg-slate-800">
              <span className="flex size-7 items-center justify-center rounded-full bg-brand-600 text-xs font-semibold text-white">
                {user!.name
                  .split(" ")
                  .map((p) => p[0])
                  .slice(0, 2)
                  .join("")}
              </span>
              <span className="hidden text-left leading-tight sm:block">
                <span className="block text-sm font-medium">{user!.name}</span>
                <span className="block text-[11px] text-slate-500">{role === "ADMIN" ? "Administrator" : role === "STAFF" ? "Internal staff" : "Customer"}</span>
              </span>
            </Link>
            <button
              onClick={async () => {
                await logout();
                navigate("/login");
              }}
              className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
              aria-label="Sign out"
              title="Sign out"
            >
              <LogOut className="size-4" />
            </button>
          </div>
        </header>

        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </main>

        <footer className="no-print flex items-center justify-between gap-4 border-t border-slate-200 px-6 py-2 text-[11px] text-slate-400 dark:border-slate-800">
          <span>© {new Date().getFullYear()} {meta?.company.name}</span>
          {timing && (
            <span className="flex items-center gap-1" title="Server time for the last request">
              <Timer className="size-3" /> {timing}
            </span>
          )}
        </footer>
      </div>
      {internal && <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />}
    </div>
  );
}
