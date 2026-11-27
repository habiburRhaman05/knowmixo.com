"use client";
import * as React from "react";
import { KeyRound, Copy, Check, Trash2, Plus, AlertTriangle } from "lucide-react";

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
import { fromNow } from "@/lib/utils";

const ALL_SCOPES = ["conversations:read", "conversations:write", "leads:read", "sources:write", "events:webhook"] as const;
const SCOPE_LABEL: Record<string, string> = {
  "conversations:read": "Read conversations",
  "conversations:write": "Reply to conversations",
  "leads:read": "Read leads",
  "sources:write": "Create knowledge sources",
  "events:webhook": "Register webhooks",
};

type ApiKey = {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
};

export default function ApiKeysSettingsPage() {
  const { toast } = useToast();
  const [keys, setKeys] = React.useState<ApiKey[] | null>(null);
  const [error, setError] = React.useState<unknown>(null);
  const [name, setName] = React.useState("");
  const [scopes, setScopes] = React.useState<Set<string>>(new Set());
  const [creating, setCreating] = React.useState(false);
  const [createError, setCreateError] = React.useState<unknown>(null);
  const [newKey, setNewKey] = React.useState<string | null>(null);
  const [copied, setCopied] = React.useState(false);

  const load = React.useCallback(async () => {
    try {
      setKeys(await apiFetch<ApiKey[]>("/api/bff/api-keys"));
    } catch (e) {
      setError(e);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  function toggleScope(scope: string) {
    setScopes((prev) => {
      const next = new Set(prev);
      if (next.has(scope)) next.delete(scope);
      else next.add(scope);
      return next;
    });
  }

  async function createKey(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      const result = await apiFetch<{ api_key: string }>("/api/bff/api-keys", {
        method: "POST",
        json: { name: name || "API key", scopes: Array.from(scopes) },
      });
      setNewKey(result.api_key);
      setName("");
      setScopes(new Set());
      await load();
    } catch (e) {
      setCreateError(e);
    } finally {
      setCreating(false);
    }
  }

  async function revoke(id: string) {
    if (!window.confirm("Revoke this API key? Any integration using it will stop working immediately.")) return;
    try {
      await apiFetch(`/api/bff/api-keys/${id}`, { method: "DELETE" });
      toast({ tone: "success", title: "Key revoked" });
      await load();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    }
  }

  function copyKey() {
    if (!newKey) return;
    void navigator.clipboard.writeText(newKey);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
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
      {newKey && (
        <Alert tone="warning" title="Copy your API key now" icon={AlertTriangle}>
          <div className="mt-2 space-y-2">
            <p>This is the only time it will be shown.</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 overflow-x-auto rounded-md border border-border bg-card px-3 py-2 text-xs">
                {newKey}
              </code>
              <Button type="button" variant="secondary" size="icon" onClick={copyKey} aria-label="Copy API key">
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              </Button>
            </div>
            <Button variant="ghost" size="sm" onClick={() => setNewKey(null)}>
              Done
            </Button>
          </div>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Plus className="h-4 w-4" /> Create an API key
          </CardTitle>
          <CardDescription>
            Use the public API to read conversations and leads, reply programmatically, add sources, or
            register webhooks.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form onSubmit={createKey} className="space-y-4">
            <Field label="Name" hint="So you remember what this key is for.">
              {(fieldProps) => (
                <Input {...fieldProps} value={name} onChange={(e) => setName(e.target.value)} placeholder="Zapier integration" />
              )}
            </Field>
            <div>
              <p className="mb-2 text-sm font-medium">Scopes</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {ALL_SCOPES.map((scope) => (
                  <label key={scope} className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm">
                    <input
                      type="checkbox"
                      checked={scopes.has(scope)}
                      onChange={() => toggleScope(scope)}
                      className="h-4 w-4 rounded border-border"
                    />
                    {SCOPE_LABEL[scope]}
                  </label>
                ))}
              </div>
            </div>
            {createError != null && (
              <Alert tone="danger" title={describeError(createError).title}>
                {describeError(createError).message}
              </Alert>
            )}
            <Button type="submit" loading={creating} disabled={scopes.size === 0}>
              <KeyRound className="h-4 w-4" /> Create key
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Your API keys</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {keys === null ? (
            <div className="space-y-2 p-4">
              <div className="h-10 skeleton" />
            </div>
          ) : keys.length === 0 ? (
            <EmptyState icon={KeyRound} title="No API keys yet" description="Create one above to start using the public API." />
          ) : (
            <ul>
              {keys.map((k) => (
                <li key={k.id} className="flex items-center justify-between gap-3 border-b border-border px-4 py-3 last:border-b-0">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{k.name}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      km_live_{k.prefix}… · {k.scopes.length} scope{k.scopes.length === 1 ? "" : "s"} · created{" "}
                      {fromNow(k.created_at)}
                      {k.last_used_at ? ` · last used ${fromNow(k.last_used_at)}` : " · never used"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {k.revoked_at ? (
                      <Badge tone="neutral">Revoked</Badge>
                    ) : (
                      <Button variant="ghost" size="icon" aria-label="Revoke key" onClick={() => void revoke(k.id)}>
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
