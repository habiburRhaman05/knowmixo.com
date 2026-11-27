"use client";
import * as React from "react";
import { Siren, Plus, Trash2, ShieldCheck, Send, Loader2, AlertTriangle } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/field";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { useToast } from "@/components/ui/toast";

type Severity = "critical" | "high" | "medium" | "low";
type Channel = "whatsapp" | "sms" | "email" | "slack" | "telegram" | "push";

type Rule = { id: string; name: string; match: { keywords?: string[] }; severity: Severity; active: boolean };
type Contact = { id: string; channel: Channel; address: string; priority: number; verified_at: string | null; active: boolean };

const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"];
const CHANNELS: Channel[] = ["email", "slack", "telegram", "whatsapp"];
const SEVERITY_TONE: Record<Severity, "danger" | "warning" | "primary" | "neutral"> = {
  critical: "danger",
  high: "warning",
  medium: "primary",
  low: "neutral",
};

export default function EscalationSettingsPage() {
  return (
    <div className="max-w-3xl space-y-8">
      <Alert tone="info" title="Life-safety replies are always on" icon={Siren}>
        Rules and contacts below control who gets notified for angry customers, VIPs, or owner-defined
        triggers. The 911/988 safety response for genuine emergencies cannot be disabled here.
      </Alert>
      <ContactsCard />
      <RulesCard />
    </div>
  );
}

function ContactsCard() {
  const { toast } = useToast();
  const [contacts, setContacts] = React.useState<Contact[] | null>(null);
  const [error, setError] = React.useState<unknown>(null);
  const [channel, setChannel] = React.useState<Channel>("email");
  const [address, setAddress] = React.useState("");
  const [creating, setCreating] = React.useState(false);
  const [verifyingId, setVerifyingId] = React.useState<string | null>(null);
  const [code, setCode] = React.useState("");
  const [testingId, setTestingId] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    try {
      setContacts(await apiFetch<Contact[]>("/api/bff/escalations/contacts"));
    } catch (e) {
      setError(e);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  async function addContact(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      const next = (contacts?.length ?? 0) + 1;
      await apiFetch("/api/bff/escalations/contacts", {
        method: "POST",
        json: { channel, address, priority: next },
      });
      setAddress("");
      toast({ tone: "success", title: "Contact added", description: "Send a verification code before it can receive alerts." });
      await load();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    } finally {
      setCreating(false);
    }
  }

  async function sendCode(id: string) {
    try {
      await apiFetch(`/api/bff/escalations/contacts/${id}/send-code`, { method: "POST" });
      setVerifyingId(id);
      toast({ tone: "success", title: "Code sent" });
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    }
  }

  async function confirmCode(id: string) {
    try {
      await apiFetch(`/api/bff/escalations/contacts/${id}/verify`, { method: "POST", json: { code } });
      toast({ tone: "success", title: "Contact verified" });
      setVerifyingId(null);
      setCode("");
      await load();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    }
  }

  async function removeContact(id: string) {
    if (!window.confirm("Remove this contact?")) return;
    try {
      await apiFetch(`/api/bff/escalations/contacts/${id}`, { method: "DELETE" });
      await load();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    }
  }

  async function sendTest(id: string) {
    setTestingId(id);
    try {
      const result = await apiFetch<{ state: string }>("/api/bff/escalations/test", {
        method: "POST",
        json: { contact_id: id, severity: "low" },
      });
      toast({
        tone: result.state === "sent" ? "success" : "danger",
        title: result.state === "sent" ? "Test alert sent" : "Test alert failed to send",
      });
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    } finally {
      setTestingId(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Escalation contacts</CardTitle>
        <CardDescription>Who gets notified when a conversation needs a human.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={addContact} className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <Field label="Channel">
            {(fieldProps) => (
              <select
                {...fieldProps}
                value={channel}
                onChange={(e) => setChannel(e.target.value as Channel)}
                className="h-10 rounded-lg border border-input bg-card px-3 text-sm"
              >
                {CHANNELS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Address" className="flex-1" hint="Email, Slack webhook URL, bot_token:chat_id, or phone number.">
            {(fieldProps) => (
              <Input {...fieldProps} value={address} onChange={(e) => setAddress(e.target.value)} placeholder="ops@company.com" required />
            )}
          </Field>
          <Button type="submit" loading={creating} disabled={!address}>
            <Plus className="h-4 w-4" /> Add
          </Button>
        </form>

        {error != null ? (
          <Alert tone="danger" title={describeError(error).title}>
            {describeError(error).message}
          </Alert>
        ) : contacts === null ? (
          <div className="h-16 skeleton" />
        ) : contacts.length === 0 ? (
          <EmptyState icon={Siren} title="No contacts yet" description="Add one above so escalations have somewhere to go." />
        ) : (
          <ul className="space-y-2">
            {contacts.map((c) => (
              <li key={c.id} className="rounded-lg border border-border p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{c.address}</p>
                    <p className="text-xs text-muted-foreground">
                      {c.channel} · priority {c.priority}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {c.verified_at ? (
                      <Badge tone="success">
                        <ShieldCheck className="h-3 w-3" /> Verified
                      </Badge>
                    ) : (
                      <Badge tone="warning">Unverified</Badge>
                    )}
                    {c.verified_at && (
                      <Button size="sm" variant="secondary" onClick={() => void sendTest(c.id)} loading={testingId === c.id}>
                        <Send className="h-3.5 w-3.5" /> Test
                      </Button>
                    )}
                    {!c.verified_at && verifyingId !== c.id && (
                      <Button size="sm" variant="secondary" onClick={() => void sendCode(c.id)}>
                        Send code
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" onClick={() => void removeContact(c.id)} aria-label="Remove contact">
                      <Trash2 className="h-3.5 w-3.5 text-destructive" />
                    </Button>
                  </div>
                </div>
                {verifyingId === c.id && (
                  <div className="mt-2 flex items-center gap-2">
                    <Input
                      value={code}
                      onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                      placeholder="6-digit code"
                      className="h-8 w-32 text-sm"
                    />
                    <Button size="sm" onClick={() => void confirmCode(c.id)} disabled={code.length !== 6}>
                      Confirm
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function RulesCard() {
  const { toast } = useToast();
  const [rules, setRules] = React.useState<Rule[] | null>(null);
  const [error, setError] = React.useState<unknown>(null);
  const [name, setName] = React.useState("");
  const [keywords, setKeywords] = React.useState("");
  const [severity, setSeverity] = React.useState<Severity>("high");
  const [creating, setCreating] = React.useState(false);

  const load = React.useCallback(async () => {
    try {
      setRules(await apiFetch<Rule[]>("/api/bff/escalations/rules"));
    } catch (e) {
      setError(e);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  async function addRule(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      const kw = keywords.split(",").map((k) => k.trim()).filter(Boolean);
      await apiFetch("/api/bff/escalations/rules", {
        method: "POST",
        json: { name, match: { keywords: kw }, severity },
      });
      setName("");
      setKeywords("");
      await load();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    } finally {
      setCreating(false);
    }
  }

  async function toggleActive(rule: Rule) {
    try {
      await apiFetch(`/api/bff/escalations/rules/${rule.id}`, { method: "PATCH", json: { active: !rule.active } });
      await load();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    }
  }

  async function removeRule(id: string) {
    if (!window.confirm("Delete this rule?")) return;
    try {
      await apiFetch(`/api/bff/escalations/rules/${id}`, { method: "DELETE" });
      await load();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Escalation rules</CardTitle>
        <CardDescription>Trigger an alert when a conversation mentions certain keywords.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={addRule} className="space-y-3">
          <div className="flex flex-col gap-3 sm:flex-row">
            <Field label="Rule name" className="flex-1">
              {(fieldProps) => (
                <Input {...fieldProps} value={name} onChange={(e) => setName(e.target.value)} placeholder="Angry customer" required />
              )}
            </Field>
            <Field label="Severity">
              {(fieldProps) => (
                <select
                  {...fieldProps}
                  value={severity}
                  onChange={(e) => setSeverity(e.target.value as Severity)}
                  className="h-10 rounded-lg border border-input bg-card px-3 text-sm"
                >
                  {SEVERITIES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </div>
          <Field label="Keywords" hint="Comma-separated. Fires if the visitor's message contains any of these.">
            {(fieldProps) => (
              <Input {...fieldProps} value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="refund, lawyer, cancel my account" />
            )}
          </Field>
          <Button type="submit" loading={creating} disabled={!name}>
            <Plus className="h-4 w-4" /> Add rule
          </Button>
        </form>

        {error != null ? (
          <Alert tone="danger" title={describeError(error).title}>
            {describeError(error).message}
          </Alert>
        ) : rules === null ? (
          <div className="h-16 skeleton" />
        ) : rules.length === 0 ? (
          <EmptyState icon={AlertTriangle} title="No custom rules" description="Life-safety detection still runs automatically without any rules here." />
        ) : (
          <ul className="space-y-2">
            {rules.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-2 rounded-lg border border-border p-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium">{r.name}</p>
                  <p className="text-xs text-muted-foreground">{(r.match.keywords ?? []).join(", ") || "no keywords"}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={SEVERITY_TONE[r.severity]}>{r.severity}</Badge>
                  <Button size="sm" variant="ghost" onClick={() => void toggleActive(r)}>
                    {r.active ? "Disable" : "Enable"}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void removeRule(r.id)} aria-label="Delete rule">
                    <Trash2 className="h-3.5 w-3.5 text-destructive" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
