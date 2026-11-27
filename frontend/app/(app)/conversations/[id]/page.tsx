"use client";
import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Download,
  Trash2,
  Loader2,
  AlertTriangle,
  ThumbsUp,
  ThumbsDown,
  User,
  Sparkles,
  Mail,
  CheckCircle2,
} from "lucide-react";

import { TopBar } from "@/components/layout/topbar";
import { PageShell } from "@/components/layout/page-shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { useToast } from "@/components/ui/toast";
import {
  type ConversationDetail,
  type ConversationStatus,
  CONVERSATION_STATUS_LABEL,
  CONVERSATION_STATUS_TONE,
} from "@/lib/types";
import { fromNow } from "@/lib/utils";

export default function ConversationDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { toast } = useToast();
  const [data, setData] = React.useState<ConversationDetail | null>(null);
  const [error, setError] = React.useState<unknown>(null);
  const [deleting, setDeleting] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const resp = await apiFetch<ConversationDetail>(`/api/bff/conversations/${params.id}`);
        if (!cancelled) setData(resp);
      } catch (e) {
        if (!cancelled) setError(e);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [params.id]);

  async function onDelete() {
    if (!window.confirm("Delete this conversation and its messages? This can't be undone.")) return;
    setDeleting(true);
    try {
      await apiFetch(`/api/bff/conversations/${params.id}`, { method: "DELETE" });
      toast({ tone: "success", title: "Conversation deleted" });
      router.replace("/conversations");
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
      setDeleting(false);
    }
  }

  return (
    <>
      <TopBar title="Conversation" description="Transcript with the sources that were cited." />
      <main>
        <PageShell>
          <div className="mb-4 flex items-center justify-between">
            <Button asChild variant="ghost" size="sm">
              <Link href="/conversations">
                <ArrowLeft className="h-4 w-4" /> All conversations
              </Link>
            </Button>
            <div className="flex items-center gap-2">
              <Button asChild variant="secondary">
                <a href={`/api/bff/conversations/${params.id}/export`} download>
                  <Download className="h-4 w-4" /> Export JSON
                </a>
              </Button>
              <Button variant="destructive" onClick={onDelete} loading={deleting}>
                <Trash2 className="h-4 w-4" /> Delete
              </Button>
            </div>
          </div>

          {error ? (
            <Alert tone="danger" title={describeError(error).title} icon={AlertTriangle}>
              {describeError(error).message}
            </Alert>
          ) : !data ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading conversation…
            </div>
          ) : (
            <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
              <Card>
                <CardHeader className="border-b border-border">
                  <div className="flex items-center gap-2">
                    <Badge tone={CONVERSATION_STATUS_TONE[data.status as ConversationStatus] ?? "neutral"}>
                      {CONVERSATION_STATUS_LABEL[data.status as ConversationStatus] ?? data.status}
                    </Badge>
                    <span className="text-xs text-muted-foreground">Started {fromNow(data.created_at)}</span>
                  </div>
                  <CardTitle className="text-lg">Transcript</CardTitle>
                </CardHeader>
                <CardContent className="space-y-6 py-6">
                  {data.messages.map((m) => (
                    <div key={m.id} className="flex gap-3">
                      <span
                        className={
                          "mt-1 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full " +
                          (m.role === "user"
                            ? "bg-muted text-muted-foreground"
                            : "bg-gradient-to-br from-primary to-[hsl(260_100%_60%)] text-primary-foreground")
                        }
                        aria-hidden
                      >
                        {m.role === "user" ? <User className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />}
                      </span>
                      <div className="min-w-0 flex-1 space-y-2">
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <span className="font-medium text-foreground">
                            {m.role === "user" ? "Visitor" : data.messages[0]?.role === "user" ? "Assistant" : "Assistant"}
                          </span>
                          <span>· {fromNow(m.created_at)}</span>
                          {m.feedback_rating === 1 && (
                            <Badge tone="success">
                              <ThumbsUp className="h-3 w-3" /> Helpful
                            </Badge>
                          )}
                          {m.feedback_rating === -1 && (
                            <Badge tone="danger">
                              <ThumbsDown className="h-3 w-3" /> Not helpful
                            </Badge>
                          )}
                        </div>
                        <p className="whitespace-pre-wrap rounded-lg border border-border bg-subtle/60 p-3 text-sm leading-relaxed">
                          {m.content || <span className="text-muted-foreground">(empty)</span>}
                        </p>
                        {m.citations && m.citations.length > 0 && (
                          <ol className="space-y-1.5">
                            {m.citations.map((c) => (
                              <li
                                key={`${m.id}-${c.index}`}
                                className="rounded-md border border-border bg-card px-3 py-2 text-xs"
                              >
                                <div className="flex items-center gap-2 text-primary">
                                  <span className="font-semibold">[{c.index}]</span>
                                  <span className="truncate text-foreground">{c.title}</span>
                                  {c.page ? <span className="text-muted-foreground">· page {c.page}</span> : null}
                                </div>
                                {c.excerpt && (
                                  <p className="mt-1 text-muted-foreground line-clamp-3">{c.excerpt}</p>
                                )}
                              </li>
                            ))}
                          </ol>
                        )}
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>

              <aside className="space-y-4 lg:sticky lg:top-24 lg:self-start">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Lead</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {!data.lead ? (
                      <p className="text-sm text-muted-foreground">
                        The visitor didn&apos;t submit contact details.
                      </p>
                    ) : (
                      <dl className="space-y-3 text-sm">
                        {Object.entries(data.lead.values).map(([key, value]) => (
                          <div key={key} className="flex items-start gap-2">
                            <Mail aria-hidden className="mt-0.5 h-4 w-4 text-muted-foreground" />
                            <div>
                              <dt className="text-xs uppercase tracking-wide text-muted-foreground">{key}</dt>
                              <dd className="font-medium">{value}</dd>
                            </div>
                          </div>
                        ))}
                        <div className="flex items-start gap-2 pt-2 text-xs text-muted-foreground">
                          <CheckCircle2 aria-hidden className="mt-0.5 h-3.5 w-3.5 text-success" />
                          <span>Consented {fromNow(data.lead.consent_at ?? data.lead.submitted_at)}</span>
                        </div>
                      </dl>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Cited sources</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {data.citations.length === 0 ? (
                      <p className="text-sm text-muted-foreground">No citations in this conversation.</p>
                    ) : (
                      <ul className="space-y-2 text-sm">
                        {Array.from(new Map(data.citations.map((c) => [c.document_id, c])).values()).map((c) => (
                          <li key={c.document_id}>
                            <Link
                              href={`/knowledge`}
                              className="flex items-start gap-2 rounded-md border border-border bg-subtle/60 p-2 hover:bg-subtle"
                            >
                              <span className="font-mono text-xs text-muted-foreground">
                                [{c.index}]
                              </span>
                              <span className="min-w-0 flex-1 truncate">{c.title}</span>
                            </Link>
                          </li>
                        ))}
                      </ul>
                    )}
                  </CardContent>
                </Card>
              </aside>
            </div>
          )}
        </PageShell>
      </main>
    </>
  );
}
