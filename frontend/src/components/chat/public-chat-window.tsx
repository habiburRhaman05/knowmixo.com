"use client";
import * as React from "react";
import {
  Send,
  StopCircle,
  Sparkles,
  AlertTriangle,
  ThumbsUp,
  ThumbsDown,
  X,
  Mail,
  Loader2,
} from "lucide-react";

import { parseSseStream } from "@/lib/sse";
import { ERROR_COPY } from "@/lib/errors";
import { cn } from "@/lib/utils";

/**
 * Public-facing chat window used by both the hosted /chat/[publicId] page
 * and the embedded iframe widget. Owns the visitor session, conversation
 * creation, SSE streaming, lead capture and message feedback — nothing
 * about the owner's draft here.
 */

export type PublicBotConfig = {
  name?: string;
  branding?: { color?: string };
  greeting?: string;
  suggestions?: string[];
  tone?: string;
  language?: string;
  lead_capture_enabled?: boolean;
};

type PublicMessage = {
  id: string;
  backendId?: string;
  role: "user" | "assistant";
  content: string;
  status: "streaming" | "completed" | "failed";
  citations?: Array<{
    index: number;
    title: string;
    page: number | null;
    document_id: string;
    excerpt?: string;
  }>;
  errorCode?: string;
  feedback?: 1 | -1 | null;
};

type Props = {
  publicId: string;
  onClose?: () => void;
  layout?: "hosted" | "embed";
};

export function PublicChatWindow({ publicId, onClose, layout = "hosted" }: Props) {
  const [config, setConfig] = React.useState<PublicBotConfig | null>(null);
  const [visitorToken, setVisitorToken] = React.useState<string | null>(null);
  const [conversationId, setConversationId] = React.useState<string | null>(null);
  const [messages, setMessages] = React.useState<PublicMessage[]>([]);
  const [input, setInput] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const [bootError, setBootError] = React.useState<string | null>(null);
  const [leadOpen, setLeadOpen] = React.useState(false);
  const [leadSubmitted, setLeadSubmitted] = React.useState(false);
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const abortRef = React.useRef<AbortController | null>(null);
  const stick = React.useRef(true);

  // Bootstrap: load config + create a visitor session.
  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const cfgResp = await fetch(`/api/widget/config/${encodeURIComponent(publicId)}`);
        if (!cfgResp.ok) {
          const err = await cfgResp.json().catch(() => ({ code: "bot_not_found" }));
          if (!cancelled) setBootError(mapBootError(err.code));
          return;
        }
        const cfg = (await cfgResp.json()) as PublicBotConfig;
        const sessResp = await fetch(`/api/widget/sessions/${encodeURIComponent(publicId)}`, {
          method: "POST",
        });
        if (!sessResp.ok) {
          const err = await sessResp.json().catch(() => ({ code: "bot_not_found" }));
          if (!cancelled) setBootError(mapBootError(err.code));
          return;
        }
        const sess = (await sessResp.json()) as { visitor_token: string };
        if (cancelled) return;
        setConfig(cfg);
        setVisitorToken(sess.visitor_token);
      } catch {
        if (!cancelled) setBootError("We couldn't connect to the assistant.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [publicId]);

  React.useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (stick.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  async function ensureConversation(): Promise<string | null> {
    if (conversationId) return conversationId;
    if (!visitorToken) return null;
    const resp = await fetch("/api/widget/conversations", {
      method: "POST",
      headers: { authorization: `Bearer ${visitorToken}` },
    });
    if (!resp.ok) return null;
    const data = (await resp.json()) as { conversation_id: string };
    setConversationId(data.conversation_id);
    return data.conversation_id;
  }

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || sending || !visitorToken) return;
    const userId = `u-${Date.now()}`;
    const assistantId = `a-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", content: trimmed, status: "completed" },
      { id: assistantId, role: "assistant", content: "", status: "streaming" },
    ]);
    setInput("");
    setSending(true);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const conv = await ensureConversation();
      if (!conv) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, status: "failed", errorCode: "network_error", content: ERROR_COPY.network_error.message }
              : m
          )
        );
        return;
      }
      const resp = await fetch(`/api/widget/conversations/${conv}/messages`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          accept: "text/event-stream",
          authorization: `Bearer ${visitorToken}`,
          "Idempotency-Key": `${userId}:${Date.now()}`,
        },
        body: JSON.stringify({ text: trimmed }),
        signal: controller.signal,
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({} as Record<string, unknown>));
        const code = (body.code as string) || "internal_error";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  status: "failed",
                  errorCode: code,
                  content: ERROR_COPY[code]?.message ?? (body.message as string) ?? "Something went wrong.",
                }
              : m
          )
        );
        return;
      }
      for await (const event of parseSseStream(resp)) {
        if (event.kind === "heartbeat") continue;
        try {
          const data = JSON.parse(event.data) as Record<string, unknown>;
          if (event.event === "meta") {
            const msgId = data.message_id as string | undefined;
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, backendId: msgId } : m))
            );
          } else if (event.event === "sources") {
            const sources = (data.sources as PublicMessage["citations"]) ?? [];
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
                      content: ERROR_COPY[code]?.message ?? (data.message as string) ?? "The assistant couldn't finish this answer.",
                    }
                  : m
              )
            );
          }
        } catch {
          /* ignore */
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

  async function rate(messageId: string, rating: 1 | -1) {
    if (!visitorToken) return;
    setMessages((prev) =>
      prev.map((m) => (m.id === messageId ? { ...m, feedback: rating } : m))
    );
    const target = messages.find((m) => m.id === messageId);
    if (!target?.backendId) return;
    try {
      await fetch(`/api/widget/messages/${target.backendId}/feedback`, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${visitorToken}` },
        body: JSON.stringify({ rating }),
      });
    } catch {
      // Keep the optimistic UI even if feedback POST fails.
    }
  }

  if (bootError) {
    return (
      <Shell layout={layout} onClose={onClose} name="Assistant">
        <div className="flex h-full items-center justify-center p-6 text-center">
          <div className="space-y-2">
            <AlertTriangle className="mx-auto h-6 w-6 text-warning" />
            <p className="font-medium">{bootError}</p>
            <p className="text-xs text-muted-foreground">
              If you own this site, check the install snippet and publishing status.
            </p>
          </div>
        </div>
      </Shell>
    );
  }

  if (!config || !visitorToken) {
    return (
      <Shell layout={layout} onClose={onClose} name="Assistant" brandColor={undefined}>
        <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          Loading…
        </div>
      </Shell>
    );
  }

  const brandColor = config.branding?.color;
  const showLeadPrompt =
    config.lead_capture_enabled &&
    !leadSubmitted &&
    messages.filter((m) => m.role === "assistant" && m.status === "completed").length >= 2;

  return (
    <Shell layout={layout} onClose={onClose} name={config.name || "Assistant"} brandColor={brandColor}>
      <div
        ref={scrollRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}
        className="flex-1 space-y-4 overflow-y-auto px-4 py-4 text-sm"
      >
        {messages.length === 0 ? (
          <Greeting config={config} onPick={(q) => void send(q)} />
        ) : (
          messages.map((m) => (
            <PublicBubble
              key={m.id}
              message={m}
              onRate={rate}
              brandColor={brandColor}
            />
          ))
        )}
        {showLeadPrompt && (
          <div className="rounded-lg border border-dashed border-primary/30 bg-accent/40 p-3 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">Want a follow-up from a human?</span>
              <button
                type="button"
                className="link-subtle"
                onClick={() => setLeadOpen(true)}
              >
                Leave your contact
              </button>
            </div>
          </div>
        )}
      </div>

      <footer className="border-t border-border bg-card p-3">
        <p className="mb-1.5 text-center text-[10px] leading-tight text-muted-foreground">
          You&apos;re chatting with an AI assistant. Responses may be inaccurate.
        </p>
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send(input);
              }
            }}
            rows={1}
            placeholder="Ask anything…"
            disabled={sending}
            aria-label="Message"
            className="min-h-[40px] flex-1 resize-none rounded-lg border border-input bg-card px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          {sending ? (
            <button
              type="button"
              aria-label="Stop generating"
              onClick={() => abortRef.current?.abort()}
              className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground hover:bg-muted"
            >
              <StopCircle className="h-4 w-4" />
            </button>
          ) : (
            <button
              type="button"
              aria-label="Send"
              onClick={() => void send(input)}
              disabled={!input.trim()}
              style={brandColor ? { background: brandColor } : undefined}
              className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm transition hover:brightness-110 disabled:opacity-50"
            >
              <Send className="h-4 w-4" />
            </button>
          )}
        </div>
      </footer>

      {leadOpen && (
        <LeadPanel
          conversationId={conversationId}
          visitorToken={visitorToken}
          onClose={() => setLeadOpen(false)}
          onDone={() => {
            setLeadSubmitted(true);
            setLeadOpen(false);
          }}
        />
      )}
    </Shell>
  );
}

function Shell({
  children,
  layout,
  onClose,
  name,
  brandColor,
}: {
  children: React.ReactNode;
  layout: "hosted" | "embed";
  onClose?: () => void;
  name: string;
  brandColor?: string;
}) {
  return (
    <div
      className={cn(
        "flex h-full flex-col overflow-hidden bg-card",
        layout === "hosted" ? "border border-border rounded-xl shadow-elevated" : "shadow-xl"
      )}
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
            <p className="text-sm font-semibold">{name}</p>
            <p className="text-xs text-muted-foreground">Cites every source</p>
          </div>
        </div>
        {onClose && (
          <button
            type="button"
            aria-label="Close chat"
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </header>
      {children}
    </div>
  );
}

function Greeting({
  config,
  onPick,
}: {
  config: PublicBotConfig;
  onPick: (q: string) => void;
}) {
  const greeting =
    config.greeting || `Hi! I'm ${config.name || "your assistant"}. What can I help with?`;
  return (
    <div className="animate-fade-in space-y-3 py-6">
      <div className="mx-auto max-w-sm rounded-xl border border-border bg-subtle/60 p-4 text-center text-sm text-foreground">
        {greeting}
      </div>
      {(config.suggestions ?? []).slice(0, 4).length > 0 && (
        <div className="flex flex-wrap justify-center gap-2">
          {(config.suggestions ?? []).slice(0, 4).map((s) => (
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

function PublicBubble({
  message,
  onRate,
  brandColor,
}: {
  message: PublicMessage;
  onRate: (id: string, rating: 1 | -1) => void;
  brandColor?: string;
}) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div className={cn("flex max-w-[88%] flex-col gap-1.5", isUser && "items-end")}>
        <div
          className={cn(
            "rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
            isUser
              ? "rounded-br-sm text-white shadow-sm"
              : "rounded-bl-sm border border-border bg-subtle text-foreground"
          )}
          style={isUser && brandColor ? { background: brandColor } : undefined}
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
                <span className="font-semibold" style={brandColor ? { color: brandColor } : undefined}>
                  [{c.index}]
                </span>{" "}
                <span className="text-foreground">{c.title}</span>
                {c.page ? <span> · page {c.page}</span> : null}
                {c.excerpt ? <p className="mt-1 line-clamp-2 text-muted-foreground">{c.excerpt}</p> : null}
              </li>
            ))}
          </ol>
        )}
        {!isUser && message.status === "completed" && message.backendId && (
          <div className="flex items-center gap-1 pt-0.5">
            <RateButton active={message.feedback === 1} label="Helpful" icon={ThumbsUp} onClick={() => onRate(message.id, 1)} />
            <RateButton active={message.feedback === -1} label="Not helpful" icon={ThumbsDown} onClick={() => onRate(message.id, -1)} />
          </div>
        )}
      </div>
    </div>
  );
}

function RateButton({
  active,
  label,
  icon: Icon,
  onClick,
}: {
  active: boolean;
  label: string;
  icon: React.ElementType;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "inline-flex h-7 w-7 items-center justify-center rounded-md transition-colors",
        active ? "text-primary bg-accent" : "text-muted-foreground hover:bg-muted hover:text-foreground"
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

function LeadPanel({
  conversationId,
  visitorToken,
  onClose,
  onDone,
}: {
  conversationId: string | null;
  visitorToken: string | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const [name, setName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [consent, setConsent] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!consent || !conversationId || !visitorToken) return;
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch(`/api/widget/conversations/${conversationId}/lead`, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${visitorToken}` },
        body: JSON.stringify({ name: name || undefined, email: email || undefined, consent: true }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        setError((body as { message?: string }).message ?? "Couldn't submit.");
        return;
      }
      onDone();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="absolute inset-0 z-10 flex items-end bg-background/70 backdrop-blur-sm">
      <form onSubmit={submit} className="w-full border-t border-border bg-card p-4">
        <div className="mb-3 flex items-center gap-2">
          <Mail aria-hidden className="h-4 w-4 text-primary" />
          <p className="text-sm font-medium">Leave your contact</p>
        </div>
        {error && <p className="mb-2 text-xs text-destructive">{error}</p>}
        <div className="space-y-2 text-sm">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name"
            className="h-10 w-full rounded-lg border border-input bg-card px-3 placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            type="email"
            placeholder="Email"
            className="h-10 w-full rounded-lg border border-input bg-card px-3 placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <label className="flex items-start gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-border text-primary"
            />
            <span>I agree to be contacted about my question.</span>
          </label>
        </div>
        <div className="mt-3 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-9 items-center rounded-lg px-3 text-sm font-medium text-muted-foreground hover:bg-muted"
          >
            Skip
          </button>
          <button
            type="submit"
            disabled={!consent || busy || (!name && !email)}
            className="inline-flex h-9 items-center rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground shadow-sm transition hover:brightness-110 disabled:opacity-50"
          >
            {busy ? "Sending…" : "Send"}
          </button>
        </div>
      </form>
    </div>
  );
}

function mapBootError(code?: string): string {
  if (code === "bot_not_found" || code === "bot_unpublished")
    return "This assistant isn't currently available.";
  if (code === "origin_not_allowed") return "This site isn't allowed to use this assistant.";
  return "We couldn't reach the assistant.";
}
