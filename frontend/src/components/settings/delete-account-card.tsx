"use client";
import * as React from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ShieldAlert } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { useToast } from "@/components/ui/toast";
import { FormErrorAlert } from "@/components/auth/form-errors";

const CONFIRM_PHRASE = "delete my account";

export function DeleteAccountCard({ email }: { email: string }) {
  const router = useRouter();
  const { toast } = useToast();
  const [open, setOpen] = React.useState(false);
  const [password, setPassword] = React.useState("");
  const [phrase, setPhrase] = React.useState("");
  const [serverError, setServerError] = React.useState<unknown>(null);
  const [busy, setBusy] = React.useState(false);
  const [done, setDone] = React.useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (phrase.trim().toLowerCase() !== CONFIRM_PHRASE) {
      setServerError(new Error(`Type "${CONFIRM_PHRASE}" exactly to confirm.`));
      return;
    }
    setBusy(true);
    setServerError(null);
    try {
      await apiFetch("/api/bff/me/delete", {
        method: "POST",
        json: { confirm: true, current_password: password },
      });
      setDone(true);
      toast({ tone: "success", title: "Account deletion queued" });
      // Give the toast a beat, then bounce to the goodbye page.
      setTimeout(() => {
        router.replace("/login?deleted=1");
        router.refresh();
      }, 1200);
    } catch (e) {
      setServerError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Card className="border-destructive/30">
        <CardHeader>
          <div className="flex items-center gap-2">
            <ShieldAlert aria-hidden className="h-4 w-4 text-destructive" />
            <CardTitle className="text-lg text-destructive">Delete account</CardTitle>
          </div>
          <CardDescription>
            Removes your data permanently. Vectors, sources, publications and conversations are purged
            by a tracked cleanup job.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <ul className="space-y-1.5 text-sm text-muted-foreground">
            <li>• All current sessions are revoked immediately.</li>
            <li>• Your assistant is unpublished and the hosted link stops working.</li>
            <li>• A cleanup job removes vectors and tenant data within minutes.</li>
          </ul>
          <Badge tone="danger">Irreversible</Badge>
          <div>
            <Button variant="destructive" onClick={() => setOpen(true)}>
              Delete {email}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Dialog
        open={open}
        onOpenChange={(v) => {
          if (busy) return;
          setOpen(v);
          if (!v) {
            setPassword("");
            setPhrase("");
            setServerError(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete your account?</DialogTitle>
            <DialogDescription>
              This cannot be undone. Your sources, bot, published snapshots and conversation history
              will be permanently removed.
            </DialogDescription>
          </DialogHeader>
          {done ? (
            <Alert tone="success" title="Account deletion in progress">
              You&apos;ll be signed out now. The cleanup job finishes in the background.
            </Alert>
          ) : (
            <form onSubmit={submit} noValidate className="space-y-4">
              <FormErrorAlert error={serverError} />
              <Field label="Current password" required>
                {(a11y) => (
                  <PasswordInput
                    {...a11y}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="current-password"
                    placeholder="Confirm it's really you"
                  />
                )}
              </Field>
              <Field
                label={`Type "${CONFIRM_PHRASE}" to confirm`}
                required
                hint="Exactly as written, case-insensitive."
              >
                {(a11y) => (
                  <Input
                    {...a11y}
                    value={phrase}
                    onChange={(e) => setPhrase(e.target.value)}
                    placeholder={CONFIRM_PHRASE}
                    autoComplete="off"
                  />
                )}
              </Field>
              <Alert tone="warning" icon={AlertTriangle} title="Last chance">
                We don&apos;t keep backups of deleted accounts. Export your data first if you want a
                copy — the <strong>Export company data</strong> button at the top of Settings has
                everything we hold about you.
              </Alert>
              <DialogFooter>
                <Button type="button" variant="ghost" onClick={() => setOpen(false)} disabled={busy}>
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="destructive"
                  disabled={!password || phrase.trim().toLowerCase() !== CONFIRM_PHRASE}
                  loading={busy}
                >
                  Permanently delete my account
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
