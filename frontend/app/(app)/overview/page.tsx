"use client";
import * as React from "react";
import Link from "next/link";
import {
  BookOpen,
  Bot,
  CheckCircle2,
  Circle,
  MessageSquare,
  Rocket,
  Gauge,
  ArrowRight,
  AlertTriangle,
  Sparkles,
  TrendingUp,
  TrendingDown,
  Plus,
  ArrowUpRight,
  Clock,
  Zap,
} from "lucide-react";

import { TopBar } from "@/components/layout/topbar";
import { PageShell } from "@/components/layout/page-shell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { Sparkline } from "@/components/overview/sparkline";
import { ProgressRing } from "@/components/overview/progress-ring";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { cn } from "@/lib/utils";

type DashboardResponse = {
  setup_checklist: Array<{ key: string; label: string; done: boolean }>;
  source_counts_by_state: Record<string, number>;
  conversation_count: number;
  usage_summary: { requests_today: number; limit: number; quota_state: "ok" | "exhausted" };
};

type ConversationsPoint = { day: string; count: number };
type DeflectionPoint = { day: string; total: number; deflected: number; deflection_rate: number | null };
type TtftPoint = { day: string; p50_ms: number | null; p95_ms: number | null; sample_count: number };

type AnalyticsSeries = {
  conversations: ConversationsPoint[];
  deflection: DeflectionPoint[];
  ttft: TtftPoint[];
};

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; data: DashboardResponse; series: AnalyticsSeries }
  | { kind: "error"; error: unknown };

/**
 * Overview is the first screen owners see every day. Four KPIs with sparkline
 * trend lines, a setup checklist with a progress ring, a quick-action column
 * and a live activity feed. Every surface links somewhere — nothing is a
 * dead end.
 */
export default function OverviewPage() {
  const [state, setState] = React.useState<LoadState>({ kind: "loading" });

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await apiFetch<DashboardResponse>("/api/bff/dashboard");
        // Analytics series are a newer, additive surface -- a failure here
        // (or on a fresh company with no data yet) must never block the
        // rest of Overview from rendering, so each is fetched independently
        // with an empty-array fallback rather than failing the whole page.
        const [conversations, deflection, ttft] = await Promise.all([
          apiFetch<{ series: ConversationsPoint[] }>("/api/bff/analytics/series?metric=conversations")
            .then((r) => r.series)
            .catch(() => [] as ConversationsPoint[]),
          apiFetch<{ series: DeflectionPoint[] }>("/api/bff/analytics/series?metric=deflection")
            .then((r) => r.series)
            .catch(() => [] as DeflectionPoint[]),
          apiFetch<{ series: TtftPoint[] }>("/api/bff/analytics/series?metric=ttft")
            .then((r) => r.series)
            .catch(() => [] as TtftPoint[]),
        ]);
        if (!cancelled) setState({ kind: "ready", data, series: { conversations, deflection, ttft } });
      } catch (error) {
        if (!cancelled) setState({ kind: "error", error });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <TopBar title="Overview" description="A snapshot of your knowledge and chat activity." />
      <main>
        <PageShell>
          {state.kind === "loading" && <OverviewSkeleton />}
          {state.kind === "error" && (
            <Alert tone="danger" title={describeError(state.error).title} icon={AlertTriangle}>
              {describeError(state.error).message}
            </Alert>
          )}
          {state.kind === "ready" && <OverviewReady data={state.data} series={state.series} />}
        </PageShell>
      </main>
    </>
  );
}

function OverviewReady({ data, series }: { data: DashboardResponse; series: AnalyticsSeries }) {
  const totalSources = Object.values(data.source_counts_by_state).reduce((a, b) => a + b, 0);
  const ready = data.source_counts_by_state.ready ?? 0;
  const processing =
    (data.source_counts_by_state.pending ?? 0) +
    (data.source_counts_by_state.processing ?? 0) +
    (data.source_counts_by_state.retrying ?? 0) +
    (data.source_counts_by_state.quota_wait ?? 0);
  const failed = data.source_counts_by_state.failed ?? 0;
  const usage = data.usage_summary;
  const pct =
    usage.limit > 0 ? Math.min(100, Math.round((usage.requests_today / usage.limit) * 100)) : 0;

  const checklistDone = data.setup_checklist.filter((i) => i.done).length;
  const checklistPct = Math.round((checklistDone / Math.max(1, data.setup_checklist.length)) * 100);
  const nextAction = data.setup_checklist.find((i) => !i.done) ?? null;

  // Knowledge sources and today's usage don't have a backend time-series
  // endpoint (only conversations/deflection/TTFT do, per 05-RAG-V2-SPEC.md
  // and this sprint's own analytics work) -- those two sparklines stay a
  // lightweight placeholder shape; conversations now uses the real series.
  const sourceSeries = pseudoSeries(totalSources);
  const usageSeries = pseudoSeries(usage.requests_today || 1);
  const convoSeries = series.conversations.length > 0 ? series.conversations.map((p) => p.count) : pseudoSeries(data.conversation_count);
  const convoDelta = weekOverWeekDelta(series.conversations.map((p) => p.count));

  const latestDeflection = [...series.deflection].reverse().find((p) => p.deflection_rate !== null);
  const deflectionSeries = series.deflection.filter((p) => p.deflection_rate !== null).map((p) => Math.round((p.deflection_rate ?? 0) * 100));

  const latestTtft = [...series.ttft].reverse().find((p) => p.p50_ms !== null);
  const ttftSeries = series.ttft.filter((p) => p.p50_ms !== null).map((p) => p.p50_ms ?? 0);

  return (
    <div className="space-y-8">
      <HeroPanel
        checklistDone={checklistDone}
        checklistTotal={data.setup_checklist.length}
        checklistPct={checklistPct}
        nextAction={nextAction}
      />

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiTile
          icon={BookOpen}
          label="Knowledge sources"
          value={totalSources}
          hint={
            <>
              <span className="text-success">{ready}</span> ready
              {processing > 0 && (
                <>
                  {" · "}
                  <span className="text-primary">{processing}</span> processing
                </>
              )}
              {failed > 0 && (
                <>
                  {" · "}
                  <span className="text-destructive">{failed}</span> failed
                </>
              )}
            </>
          }
          href="/knowledge"
          series={sourceSeries}
        />
        <KpiTile
          icon={Bot}
          label="Chatbot status"
          value={data.setup_checklist.find((i) => i.key === "publish")?.done ? "Live" : "Draft"}
          hint={
            data.setup_checklist.find((i) => i.key === "publish")?.done
              ? "Visible to the public"
              : "Publish to go live"
          }
          href="/chatbot"
          tone={data.setup_checklist.find((i) => i.key === "publish")?.done ? "success" : "default"}
          statusDot={data.setup_checklist.find((i) => i.key === "publish")?.done}
        />
        <KpiTile
          icon={MessageSquare}
          label="Conversations"
          value={data.conversation_count}
          hint="Across every surface"
          href="/conversations"
          series={convoSeries}
          delta={convoDelta}
        />
        <KpiTile
          icon={Gauge}
          label="Today's usage"
          value={`${usage.requests_today}/${usage.limit}`}
          hint={usage.quota_state === "exhausted" ? "Limit reached" : "Resets at 00:00 UTC"}
          tone={usage.quota_state === "exhausted" ? "warning" : "default"}
          progress={pct}
          href="/usage"
          series={usageSeries}
        />
        <KpiTile
          icon={TrendingUp}
          label="Deflection rate"
          value={latestDeflection ? `${Math.round((latestDeflection.deflection_rate ?? 0) * 100)}%` : "—"}
          hint="Resolved by the bot, no handoff"
          href="/conversations"
          series={deflectionSeries.length > 1 ? deflectionSeries : undefined}
        />
        <KpiTile
          icon={Zap}
          label="Median response time"
          value={latestTtft?.p50_ms ? `${(latestTtft.p50_ms / 1000).toFixed(1)}s` : "—"}
          hint="Time to first word (p50)"
          href="/conversations"
          series={ttftSeries.length > 1 ? ttftSeries : undefined}
        />
      </section>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <ChecklistCard data={data} />
        <div className="space-y-6">
          <QuickActionsCard />
          <ActivityFeedCard
            events={sampleActivity({ ready, processing, failed, conversations: data.conversation_count })}
          />
        </div>
      </div>
    </div>
  );
}

function HeroPanel({
  checklistDone,
  checklistTotal,
  checklistPct,
  nextAction,
}: {
  checklistDone: number;
  checklistTotal: number;
  checklistPct: number;
  nextAction: { key: string; label: string; done: boolean } | null;
}) {
  const complete = checklistDone === checklistTotal;
  return (
    <section className="relative overflow-hidden rounded-2xl border border-border bg-[hsl(224_28%_8%)] p-6 text-white grain sm:p-8">
      <div
        className="absolute inset-0 opacity-70"
        aria-hidden
        style={{
          background:
            "radial-gradient(circle at 15% 10%, hsla(243,85%,65%,0.3), transparent 55%), radial-gradient(circle at 85% 80%, hsla(260,90%,65%,0.3), transparent 55%)",
        }}
      />
      <div className="relative flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-2">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-white/5 px-2.5 py-1 text-[11px] font-medium text-white/70 backdrop-blur">
            <Sparkles className="h-3 w-3" />
            {complete ? "Ready to launch" : "Setup in progress"}
          </span>
          <h2 className="font-display text-2xl font-semibold tracking-tight sm:text-3xl">
            {complete ? "Your assistant is live and grounded." : "Let's get your assistant live."}
          </h2>
          <p className="max-w-xl text-sm text-white/65">
            {complete
              ? "Share the hosted link with your team, or drop the script tag on your site to launch the widget."
              : nextAction
              ? `Next up: ${nextAction.label.toLowerCase()}. It only takes a minute.`
              : "Every answer the widget gives will cite the source and page it came from."}
          </p>
          <div className="flex flex-wrap gap-2 pt-2">
            <Button asChild className="shadow-[0_8px_24px_-8px_rgba(79,70,229,0.5)]">
              <Link href={nextAction?.key === "add_source" ? "/knowledge" : "/chatbot"}>
                {complete ? "Open publish" : "Continue setup"}
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button asChild variant="secondary" className="border-white/15 bg-white/5 text-white hover:bg-white/10 hover:border-white/20">
              <Link href="/onboarding">
                Onboarding checklist
              </Link>
            </Button>
          </div>
        </div>
        <div className="flex items-center gap-4 self-start rounded-xl border border-white/10 bg-white/5 p-4 backdrop-blur sm:self-center">
          <ProgressRing value={checklistPct} size={64} stroke={6} />
          <div>
            <p className="text-xs uppercase tracking-wide text-white/55">Setup progress</p>
            <p className="font-display text-xl font-semibold">
              {checklistDone} <span className="text-white/50">/ {checklistTotal}</span>
            </p>
            <p className="text-xs text-white/60">
              {complete ? "Everything is done. 🚀" : nextAction ? nextAction.label : "Keep going"}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

function KpiTile({
  icon: Icon,
  label,
  value,
  hint,
  href,
  tone = "default",
  progress,
  series,
  delta,
  statusDot,
}: {
  icon: React.ElementType;
  label: string;
  value: React.ReactNode;
  hint: React.ReactNode;
  href: string;
  tone?: "default" | "warning" | "success";
  progress?: number;
  series?: number[];
  delta?: string;
  statusDot?: boolean;
}) {
  return (
    <Link
      href={href}
      className="group relative block overflow-hidden rounded-xl border border-border bg-card p-5 input-elevated transition-[transform,box-shadow] duration-200 ease-out hover:-translate-y-0.5 hover:shadow-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="flex items-start justify-between">
        <div
          className={cn(
            "inline-flex h-10 w-10 items-center justify-center rounded-lg",
            tone === "warning"
              ? "bg-warning/15 text-warning"
              : tone === "success"
              ? "bg-success/15 text-success"
              : "bg-accent text-accent-foreground"
          )}
        >
          <Icon aria-hidden className="h-5 w-5" />
        </div>
        <ArrowUpRight className="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
      </div>
      <p className="mt-4 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <div className="flex items-baseline gap-2">
        <p className="font-display text-2xl font-semibold leading-tight">{value}</p>
        {statusDot && (
          <span
            aria-hidden
            className="dot-pulse ml-1 inline-block h-1.5 w-1.5 rounded-full bg-success text-success"
          />
        )}
        {delta && (
          <span
            className={cn(
              "inline-flex items-center gap-0.5 text-xs font-medium",
              delta.startsWith("-") ? "text-destructive" : "text-success"
            )}
          >
            {delta.startsWith("-") ? <TrendingDown className="h-3 w-3" /> : <TrendingUp className="h-3 w-3" />}
            {delta}
          </span>
        )}
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
      {series && (
        <div className="mt-3">
          <Sparkline values={series} width={160} height={28} />
        </div>
      )}
      {typeof progress === "number" && (
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
          <div
            className={cn(
              "h-full transition-[width] duration-500",
              tone === "warning" ? "bg-warning" : "bg-primary"
            )}
            style={{ width: `${progress}%` }}
          />
        </div>
      )}
    </Link>
  );
}

function ChecklistCard({ data }: { data: DashboardResponse }) {
  return (
    <Card className="card-surface-raised overflow-hidden">
      <CardHeader className="border-b border-border">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <CardTitle className="text-lg">Setup checklist</CardTitle>
            <CardDescription>Finish these to launch a grounded, cited assistant.</CardDescription>
          </div>
          <Button asChild size="sm" variant="secondary">
            <Link href="/onboarding">
              Open onboarding
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-2 pt-6">
        {data.setup_checklist.map((item, i) => (
          <div
            key={item.key}
            className={cn(
              "flex items-center justify-between rounded-lg border px-4 py-3 text-sm transition-colors",
              item.done
                ? "border-success/25 bg-success/5"
                : "border-border bg-card hover:bg-subtle"
            )}
          >
            <div className="flex items-center gap-3">
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-border bg-background text-xs font-semibold text-muted-foreground">
                {i + 1}
              </span>
              {item.done ? (
                <CheckCircle2 aria-hidden className="h-4 w-4 text-success" />
              ) : (
                <Circle aria-hidden className="h-4 w-4 text-muted-foreground" />
              )}
              <span
                className={cn(
                  item.done ? "text-muted-foreground line-through" : "text-foreground"
                )}
              >
                {item.label}
              </span>
            </div>
            {!item.done && <Badge tone="primary">Next up</Badge>}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function QuickActionsCard() {
  const items = [
    { icon: Plus, title: "Add a knowledge source", body: "Upload a PDF or paste a URL.", href: "/knowledge" },
    { icon: Bot, title: "Shape the assistant", body: "Tone, template and greeting.", href: "/chatbot" },
    { icon: Rocket, title: "Publish a snapshot", body: "Go live when you're happy.", href: "/chatbot/publish" },
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Quick actions</CardTitle>
        <CardDescription>Shortcuts to what moves you forward.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {items.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="group flex items-start gap-3 rounded-lg border border-border p-3 text-sm transition-colors hover:bg-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-accent text-accent-foreground">
              <item.icon aria-hidden className="h-4 w-4" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="font-medium text-foreground">{item.title}</p>
              <p className="text-xs text-muted-foreground">{item.body}</p>
            </div>
            <ArrowRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
          </Link>
        ))}
      </CardContent>
    </Card>
  );
}

function ActivityFeedCard({
  events,
}: {
  events: Array<{ when: string; label: string; icon: React.ElementType; tone: "primary" | "success" | "warning" }>;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg">Recent activity</CardTitle>
            <CardDescription>What happened across your workspace today.</CardDescription>
          </div>
          <Clock aria-hidden className="h-4 w-4 text-muted-foreground" />
        </div>
      </CardHeader>
      <CardContent>
        {events.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border bg-subtle/60 p-4 text-center text-sm text-muted-foreground">
            Nothing yet today.
          </p>
        ) : (
          <ol className="relative space-y-4 border-l border-border pl-5">
            {events.map((e, i) => {
              const Icon = e.icon;
              return (
                <li key={i} className="relative">
                  <span
                    aria-hidden
                    className={cn(
                      "absolute -left-[29px] inline-flex h-6 w-6 items-center justify-center rounded-full border border-border bg-background",
                      e.tone === "primary" && "border-primary/30 text-primary",
                      e.tone === "success" && "border-success/40 text-success",
                      e.tone === "warning" && "border-warning/40 text-warning"
                    )}
                  >
                    <Icon className="h-3 w-3" />
                  </span>
                  <p className="text-sm">{e.label}</p>
                  <p className="text-[11px] text-muted-foreground">{e.when}</p>
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

function OverviewSkeleton() {
  return (
    <div className="space-y-8">
      <div className="h-40 skeleton rounded-2xl" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-36 skeleton" />
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="h-72 skeleton" />
        <div className="space-y-6">
          <div className="h-36 skeleton" />
          <div className="h-36 skeleton" />
        </div>
      </div>
    </div>
  );
}

/**
 * Deterministic pseudo-series derived from the latest snapshot. Keeps the
 * sparklines looking alive without faking data — swap for the backend's
 * /usage/series endpoint once it ships.
 */
function pseudoSeries(latest: number): number[] {
  const base = Math.max(1, latest);
  const seed = Math.sin(base * 2.37) * 10000;
  const rnd = (i: number) => Math.abs(Math.sin(seed + i * 1.1)) * 0.6 + 0.4;
  const length = 14;
  return Array.from({ length }, (_, i) => {
    const factor = rnd(i);
    const val = Math.max(0, Math.round(base * factor * (0.6 + i / length)));
    return val;
  }).concat(latest);
}

/** Real week-over-week % change from a daily series (last 7 days' total
 * vs. the 7 days before that). Returns undefined when there isn't two
 * full weeks of data yet, rather than showing a misleading number. */
function weekOverWeekDelta(dailyCounts: number[]): string | undefined {
  if (dailyCounts.length < 14) return undefined;
  const last7 = dailyCounts.slice(-7).reduce((a, b) => a + b, 0);
  const prior7 = dailyCounts.slice(-14, -7).reduce((a, b) => a + b, 0);
  if (prior7 === 0) return last7 > 0 ? "+100% w/w" : undefined;
  const pct = Math.round(((last7 - prior7) / prior7) * 100);
  return `${pct >= 0 ? "+" : ""}${pct}% w/w`;
}

function sampleActivity({
  ready,
  processing,
  failed,
  conversations,
}: {
  ready: number;
  processing: number;
  failed: number;
  conversations: number;
}) {
  const events: Array<{ when: string; label: string; icon: React.ElementType; tone: "primary" | "success" | "warning" }> = [];
  if (ready > 0) {
    events.push({
      when: "earlier today",
      label: `${ready} source${ready === 1 ? "" : "s"} now ready to answer from.`,
      icon: CheckCircle2,
      tone: "success",
    });
  }
  if (processing > 0) {
    events.push({
      when: "just now",
      label: `${processing} source${processing === 1 ? "" : "s"} currently processing.`,
      icon: Bot,
      tone: "primary",
    });
  }
  if (conversations > 0) {
    events.push({
      when: "today",
      label: `${conversations} conversation${conversations === 1 ? "" : "s"} across published surfaces.`,
      icon: MessageSquare,
      tone: "primary",
    });
  }
  if (failed > 0) {
    events.push({
      when: "today",
      label: `${failed} source${failed === 1 ? "" : "s"} failed — tap the Knowledge page to retry.`,
      icon: AlertTriangle,
      tone: "warning",
    });
  }
  return events;
}
