import { useQuery } from "@tanstack/react-query";
import { Mail, Paperclip, Plus, UserCog } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, ErrorBox, Field, formatDate, formatDateTime, Input, Loading, Modal, PageHeader, Pagination, Select, Table, Toggle, timeAgo } from "../components/ui";
import { ApiError, get, patch, post, type Page } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useAction, useListParams } from "../lib/hooks";
import type { OutboundEmail, User } from "../lib/types";
import { PasswordRules } from "./auth";

export function TeamPage() {
  const { user: me } = useAuth();
  const { data, isLoading } = useQuery({ queryKey: ["team"], queryFn: () => get<Page<User>>("team/", { page_size: 200 }) });
  const [editing, setEditing] = useState<User | "new" | null>(null);
  return (
    <>
      <PageHeader title="Team" subtitle="Only an administrator can add staff. Staff handle day-to-day work; catalog, taxes and discounts stay with admins." actions={<Button icon={<Plus className="size-4" />} onClick={() => setEditing("new")}>Add team member</Button>} />
      <div className="card overflow-hidden">
        {isLoading ? <Loading /> : (
          <Table head={<><th className="th">Name</th><th className="th">Email</th><th className="th">Role</th><th className="th">Status</th><th className="th">Joined</th><th className="th" /></>}
            empty={data?.results.length === 0 && <Empty icon={<UserCog className="size-5" />} title="No team members" />}>
            {data?.results.map((u) => (
              <tr key={u.id}>
                <td className="td font-medium">{u.name}{u.id === me?.id && <span className="ml-2 text-xs text-slate-500">(you)</span>}</td>
                <td className="td text-sm">{u.email}</td>
                <td className="td"><Badge status={u.role === "ADMIN" ? "CONFIRMED" : "QUOTATION"}>{u.role === "ADMIN" ? "Admin" : "Internal staff"}</Badge></td>
                <td className="td">{u.is_active ? <Badge status="ACTIVE">Active</Badge> : <Badge status="CLOSED">Deactivated</Badge>}</td>
                <td className="td text-sm">{formatDate(u.date_joined)}</td>
                <td className="td text-right"><Button size="sm" variant="ghost" onClick={() => setEditing(u)}>Edit</Button></td>
              </tr>
            ))}
          </Table>
        )}
      </div>
      {editing && <MemberModal member={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
    </>
  );
}

function MemberModal({ member, onClose }: { member?: User; onClose: () => void }) {
  const [form, setForm] = useState({ name: member?.name ?? "", email: member?.email ?? "", phone: member?.phone ?? "", role: member?.role ?? "STAFF", is_active: member?.is_active ?? true, password: "" });
  const save = useAction(() => {
    const body: Record<string, unknown> = { ...form };
    if (!form.password) delete body.password;
    return member ? patch<User>(`team/${member.id}/`, body) : post<User>("team/", body);
  }, { invalidate: [["team"]], success: (u) => `${u.name} saved`, onSuccess: onClose });
  const err = save.error instanceof ApiError ? save.error : null;
  return (
    <Modal open onClose={onClose} title={member ? `Edit ${member.name}` : "Add team member"} footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate(undefined)}>Save</Button></>}>
      {err && !err.fields?.password && !err.fields?.email && <ErrorBox error={err} />}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
        <Field label="Role"><Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as User["role"] })}><option value="STAFF">Internal staff</option><option value="ADMIN">Admin</option></Select></Field>
        <Field label="Email" error={err?.fieldError("email")} className="sm:col-span-2"><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
        <Field label={member ? "New password (optional)" : "Starting password"} error={err?.fieldError("password")} className="sm:col-span-2">
          <Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} autoComplete="new-password" />
          {form.password && <PasswordRules password={form.password} />}
        </Field>
        {member && <div className="sm:col-span-2"><Toggle checked={form.is_active} onChange={(v) => setForm({ ...form, is_active: v })} label="Active" hint="Deactivated members cannot sign in" /></div>}
      </div>
    </Modal>
  );
}

export function OutboxPage() {
  const { value, set, page } = useListParams();
  const { data, isLoading, error } = useQuery({ queryKey: ["outbox", page, value("category")], queryFn: () => get<Page<OutboundEmail>>("outbox/", { page, category: value("category") }), placeholderData: (p) => p });
  const [open, setOpen] = useState<OutboundEmail | null>(null);
  return (
    <>
      <PageHeader title="Email outbox" subtitle="Every email the platform sent: quotations, invoices, receipts, reminders and password resets." actions={
        <Select value={value("category")} onChange={(e) => set({ category: e.target.value })} className="w-48">
          <option value="">All emails</option>
          {["quotation", "invoice", "receipt", "reminder", "password_reset", "welcome"].map((c) => <option key={c} value={c}>{c.replace("_", " ")}</option>)}
        </Select>
      } />
      <ErrorBox error={error} />
      <div className="card overflow-hidden">
        {isLoading ? <Loading /> : (
          <Table head={<><th className="th">To</th><th className="th">Subject</th><th className="th">Type</th><th className="th">Status</th><th className="th">Sent</th></>}
            empty={data?.results.length === 0 && <Empty icon={<Mail className="size-5" />} title="No emails yet" />}>
            {data?.results.map((m) => (
              <tr key={m.id} className="cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/40" onClick={() => setOpen(m)}>
                <td className="td text-sm">{m.to}</td>
                <td className="td text-sm font-medium">{m.subject}{m.attachments.length > 0 && <Paperclip className="ml-1 inline size-3.5 text-slate-400" />}</td>
                <td className="td"><Badge status="CONFIRMED">{m.category.replace("_", " ") || "other"}</Badge></td>
                <td className="td">{m.status === "failed" ? <Badge status="OVERDUE">Failed</Badge> : <Badge status="ACTIVE">{m.status === "stored" ? "In outbox" : "Delivered"}</Badge>}</td>
                <td className="td text-xs text-slate-500" title={formatDateTime(m.created_at)}>{timeAgo(m.created_at)}</td>
              </tr>
            ))}
          </Table>
        )}
        {data && <Pagination page={page} count={data.count} onPage={(p) => set({ page: p })} />}
      </div>
      <Modal open={!!open} onClose={() => setOpen(null)} title={open?.subject} wide>
        {open && (
          <Card padded>
            <div className="mb-3 text-xs text-slate-500">To {open.to} · {formatDateTime(open.created_at)}{open.attachments.length > 0 && ` · Attached: ${open.attachments.join(", ")}`}</div>
            <pre className="font-sans text-sm whitespace-pre-wrap">{linkify(open.body)}</pre>
            {open.error && <ErrorBox error={open.error} />}
          </Card>
        )}
      </Modal>
    </>
  );
}

function linkify(text: string) {
  return text.split(/(https?:\/\/\S+)/g).map((part, i) =>
    /^https?:\/\//.test(part) ? <a key={i} href={part.replace(/^https?:\/\/[^/]+/, "")} className="text-brand-600 underline">{part}</a> : part,
  );
}
