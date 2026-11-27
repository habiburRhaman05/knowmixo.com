"use client";
import * as React from "react";
import { Users, Mail, Trash2, Loader2, UserPlus, Clock, X } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/field";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/ui/empty-state";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { useToast } from "@/components/ui/toast";
import { fromNow } from "@/lib/utils";

type Role = "owner" | "admin" | "agent" | "viewer";
type Member = { user_id: string; email: string; name: string | null; role: Role; created_at: string };
type Invite = { id: string; email: string; role: Role; expires_at: string; accepted_at: string | null; revoked_at: string | null; created_at: string };

const ROLE_LABEL: Record<Role, string> = { owner: "Owner", admin: "Admin", agent: "Agent", viewer: "Viewer" };
const INVITABLE_ROLES: Array<{ value: "admin" | "agent" | "viewer"; label: string }> = [
  { value: "admin", label: "Admin — manage everything except billing and ownership" },
  { value: "agent", label: "Agent — handle conversations and canned replies" },
  { value: "viewer", label: "Viewer — read-only access" },
];

export default function TeamSettingsPage() {
  const { toast } = useToast();
  const [members, setMembers] = React.useState<Member[] | null>(null);
  const [invites, setInvites] = React.useState<Invite[] | null>(null);
  const [error, setError] = React.useState<unknown>(null);
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState<"admin" | "agent" | "viewer">("agent");
  const [inviting, setInviting] = React.useState(false);
  const [inviteError, setInviteError] = React.useState<unknown>(null);

  const load = React.useCallback(async () => {
    try {
      const [m, i] = await Promise.all([
        apiFetch<Member[]>("/api/bff/team/members"),
        apiFetch<Invite[]>("/api/bff/team/invites"),
      ]);
      setMembers(m);
      setInvites(i.filter((inv) => !inv.accepted_at && !inv.revoked_at));
    } catch (e) {
      setError(e);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  async function sendInvite(e: React.FormEvent) {
    e.preventDefault();
    setInviting(true);
    setInviteError(null);
    try {
      await apiFetch("/api/bff/team/invites", { method: "POST", json: { email, role } });
      toast({ tone: "success", title: "Invite sent", description: `We emailed ${email}.` });
      setEmail("");
      await load();
    } catch (e) {
      setInviteError(e);
    } finally {
      setInviting(false);
    }
  }

  async function revokeInvite(id: string) {
    try {
      await apiFetch(`/api/bff/team/invites/${id}`, { method: "DELETE" });
      toast({ tone: "success", title: "Invite revoked" });
      await load();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    }
  }

  async function updateRole(userId: string, newRole: "admin" | "agent" | "viewer") {
    try {
      await apiFetch(`/api/bff/team/members/${userId}`, { method: "PATCH", json: { role: newRole } });
      toast({ tone: "success", title: "Role updated" });
      await load();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    }
  }

  async function removeMember(userId: string, email: string) {
    if (!window.confirm(`Remove ${email} from your team?`)) return;
    try {
      await apiFetch(`/api/bff/team/members/${userId}`, { method: "DELETE" });
      toast({ tone: "success", title: "Member removed" });
      await load();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    }
  }

  if (error) {
    const info = describeError(error);
    return (
      <Alert tone="danger" title={info.title}>
        {info.message}
      </Alert>
    );
  }

  return (
    <div className="max-w-3xl space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <UserPlus className="h-4 w-4" /> Invite a teammate
          </CardTitle>
          <CardDescription>They&apos;ll get an email with a link to join your workspace.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={sendInvite} className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <Field label="Email" className="flex-1">
              {(fieldProps) => (
                <Input
                  {...fieldProps}
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="teammate@company.com"
                  required
                />
              )}
            </Field>
            <Field label="Role">
              {(fieldProps) => (
                <select
                  {...fieldProps}
                  value={role}
                  onChange={(e) => setRole(e.target.value as typeof role)}
                  className="h-10 rounded-lg border border-input bg-card px-3 text-sm"
                >
                  {INVITABLE_ROLES.map((r) => (
                    <option key={r.value} value={r.value}>
                      {ROLE_LABEL[r.value]}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Button type="submit" loading={inviting} disabled={!email}>
              <Mail className="h-4 w-4" /> Send invite
            </Button>
          </form>
          {inviteError != null && (
            <Alert tone="danger" title={describeError(inviteError).title} className="mt-3">
              {describeError(inviteError).message}
            </Alert>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users className="h-4 w-4" /> Members
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {members === null ? (
            <div className="space-y-2 p-4">
              <div className="h-10 skeleton" />
              <div className="h-10 skeleton" />
            </div>
          ) : (
            <ul>
              {members.map((m) => (
                <li key={m.user_id} className="flex items-center justify-between gap-3 border-b border-border px-4 py-3 last:border-b-0">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{m.name || m.email}</p>
                    <p className="truncate text-xs text-muted-foreground">{m.email}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone={m.role === "owner" ? "primary" : "neutral"}>{ROLE_LABEL[m.role]}</Badge>
                    {m.role !== "owner" && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="sm">
                            Manage
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          {INVITABLE_ROLES.map((r) => (
                            <DropdownMenuItem key={r.value} onSelect={() => void updateRole(m.user_id, r.value)}>
                              Make {ROLE_LABEL[r.value]}
                            </DropdownMenuItem>
                          ))}
                          <DropdownMenuItem
                            onSelect={() => void removeMember(m.user_id, m.email)}
                            className="text-destructive focus:text-destructive"
                          >
                            <Trash2 className="h-4 w-4" /> Remove from team
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {invites && invites.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock className="h-4 w-4" /> Pending invites
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <ul>
              {invites.map((inv) => (
                <li key={inv.id} className="flex items-center justify-between gap-3 border-b border-border px-4 py-3 last:border-b-0">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{inv.email}</p>
                    <p className="text-xs text-muted-foreground">
                      {ROLE_LABEL[inv.role]} · expires {fromNow(inv.expires_at)}
                    </p>
                  </div>
                  <Button variant="ghost" size="icon" aria-label="Revoke invite" onClick={() => void revokeInvite(inv.id)}>
                    <X className="h-4 w-4" />
                  </Button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
