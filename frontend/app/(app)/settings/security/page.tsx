"use client";
import * as React from "react";
import { ShieldCheck, ShieldOff, Copy, Check, KeyRound, AlertTriangle, Loader2 } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/field";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { useToast } from "@/components/ui/toast";

type MfaStatus = { enabled: boolean };
type SetupResponse = { secret: string; provisioning_uri: string };
type ConfirmResponse = { enabled: boolean; recovery_codes: string[] };

/**
 * No QR image is rendered here: a QR-image web service would need the
 * raw otpauth:// URI (which carries the TOTP secret) sent to a third
 * party, which is exactly the kind of secret exposure MFA exists to
 * prevent. Manual entry of the secret is universally supported by
 * authenticator apps (Google Authenticator, Authy, 1Password, etc.) and
 * keeps the secret from ever leaving this page.
 */
export default function SecuritySettingsPage() {
  const { toast } = useToast();
  const [status, setStatus] = React.useState<MfaStatus | null>(null);
  const [loadError, setLoadError] = React.useState<unknown>(null);
  const [setup, setSetup] = React.useState<SetupResponse | null>(null);
  const [code, setCode] = React.useState("");
  const [confirming, setConfirming] = React.useState(false);
  const [confirmError, setConfirmError] = React.useState<unknown>(null);
  const [recoveryCodes, setRecoveryCodes] = React.useState<string[] | null>(null);
  const [copied, setCopied] = React.useState(false);
  const [busy, setBusy] = React.useState(false);

  const load = React.useCallback(async () => {
    try {
      const data = await apiFetch<MfaStatus>("/api/bff/mfa/status");
      setStatus(data);
    } catch (e) {
      setLoadError(e);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  async function startSetup() {
    setBusy(true);
    try {
      const data = await apiFetch<SetupResponse>("/api/bff/mfa/setup", { method: "POST" });
      setSetup(data);
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    } finally {
      setBusy(false);
    }
  }

  async function confirmSetup(e: React.FormEvent) {
    e.preventDefault();
    setConfirming(true);
    setConfirmError(null);
    try {
      const data = await apiFetch<ConfirmResponse>("/api/bff/mfa/confirm", {
        method: "POST",
        json: { code },
      });
      setRecoveryCodes(data.recovery_codes);
      setSetup(null);
      setCode("");
      await load();
    } catch (e) {
      setConfirmError(e);
    } finally {
      setConfirming(false);
    }
  }

  async function disable() {
    if (!window.confirm("Turn off two-factor authentication? You'll be able to sign in with just your password.")) return;
    setBusy(true);
    try {
      await apiFetch("/api/bff/mfa/disable", { method: "POST" });
      toast({ tone: "success", title: "Two-factor authentication turned off" });
      setRecoveryCodes(null);
      await load();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    } finally {
      setBusy(false);
    }
  }

  function copySecret() {
    if (!setup) return;
    void navigator.clipboard.writeText(setup.secret);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  if (loadError) {
    const info = describeError(loadError);
    return (
      <Alert tone="danger" title={info.title}>
        {info.message}
      </Alert>
    );
  }

  if (!status) return <div className="h-64 skeleton" />;

  return (
    <div className="max-w-2xl space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                Two-factor authentication
                {status.enabled && <Badge tone="success">Enabled</Badge>}
              </CardTitle>
              <CardDescription>
                Require a 6-digit code from an authenticator app in addition to your password.
              </CardDescription>
            </div>
            {status.enabled ? (
              <ShieldCheck className="h-6 w-6 text-success" aria-hidden />
            ) : (
              <ShieldOff className="h-6 w-6 text-muted-foreground" aria-hidden />
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {recoveryCodes ? (
            <RecoveryCodesPanel codes={recoveryCodes} onDone={() => setRecoveryCodes(null)} />
          ) : status.enabled ? (
            <Button variant="destructive" onClick={disable} loading={busy}>
              Turn off two-factor authentication
            </Button>
          ) : setup ? (
            <form onSubmit={confirmSetup} className="space-y-4">
              <div className="rounded-lg border border-border bg-subtle/60 p-4">
                <p className="mb-2 text-sm font-medium">1. Add this key to your authenticator app</p>
                <p className="mb-3 text-xs text-muted-foreground">
                  Open Google Authenticator, Authy, 1Password or similar, and choose "Enter a setup key manually."
                </p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 rounded-md border border-border bg-card px-3 py-2 text-sm tracking-wider">
                    {setup.secret}
                  </code>
                  <Button type="button" variant="secondary" size="icon" onClick={copySecret} aria-label="Copy setup key">
                    {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </div>
              </div>
              <div>
                <p className="mb-2 text-sm font-medium">2. Enter the 6-digit code it shows</p>
                {confirmError != null && (
                  <Alert tone="danger" title={describeError(confirmError).title} className="mb-2">
                    {describeError(confirmError).message}
                  </Alert>
                )}
                <Field label="Authenticator code">
                  {(fieldProps) => (
                    <Input
                      {...fieldProps}
                      value={code}
                      onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                      placeholder="123456"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      className="font-mono tracking-widest"
                    />
                  )}
                </Field>
              </div>
              <div className="flex gap-2">
                <Button type="submit" loading={confirming} disabled={code.length !== 6}>
                  Confirm and enable
                </Button>
                <Button type="button" variant="ghost" onClick={() => setSetup(null)}>
                  Cancel
                </Button>
              </div>
            </form>
          ) : (
            <Button onClick={startSetup} loading={busy}>
              <KeyRound className="h-4 w-4" /> Set up two-factor authentication
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function RecoveryCodesPanel({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const [saved, setSaved] = React.useState(false);
  return (
    <div className="space-y-3">
      <Alert tone="warning" title="Save your recovery codes" icon={AlertTriangle}>
        Each code can be used once to sign in if you lose access to your authenticator app. They won&apos;t be shown again.
      </Alert>
      <div className="grid grid-cols-2 gap-2 rounded-lg border border-border bg-subtle/60 p-4 font-mono text-sm">
        {codes.map((c) => (
          <span key={c}>{c}</span>
        ))}
      </div>
      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} className="h-4 w-4 rounded border-border" />
        I&apos;ve saved these codes somewhere safe.
      </label>
      <Button disabled={!saved} onClick={onDone}>
        Done
      </Button>
    </div>
  );
}
