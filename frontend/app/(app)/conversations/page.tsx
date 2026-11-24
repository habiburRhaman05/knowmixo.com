"use client";
import * as React from "react";
import Link from "next/link";
import {
  MessageSquare,
  MessageSquareText,
  Filter,
  Tag,
  Loader2,
  AlertTriangle,
  ArrowRight,
  Search,
  ThumbsUp,
  Users,
  CheckCircle2,
} from "lucide-react";

import { TopBar } from "@/components/layout/topbar";
import { PageShell } from "@/components/layout/page-shell";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { type ConversationListResponse, type ConversationListItem } from "@/lib/types";
import { cn, fromNow } from "@/lib/utils";

const PAGE_SIZE = 25;

type Status = "" | "active" | "closed";
type Feedback = "" | "yes" | "no";

export default function ConversationsPage() {
  const [items, setItems] = React.useState<ConversationListItem[] | null>(null);
  const [cursor, setCursor] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<unknown>(null);
  const [status, setStatus] = React.useState<Status>("");
  const [feedback, setFeedback] = React.useState<Feedback>("");

  const key = React.useMemo(() => JSON.stringify([status, feedback]), [status, feedback]);

  const load = React.useCallback(
    async (opts: { reset?: boolean } = {}) => {
      const params = new URLSearchParams();
      if (status) params.set("status", status);
      if (feedback === "yes") params.set("has_feedback", "true");
      if (feedback === "no") params.set("has_feedback", "false");
      params.set("limit", String(PAGE_SIZE));
      if (!opts.reset && cursor) params.set("cursor", cursor);
      setLoading(true);
      setError(null);
      try {
        const data = await apiFetch<ConversationListResponse>(`/api/bff/conversations?${params.toString()}`);
        setItems((prev) => (opts.reset || !prev ? data.items : [...prev, ...data.items]));
        setCursor(data.next_cursor);
      } catch (e) {
        setError(e);
      } finally {
        setLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key]
  );

  React.useEffect(() => {
    setCursor(null);
    void load({ reset: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const total = items?.length ?? 0;
  const withFeedback = items?.filter((i) => i.has_feedback).length ?? 0;
  const withLead = items?.filter((i) => i.has_lead).length ?? 0;

  return (
    <>
      <TopBar
        title="Conversations"
        description="Every chat visitors had, with citations and leads."
      />
      <main>
        <PageShell>
          <section className="mb-6 grid gap-4 sm:grid-cols-3">
            <KpiPill icon={MessageSquare} label="In view" value={total.toString()} />
            <KpiPill icon={ThumbsUp} label="With feedback" value={withFeedback.toString()} />
            <KpiPill icon={Users} label="With a lead" value={withLead.toString()} />
          </section>

          <Card>
            <div className="flex flex-wrap items-center gap-3 border-b border-border p-4">
              <Filter aria-hidden className="h-4 w-4 text-muted-foreground" />
              <SegmentedGroup<Status>
                label="Status"
                value={status}
                onChange={setStatus}
                options={[
                  { value: "", label: "All" },
                  { value: "active", label: "Active" },
                  { value: "closed", label: "Closed" },
                ]}
              />
              <SegmentedGroup<Feedback>
                label="Feedback"
                value={feedback}
                onChange={setFeedback}
                options={[
                  { value: "", label: "Any" },
                  { value: "yes", label: "With feedback" },
                  { value: "no", label: "No feedback" },
                ]}
              />
            </div>

            {error ? (
              <div className="p-5">
                <Alert tone="danger" title={describeError(error).title} icon={AlertTriangle}>
                  {describeError(error).message}
                </Alert>
              </div>
            ) : items === null || (loading && items.length === 0) ? (
              <SkeletonList />
            ) : items.length === 0 ? (
              <EmptyState
                icon={MessageSquareText}
                title="No conversations yet"
                description="Publish your assistant and share the hosted link to start collecting conversations."
                action={
                  <Button asChild variant="secondary">
                    <Link href="/chatbot/publish">
                      Open publish <ArrowRight className="h-4 w-4" />
                    </Link>
                  </Button>
                }
              />
            ) : (
              <ul>
                {items.map((row) => (
                  <li key={row.id}>
                    <Link
                      href={`/conversations/${row.id}`}
                      className="group grid grid-cols-[1fr_auto] items-start gap-4 border-b border-border px-5 py-4 last:border-b-0 hover:bg-subtle/60"
                    >
                      <div className="min-w-0 space-y-1.5">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-foreground">
                            Conversation {row.id.slice(0, 8)}…
                          </span>
                          <Badge tone={row.status === "active" ? "primary" : "neutral"}>
                            {row.status}
                          </Badge>
                          {row.has_lead && (
                            <Badge tone="success">
                              <Users className="h-3 w-3" /> Lead
                            </Badge>
                          )}
                          {row.has_feedback && (
                            <Badge tone="warning">
                              <ThumbsUp className="h-3 w-3" /> Feedback
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground">
                          Started {fromNow(row.created_at)} · {row.message_count} message
                          {row.message_count === 1 ? "" : "s"}
                        </p>
                      </div>
                      <ArrowRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            {cursor && items && items.length > 0 && (
              <div className="flex items-center justify-center p-4">
                <Button variant="secondary" onClick={() => void load()} loading={loading}>
                  Load more
                </Button>
              </div>
            )}
          </Card>
        </PageShell>
      </main>
    </>
  );
}

function KpiPill({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-card p-4 shadow-card">
      <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-accent-foreground">
        <Icon aria-hidden className="h-5 w-5" />
      </span>
      <div>
        <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="font-display text-xl font-semibold">{value}</p>
      </div>
    </div>
  );
}

function SegmentedGroup<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: Array<{ value: T; label: string }>;
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      <div role="group" aria-label={label} className="flex rounded-md border border-border bg-subtle p-0.5">
        {options.map((o) => (
          <button
            key={o.value || "any"}
            type="button"
            onClick={() => onChange(o.value)}
            aria-pressed={value === o.value}
            className={cn(
              "rounded-sm px-2.5 py-1 text-xs font-medium transition-colors",
              value === o.value
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function SkeletonList() {
  return (
    <ul>
      {Array.from({ length: 5 }).map((_, i) => (
        <li key={i} className="border-b border-border px-5 py-4 last:border-b-0">
          <div className="space-y-2">
            <div className="h-4 w-1/3 skeleton" />
            <div className="h-3 w-1/4 skeleton" />
          </div>
        </li>
      ))}
    </ul>
  );
}
