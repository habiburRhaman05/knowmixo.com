"use client";
import * as React from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowRight, MailCheck } from "lucide-react";

import { AuthShell } from "@/components/auth/auth-shell";
import { FormErrorAlert } from "@/components/auth/form-errors";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api-client";
import { forgotSchema, type ForgotInput } from "@/lib/auth-schemas";

export default function ForgotPasswordPage() {
  const [serverError, setServerError] = React.useState<unknown>(null);
  const [sent, setSent] = React.useState<{ email: string } | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForgotInput>({
    resolver: zodResolver(forgotSchema),
    defaultValues: { email: "" },
  });

  async function onSubmit(values: ForgotInput) {
    setServerError(null);
    try {
      await apiFetch("/api/bff/auth/forgot-password", { method: "POST", json: values });
      setSent({ email: values.email });
    } catch (error) {
      setServerError(error);
    }
  }

  if (sent) {
    return (
      <AuthShell
        title="Check your email"
        description="If an account exists for that address, a reset link is on its way."
        footer={
          <Link href="/login" className="link-subtle">
            Back to sign in
          </Link>
        }
      >
        <Alert tone="success" icon={MailCheck} title="Reset link sent">
          <p>
            We&apos;ve sent a password reset link to{" "}
            <strong className="text-foreground">{sent.email}</strong>. The link expires in an hour.
          </p>
        </Alert>
        <p className="mt-4 text-xs text-muted-foreground">
          We always show this screen whether or not the email is registered. If you don&apos;t see the
          email, check spam or request another in a minute.
        </p>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Reset your password"
      description="Enter your email and we'll send a reset link."
      footer={
        <>
          Remembered it?{" "}
          <Link href="/login" className="link-subtle">
            Back to sign in
          </Link>
        </>
      }
    >
      <form noValidate onSubmit={handleSubmit(onSubmit)} className="space-y-5">
        <FormErrorAlert error={serverError} />
        <Field label="Email" error={errors.email?.message} required>
          {(a11y) => (
            <Input
              {...a11y}
              {...register("email")}
              type="email"
              inputMode="email"
              autoComplete="email"
              placeholder="you@company.com"
              invalid={Boolean(errors.email)}
              autoFocus
            />
          )}
        </Field>
        <Button type="submit" block loading={isSubmitting}>
          {isSubmitting ? "Sending link" : "Send reset link"}
          {!isSubmitting && <ArrowRight className="h-4 w-4" />}
        </Button>
      </form>
    </AuthShell>
  );
}
