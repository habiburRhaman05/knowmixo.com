"use client";
import * as React from "react";
import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, Building2, Loader2 } from "lucide-react";

import { AuthShell } from "@/components/auth/auth-shell";
import { FormErrorAlert } from "@/components/auth/form-errors";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { PasswordStrength } from "@/components/ui/password-strength";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { apiFetch } from "@/lib/api-client";

type Preview = { email: string; role: string; company_name: string };

export default function AcceptInvitePage() {
  return (
    <Suspense
      fallback={
        <AuthShell title="Loading invite…" description="One moment.">
          <div className="flex items-center justify-center p-10">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        </AuthShell>
      }
    >
      <AcceptInviteForm />
    </Suspense>
  );
}

function AcceptInviteForm() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [preview, setPreview] = React.useState<Preview | null>(null);
  const [previewError, setPreviewError] = React.useState<unknown>(null);
  const [name, setName] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [serverError, setServerError] = React.useState<unknown>(null);

  React.useEffect(() => {
    if (!token) {
      setPreviewError(new Error("missing_token"));
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const data = await apiFetch<Preview>(`/api/bff/team/invites/${encodeURIComponent(token)}`);
        if (!cancelled) setPreview(data);
      } catch (e) {
        if (!cancelled) setPreviewError(e);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setServerError(null);
    try {
      await apiFetch("/api/bff/team/invites/accept", {
        method: "POST",
        json: { token, name, password },
      });
      router.replace("/overview");
    } catch (e) {
      setServerError(e);
    } finally {
      setSubmitting(false);
    }
  }

  if (previewError) {
    return (
      <AuthShell title="Invite not found" description="This invite link is invalid.">
        <Alert tone="danger" title="This invite link has expired or was already used">
          Ask whoever invited you to send a new one.
        </Alert>
      </AuthShell>
    );
  }

  if (!preview) {
    return (
      <AuthShell title="Loading invite…" description="One moment.">
        <div className="flex items-center justify-center p-10">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title={`Join ${preview.company_name}`}
      description={`You've been invited as ${preview.role} — set a name and password to finish joining.`}
    >
      <div className="mb-4 flex items-center gap-2 rounded-lg border border-border bg-subtle/60 p-3 text-sm">
        <Building2 className="h-4 w-4 text-muted-foreground" />
        <span>
          <strong>{preview.email}</strong> is invited to <strong>{preview.company_name}</strong> as a{" "}
          <strong>{preview.role}</strong>.
        </span>
      </div>
      <form onSubmit={onSubmit} className="space-y-4">
        {serverError != null && <FormErrorAlert error={serverError} />}
        <Field label="Your name">
          {(fieldProps) => (
            <Input {...fieldProps} value={name} onChange={(e) => setName(e.target.value)} placeholder="Jane Doe" required />
          )}
        </Field>
        <div>
          <Field label="Choose a password">
            {(fieldProps) => (
              <PasswordInput
                {...fieldProps}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                required
                minLength={8}
              />
            )}
          </Field>
          <PasswordStrength value={password} className="mt-2" />
        </div>
        <Button type="submit" loading={submitting} className="w-full">
          Join {preview.company_name} <ArrowRight className="h-4 w-4" />
        </Button>
      </form>
    </AuthShell>
  );
}
