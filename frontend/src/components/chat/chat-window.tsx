"use client";
import * as React from "react";
import { Send, StopCircle, Sparkles, AlertTriangle, ThumbsUp, ThumbsDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { parseSseStream } from "@/lib/sse";
import { ERROR_COPY } from "@/lib/errors";

/**
 * Shared chat window used by the Bot Studio preview and later by the
 * public widget. Handles the SSE event sequence (meta, sources, delta,
 * done, error), Stop/abort, scroll sticking, and the "no evidence"
 * fallback message state. Visual-only: the parent passes the endpoint,
 * auth header strategy and session bootstrap.
 */

export type ChatSource = {
  index: number;
  document_id: string;
  title: string;
  page: number | null;
  excerpt?: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: "pending" | "streaming" | "completed" | "failed";
  citations?: ChatSource[];
  errorCode?: string;
  errorRetry?: number;
};

export type ChatConfig = {
  name?: string;
  greeting?: string;
  suggestions?: string[];
  tone?: string;
  language?: string;
  fallback_message?: string;
  branding?: { color?: string };
};

type Props = {
  config: ChatConfig;
  endpoint: string; // BFF url
  buildBody: (text: string) => Record<string, unknown>;
  idempotencyKey?: (text: string) => string | undefined;
  disabled?: boolean;
  disabledReason?: string;
  draftLabel?: string;
  onNewConversation?: () => Promise<void> | void;
  className?: string;
};

export function ChatWindow({
  config,
  endpoint,
  buildBody,
  idempotencyKey,
  disabled,
  disabledReason,
  draftLabel,
  onNewConversation,
  className,
}: Props) {
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [input, setInput] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const abortRef = React.useRef<AbortController | null>(null);
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const stickToBottom = React.useRef(true);

  React.useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  function onScroll(event: React.UIEvent<HTMLDivElement>) {
    const el = event.currentTarget;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    stickToBottom.current = near;
  }

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || sending) return;

    const userId = `u-${Date.now()}`;
    const assistantId = `a-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", content: trimmed, status: "completed" },
      { id: assistantId, role: "assistant", content: "", status: "streaming", citations: [] },
    ]);
    setInput("");
    setSending(true);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      if (onNewConversation) await onNewConversation();
      const headers: Record<string, string> = { "content-type": "application/json", accept: "text/event-stream" };
      const key = idempotencyKey?.(trimmed);
      if (key) headers["Idempotency-Key"] = key;
      const response = await fetch(endpoint, {
        method: "POST",
        headers,
        body: JSON.stringify(buildBody(trimmed)),
        signal: controller.signal,
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        const code = (body as { code?: string }).code || "internal_error";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  status: "failed",
                  errorCode: code,
                  content: ERROR_COPY[code]?.message ?? (body as { message?: string }).message ?? "Something went wrong.",
                  errorRetry: (body as { retry_after_seconds?: number }).retry_after_seconds,
                }
              : m
          )
        );
        return;
      }

      for await (const event of parseSseStream(response)) {
        if (event.kind === "heartbeat") continue;
        try {
          const data = JSON.parse(event.data) as Record<string, unknown>;
          if (event.event === "sources") {
            const sources = (data.sources as ChatSource[]) ?? [];
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, citations: sources } : m))
            );
          } else if (event.event === "delta") {
            const piece = (data.text as string) ?? "";
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + piece } : m))
            );
          } else if (event.event === "done") {
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, status: "completed" } : m))
            );
          } else if (event.event === "error") {
            const code = (data.code as string) ?? "internal_error";
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      status: "failed",
                      errorCode: code,
                      content:
                        ERROR_COPY[code]?.message ??
                        (data.message as string) ??
                        "The assistant couldn't finish this answer.",
                      errorRetry: data.retry_after_seconds as number | undefined,
                    }
                  : m
              )
            );
          }
        } catch {
          // ignore malformed event
        }
      }
    } catch (err) {
      if ((err as DOMException)?.name === "AbortError") {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId && m.status === "streaming"
              ? { ...m, status: "failed", errorCode: "aborted", content: m.content || "Stopped." }
              : m
          )
        );
      } else {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, status: "failed", errorCode: "network_error", content: ERROR_COPY.network_error.message }
              : m
          )
        );
      }
    } finally {
      setSending(false);
      abortRef.current = null;
    }
  }

  function stop() {
    abortRef.current?.abort();
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send(input);
    }
  }

  const brandColor = config.branding?.color;

  return (
    <div
      className={cn(
        "relative flex h-full min-h-[480px] flex-col overflow-hidden rounded-xl border border-border bg-card shadow-card",
        className
      )}
      style={brandColor ? ({ "--chat-brand": brandColor } as React.CSSProperties) : undefined}
    >
      <header className="flex items-center justify-between border-b border-border bg-subtle/60 px-4 py-3">
        <div className="flex items-center gap-2.5">
          <div
            aria-hidden
            className="inline-flex h-8 w-8 items-center justify-center rounded-full text-white"
            style={{
              background:
                brandColor ??
                "linear-gradient(135deg, hsl(var(--primary)), hsl(260 100% 60%))",
            }}
          >
            <Sparkles className="h-4 w-4" />
          </div>
          <div>
            <p className="text-sm font-semibold">{config.name || "Assistant"}</p>
            <p className="text-xs text-muted-foreground">
              Cites every source · Language: {(config.language || "en").toUpperCase()}
            </p>
          </div>
        </div>
        {draftLabel && <Badge tone="primary">{draftLabel}</Badge>}
      </header>

      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="flex-1 space-y-4 overflow-y-auto px-4 py-4 text-sm"
      >
        {messages.length === 0 ? (
          <GreetingPanel config={config} onPick={(q) => void send(q)} />
        ) : (
          messages.map((m) => <MessageBubble key={m.id} message={m} />)
        )}
      </div>

      <footer className="border-t border-border bg-card p-3">
        {disabled ? (
          <div className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
            {disabledReason || "Chat isn't available right now."}
          </div>
        ) : (
          <div className="flex items-end gap-2">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Ask anything about your sources…"
              rows={1}
              className="min-h-[44px] resize-none"
              aria-label="Message"
              disabled={sending}
            />
            {sending ? (
              <Button type="button" variant="secondary" size="icon" onClick={stop} aria-label="Stop generating">
                <StopCircle className="h-4 w-4" />
              </Button>
            ) : (
              <Button
                type="button"
                size="icon"
                onClick={() => void send(input)}
                disabled={!input.trim()}
                aria-label="Send message"
              >
                <Send className="h-4 w-4" />
              </Button>
            )}
          </div>
        )}
      </footer>
    </div>
  );
}

function GreetingPanel({ config, onPick }: { config: ChatConfig; onPick: (q: string) => void }) {
  const greeting =
    config.greeting ||
    `Hi! I'm ${config.name || "your assistant"}. Ask me anything about the sources you've added.`;
  const suggestions = (config.suggestions ?? []).slice(0, 4);
  return (
    <div className="animate-fade-in space-y-3 py-6">
      <div className="mx-auto max-w-sm rounded-xl border border-border bg-subtle/60 p-4 text-center text-sm text-foreground">
        {greeting}
      </div>
      {suggestions.length > 0 && (
        <div className="flex flex-wrap justify-center gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => onPick(s)}
              className="rounded-full border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-primary/40 hover:bg-accent"
            >
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div className={cn("flex max-w-[88%] flex-col gap-1.5", isUser && "items-end")}>
        <div
          className={cn(
            "rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
            isUser
              ? "rounded-br-sm bg-primary text-primary-foreground shadow-sm"
              : "rounded-bl-sm border border-border bg-subtle text-foreground"
          )}
        >
          {message.status === "failed" ? (
            <p className="flex items-start gap-1.5">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
              <span>{message.content}</span>
            </p>
          ) : message.content === "" && message.status === "streaming" ? (
            <TypingDots />
          ) : (
            <p className="whitespace-pre-wrap">{message.content}</p>
          )}
        </div>
        {!isUser && message.citations && message.citations.length > 0 && (
          <ol className="space-y-1">
            {message.citations.map((c) => (
              <li
                key={c.index}
                className="rounded-md border border-border bg-card px-2.5 py-1.5 text-[11px] leading-snug text-muted-foreground"
              >
                <span className="font-semibold text-primary">[{c.index}]</span>{" "}
                <span className="text-foreground">{c.title}</span>
                {c.page ? <span> · page {c.page}</span> : null}
                {c.excerpt ? (
                  <p className="mt-1 line-clamp-2 text-muted-foreground">{c.excerpt}</p>
                ) : null}
              </li>
            ))}
          </ol>
        )}
        {!isUser && message.status === "completed" && (
          <div className="flex items-center gap-1 pt-0.5">
            <FeedbackButton label="Helpful" icon={ThumbsUp} />
            <FeedbackButton label="Not helpful" icon={ThumbsDown} />
          </div>
        )}
      </div>
    </div>
  );
}

function FeedbackButton({ label, icon: Icon }: { label: string; icon: React.ElementType }) {
  const [picked, setPicked] = React.useState(false);
  return (
    <button
      type="button"
      aria-label={label}
      onClick={() => setPicked(true)}
      className={cn(
        "inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
        picked && "text-primary"
      )}
    >
      <Icon className="h-3.5 w-3.5" />
    </button>
  );
}

function TypingDots() {
  return (
    <span className="flex items-center gap-1" aria-label="Assistant is typing">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground"
          style={{ animationDelay: `${i * 150}ms` }}
        />
      ))}
    </span>
  );
}
