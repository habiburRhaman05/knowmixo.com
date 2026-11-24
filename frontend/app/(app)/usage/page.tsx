"use client";
import * as React from "react";
import { AlertTriangle, Clock, Zap, Gauge } from "lucide-react";
import { TopBar } from "@/components/layout/topbar";
import { PageShell } from "@/components/layout/page-shell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert } from "@/components/ui/alert";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { cn } from "@/lib/utils";

type UsageResponse = {
  company_daily: { requests: number; tokens: number; embeddings: number; limit: number };
  global_daily: { requests: number; limit: number };
  quota_state: "ok" | "exhausted";
  next_reset_at: string;
};

export default function UsagePage() {
  const [data, setData] = React.useState<UsageResponse | null>(null);
  const [error, setError] = React.useState<unknown>(null);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await apiFetch<UsageResponse>("/api/bff/usage");
        if (!cancelled) setData(res);
      } catch (e) {
        if (!cancelled) setError(e);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <TopBar
        title="Usage"
        description="Daily allowance for your assistant. No paid upgrade — resets at 00:00 UTC."
      />
      <main>
        <PageShell>
          {error ? (() => {
            const info = describeError(error);
            return (
              <Alert tone="danger" title={info.title} icon={AlertTriangle}>
                {info.message}
              </Alert>
            );
          })() : null}
          {!error && !data && <SkeletonCards />}
          {data && (
            <div className="space-y-6">
              {data.quota_state === "exhausted" && (
                <Alert tone="warning" title="Daily limit reached" icon={AlertTriangle}>
                  Your assistant is temporarily paused for new replies. Usage resets at{" "}
                  <strong className="text-foreground">{new Date(data.next_reset_at).toLocaleString()}</strong>.
                </Alert>
              )}
              <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <UsageCard
                  icon={Gauge}
                  title="Chat requests today"
                  used={data.company_daily.requests}
                  limit={data.company_daily.limit}
                  description="Replies the assistant generated across every surface."
                />
                <UsageCard
                  icon={Zap}
                  title="Tokens today"
                  used={data.company_daily.tokens}
                  limit={null}
                  description="Approximate — counted when a reply completes."
                />
                <UsageCard
                  icon={Zap}
                  title="Embeddings today"
                  used={data.company_daily.embeddings}
                  limit={null}
                  description="Spent indexing new sources or refreshes."
                />
              </section>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Platform allowance</CardTitle>
                  <CardDescription>
                    A shared daily cap across every Knowmivo workspace while we&apos;re in open beta.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Platform requests today</span>
                    <span className="font-medium">
                      {data.global_daily.requests} / {data.global_daily.limit}
                    </span>
                  </div>
                  <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
                    <div
                      className={cn(
                        "h-full transition-[width] duration-500",
                        data.global_daily.requests >= data.global_daily.limit ? "bg-warning" : "bg-primary"
                      )}
                      style={{
                        width: `${Math.min(100, Math.round((data.global_daily.requests / data.global_daily.limit) * 100))}%`,
                      }}
                    />
                  </div>
                  <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground">
                    <Clock className="h-3.5 w-3.5" aria-hidden />
                    Next reset {new Date(data.next_reset_at).toLocaleString()}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </PageShell>
      </main>
    </>
  );
}

function UsageCard({
  icon: Icon,
  title,
  description,
  used,
  limit,
}: {
  icon: React.ElementType;
  title: string;
  description: string;
  used: number;
  limit: number | null;
}) {
  const pct = limit && limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : null;
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-accent text-accent-foreground">
            <Icon aria-hidden className="h-4 w-4" />
          </div>
          <span className="text-xs text-muted-foreground">Today</span>
        </div>
        <CardTitle className="mt-2 text-base">{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-baseline gap-2">
          <span className="font-display text-3xl font-semibold tracking-tight">{used.toLocaleString()}</span>
          {limit !== null && <span className="text-sm text-muted-foreground">/ {limit.toLocaleString()}</span>}
        </div>
        {pct !== null && (
          <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-muted">
            <div
              className={cn(
                "h-full transition-[width] duration-500",
                pct >= 90 ? "bg-warning" : "bg-primary"
              )}
              style={{ width: `${pct}%` }}
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function SkeletonCards() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="h-40 skeleton" />
      ))}
    </div>
  );
}
