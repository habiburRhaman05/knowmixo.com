"use client";
import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2 } from "lucide-react";

import { AuthShell } from "@/components/auth/auth-shell";
import { FormErrorAlert } from "@/components/auth/form-errors";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { PasswordInput } from "@/components/ui/password-input";
import { PasswordStrength } from "@/components/ui/password-strength";
import { apiFetch } from "@/lib/api-client";
import { resetSchema, type ResetInput } from "@/lib/auth-schemas";

export default function ResetPasswordPage() {
  return (
    <React.Suspense fallback={null}>
      <ResetPasswordPageInner />
    </React.Suspense>
  );
}

function ResetPasswordPageInner() {
  const router = useRouter();
  const search = useSearchParams();
  const token = search.get("token") ?? "";

  const [serverError, setServerError] = React.useState<unknown>(null);
  const [done, setDone] = React.useState(false);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<ResetInput>({
    resolver: zodResolver(resetSchema),
    defaultValues: { token, new_password: "", confirm_password: "" },
  });

  const password = watch("new_password");

  async function onSubmit(values: ResetInput) {
    setServerError(null);
    try {
      await apiFetch("/api/bff/auth/reset-password", {
        method: "POST",
        json: { token: values.token, new_password: values.new_password },
      });
      setDone(true);
    } catch (error) {
      setServerError(error);
    }
  }

  if (!token) {
    return (
      <AuthShell
        title="Reset link missing"
        description="This page needs a reset token from the email we sent you."
        footer={
          <Link href="/forgot-password" className="link-subtle">
            Request a new reset link
          </Link>
        }
      >
        <Alert tone="warning" title="No token found">
          Open the exact link from the email we sent, or request a new one.
        </Alert>
      </AuthShell>
    );
  }

  if (done) {
    return (
      <AuthShell title="Password reset" description="You can sign in with your new password.">
        <Alert tone="success" icon={CheckCircle2} title="All set">
          For security, we&apos;ve signed out every other session on your account.
        </Alert>
        <div className="mt-6">
          <Button block onClick={() => router.push("/login")}>
            Continue to sign in
          </Button>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Choose a new password"
      description="Pick something you'll remember but attackers won't guess."
      footer={
        <Link href="/login" className="link-subtle">
          Back to sign in
        </Link>
      }
    >
      <form noValidate onSubmit={handleSubmit(onSubmit)} className="space-y-5">
        <FormErrorAlert error={serverError} />
        <input type="hidden" {...register("token")} />
        <Field label="New password" error={errors.new_password?.message} required>
          {(a11y) => (
            <PasswordInput
              {...a11y}
              {...register("new_password")}
              autoComplete="new-password"
              placeholder="At least 10 characters"
              invalid={Boolean(errors.new_password)}
              autoFocus
            />
          )}
        </Field>
        <PasswordStrength value={password ?? ""} />
        <Field label="Confirm new password" error={errors.confirm_password?.message} required>
          {(a11y) => (
            <PasswordInput
              {...a11y}
              {...register("confirm_password")}
              autoComplete="new-password"
              placeholder="Type the password again"
              invalid={Boolean(errors.confirm_password)}
            />
          )}
        </Field>
        <Button type="submit" block loading={isSubmitting}>
          {isSubmitting ? "Updating password" : "Update password"}
        </Button>
      </form>
    </AuthShell>
  );
}
