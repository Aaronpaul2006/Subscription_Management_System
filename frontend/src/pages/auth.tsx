import { Check, CircleAlert, KeyRound, Mail, X } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";
import { Button, ErrorBox, Field, Input } from "../components/ui";
import { ApiError, post } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useMeta } from "../lib/hooks";

function AuthShell({ title, subtitle, children, footer }: { title: string; subtitle?: ReactNode; children: ReactNode; footer?: ReactNode }) {
  const { data: meta } = useMeta();
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="relative hidden overflow-hidden bg-gradient-to-br from-brand-700 via-brand-600 to-violet-600 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="flex items-center gap-3">
          <img src="/favicon.svg" alt="" className="size-10 rounded-xl ring-2 ring-white/30" />
          <span className="text-lg font-semibold">{meta?.company.name ?? "Brightloop Software"}</span>
        </div>
        <div className="max-w-md">
          <h2 className="text-4xl leading-tight font-semibold">Plans, subscriptions and recurring billing in one place.</h2>
          <ul className="mt-8 space-y-3 text-brand-100">
            {[
              "Quotations become subscriptions in a few clicks",
              "Billing day runs itself — nothing billed twice, nothing skipped",
              "Discounts apply on their own, and stop on their own",
              "Know your MRR, collections and overdue invoices at a glance",
            ].map((line) => (
              <li key={line} className="flex items-start gap-3">
                <Check className="mt-0.5 size-5 shrink-0 rounded-full bg-white/20 p-0.5" />
                {line}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-brand-200">Secure sign-in · Your data stays on Brightloop servers</p>
        <div className="pointer-events-none absolute -right-24 -bottom-24 size-96 rounded-full bg-white/10 blur-2xl" />
      </div>
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <img src="/favicon.svg" alt="" className="mb-6 size-10 lg:hidden" />
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
          <div className="mt-8">{children}</div>
          {footer && <div className="mt-6 text-center text-sm text-slate-500">{footer}</div>}
        </div>
      </div>
    </div>
  );
}

export function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await login(email, password);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from ?? (user.role === "CUSTOMER" ? "/portal" : "/"), { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  const demo = (e: string, p: string) => {
    setEmail(e);
    setPassword(p);
  };

  return (
    <AuthShell
      title="Welcome back"
      subtitle="Sign in to your Brightloop account."
      footer={
        <>
          New to Brightloop?{" "}
          <Link to="/signup" className="font-medium text-brand-600 hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4">
        <ErrorBox error={error} />
        <Field label="Email">
          <Input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password">
          <Input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <div className="flex justify-end">
          <Link to="/forgot-password" className="text-xs font-medium text-brand-600 hover:underline">
            Forgot password?
          </Link>
        </div>
        <Button type="submit" loading={busy} className="w-full">
          Sign in
        </Button>
      </form>
      {import.meta.env.DEV && (
        <div className="mt-6 rounded-lg border border-dashed border-slate-300 p-3 text-xs dark:border-slate-700">
          <div className="mb-2 font-medium text-slate-500">Demo accounts (development only)</div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="rounded bg-slate-100 px-2 py-1 hover:bg-slate-200 dark:bg-slate-800" onClick={() => demo("admin@brightloop.test", "Admin@12345")}>
              Admin
            </button>
            <button type="button" className="rounded bg-slate-100 px-2 py-1 hover:bg-slate-200 dark:bg-slate-800" onClick={() => demo("staff@brightloop.test", "Staff@12345")}>
              Staff
            </button>
            <button type="button" className="rounded bg-slate-100 px-2 py-1 hover:bg-slate-200 dark:bg-slate-800" onClick={() => demo("priya@acmeretail.test", "Customer@123")}>
              Customer
            </button>
          </div>
        </div>
      )}
    </AuthShell>
  );
}

/** Live checklist of the password rules, mirrored on the server. */
export function PasswordRules({ password }: { password: string }) {
  const rules = [
    { ok: password.length > 8, label: "More than 8 characters" },
    { ok: /[A-Z]/.test(password), label: "An uppercase letter" },
    { ok: /[a-z]/.test(password), label: "A lowercase letter" },
    { ok: /[^A-Za-z0-9]/.test(password), label: "A special character" },
  ];
  return (
    <ul className="mt-2 grid grid-cols-2 gap-1 text-xs">
      {rules.map((r) => (
        <li key={r.label} className={r.ok ? "flex items-center gap-1 text-emerald-600" : "flex items-center gap-1 text-slate-400"}>
          {r.ok ? <Check className="size-3" /> : <X className="size-3" />} {r.label}
        </li>
      ))}
    </ul>
  );
}

export const passwordOk = (p: string) => p.length > 8 && /[A-Z]/.test(p) && /[a-z]/.test(p) && /[^A-Za-z0-9]/.test(p);

export function Signup() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", company: "", email: "", password: "", confirm: "" });
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signup({ name: form.name, company: form.company, email: form.email, password: form.password });
      navigate("/portal", { replace: true });
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setBusy(false);
    }
  };
  const mismatch = form.confirm.length > 0 && form.confirm !== form.password;

  return (
    <AuthShell
      title="Create your account"
      subtitle="See and manage your subscriptions and invoices online."
      footer={
        <>
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-brand-600 hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4">
        {error && !error.fields?.email && !error.fields?.password && <ErrorBox error={error} />}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Your name">
            <Input required value={form.name} onChange={set("name")} autoComplete="name" />
          </Field>
          <Field label="Company (optional)">
            <Input value={form.company} onChange={set("company")} autoComplete="organization" />
          </Field>
        </div>
        <Field label="Email" error={error?.fieldError("email")}>
          <Input type="email" required value={form.email} onChange={set("email")} autoComplete="email" />
        </Field>
        <Field label="Password" error={error?.fieldError("password") ?? error?.fieldError("non_field_errors")}>
          <Input type="password" required value={form.password} onChange={set("password")} autoComplete="new-password" />
          <PasswordRules password={form.password} />
        </Field>
        <Field label="Confirm password" error={mismatch ? "Passwords do not match" : undefined}>
          <Input type="password" required value={form.confirm} onChange={set("confirm")} autoComplete="new-password" />
        </Field>
        <Button type="submit" loading={busy} disabled={!passwordOk(form.password) || mismatch} className="w-full">
          Create account
        </Button>
      </form>
    </AuthShell>
  );
}

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post("auth/password-reset/", { email });
      setSent(true);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthShell title="Reset your password" subtitle="We'll email a reset link to your registered address." footer={<Link to="/login" className="font-medium text-brand-600 hover:underline">Back to sign in</Link>}>
      {sent ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300">
          <Mail className="mb-2 size-5" />
          If <strong>{email}</strong> has an account, a reset link is on its way. It is valid for 24 hours.
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <ErrorBox error={error} />
          <Field label="Email">
            <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Button type="submit" loading={busy} className="w-full" icon={<KeyRound className="size-4" />}>
            Send reset link
          </Button>
        </form>
      )}
    </AuthShell>
  );
}

export function ResetPassword() {
  const { uid, token } = useParams();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post("auth/password-reset/confirm/", { uid, token, password });
      setDone(true);
      setTimeout(() => navigate("/login"), 1800);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthShell title="Choose a new password">
      {done ? (
        <div className="flex items-center gap-2 rounded-lg bg-emerald-50 p-4 text-sm text-emerald-700">
          <Check className="size-4" /> Password updated. Taking you to sign in…
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          {error ? (
            <div className="flex gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
              <CircleAlert className="size-4 shrink-0" />
              {(error as Error).message}
            </div>
          ) : null}
          <Field label="New password">
            <Input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
            <PasswordRules password={password} />
          </Field>
          <Button type="submit" loading={busy} disabled={!passwordOk(password)} className="w-full">
            Update password
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
