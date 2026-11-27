"use client";
import * as React from "react";
import { Inbox as InboxIcon, UserCheck, CheckCircle2, Bot, Send, MessageSquareQuote, Loader2 } from "lucide-react";

import { TopBar } from "@/components/layout/topbar";
import { PageShell } from "@/components/layout/page-shell";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { useToast } from "@/components/ui/toast";
import { fromNow, cn } from "@/lib/utils";
import { type ConversationDetail } from "@/lib/types";

type QueueItem = {
  id: string;
  status: "queued" | "assigned";
  assigned_to: string | null;
  handed_off_at: string;
  updated_at: string;
  bot_name: string | null;
};

type CannedReply = { id: string; title: string; body: string; shortcut: string | null };

export default function InboxPage() {
  const { toast } = useToast();
  const [queue, setQueue] = React.useState<QueueItem[] | null>(null);
  const [queueError, setQueueError] = React.useState<unknown>(null);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [detail, setDetail] = React.useState<ConversationDetail | null>(null);
  const [canned, setCanned] = React.useState<CannedReply[]>([]);
  const [reply, setReply] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const [busyAction, setBusyAction] = React.useState(false);

  const loadQueue = React.useCallback(async () => {
    try {
      const data = await apiFetch<QueueItem[]>("/api/bff/handoff/queue");
      setQueue(data);
    } catch (e) {
      setQueueError(e);
    }
  }, []);

  const loadDetail = React.useCallback(async (id: string) => {
    try {
      const data = await apiFetch<ConversationDetail>(`/api/bff/conversations/${id}`);
      setDetail(data);
    } catch {
      /* keep previous detail on a transient failure */
    }
  }, []);

  React.useEffect(() => {
    void loadQueue();
    apiFetch<CannedReply[]>("/api/bff/handoff/canned-replies").then(setCanned).catch(() => {});
  }, [loadQueue]);

  React.useEffect(() => {
    if (selectedId) void loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  // ADR 005: live inbox via SSE. Any event on the stream is cheap to react
  // to by just refetching -- the backend already seeds from event_outbox
  // on connect, so a dropped connection never silently misses a turn.
  React.useEffect(() => {
    const es = new EventSource("/api/bff/inbox/stream");
    const onEvent = (ev: MessageEvent) => {
      void loadQueue();
      try {
        const data = JSON.parse(ev.data) as { conversation_id?: string };
        if (data.conversation_id && data.conversation_id === selectedId) {
          void loadDetail(data.conversation_id);
        }
      } catch {
        /* ignore malformed event payloads */
      }
    };
    const events = ["conversation.message", "conversation.agent_message", "conversation.handoff_requested", "conversation.assigned", "conversation.resolved", "conversation.returned_to_bot"];
    for (const name of events) es.addEventListener(name, onEvent);
    es.onerror = () => {
      /* EventSource auto-reconnects; nothing to do here */
    };
    return () => es.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  async function takeOver(id: string) {
    setBusyAction(true);
    try {
      await apiFetch("/api/bff/handoff/take", { method: "POST", json: { conversation_id: id } });
      setSelectedId(id);
      await loadQueue();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    } finally {
      setBusyAction(false);
    }
  }

  async function resolve(id: string) {
    setBusyAction(true);
    try {
      await apiFetch(`/api/bff/handoff/${id}/resolve`, { method: "POST" });
      toast({ tone: "success", title: "Marked resolved" });
      if (selectedId === id) setSelectedId(null);
      await loadQueue();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    } finally {
      setBusyAction(false);
    }
  }

  async function returnToBot(id: string) {
    setBusyAction(true);
    try {
      await apiFetch(`/api/bff/handoff/${id}/return-to-bot`, { method: "POST" });
      toast({ tone: "success", title: "Returned to the bot" });
      if (selectedId === id) setSelectedId(null);
      await loadQueue();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    } finally {
      setBusyAction(false);
    }
  }

  async function sendReply() {
    if (!selectedId || !reply.trim()) return;
    setSending(true);
    try {
      await apiFetch(`/api/bff/handoff/${selectedId}/reply`, { method: "POST", json: { text: reply.trim() } });
      setReply("");
      await loadDetail(selectedId);
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    } finally {
      setSending(false);
    }
  }

  const selected = queue?.find((q) => q.id === selectedId) ?? null;

  return (
    <>
      <TopBar title="Inbox" description="Conversations waiting for a human." />
      <main>
        <PageShell className="max-w-none">
          <div className="grid gap-4 lg:grid-cols-[320px_1fr]" style={{ height: "calc(100vh - 160px)" }}>
            <Card className="flex flex-col overflow-hidden p-0">
              <div className="border-b border-border px-4 py-3">
                <p className="text-sm font-medium">Waiting ({queue?.length ?? 0})</p>
              </div>
              <div className="flex-1 overflow-y-auto">
                {queueError ? (
                  <div className="p-4">
                    <Alert tone="danger" title={describeError(queueError).title}>
                      {describeError(queueError).message}
                    </Alert>
                  </div>
                ) : queue === null ? (
                  <div className="space-y-2 p-4">
                    <div className="h-14 skeleton" />
                    <div className="h-14 skeleton" />
                  </div>
                ) : queue.length === 0 ? (
                  <EmptyState icon={InboxIcon} title="All caught up" description="No conversations are waiting for a human right now." />
                ) : (
                  <ul>
                    {queue.map((item) => (
                      <li key={item.id}>
                        <button
                          type="button"
                          onClick={() => setSelectedId(item.id)}
                          className={cn(
                            "w-full border-b border-border px-4 py-3 text-left transition-colors hover:bg-subtle/60",
                            selectedId === item.id && "bg-accent"
                          )}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="truncate text-sm font-medium">Conversation {item.id.slice(0, 8)}…</span>
                            <Badge tone={item.status === "assigned" ? "primary" : "warning"}>
                              {item.status === "assigned" ? "Assigned" : "Queued"}
                            </Badge>
                          </div>
                          <p className="mt-0.5 text-xs text-muted-foreground">
                            {item.bot_name ?? "Assistant"} · waiting {fromNow(item.handed_off_at)}
                          </p>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </Card>

            <Card className="flex flex-col overflow-hidden p-0">
              {!selected || !detail ? (
                <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
                  Select a conversation to view and reply.
                </div>
              ) : (
                <>
                  <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
                    <p className="text-sm font-medium">Conversation {selected.id.slice(0, 8)}…</p>
                    <div className="flex items-center gap-2">
                      {selected.status === "queued" && (
                        <Button size="sm" onClick={() => void takeOver(selected.id)} loading={busyAction}>
                          <UserCheck className="h-4 w-4" /> Take over
                        </Button>
                      )}
                      <Button size="sm" variant="secondary" onClick={() => void returnToBot(selected.id)} loading={busyAction}>
                        <Bot className="h-4 w-4" /> Return to bot
                      </Button>
                      <Button size="sm" variant="secondary" onClick={() => void resolve(selected.id)} loading={busyAction}>
                        <CheckCircle2 className="h-4 w-4" /> Resolve
                      </Button>
                    </div>
                  </div>
                  <div className="flex-1 space-y-3 overflow-y-auto p-4">
                    {detail.messages.map((m) => (
                      <div key={m.id} className={cn("flex", m.role === "user" ? "justify-start" : "justify-end")}>
                        <div
                          className={cn(
                            "max-w-[75%] rounded-xl px-3 py-2 text-sm",
                            m.role === "user" ? "bg-subtle text-foreground" : "bg-primary text-primary-foreground"
                          )}
                        >
                          <p className="whitespace-pre-wrap">{m.content}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="border-t border-border p-3">
                    <div className="flex items-end gap-2">
                      <textarea
                        value={reply}
                        onChange={(e) => setReply(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault();
                            void sendReply();
                          }
                        }}
                        rows={2}
                        placeholder="Reply as a human…"
                        className="min-h-[40px] flex-1 resize-none rounded-lg border border-input bg-card px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      />
                      {canned.length > 0 && (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="secondary" size="icon" aria-label="Canned replies">
                              <MessageSquareQuote className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            {canned.map((c) => (
                              <DropdownMenuItem key={c.id} onSelect={() => setReply(c.body)}>
                                {c.title}
                              </DropdownMenuItem>
                            ))}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                      <Button size="icon" onClick={() => void sendReply()} disabled={!reply.trim() || sending} aria-label="Send reply">
                        {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                      </Button>
                    </div>
                  </div>
                </>
              )}
            </Card>
          </div>
        </PageShell>
      </main>
    </>
  );
}
