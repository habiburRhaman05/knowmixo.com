"use client";
import * as React from "react";
import { Slack, Check, X, Loader2 } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { useToast } from "@/components/ui/toast";
import { fromNow } from "@/lib/utils";

type SlackStatus = { connected: boolean; team_name?: string; incoming_webhook_channel?: string; created_at?: string };

export default function IntegrationsSettingsPage() {
  const { toast } = useToast();
  const [status, setStatus] = React.useState<SlackStatus | null>(null);
  const [error, setError] = React.useState<unknown>(null);
  const [connecting, setConnecting] = React.useState(false);
  const [disconnecting, setDisconnecting] = React.useState(false);

  const load = React.useCallback(async () => {
    try {
      setStatus(await apiFetch<SlackStatus>("/api/bff/integrations/slack/status"));
    } catch (e) {
      setError(e);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  async function connect() {
    setConnecting(true);
    try {
      const { install_url } = await apiFetch<{ install_url: string }>("/api/bff/integrations/slack/install");
      window.location.href = install_url;
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
      setConnecting(false);
    }
  }

  async function disconnect() {
    if (!window.confirm("Disconnect Slack? You'll stop receiving alerts there.")) return;
    setDisconnecting(true);
    try {
      await apiFetch("/api/bff/integrations/slack", { method: "DELETE" });
      toast({ tone: "success", title: "Slack disconnected" });
      await load();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    } finally {
      setDisconnecting(false);
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
    <div className="max-w-2xl space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                <Slack className="h-5 w-5" />
              </span>
              <div>
                <CardTitle className="flex items-center gap-2">
                  Slack
                  {status?.connected && <Badge tone="success">Connected</Badge>}
                </CardTitle>
                <CardDescription>
                  Get alerts (quota limits, unanswered-question spikes, ingestion failures) posted to a Slack channel.
                </CardDescription>
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {status === null ? (
            <div className="h-9 w-40 skeleton" />
          ) : status.connected ? (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Connected to <strong className="text-foreground">{status.team_name}</strong>
                {status.incoming_webhook_channel ? (
                  <>
                    {" "}
                    posting to <strong className="text-foreground">#{status.incoming_webhook_channel}</strong>
                  </>
                ) : null}
                {status.created_at ? ` · connected ${fromNow(status.created_at)}` : ""}
              </p>
              <Button variant="secondary" onClick={disconnect} loading={disconnecting}>
                <X className="h-4 w-4" /> Disconnect
              </Button>
            </div>
          ) : (
            <Button onClick={connect} loading={connecting}>
              <Slack className="h-4 w-4" /> Connect Slack
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
