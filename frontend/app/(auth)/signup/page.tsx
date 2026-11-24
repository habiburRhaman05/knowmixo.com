"use client";
import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowRight, MailCheck } from "lucide-react";

import { AuthShell } from "@/components/auth/auth-shell";
import { FormErrorAlert } from "@/components/auth/form-errors";
import { GoogleSignIn } from "@/components/auth/google-sign-in";
import { Alert } from "@/components/ui/alert";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { PasswordStrength } from "@/components/ui/password-strength";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { apiFetch } from "@/lib/api-client";
import { signupSchema, type SignupInput } from "@/lib/auth-schemas";

export default function SignupPage() {
  const router = useRouter();
  const [serverError, setServerError] = React.useState<unknown>(null);
  const [submitted, setSubmitted] = React.useState<{ email: string } | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<SignupInput>({
    resolver: zodResolver(signupSchema),
    defaultValues: { email: "", password: "", name: "" },
  });

  const password = watch("password");

  async function onSubmit(values: SignupInput) {
    setServerError(null);
    try {
      await apiFetch("/api/bff/auth/signup", { method: "POST", json: values });
      setSubmitted({ email: values.email });
    } catch (error) {
      setServerError(error);
    }
  }

  if (submitted) {
    return (
      <AuthShell
        title="Check your email"
        description="We've sent a verification link so we know it's you."
        footer={
          <>
            Didn&apos;t see it?{" "}
            <Link href={`/verify-email?email=${encodeURIComponent(submitted.email)}`} className="link-subtle">
              Resend the verification
            </Link>
          </>
        }
      >
        <Alert tone="success" icon={MailCheck} title="Verification sent">
          <p>
            A verification link is on its way to{" "}
            <strong className="text-foreground">{submitted.email}</strong>. Open it on this device to
            finish setting up your account.
          </p>
        </Alert>
        <div className="mt-6 space-y-3">
          <Button
            type="button"
            variant="secondary"
            block
            onClick={() => router.push(`/verify-email?email=${encodeURIComponent(submitted.email)}`)}
          >
            Go to verification page
          </Button>
          <p className="text-center text-xs text-muted-foreground">
            The link expires in 1 hour. You can request a new one from the verification page.
          </p>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Create your account"
      description="Takes under a minute. You can start adding sources right away."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="link-subtle">
            Sign in
          </Link>
        </>
      }
    >
      <div className="space-y-4">
        <GoogleSignIn label="Sign up with Google" />
        <div className="relative">
          <Separator />
          <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-background px-2 text-xs uppercase tracking-wide text-muted-foreground">
            or with email
          </span>
        </div>
      </div>

      <form noValidate onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-5">
        <FormErrorAlert error={serverError} />

        <Field label="Your name" error={errors.name?.message} required>
          {(a11y) => (
            <Input
              {...a11y}
              {...register("name")}
              autoComplete="name"
              placeholder="Alex Rivera"
              invalid={Boolean(errors.name)}
              autoFocus
            />
          )}
        </Field>

        <Field label="Work email" error={errors.email?.message} required>
          {(a11y) => (
            <Input
              {...a11y}
              {...register("email")}
              type="email"
              inputMode="email"
              autoComplete="email"
              placeholder="you@company.com"
              invalid={Boolean(errors.email)}
            />
          )}
        </Field>

        <Field label="Password" error={errors.password?.message} required>
          {(a11y) => (
            <PasswordInput
              {...a11y}
              {...register("password")}
              autoComplete="new-password"
              placeholder="At least 10 characters"
              invalid={Boolean(errors.password)}
            />
          )}
        </Field>
        <PasswordStrength value={password ?? ""} />

        <Button type="submit" block loading={isSubmitting} size="lg">
          {isSubmitting ? "Creating account" : "Create account"}
          {!isSubmitting && <ArrowRight className="h-4 w-4" />}
        </Button>

        <p className="text-center text-xs text-muted-foreground">
          By continuing you agree to Knowmivo&apos;s{" "}
          <Link href="/terms" className="link-subtle">
            Terms
          </Link>{" "}
          and{" "}
          <Link href="/privacy" className="link-subtle">
            Privacy Policy
          </Link>
          .
        </p>
      </form>
    </AuthShell>
  );
}
