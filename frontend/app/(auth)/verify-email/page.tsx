"use client";
import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2, MailCheck, RefreshCw } from "lucide-react";

import { AuthShell } from "@/components/auth/auth-shell";
import { FormErrorAlert } from "@/components/auth/form-errors";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { useToast } from "@/components/ui/toast";

/**
 * Verify-email has two modes:
 *   1. A `?token=` in the URL: consume it immediately. A single-use token
 *      can't be auto-retried, so on failure we explain why.
 *   2. No token: show a "waiting for email" state with a resend button. The
 *      resend endpoint is rate-limited by the backend; we honour that with
 *      a visible cooldown.
 */
const RESEND_COOLDOWN_SECONDS = 60;

type State =
  | { kind: "idle" }
  | { kind: "verifying" }
  | { kind: "verified" }
  | { kind: "error"; error: unknown };

export default function VerifyEmailPage() {
  return (
    <React.Suspense fallback={null}>
      <VerifyEmailPageInner />
    </React.Suspense>
  );
}

function VerifyEmailPageInner() {
  const search = useSearchParams();
  const router = useRouter();
  const { toast } = useToast();

  const tokenFromUrl = search.get("token");
  const emailFromUrl = search.get("email") ?? "";

  const [state, setState] = React.useState<State>(tokenFromUrl ? { kind: "verifying" } : { kind: "idle" });
  const [email, setEmail] = React.useState(emailFromUrl);
  const [cooldown, setCooldown] = React.useState(0);
  const attempted = React.useRef(false);

  React.useEffect(() => {
    if (!tokenFromUrl || attempted.current) return;
    attempted.current = true;
    void (async () => {
      try {
        await apiFetch("/api/bff/auth/verify-email", {
          method: "POST",
          json: { token: tokenFromUrl },
        });
        setState({ kind: "verified" });
      } catch (error) {
        setState({ kind: "error", error });
      }
    })();
  }, [tokenFromUrl]);

  React.useEffect(() => {
    if (cooldown <= 0) return;
    const id = window.setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => window.clearTimeout(id);
  }, [cooldown]);

  const [resending, setResending] = React.useState(false);
  async function resend() {
    if (cooldown > 0 || resending) return;
    if (!email) {
      toast({ tone: "warning", title: "Enter your email first" });
      return;
    }
    setResending(true);
    try {
      await apiFetch("/api/bff/auth/resend-verification", { method: "POST", json: { email } });
      toast({ tone: "success", title: "Verification resent", description: `Check ${email} for the link.` });
      setCooldown(RESEND_COOLDOWN_SECONDS);
    } catch (error) {
      const info = describeError(error);
      toast({ tone: "danger", title: info.title, description: info.message });
    } finally {
      setResending(false);
    }
  }

  if (state.kind === "verifying") {
    return (
      <AuthShell title="Verifying your email…" description="This only takes a moment.">
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <RefreshCw className="h-4 w-4 animate-spin" aria-hidden />
          <span>Confirming your verification link.</span>
        </div>
      </AuthShell>
    );
  }

  if (state.kind === "verified") {
    return (
      <AuthShell
        title="Email verified"
        description="Your account is ready. Sign in to start adding sources."
      >
        <Alert tone="success" icon={CheckCircle2} title="All set">
          Your email has been verified. You can sign in now.
        </Alert>
        <div className="mt-6">
          <Button block onClick={() => router.push("/login")}>
            Continue to sign in
          </Button>
        </div>
      </AuthShell>
    );
  }

  if (state.kind === "error") {
    return (
      <AuthShell
        title="This link didn't work"
        description="Verification links expire after an hour or can only be used once."
        footer={
          <>
            Already verified?{" "}
            <Link href="/login" className="link-subtle">
              Sign in instead
            </Link>
          </>
        }
      >
        <FormErrorAlert error={state.error} />
        <div className="mt-6 space-y-3">
          <Field label="Email to resend to" required>
            {(a11y) => (
              <Input
                {...a11y}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                type="email"
                inputMode="email"
                autoComplete="email"
                placeholder="you@company.com"
              />
            )}
          </Field>
          <Button
            block
            onClick={resend}
            loading={resending}
            disabled={cooldown > 0 || !email}
          >
            {cooldown > 0 ? `Resend in ${cooldown}s` : "Send me a new link"}
          </Button>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Check your email"
      description="We'll send a verification link so we know it's you."
      footer={
        <>
          Entered the wrong address?{" "}
          <Link href="/signup" className="link-subtle">
            Start sign-up again
          </Link>
        </>
      }
    >
      <Alert tone="info" icon={MailCheck} title="Waiting for your click">
        Open the verification link on this device to finish setting up your account.
      </Alert>
      <div className="mt-6 space-y-3">
        <Field label="Your email" required>
          {(a11y) => (
            <Input
              {...a11y}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
              inputMode="email"
              autoComplete="email"
              placeholder="you@company.com"
            />
          )}
        </Field>
        <Button
          block
          variant="secondary"
          onClick={resend}
          loading={resending}
          disabled={cooldown > 0 || !email}
        >
          {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend verification email"}
        </Button>
      </div>
    </AuthShell>
  );
}
