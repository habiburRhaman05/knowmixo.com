"use client";
import * as React from "react";
import Link from "next/link";
import {
  ArrowRight,
  Building2,
  BookOpen,
  Palette,
  Eye,
  Rocket,
  Check,
  Loader2,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { TopBar } from "@/components/layout/topbar";
import { PageShell } from "@/components/layout/page-shell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/field";
import { Alert } from "@/components/ui/alert";
import { useToast } from "@/components/ui/toast";
import { ChatWindow, type ChatConfig } from "@/components/chat/chat-window";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { useBot } from "@/lib/hooks/use-bot";
import { useCompany, useInvalidateCompany } from "@/lib/hooks/use-company";
import { DEFAULT_CONFIG, INDUSTRY_TEMPLATES } from "@/components/chatbot/studio-config";
import type { BotResponse, CompanyResponse, DocumentListResponse } from "@/lib/types";

type Step = "company" | "source" | "appearance" | "preview" | "publish";

export default function OnboardingPage() {
  const { data: company, error: companyError, isPending: companyPending } = useCompany();
  const { data: bot, error: botError, isPending: botPending } = useBot();
  const {
    data: docsResp,
    error: docsError,
    isPending: docsPending,
    refetch: refetchDocuments,
  } = useQuery({
    queryKey: ["documents", "onboarding-has-source"],
    queryFn: () => apiFetch<DocumentListResponse>("/api/bff/documents?limit=1"),
  });
  const invalidateCompany = useInvalidateCompany();

  const loading = companyPending || botPending || docsPending;
  const loadError = companyError ?? botError ?? docsError;
  const hasSource = Boolean(docsResp && docsResp.items.length > 0);

  if (loading) {
    return (
      <>
        <TopBar title="Onboarding" />
        <main>
          <PageShell>
            <div className="flex items-center justify-center py-16 text-muted-foreground">
              <Loader2 aria-hidden className="h-5 w-5 animate-spin" />
            </div>
          </PageShell>
        </main>
      </>
    );
  }

  if (loadError) {
    const info = describeError(loadError);
    return (
      <>
        <TopBar title="Onboarding" />
        <main>
          <PageShell>
            <Alert tone="danger" title={info.title}>
              {info.message}
            </Alert>
          </PageShell>
        </main>
      </>
    );
  }

  const appearanceDone = (bot?.draft_revision ?? 1) > 1;
  const publishDone = Boolean(bot?.active_publication_id);
  const companyDone = Boolean(company?.website);

  const statusFor: Record<Step, boolean> = {
    company: companyDone,
    source: hasSource,
    appearance: appearanceDone,
    preview: hasSource,
    publish: publishDone,
  };

  return (
    <>
      <TopBar
        title="Onboarding"
        description="Get your assistant live in a few focused steps. You can return any time."
      />
      <main>
        <PageShell>
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Welcome — let&apos;s get you grounded</CardTitle>
                <CardDescription>
                  Each step reflects your real setup, not a checklist — it updates as you actually finish things.
                </CardDescription>
              </CardHeader>
            </Card>

            <ol className="relative space-y-4 border-l border-border pl-6">
              <StepItem index={1} icon={Building2} title="Company details" done={statusFor.company}>
                <CompanyStep company={company ?? null} onSaved={invalidateCompany} />
              </StepItem>

              <StepItem index={2} icon={BookOpen} title="Add your first source" done={statusFor.source}>
                <SourceStep hasSource={hasSource} onImported={() => void refetchDocuments()} />
              </StepItem>

              <StepItem index={3} icon={Palette} title="Shape the assistant" done={statusFor.appearance}>
                <p className="text-sm text-muted-foreground">
                  Name, tone, greeting and starter instructions — pick an industry starter to fill these in one click.
                </p>
                <Button asChild size="sm" variant="secondary" className="mt-3">
                  <Link href="/chatbot">
                    Open studio
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
              </StepItem>

              <StepItem index={4} icon={Eye} title="Preview the answers" done={statusFor.preview}>
                <PreviewStep bot={bot ?? null} hasSource={hasSource} />
              </StepItem>

              <StepItem index={5} icon={Rocket} title="Publish the first snapshot" done={statusFor.publish}>
                <p className="text-sm text-muted-foreground">
                  Choose which ready sources to include, then go live.
                </p>
                <Button asChild size="sm" variant="secondary" className="mt-3">
                  <Link href="/chatbot/publish">
                    {publishDone ? "Publish an update" : "Publish"}
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
              </StepItem>
            </ol>

            <Card>
              <CardContent className="flex items-center gap-3 py-5 text-sm">
                <Check aria-hidden className="h-5 w-5 text-success" />
                <p>
                  Nothing is published until you choose to. Every change is saved as a draft and only
                  the <strong className="font-medium">published snapshot</strong> is visible to visitors.
                </p>
              </CardContent>
            </Card>
          </div>
        </PageShell>
      </main>
    </>
  );
}

function StepItem({
  index,
  icon: Icon,
  title,
  done,
  children,
}: {
  index: number;
  icon: React.ElementType;
  title: string;
  done: boolean;
  children: React.ReactNode;
}) {
  return (
    <li className="relative">
      <span
        className={
          "absolute -left-[33px] flex h-6 w-6 items-center justify-center rounded-full border text-xs font-semibold " +
          (done ? "border-success bg-success/10 text-success" : "border-border bg-background text-muted-foreground")
        }
      >
        {done ? <Check aria-hidden className="h-3.5 w-3.5" /> : index}
      </span>
      <Card>
        <CardContent className="space-y-1 py-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex items-start gap-4">
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                <Icon aria-hidden className="h-5 w-5" />
              </span>
              <p className="font-display text-base font-semibold">{title}</p>
            </div>
            <Badge tone={done ? "success" : "neutral"}>{done ? "Done" : "Not started"}</Badge>
          </div>
          <div className="pl-14">{children}</div>
        </CardContent>
      </Card>
    </li>
  );
}

function CompanyStep({ company, onSaved }: { company: CompanyResponse | null; onSaved: () => void }) {
  const { toast } = useToast();
  const [website, setWebsite] = React.useState(company?.website ?? "");
  const [industryKey, setIndustryKey] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<unknown>(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const tpl = INDUSTRY_TEMPLATES.find((t) => t.key === industryKey);
      await apiFetch("/api/bff/company", {
        method: "PATCH",
        json: { website: website.trim() || undefined, industry: tpl?.name },
      });
      toast({ tone: "success", title: "Company details saved" });
      onSaved();
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3">
      <Field label="Website" hint="Used to crawl your site for the knowledge base.">
        {(a) => (
          <Input
            {...a}
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
            placeholder="https://example.com"
          />
        )}
      </Field>
      <Field label="Industry" hint="Picks a matching starter kit for step 3 (instructions, greeting, suggestions).">
        {() => (
          <div className="flex flex-wrap gap-2">
            {INDUSTRY_TEMPLATES.map((t) => (
              <button
                key={t.key}
                type="button"
                onClick={() => setIndustryKey(t.key)}
                className={
                  "rounded-full border px-3 py-1 text-xs font-medium transition " +
                  (industryKey === t.key
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border bg-card text-foreground hover:border-primary/40 hover:bg-accent")
                }
              >
                {t.name}
              </button>
            ))}
          </div>
        )}
      </Field>
      {error != null && <Alert tone="danger" title={describeError(error).title}>{describeError(error).message}</Alert>}
      <Button size="sm" onClick={save} loading={saving}>
        Save
      </Button>
    </div>
  );
}

function SourceStep({ hasSource, onImported }: { hasSource: boolean; onImported: () => void }) {
  const { toast } = useToast();
  const [url, setUrl] = React.useState("");
  const [importing, setImporting] = React.useState(false);
  const [error, setError] = React.useState<unknown>(null);
  const [result, setResult] = React.useState<{ pages_found: number } | null>(null);

  async function crawl() {
    if (!url.trim()) return;
    setImporting(true);
    setError(null);
    setResult(null);
    try {
      const resp = await apiFetch<{ pages_found: number }>("/api/bff/sources/crawl", {
        method: "POST",
        json: { root_url: url.trim() },
      });
      setResult(resp);
      toast({ tone: "success", title: `Imported ${resp.pages_found} page(s)`, description: "Processing will finish in the background." });
      onImported();
    } catch (e) {
      setError(e);
    } finally {
      setImporting(false);
    }
  }

  return (
    <div className="space-y-3">
      {hasSource ? (
        <p className="text-sm text-muted-foreground">
          You have at least one source. Add more any time from the{" "}
          <Link href="/knowledge" className="font-medium text-primary underline-offset-2 hover:underline">
            Knowledge
          </Link>{" "}
          page.
        </p>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">
            Paste your site's URL to auto-crawl and import it, or{" "}
            <Link href="/knowledge" className="font-medium text-primary underline-offset-2 hover:underline">
              add one manually
            </Link>{" "}
            (upload a file, paste text or FAQs).
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com"
              className="sm:flex-1"
            />
            <Button size="sm" onClick={crawl} loading={importing}>
              Crawl &amp; import
            </Button>
          </div>
          {result && (
            <p className="text-sm text-success">Found and queued {result.pages_found} page(s) for processing.</p>
          )}
          {error != null && <Alert tone="danger" title={describeError(error).title}>{describeError(error).message}</Alert>}
        </>
      )}
    </div>
  );
}

function PreviewStep({ bot, hasSource }: { bot: BotResponse | null; hasSource: boolean }) {
  const [conversationId, setConversationId] = React.useState<string | null>(null);

  async function ensureConversation() {
    if (conversationId) return conversationId;
    const resp = await apiFetch<{ conversation_id: string }>("/api/bff/bot/preview/conversations", { method: "POST" });
    setConversationId(resp.conversation_id);
    return resp.conversation_id;
  }

  if (!hasSource) {
    return <p className="text-sm text-muted-foreground">Add a source in step 2 to try a real preview here.</p>;
  }

  const draft = (bot?.draft_config ?? {}) as Partial<typeof DEFAULT_CONFIG>;
  const chatConfig: ChatConfig = {
    name: draft.name ?? DEFAULT_CONFIG.name,
    tone: draft.tone ?? DEFAULT_CONFIG.tone,
    language: draft.language ?? DEFAULT_CONFIG.language,
    greeting: draft.greeting ?? DEFAULT_CONFIG.greeting,
    suggestions: draft.suggestions ?? DEFAULT_CONFIG.suggestions,
    fallback_message: draft.fallback_message ?? DEFAULT_CONFIG.fallback_message,
    branding: draft.branding ?? DEFAULT_CONFIG.branding,
  };

  return (
    <div className="space-y-2">
      <p className="text-sm text-muted-foreground">Ask it something a visitor might ask — using your real draft and sources.</p>
      <ChatWindow
        config={chatConfig}
        endpoint="/api/bff/bot/preview/chat"
        buildBody={(text) => ({ conversation_id: conversationId ?? "", message: text })}
        onNewConversation={async () => {
          await ensureConversation();
        }}
        idempotencyKey={(t) => `onboarding-preview:${conversationId ?? "pending"}:${t.slice(0, 32)}:${Date.now()}`}
        draftLabel="Draft preview"
        className="min-h-[360px] max-w-xl"
      />
    </div>
  );
}
