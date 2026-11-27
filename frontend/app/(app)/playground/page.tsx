"use client";
import * as React from "react";
import { FlaskConical, Clock, Coins, ShieldAlert, CheckCircle2, XCircle, ChevronRight } from "lucide-react";

import { TopBar } from "@/components/layout/topbar";
import { PageShell } from "@/components/layout/page-shell";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert } from "@/components/ui/alert";
import { EmptyState } from "@/components/ui/empty-state";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { fromNow, cn } from "@/lib/utils";

type TraceListItem = {
  id: string;
  conversation_id: string;
  message_id: string;
  intent: string | null;
  severity: string | null;
  language: string | null;
  grade_iterations: number;
  latency_ms_total: number;
  abstained: boolean;
  escalated: boolean;
  created_at: string;
};

type Passage = { chunk_id: string; score?: number; score_dense?: number; score_fts?: number; rrf?: number };

type TraceDetail = TraceListItem & {
  rewritten_queries: string[];
  retrieved: Passage[];
  reranked: Passage[];
  tools_used: string[];
  verifier_result: { faithful?: boolean; unsupported_claims?: string[] } | null;
  tokens_in: number | null;
  tokens_out: number | null;
  latency_ms_per_stage: Record<string, number>;
  provider: string | null;
  model: string | null;
  cost_est_cents: number | null;
};

export default function PlaygroundPage() {
  const [traces, setTraces] = React.useState<TraceListItem[] | null>(null);
  const [error, setError] = React.useState<unknown>(null);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [detail, setDetail] = React.useState<TraceDetail | null>(null);

  React.useEffect(() => {
    void (async () => {
      try {
        const data = await apiFetch<TraceListItem[]>("/api/bff/rag-traces?limit=50");
        setTraces(data);
        if (data.length > 0) setSelectedId(data[0].id);
      } catch (e) {
        setError(e);
      }
    })();
  }, []);

  React.useEffect(() => {
    if (!selectedId) return;
    void (async () => {
      try {
        setDetail(await apiFetch<TraceDetail>(`/api/bff/rag-traces/${selectedId}`));
      } catch {
        setDetail(null);
      }
    })();
  }, [selectedId]);

  return (
    <>
      <TopBar title="Playground" description="Inspect exactly how the assistant answered a question." />
      <main>
        <PageShell className="max-w-none">
          {error ? (
            <Alert tone="danger" title={describeError(error).title}>
              {describeError(error).message}
            </Alert>
          ) : traces !== null && traces.length === 0 ? (
            <EmptyState
              icon={FlaskConical}
              title="No traces yet"
              description="The retrieval inspector reads traces from the next-generation RAG pipeline, which isn't enabled for live traffic yet. Nothing to inspect until it runs at least one turn."
            />
          ) : (
            <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
              <Card className="flex flex-col overflow-hidden p-0" style={{ height: "calc(100vh - 160px)" }}>
                <div className="border-b border-border px-4 py-3">
                  <p className="text-sm font-medium">Recent turns</p>
                </div>
                <div className="flex-1 overflow-y-auto">
                  {traces === null ? (
                    <div className="space-y-2 p-4">
                      <div className="h-14 skeleton" />
                      <div className="h-14 skeleton" />
                    </div>
                  ) : (
                    <ul>
                      {traces.map((t) => (
                        <li key={t.id}>
                          <button
                            type="button"
                            onClick={() => setSelectedId(t.id)}
                            className={cn(
                              "flex w-full items-center justify-between gap-2 border-b border-border px-4 py-3 text-left text-sm transition-colors hover:bg-subtle/60",
                              selectedId === t.id && "bg-accent"
                            )}
                          >
                            <div className="min-w-0">
                              <p className="truncate font-medium">{t.intent ?? "turn"}</p>
                              <p className="text-xs text-muted-foreground">{fromNow(t.created_at)}</p>
                            </div>
                            <div className="flex items-center gap-1">
                              {t.abstained && <Badge tone="warning">Abstained</Badge>}
                              {t.escalated && <Badge tone="danger">Escalated</Badge>}
                              <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                            </div>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </Card>

              <div className="space-y-4">
                {!detail ? (
                  <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
                    Select a turn to inspect it.
                  </div>
                ) : (
                  <>
                    <Card className="p-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone="primary">{detail.intent ?? "—"}</Badge>
                        {detail.severity && <Badge tone={detail.severity === "critical" ? "danger" : "neutral"}>{detail.severity}</Badge>}
                        {detail.language && <Badge tone="neutral">{detail.language}</Badge>}
                        {detail.provider && <Badge tone="neutral">{detail.provider}{detail.model ? ` / ${detail.model}` : ""}</Badge>}
                      </div>
                      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                        <Stat icon={Clock} label="Total latency" value={`${detail.latency_ms_total} ms`} />
                        <Stat icon={CheckCircle2} label="Grade iterations" value={String(detail.grade_iterations)} />
                        <Stat
                          icon={Coins}
                          label="Tokens in/out"
                          value={`${detail.tokens_in ?? "—"} / ${detail.tokens_out ?? "—"}`}
                        />
                        <Stat
                          icon={ShieldAlert}
                          label="Faithful"
                          value={detail.verifier_result?.faithful === false ? "No" : detail.verifier_result?.faithful === true ? "Yes" : "—"}
                        />
                      </div>
                    </Card>

                    {detail.rewritten_queries.length > 0 && (
                      <Card className="p-4">
                        <p className="mb-2 text-sm font-medium">Rewritten queries</p>
                        <ul className="space-y-1 text-sm text-muted-foreground">
                          {detail.rewritten_queries.map((q, i) => (
                            <li key={i} className="rounded-md bg-subtle/60 px-2 py-1">
                              {q}
                            </li>
                          ))}
                        </ul>
                      </Card>
                    )}

                    <Card className="p-4">
                      <p className="mb-2 text-sm font-medium">Retrieval → rerank</p>
                      <p className="mb-2 text-xs text-muted-foreground">
                        {detail.retrieved.length} candidates retrieved, {detail.reranked.length} kept after rerank.
                      </p>
                      {detail.reranked.length === 0 ? (
                        <p className="text-sm text-muted-foreground">No passages were used for this turn.</p>
                      ) : (
                        <ul className="space-y-1">
                          {detail.reranked.map((p, i) => (
                            <li key={p.chunk_id} className="flex items-center justify-between gap-2 rounded-md bg-subtle/60 px-2 py-1 text-xs">
                              <span className="font-mono text-muted-foreground">
                                [{i + 1}] {p.chunk_id.slice(0, 8)}…
                              </span>
                              <span className="text-foreground">score {p.score?.toFixed(3) ?? "—"}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </Card>

                    {detail.verifier_result?.unsupported_claims && detail.verifier_result.unsupported_claims.length > 0 && (
                      <Card className="p-4">
                        <p className="mb-2 flex items-center gap-1.5 text-sm font-medium text-destructive">
                          <XCircle className="h-4 w-4" /> Unsupported claims flagged by the verifier
                        </p>
                        <ul className="space-y-1 text-sm text-muted-foreground">
                          {detail.verifier_result.unsupported_claims.map((c, i) => (
                            <li key={i}>{c}</li>
                          ))}
                        </ul>
                      </Card>
                    )}

                    <Card className="p-4">
                      <p className="mb-2 text-sm font-medium">Latency per stage</p>
                      <div className="space-y-1.5">
                        {Object.entries(detail.latency_ms_per_stage).map(([stage, ms]) => (
                          <div key={stage} className="flex items-center gap-2 text-xs">
                            <span className="w-24 shrink-0 capitalize text-muted-foreground">{stage}</span>
                            <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                              <div
                                className="h-full rounded-full bg-primary"
                                style={{ width: `${Math.min(100, (ms / Math.max(1, detail.latency_ms_total)) * 100)}%` }}
                              />
                            </div>
                            <span className="w-14 shrink-0 text-right text-muted-foreground">{ms} ms</span>
                          </div>
                        ))}
                      </div>
                    </Card>
                  </>
                )}
              </div>
            </div>
          )}
        </PageShell>
      </main>
    </>
  );
}

function Stat({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-subtle/60 p-2.5">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Icon className="h-3.5 w-3.5" /> {label}
      </div>
      <p className="mt-0.5 text-sm font-semibold">{value}</p>
    </div>
  );
}
