"use client";
import * as React from "react";
import { CreditCard, Check, ExternalLink, Loader2 } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

type Plan = {
  id: string;
  name: string;
  interval: string;
  limits: Record<string, number | string | null>;
  features: Record<string, unknown>;
};

type MyPlan = { plan_id?: string; subscription_status?: string } & Record<string, unknown>;

const MONTHLY_PLAN_ORDER = ["free", "starter_monthly", "growth_monthly", "scale_monthly", "agency_monthly"];

export default function BillingSettingsPage() {
  const { toast } = useToast();
  const [plans, setPlans] = React.useState<Plan[] | null>(null);
  const [myPlan, setMyPlan] = React.useState<MyPlan | null>(null);
  const [error, setError] = React.useState<unknown>(null);
  const [checkingOut, setCheckingOut] = React.useState<string | null>(null);
  const [openingPortal, setOpeningPortal] = React.useState(false);

  React.useEffect(() => {
    void (async () => {
      try {
        const [p, mp] = await Promise.all([
          apiFetch<Plan[]>("/api/bff/billing/plans"),
          apiFetch<MyPlan>("/api/bff/billing/me/plan"),
        ]);
        setPlans(p.filter((x) => MONTHLY_PLAN_ORDER.includes(x.id)));
        setMyPlan(mp);
      } catch (e) {
        setError(e);
      }
    })();
  }, []);

  async function checkout(planId: string) {
    setCheckingOut(planId);
    try {
      const { checkout_url } = await apiFetch<{ checkout_url: string }>("/api/bff/billing/checkout", {
        method: "POST",
        json: { price_lookup_key: planId },
      });
      window.location.href = checkout_url;
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
      setCheckingOut(null);
    }
  }

  async function openPortal() {
    setOpeningPortal(true);
    try {
      const { portal_url } = await apiFetch<{ portal_url: string }>("/api/bff/billing/portal", { method: "POST" });
      window.location.href = portal_url;
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    } finally {
      setOpeningPortal(false);
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

  const currentPlanId = myPlan?.plan_id ?? "free";

  return (
    <div className="max-w-4xl space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Current plan</CardTitle>
              <CardDescription>
                {myPlan ? `You're on the ${currentPlanId.replace("_monthly", "")} plan.` : "Loading…"}
              </CardDescription>
            </div>
            {currentPlanId !== "free" && (
              <Button variant="secondary" onClick={openPortal} loading={openingPortal}>
                <ExternalLink className="h-4 w-4" /> Manage billing
              </Button>
            )}
          </div>
        </CardHeader>
      </Card>

      {plans === null ? (
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="h-64 skeleton" />
          <div className="h-64 skeleton" />
          <div className="h-64 skeleton" />
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-3">
          {plans.map((plan) => {
            const isCurrent = plan.id === currentPlanId;
            const price = PRICE_BY_PLAN[plan.id];
            return (
              <Card key={plan.id} className={cn(isCurrent && "border-primary ring-1 ring-primary/30")}>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">{plan.name.replace(" · Monthly", "")}</CardTitle>
                    {isCurrent && <Badge tone="primary">Current</Badge>}
                  </div>
                  <p className="font-display text-2xl font-semibold">
                    {price ?? "—"}
                    {price && <span className="text-sm font-normal text-muted-foreground">/mo</span>}
                  </p>
                </CardHeader>
                <CardContent className="space-y-3">
                  <ul className="space-y-1.5 text-sm text-muted-foreground">
                    <PlanLimit label="AI replies / mo" value={plan.limits.ai_replies_per_month} />
                    <PlanLimit label="Sources" value={plan.limits.sources} />
                    <PlanLimit label="Storage" value={plan.limits.storage_mb ? `${plan.limits.storage_mb} MB` : null} />
                    <PlanLimit label="Team members" value={plan.limits.members} />
                  </ul>
                  <Button
                    variant={isCurrent ? "secondary" : "primary"}
                    className="w-full"
                    disabled={isCurrent}
                    loading={checkingOut === plan.id}
                    onClick={() => void checkout(plan.id)}
                  >
                    {isCurrent ? <Check className="h-4 w-4" /> : <CreditCard className="h-4 w-4" />}
                    {isCurrent ? "Current plan" : "Upgrade"}
                  </Button>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

const PRICE_BY_PLAN: Record<string, string> = {
  free: "$0",
  starter_monthly: "$29",
  growth_monthly: "$99",
  scale_monthly: "$299",
  agency_monthly: "$699",
};

function PlanLimit({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined) return null;
  return (
    <li className="flex items-center gap-1.5">
      <Check className="h-3.5 w-3.5 text-success" /> {value === "unlimited" ? "Unlimited" : String(value)} {label}
    </li>
  );
}
