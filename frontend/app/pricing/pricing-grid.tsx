"use client";
import * as React from "react";
import Link from "next/link";
import { Check, Minus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { cn } from "@/lib/utils";

type Plan = {
  id: string;
  name: string;
  interval: string;
  limits: Record<string, number | string | string[] | null>;
  features: Record<string, unknown>;
};

const MONTHLY_PLAN_ORDER = ["free", "starter_monthly", "growth_monthly", "scale_monthly", "agency_monthly"];

const PRICE_BY_PLAN: Record<string, string> = {
  free: "$0",
  starter_monthly: "$29",
  growth_monthly: "$99",
  scale_monthly: "$299",
  agency_monthly: "$699",
};

const BLURB_BY_PLAN: Record<string, string> = {
  free: "Try it out with a single source and a handful of conversations.",
  starter_monthly: "For a single site that needs a grounded assistant.",
  growth_monthly: "For growing teams with WhatsApp and SMS escalation.",
  scale_monthly: "For teams running several bots with API access.",
  agency_monthly: "For agencies managing many client workspaces.",
};

const HIGHLIGHT_PLAN = "growth_monthly";

export function PricingGrid() {
  const [plans, setPlans] = React.useState<Plan[] | null>(null);
  const [error, setError] = React.useState<unknown>(null);

  React.useEffect(() => {
    void (async () => {
      try {
        const resp = await apiFetch<Plan[]>("/api/bff/billing/plans");
        const ordered = MONTHLY_PLAN_ORDER
          .map((id) => resp.find((p) => p.id === id))
          .filter((p): p is Plan => Boolean(p));
        setPlans(ordered);
      } catch (e) {
        setError(e);
      }
    })();
  }, []);

  if (error) {
    const info = describeError(error);
    return (
      <Alert tone="danger" title={info.title}>
        {info.message}
      </Alert>
    );
  }

  if (!plans) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {MONTHLY_PLAN_ORDER.map((id) => (
          <div key={id} className="h-80 skeleton rounded-2xl" />
        ))}
      </div>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
      {plans.map((plan) => {
        const highlighted = plan.id === HIGHLIGHT_PLAN;
        const price = PRICE_BY_PLAN[plan.id] ?? "—";
        const channels = (plan.limits.channels ?? plan.features.channels) as string[] | undefined;
        return (
          <div
            key={plan.id}
            className={cn(
              "card-surface flex flex-col gap-4 p-6",
              highlighted && "border-primary ring-1 ring-primary/30",
            )}
          >
            <div>
              {highlighted && (
                <span className="mb-2 inline-flex rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
                  Most popular
                </span>
              )}
              <h3 className="font-display text-lg font-semibold">{plan.name.replace(" · Monthly", "")}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{BLURB_BY_PLAN[plan.id]}</p>
            </div>

            <p className="font-display text-3xl font-semibold">
              {price}
              {price !== "—" && <span className="text-sm font-normal text-muted-foreground">/mo</span>}
            </p>

            <ul className="flex-1 space-y-2 text-sm text-muted-foreground">
              <Row label={`${fmt(plan.limits.ai_replies_per_month)} AI replies / mo`} ok />
              <Row label={`${fmt(plan.limits.sources)} knowledge sources`} ok />
              <Row label={`${fmtMb(plan.limits.storage_mb)} storage`} ok />
              <Row label={`${fmt(plan.limits.bots)} bot${plan.limits.bots === 1 ? "" : "s"}`} ok />
              <Row label={`${fmt(plan.limits.members)} team member${plan.limits.members === 1 ? "" : "s"}`} ok />
              <Row label="WhatsApp + SMS escalation" ok={Boolean(plan.features.whatsapp)} />
              <Row label="Shopify + HubSpot + API" ok={Boolean(plan.features.api)} />
              <Row label={plan.features.sla_hours ? `${plan.features.sla_hours}h response SLA` : "No response SLA"} ok={Boolean(plan.features.sla_hours)} />
              {channels && <Row label={`Channels: ${channels.join(", ")}`} ok />}
            </ul>

            <Button asChild variant={highlighted ? "primary" : "secondary"} className="w-full">
              <Link href="/signup">{plan.id === "free" ? "Start free" : "Start free trial"}</Link>
            </Button>
          </div>
        );
      })}
    </div>
  );
}

function fmt(value: number | string | string[] | null | undefined): string {
  if (value === null || value === undefined) return "Unlimited";
  return String(value);
}

function fmtMb(value: number | string | string[] | null | undefined): string {
  if (value === null || value === undefined) return "Unlimited";
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return n >= 1000 ? `${(n / 1000).toFixed(n % 1000 === 0 ? 0 : 1)} GB` : `${n} MB`;
}

function Row({ label, ok }: { label: string; ok: boolean }) {
  return (
    <li className="flex items-start gap-2">
      {ok ? (
        <Check aria-hidden className="mt-0.5 h-4 w-4 flex-shrink-0 text-success" />
      ) : (
        <Minus aria-hidden className="mt-0.5 h-4 w-4 flex-shrink-0 text-muted-foreground/50" />
      )}
      <span className={ok ? "" : "text-muted-foreground/60"}>{label}</span>
    </li>
  );
}
