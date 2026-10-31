import { useState } from "react";
import { Button, Card, ErrorBox, Field, Input, KeyValue, PageHeader, formatDate } from "../components/ui";
import { patch, post } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useAction } from "../lib/hooks";
import type { User } from "../lib/types";
import { PasswordRules, passwordOk } from "./auth";

export function ProfilePage() {
  const { user, refresh } = useAuth();
  const [name, setName] = useState(user!.name);
  const [phone, setPhone] = useState(user!.phone);
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const saveProfile = useAction(() => patch<User>("auth/me/", { name, phone }), { success: "Profile updated", onSuccess: () => void refresh() });
  const changePw = useAction(() => post("auth/change-password/", pw), { success: "Password changed", onSuccess: () => setPw({ current_password: "", new_password: "" }) });
  return (
    <>
      <PageHeader title="Your profile" subtitle={user!.email} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Details">
          <div className="space-y-4">
            <KeyValue items={[["Email", user!.email], ["Role", user!.role === "ADMIN" ? "Administrator" : user!.role === "STAFF" ? "Internal staff" : "Customer"], ["Member since", formatDate(user!.date_joined)]]} />
            <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <Field label="Phone"><Input value={phone} onChange={(e) => setPhone(e.target.value)} /></Field>
            <Button loading={saveProfile.isPending} onClick={() => saveProfile.mutate(undefined)}>Save</Button>
          </div>
        </Card>
        <Card title="Change password">
          <div className="space-y-4">
            <ErrorBox error={changePw.error} />
            <Field label="Current password"><Input type="password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} autoComplete="current-password" /></Field>
            <Field label="New password">
              <Input type="password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} autoComplete="new-password" />
              <PasswordRules password={pw.new_password} />
            </Field>
            <Button loading={changePw.isPending} disabled={!pw.current_password || !passwordOk(pw.new_password)} onClick={() => changePw.mutate(undefined)}>Change password</Button>
          </div>
        </Card>
      </div>
    </>
  );
}
