"use client";
import * as React from "react";
import { Webhook, Plus, Trash2, Play, Loader2 } from "lucide-react";

import { TopBar } from "@/components/layout/topbar";
import { PageShell } from "@/components/layout/page-shell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/field";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { useToast } from "@/components/ui/toast";
import { useBot } from "@/lib/hooks/use-bot";

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
type Action = { id: string; name: string; description: string; method: Method; url: string; active: boolean; created_at: string };
type TestResult = { status_code?: number; body?: string; error?: string };

export default function ActionsPage() {
  const { toast } = useToast();
  const botQuery = useBot();
  const botId = botQuery.data?.id ?? null;
  const [showForm, setShowForm] = React.useState(false);
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [method, setMethod] = React.useState<Method>("POST");
  const [url, setUrl] = React.useState("");
  const [creating, setCreating] = React.useState(false);
  const [testResults, setTestResults] = React.useState<Record<string, TestResult>>({});
  const [testingId, setTestingId] = React.useState<string | null>(null);

  const {
    data: actions,
    error,
    refetch: load,
  } = useQuery({
    queryKey: ["actions", botId],
    queryFn: () => apiFetch<Action[]>(`/api/bff/actions?bot_id=${botId}`),
    enabled: Boolean(botId),
  });

  async function createAction(e: React.FormEvent) {
    e.preventDefault();
    if (!botId) {
      toast({ tone: "danger", title: "Still loading", description: "Hang on a moment and try again." });
      return;
    }
    setCreating(true);
    try {
      await apiFetch("/api/bff/actions", {
        method: "POST",
        json: { bot_id: botId, name, description, method, url },
      });
      setName("");
      setDescription("");
      setUrl("");
      setShowForm(false);
      toast({ tone: "success", title: "Action created" });
      await load();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    } finally {
      setCreating(false);
    }
  }

  async function removeAction(id: string) {
    if (!window.confirm("Delete this action? The assistant will no longer be able to call it.")) return;
    try {
      await apiFetch(`/api/bff/actions/${id}`, { method: "DELETE" });
      await load();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    }
  }

  async function testAction(id: string) {
    setTestingId(id);
    try {
      const result = await apiFetch<TestResult>(`/api/bff/actions/${id}/test`, { method: "POST" });
      setTestResults((prev) => ({ ...prev, [id]: result }));
    } catch (e) {
      setTestResults((prev) => ({ ...prev, [id]: { error: describeError(e).message } }));
    } finally {
      setTestingId(null);
    }
  }

  return (
    <>
      <TopBar
        title="Actions"
        description="HTTP endpoints your assistant can call to do things, not just answer questions."
      />
      <main>
        <PageShell>
          {(botQuery.error ?? error) ? (
            <Alert tone="danger" title={describeError(botQuery.error ?? error).title}>
              {describeError(botQuery.error ?? error).message}
            </Alert>
          ) : (
            <div className="space-y-4">
              <div className="flex justify-end">
                <Button onClick={() => setShowForm((v) => !v)} disabled={!botId} loading={!botId}>
                  <Plus className="h-4 w-4" /> New action
                </Button>
              </div>

              {showForm && (
                <Card>
                  <CardHeader>
                    <CardTitle>New HTTP action</CardTitle>
                    <CardDescription>
                      Requests are validated against private/internal networks before every send.
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <form onSubmit={createAction} className="space-y-3">
                      <Field label="Name">
                        {(fieldProps) => (
                          <Input {...fieldProps} value={name} onChange={(e) => setName(e.target.value)} placeholder="Create a support ticket" required />
                        )}
                      </Field>
                      <Field label="Description" hint="Tells the assistant when to use this.">
                        {(fieldProps) => (
                          <Input
                            {...fieldProps}
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            placeholder="Use this when a visitor wants to open a support ticket."
                          />
                        )}
                      </Field>
                      <div className="flex gap-3">
                        <Field label="Method">
                          {(fieldProps) => (
                            <select
                              {...fieldProps}
                              value={method}
                              onChange={(e) => setMethod(e.target.value as Method)}
                              className="h-10 rounded-lg border border-input bg-card px-3 text-sm"
                            >
                              {(["GET", "POST", "PUT", "PATCH", "DELETE"] as Method[]).map((m) => (
                                <option key={m} value={m}>
                                  {m}
                                </option>
                              ))}
                            </select>
                          )}
                        </Field>
                        <Field label="URL" className="flex-1">
                          {(fieldProps) => (
                            <Input {...fieldProps} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://api.yourcompany.com/tickets" required />
                          )}
                        </Field>
                      </div>
                      <Button type="submit" loading={creating}>
                        Create action
                      </Button>
                    </form>
                  </CardContent>
                </Card>
              )}

              {!actions ? (
                <div className="space-y-2">
                  <div className="h-20 skeleton" />
                </div>
              ) : actions.length === 0 ? (
                <EmptyState icon={Webhook} title="No actions yet" description="Give your assistant a way to do things, not just answer questions." />
              ) : (
                <div className="space-y-3">
                  {actions.map((a) => {
                    const result = testResults[a.id];
                    return (
                      <Card key={a.id}>
                        <CardContent className="p-4">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <p className="font-medium">{a.name}</p>
                                <Badge tone="neutral">{a.method}</Badge>
                              </div>
                              <p className="mt-0.5 truncate text-xs text-muted-foreground">{a.url}</p>
                              {a.description && <p className="mt-1 text-sm text-muted-foreground">{a.description}</p>}
                            </div>
                            <div className="flex shrink-0 gap-2">
                              <Button size="sm" variant="secondary" onClick={() => void testAction(a.id)} loading={testingId === a.id}>
                                <Play className="h-3.5 w-3.5" /> Test
                              </Button>
                              <Button size="sm" variant="ghost" onClick={() => void removeAction(a.id)} aria-label="Delete action">
                                <Trash2 className="h-3.5 w-3.5 text-destructive" />
                              </Button>
                            </div>
                          </div>
                          {result && (
                            <div className="mt-3 rounded-lg border border-border bg-subtle/60 p-3 text-xs">
                              {result.error ? (
                                <p className="text-destructive">{result.error}</p>
                              ) : (
                                <>
                                  <p className="font-medium">Status: {result.status_code}</p>
                                  {result.body && <pre className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap font-mono">{result.body}</pre>}
                                </>
                              )}
                            </div>
                          )}
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </PageShell>
      </main>
    </>
  );
}
