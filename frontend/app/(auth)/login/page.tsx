"use client";
import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowRight } from "lucide-react";

import { AuthShell } from "@/components/auth/auth-shell";
import { FormErrorAlert } from "@/components/auth/form-errors";
import { GoogleSignIn } from "@/components/auth/google-sign-in";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { apiFetch } from "@/lib/api-client";
import { loginSchema, type LoginInput } from "@/lib/auth-schemas";

export default function LoginPage() {
  // useSearchParams needs a Suspense boundary for static rendering (Next.js
  // 15) -- the inner component below is the actual page body.
  return (
    <React.Suspense fallback={null}>
      <LoginPageInner />
    </React.Suspense>
  );
}

function LoginPageInner() {
  const router = useRouter();
  const search = useSearchParams();
  const nextPath = sanitizeNext(search.get("next"));
  const deleted = search.get("deleted") === "1";

  const [serverError, setServerError] = React.useState<unknown>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  async function onSubmit(values: LoginInput) {
    setServerError(null);
    try {
      await apiFetch("/api/bff/auth/login", { method: "POST", json: values });
      router.replace(nextPath);
      router.refresh();
    } catch (error) {
      setServerError(error);
    }
  }

  return (
    <AuthShell
      title="Welcome back"
      description="Sign in to manage your assistant, sources and conversations."
      footer={
        <>
          New to Knowmivo?{" "}
          <Link href="/signup" className="link-subtle">
            Create an account
          </Link>
        </>
      }
    >
      {deleted && (
        <div className="mb-5 rounded-lg border border-success/30 bg-success/10 p-3 text-sm text-success">
          Your account has been deleted. Thanks for giving Knowmivo a try.
        </div>
      )}
      <div className="space-y-4">
        <GoogleSignIn nextPath={nextPath} />
        <div className="relative">
          <Separator />
          <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-background px-2 text-xs uppercase tracking-wide text-muted-foreground">
            or
          </span>
        </div>
      </div>

      <form noValidate onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-5">
        <FormErrorAlert error={serverError} />
        <Field label="Email" error={errors.email?.message} required>
          {(a11y) => (
            <Input
              {...a11y}
              {...register("email")}
              type="email"
              inputMode="email"
              autoComplete="email"
              autoFocus
              placeholder="you@company.com"
              invalid={Boolean(errors.email)}
            />
          )}
        </Field>
        <Field
          label="Password"
          error={errors.password?.message}
          required
          hint={
            <span>
              Forgot it?{" "}
              <Link href="/forgot-password" className="link-subtle">
                Reset your password
              </Link>
            </span>
          }
        >
          {(a11y) => (
            <PasswordInput
              {...a11y}
              {...register("password")}
              autoComplete="current-password"
              placeholder="Enter your password"
              invalid={Boolean(errors.password)}
            />
          )}
        </Field>
        <Button type="submit" block loading={isSubmitting}>
          {isSubmitting ? "Signing in" : "Sign in"}
          {!isSubmitting && <ArrowRight className="h-4 w-4" />}
        </Button>
      </form>
    </AuthShell>
  );
}

function sanitizeNext(value: string | null): string {
  if (!value) return "/overview";
  // Only allow same-site pathnames, not full URLs; this stops open-redirects
  // via the ?next= param.
  if (!value.startsWith("/") || value.startsWith("//")) return "/overview";
  return value;
}
