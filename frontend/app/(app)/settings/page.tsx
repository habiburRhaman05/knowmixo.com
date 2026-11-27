"use client";
import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { User, Building2, KeyRound, ShieldCheck, LogOut, Save, Loader2 } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { PasswordStrength } from "@/components/ui/password-strength";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { GoogleSignIn } from "@/components/auth/google-sign-in";
import { DeleteAccountCard } from "@/components/settings/delete-account-card";
import { apiFetch } from "@/lib/api-client";
import { changePasswordSchema, nameSchema } from "@/lib/auth-schemas";
import { useToast } from "@/components/ui/toast";
import { describeError } from "@/lib/errors";
import { useCompany, useSetCompanyData } from "@/lib/hooks/use-company";
import { z } from "zod";
import { FormErrorAlert } from "@/components/auth/form-errors";
import type { CompanyResponse } from "@/lib/types";

type MeResponse = {
  id: string;
  email: string;
  name: string | null;
  avatar_key: string | null;
  email_verified_at: string | null;
};

const profileSchema = z.object({ name: nameSchema });
type ProfileInput = z.infer<typeof profileSchema>;

const companySchema = z.object({
  name: z.string().trim().min(1, "Company name is required.").max(200),
  website: z.string().trim().max(2000).optional().or(z.literal("")),
  industry: z.string().trim().max(120).optional().or(z.literal("")),
  contact: z.string().trim().max(200).optional().or(z.literal("")),
});
type CompanyInput = z.infer<typeof companySchema>;

type ChangePasswordInput = z.infer<typeof changePasswordSchema>;

export default function SettingsPage() {
  const router = useRouter();
  const { toast } = useToast();
  const [me, setMe] = React.useState<MeResponse | null>(null);
  const [loadError, setLoadError] = React.useState<unknown>(null);
  const companyQuery = useCompany();
  const setCompanyData = useSetCompanyData();
  const company = companyQuery.data ?? null;

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const m = await apiFetch<MeResponse>("/api/bff/me");
        if (!cancelled) setMe(m);
      } catch (e) {
        if (!cancelled) setLoadError(e);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function signOutAll() {
    try {
      await apiFetch("/api/bff/auth/logout-all", { method: "POST" });
      router.replace("/login");
      router.refresh();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    }
  }

  return (
    <>
      {loadError ? (() => {
        const info = describeError(loadError);
        return (
          <Alert tone="danger" title={info.title}>
            {info.message}
          </Alert>
        );
      })() : null}
      {!loadError && !me && <div className="h-80 skeleton" />}
      {me && (
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <div className="space-y-6">
            <ProfileCard me={me} onSaved={setMe} />
            <CompanyCard company={company} onSaved={setCompanyData} />
            <ChangePasswordCard />
          </div>
          <aside className="space-y-6">
            <SecurityCard me={me} onSignOutAll={signOutAll} />
            <DeleteAccountCard email={me.email} />
          </aside>
        </div>
      )}
    </>
  );
}

function ProfileCard({ me, onSaved }: { me: MeResponse; onSaved: (m: MeResponse) => void }) {
  const { toast } = useToast();
  const [serverError, setServerError] = React.useState<unknown>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<ProfileInput>({
    resolver: zodResolver(profileSchema),
    defaultValues: { name: me.name ?? "" },
  });

  async function onSubmit(values: ProfileInput) {
    setServerError(null);
    try {
      await apiFetch("/api/bff/me", { method: "PATCH", json: values });
      onSaved({ ...me, name: values.name });
      toast({ tone: "success", title: "Profile updated" });
    } catch (e) {
      setServerError(e);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <User aria-hidden className="h-4 w-4 text-primary" />
          <CardTitle className="text-lg">Profile</CardTitle>
        </div>
        <CardDescription>Your name and account email.</CardDescription>
      </CardHeader>
      <CardContent>
        <form noValidate onSubmit={handleSubmit(onSubmit)} className="space-y-5">
          <FormErrorAlert error={serverError} />
          <Field label="Name" error={errors.name?.message} required>
            {(a11y) => <Input {...a11y} {...register("name")} autoComplete="name" />}
          </Field>
          <Field
            label="Email"
            hint={
              me.email_verified_at ? (
                <span className="inline-flex items-center gap-1 text-success">
                  <ShieldCheck className="h-3.5 w-3.5" /> Verified
                </span>
              ) : (
                <Link href={`/verify-email?email=${encodeURIComponent(me.email)}`} className="link-subtle">
                  Verify your email
                </Link>
              )
            }
          >
            {(a11y) => <Input {...a11y} value={me.email} disabled readOnly />}
          </Field>
          <div className="flex items-center justify-end">
            <Button type="submit" loading={isSubmitting} disabled={!isDirty}>
              <Save className="h-4 w-4" /> Save changes
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function CompanyCard({
  company,
  onSaved,
}: {
  company: CompanyResponse | null;
  onSaved: (c: CompanyResponse) => void;
}) {
  const { toast } = useToast();
  const [serverError, setServerError] = React.useState<unknown>(null);
  const existing = Boolean(company);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<CompanyInput>({
    resolver: zodResolver(companySchema),
    defaultValues: {
      name: company?.name ?? "",
      website: company?.website ?? "",
      industry: company?.industry ?? "",
      contact: company?.contact ?? "",
    },
  });

  React.useEffect(() => {
    reset({
      name: company?.name ?? "",
      website: company?.website ?? "",
      industry: company?.industry ?? "",
      contact: company?.contact ?? "",
    });
  }, [company, reset]);

  async function onSubmit(values: CompanyInput) {
    setServerError(null);
    try {
      if (existing) {
        await apiFetch("/api/bff/company", { method: "PATCH", json: values });
      } else {
        await apiFetch("/api/bff/company", { method: "POST", json: values });
      }
      const next = await apiFetch<CompanyResponse>("/api/bff/company");
      onSaved(next);
      toast({ tone: "success", title: existing ? "Company updated" : "Company created" });
    } catch (e) {
      setServerError(e);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Building2 aria-hidden className="h-4 w-4 text-primary" />
          <CardTitle className="text-lg">Company</CardTitle>
        </div>
        <CardDescription>Shown to your visitors in the hosted chat page.</CardDescription>
      </CardHeader>
      <CardContent>
        <form noValidate onSubmit={handleSubmit(onSubmit)} className="space-y-5">
          <FormErrorAlert error={serverError} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Company name" error={errors.name?.message} required>
              {(a11y) => <Input {...a11y} {...register("name")} placeholder="Acme Inc." />}
            </Field>
            <Field label="Website" error={errors.website?.message} optional>
              {(a11y) => <Input {...a11y} {...register("website")} placeholder="https://example.com" />}
            </Field>
            <Field label="Industry" error={errors.industry?.message} optional>
              {(a11y) => <Input {...a11y} {...register("industry")} placeholder="SaaS" />}
            </Field>
            <Field label="Contact email" error={errors.contact?.message} optional>
              {(a11y) => <Input {...a11y} {...register("contact")} placeholder="support@example.com" />}
            </Field>
          </div>
          <div className="flex items-center justify-end">
            <Button type="submit" loading={isSubmitting} disabled={!isDirty && existing}>
              <Save className="h-4 w-4" /> {existing ? "Save changes" : "Create company"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function ChangePasswordCard() {
  const { toast } = useToast();
  const [serverError, setServerError] = React.useState<unknown>(null);
  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<ChangePasswordInput>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: { current_password: "", new_password: "", confirm_password: "" },
  });
  const value = watch("new_password");

  async function onSubmit(values: ChangePasswordInput) {
    setServerError(null);
    try {
      await apiFetch("/api/bff/auth/change-password", {
        method: "POST",
        json: { current_password: values.current_password, new_password: values.new_password },
      });
      reset({ current_password: "", new_password: "", confirm_password: "" });
      toast({ tone: "success", title: "Password changed" });
    } catch (e) {
      setServerError(e);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <KeyRound aria-hidden className="h-4 w-4 text-primary" />
          <CardTitle className="text-lg">Password</CardTitle>
        </div>
        <CardDescription>Use a password you don&apos;t use anywhere else.</CardDescription>
      </CardHeader>
      <CardContent>
        <form noValidate onSubmit={handleSubmit(onSubmit)} className="space-y-5">
          <FormErrorAlert error={serverError} />
          <Field label="Current password" error={errors.current_password?.message} required>
            {(a11y) => <PasswordInput {...a11y} {...register("current_password")} autoComplete="current-password" />}
          </Field>
          <Field label="New password" error={errors.new_password?.message} required>
            {(a11y) => <PasswordInput {...a11y} {...register("new_password")} autoComplete="new-password" />}
          </Field>
          <PasswordStrength value={value ?? ""} />
          <Field label="Confirm new password" error={errors.confirm_password?.message} required>
            {(a11y) => <PasswordInput {...a11y} {...register("confirm_password")} autoComplete="new-password" />}
          </Field>
          <div className="flex items-center justify-end">
            <Button type="submit" loading={isSubmitting}>
              <Save className="h-4 w-4" /> Change password
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function SecurityCard({ me, onSignOutAll }: { me: MeResponse; onSignOutAll: () => void }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <ShieldCheck aria-hidden className="h-4 w-4 text-primary" />
          <CardTitle className="text-lg">Security</CardTitle>
        </div>
        <CardDescription>Link accounts and manage sessions.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-2">
          <p className="text-sm font-medium">Linked accounts</p>
          <GoogleSignIn mode="link" label="Link your Google account" />
          <p className="text-xs text-muted-foreground">
            Lets you sign in with Google. We re-check your current password before linking.
          </p>
        </div>
        <div className="space-y-2">
          <p className="text-sm font-medium">Sessions</p>
          <Button variant="secondary" block onClick={onSignOutAll}>
            <LogOut className="h-4 w-4" />
            Sign out of every session
          </Button>
          <p className="text-xs text-muted-foreground">
            Revokes every active session for {me.email} immediately, including this one.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

