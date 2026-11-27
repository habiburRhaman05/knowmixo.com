"use client";
import * as React from "react";
import {
  Save,
  Palette,
  MessageSquareText,
  ListChecks,
  Rocket,
  Globe,
  AlertCircle,
  Loader2,
} from "lucide-react";

import { TopBar } from "@/components/layout/topbar";
import { PageShell } from "@/components/layout/page-shell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Alert } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import { useToast } from "@/components/ui/toast";
import { ChatWindow, type ChatConfig } from "@/components/chat/chat-window";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { ApiError } from "@/lib/errors";
import {
  DEFAULT_CONFIG,
  diffConfig,
  INDUSTRY_TEMPLATES,
  LANGUAGE_OPTIONS,
  TEMPLATES,
  TONE_OPTIONS,
  type DraftConfig,
} from "@/components/chatbot/studio-config";
import { cn } from "@/lib/utils";
import { useBot, useSetBotData } from "@/lib/hooks/use-bot";
import type { BotResponse, LeadFormResponse } from "@/lib/types";

export default function ChatbotStudio() {
  const { toast } = useToast();
  const botQuery = useBot();
  const setBotData = useSetBotData();
  const bot = botQuery.data ?? null;
  const [draft, setDraft] = React.useState<DraftConfig>(DEFAULT_CONFIG);
  const [savedDraft, setSavedDraft] = React.useState<DraftConfig>(DEFAULT_CONFIG);
  const [revision, setRevision] = React.useState(1);
  const [saving, setSaving] = React.useState(false);
  const [leadForm, setLeadForm] = React.useState<LeadFormResponse | null>(null);
  const [previewConversationId, setPreviewConversationId] = React.useState<string | null>(null);
  const [leadFormLoading, setLeadFormLoading] = React.useState(true);
  const seededRef = React.useRef(false);

  // Seeds local draft/savedDraft/revision the first time the shared bot
  // query resolves (not on every refetch) -- a cache update from another
  // page (e.g. after a save elsewhere) must not stomp in-progress local
  // edits the way the old per-page fetch used to.
  React.useEffect(() => {
    if (botQuery.data && !seededRef.current) {
      seededRef.current = true;
      const merged = { ...DEFAULT_CONFIG, ...(botQuery.data.draft_config as DraftConfig) };
      setDraft(merged);
      setSavedDraft(merged);
      setRevision(botQuery.data.draft_revision);
    }
  }, [botQuery.data]);

  React.useEffect(() => {
    void (async () => {
      try {
        setLeadForm(await apiFetch<LeadFormResponse>("/api/bff/bot/lead-form"));
      } catch {
        setLeadForm(null);
      } finally {
        setLeadFormLoading(false);
      }
    })();
  }, []);

  const loading = botQuery.isPending || leadFormLoading;
  const loadError = botQuery.error;

  const dirty = React.useMemo(() => JSON.stringify(draft) !== JSON.stringify(savedDraft), [draft, savedDraft]);

  async function onSave() {
    const patch = diffConfig(draft, savedDraft);
    if (!Object.keys(patch).length) return;
    setSaving(true);
    try {
      const resp = await apiFetch<{ draft_revision: number }>("/api/bff/bot", {
        method: "PATCH",
        json: { draft_revision: revision, config_patch: patch },
      });
      setRevision(resp.draft_revision);
      setSavedDraft(draft);
      if (botQuery.data) {
        setBotData({ ...botQuery.data, draft_config: draft, draft_revision: resp.draft_revision });
      }
      toast({ tone: "success", title: "Draft saved" });
    } catch (e) {
      if (e instanceof ApiError && e.code === "draft_revision_conflict") {
        toast({
          tone: "warning",
          title: "Someone else edited the draft",
          description: "Reloading the latest version — your edits are still in the form; save again to apply.",
        });
        try {
          const botResp = await apiFetch<BotResponse>("/api/bff/bot");
          const merged = { ...DEFAULT_CONFIG, ...(botResp.draft_config as DraftConfig) };
          setSavedDraft(merged);
          setRevision(botResp.draft_revision);
          setBotData(botResp);
        } catch {
          /* fall-through */
        }
      } else {
        const info = describeError(e);
        toast({ tone: "danger", title: info.title, description: info.message });
      }
    } finally {
      setSaving(false);
    }
  }

  async function ensurePreviewConversation() {
    if (previewConversationId) return previewConversationId;
    const resp = await apiFetch<{ conversation_id: string }>(
      "/api/bff/bot/preview/conversations",
      { method: "POST" }
    );
    setPreviewConversationId(resp.conversation_id);
    return resp.conversation_id;
  }

  const chatConfig: ChatConfig = {
    name: draft.name,
    tone: draft.tone,
    language: draft.language,
    greeting: draft.greeting,
    suggestions: draft.suggestions,
    fallback_message: draft.fallback_message,
    branding: draft.branding,
  };

  if (loadError) {
    return (
      <>
        <TopBar title="Chatbot" />
        <main>
          <PageShell>
            <Alert tone="danger" title={describeError(loadError).title}>
              {describeError(loadError).message}
            </Alert>
          </PageShell>
        </main>
      </>
    );
  }

  if (loading) {
    return (
      <>
        <TopBar title="Chatbot" description="Shape how your assistant talks, then publish when ready." />
        <main>
          <PageShell>
            <div className="grid gap-6 lg:grid-cols-[1fr_440px] xl:grid-cols-[1fr_520px]">
              <div className="space-y-6">
                <div className="h-64 skeleton rounded-2xl" />
                <div className="h-48 skeleton rounded-2xl" />
              </div>
              <div className="h-[560px] skeleton rounded-2xl" />
            </div>
          </PageShell>
        </main>
      </>
    );
  }

  return (
    <>
      <TopBar
        title="Chatbot"
        description={
          bot?.active_publication_id
            ? "Your assistant is published. Changes here are drafts until you republish."
            : "Shape how your assistant talks, then publish when ready."
        }
      />
      <main>
        <PageShell>
          <div className="mb-6 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Badge tone={bot?.active_publication_id ? "success" : "neutral"}>
                {bot?.active_publication_id ? "Live" : "Draft only"}
              </Badge>
              {dirty && <Badge tone="warning">Unsaved changes</Badge>}
            </div>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => setDraft(savedDraft)} disabled={!dirty || saving}>
                Revert
              </Button>
              <Button onClick={onSave} loading={saving} disabled={!dirty}>
                <Save className="h-4 w-4" /> Save draft
              </Button>
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-[1fr_440px] xl:grid-cols-[1fr_520px]">
            <div className="space-y-6">
              <BehaviorCard draft={draft} setDraft={setDraft} />
              <AppearanceCard draft={draft} setDraft={setDraft} />
              <LeadFormCard leadForm={leadForm} onChange={setLeadForm} />
              <PublishHint botPublished={Boolean(bot?.active_publication_id)} />
            </div>

            <div className="lg:sticky lg:top-24 lg:self-start">
              <div className="mb-3 flex items-center justify-between">
                <p className="text-sm font-semibold">Live preview</p>
                <span className="text-xs text-muted-foreground">Using your draft and ready sources.</span>
              </div>
              <ChatWindow
                config={chatConfig}
                endpoint="/api/bff/bot/preview/chat"
                buildBody={(text) => ({
                  conversation_id: previewConversationId ?? "",
                  message: text,
                })}
                onNewConversation={async () => {
                  await ensurePreviewConversation();
                }}
                idempotencyKey={(t) => `preview:${previewConversationId ?? "pending"}:${t.slice(0, 32)}:${Date.now()}`}
                draftLabel="Draft preview"
                className="min-h-[560px]"
              />
            </div>
          </div>
        </PageShell>
      </main>
    </>
  );
}

function BehaviorCard({
  draft,
  setDraft,
}: {
  draft: DraftConfig;
  setDraft: React.Dispatch<React.SetStateAction<DraftConfig>>;
}) {
  function applyTemplate(key: string) {
    const tpl = TEMPLATES.find((t) => t.key === key);
    if (!tpl) return;
    setDraft((d) => ({ ...d, instructions: tpl.instructions }));
  }

  function applyIndustryTemplate(key: string) {
    const tpl = INDUSTRY_TEMPLATES.find((t) => t.key === key);
    if (!tpl) return;
    setDraft((d) => ({ ...d, instructions: tpl.instructions, greeting: tpl.greeting, suggestions: tpl.suggestions }));
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <MessageSquareText aria-hidden className="h-4 w-4 text-primary" />
          <CardTitle className="text-lg">Behavior</CardTitle>
        </div>
        <CardDescription>
          How your assistant answers. Instructions are followed on every reply, but the backend will
          never let the model ignore retrieved sources.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <Field label="Name" required>
          {(a) => (
            <Input
              {...a}
              value={draft.name}
              onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value.slice(0, 60) }))}
              placeholder="Acme Support"
            />
          )}
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Tone">
            {(a) => (
              <Select {...a} value={draft.tone} onChange={(v) => setDraft((d) => ({ ...d, tone: v }))} options={TONE_OPTIONS} />
            )}
          </Field>
          <Field label="Language">
            {(a) => (
              <Select
                {...a}
                value={draft.language}
                onChange={(v) => setDraft((d) => ({ ...d, language: v }))}
                options={LANGUAGE_OPTIONS}
              />
            )}
          </Field>
        </div>

        <Field label="Templates" hint="Starting points — edit to taste.">
          {() => (
            <div className="flex flex-wrap gap-2">
              {TEMPLATES.map((t) => (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => applyTemplate(t.key)}
                  className="rounded-full border border-border bg-card px-3 py-1 text-xs font-medium text-foreground hover:border-primary/40 hover:bg-accent"
                >
                  {t.name}
                </button>
              ))}
            </div>
          )}
        </Field>

        <Field label="Industry starter" hint="Sets instructions, greeting and suggested questions together.">
          {() => (
            <div className="flex flex-wrap gap-2">
              {INDUSTRY_TEMPLATES.map((t) => (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => applyIndustryTemplate(t.key)}
                  className="rounded-full border border-border bg-card px-3 py-1 text-xs font-medium text-foreground hover:border-primary/40 hover:bg-accent"
                >
                  {t.name}
                </button>
              ))}
            </div>
          )}
        </Field>

        <Field
          label="Instructions"
          hint={`${draft.instructions.length}/2000 characters`}
        >
          {(a) => (
            <Textarea
              {...a}
              rows={5}
              value={draft.instructions}
              onChange={(e) =>
                setDraft((d) => ({ ...d, instructions: e.target.value.slice(0, 2000) }))
              }
              placeholder="Explain pricing in plain English, cite the price sheet, and never guess a discount…"
            />
          )}
        </Field>

        <Field label="Fallback message" hint="Shown when nothing in your sources answers the question.">
          {(a) => (
            <Input
              {...a}
              value={draft.fallback_message}
              onChange={(e) => setDraft((d) => ({ ...d, fallback_message: e.target.value.slice(0, 200) }))}
            />
          )}
        </Field>

        <ToggleRow
          label="Show citations in replies"
          description="Attach the source and page under every assistant answer."
          checked={draft.citations_enabled}
          onChange={(v) => setDraft((d) => ({ ...d, citations_enabled: v }))}
        />
      </CardContent>
    </Card>
  );
}

function AppearanceCard({
  draft,
  setDraft,
}: {
  draft: DraftConfig;
  setDraft: React.Dispatch<React.SetStateAction<DraftConfig>>;
}) {
  const brandColor = draft.branding.color ?? "#4f46e5";
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Palette aria-hidden className="h-4 w-4 text-primary" />
          <CardTitle className="text-lg">Appearance</CardTitle>
        </div>
        <CardDescription>Brand color and greeting your visitors see first.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <Field label="Greeting" hint="First thing the widget says when it opens.">
          {(a) => (
            <Input
              {...a}
              value={draft.greeting}
              onChange={(e) => setDraft((d) => ({ ...d, greeting: e.target.value.slice(0, 200) }))}
            />
          )}
        </Field>

        <Field label="Suggested questions" hint="Up to 4. One per line.">
          {(a) => (
            <Textarea
              {...a}
              rows={3}
              value={(draft.suggestions ?? []).join("\n")}
              onChange={(e) =>
                setDraft((d) => ({
                  ...d,
                  suggestions: e.target.value
                    .split("\n")
                    .map((s) => s.trim())
                    .filter(Boolean)
                    .slice(0, 4),
                }))
              }
              placeholder="How do I reset my password?"
            />
          )}
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Brand color">
            {() => (
              <div className="flex items-center gap-3">
                <label className="relative inline-flex h-10 w-10 cursor-pointer items-center justify-center rounded-lg border border-border bg-card">
                  <input
                    type="color"
                    value={brandColor}
                    onChange={(e) =>
                      setDraft((d) => ({
                        ...d,
                        branding: { ...d.branding, color: e.target.value },
                      }))
                    }
                    className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                    aria-label="Pick brand color"
                  />
                  <span
                    aria-hidden
                    className="h-6 w-6 rounded-md shadow-inner"
                    style={{ background: brandColor }}
                  />
                </label>
                <Input
                  value={brandColor}
                  onChange={(e) =>
                    setDraft((d) => ({
                      ...d,
                      branding: { ...d.branding, color: e.target.value.slice(0, 20) },
                    }))
                  }
                  className="font-mono"
                />
              </div>
            )}
          </Field>
          <Field label="Widget position">
            {() => (
              <div className="grid grid-cols-2 gap-2">
                {(["bottom-right", "bottom-left"] as const).map((pos) => (
                  <button
                    key={pos}
                    type="button"
                    onClick={() => setDraft((d) => ({ ...d, branding: { ...d.branding, position: pos } }))}
                    className={cn(
                      "flex items-center justify-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors",
                      draft.branding.position === pos
                        ? "border-primary bg-accent text-accent-foreground"
                        : "border-border bg-card text-muted-foreground hover:text-foreground"
                    )}
                    aria-pressed={draft.branding.position === pos}
                  >
                    <span
                      aria-hidden
                      className={cn(
                        "inline-block h-3 w-3 rounded-sm bg-primary",
                        pos === "bottom-right" ? "ml-auto" : "mr-auto"
                      )}
                    />
                    {pos === "bottom-right" ? "Bottom right" : "Bottom left"}
                  </button>
                ))}
              </div>
            )}
          </Field>
        </div>
      </CardContent>
    </Card>
  );
}

function LeadFormCard({
  leadForm,
  onChange,
}: {
  leadForm: LeadFormResponse | null;
  onChange: (form: LeadFormResponse | null) => void;
}) {
  const { toast } = useToast();
  const [busy, setBusy] = React.useState<string | null>(null);

  async function toggleField(key: string, value: boolean) {
    if (!leadForm) return;
    setBusy(key);
    try {
      await apiFetch(`/api/bff/bot/lead-form/fields/${encodeURIComponent(key)}`, {
        method: "PATCH",
        json: { is_required: value },
      });
      onChange({
        ...leadForm,
        fields: leadForm.fields.map((f) => (f.field_key === key ? { ...f, is_required: value } : f)),
      });
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <ListChecks aria-hidden className="h-4 w-4 text-primary" />
          <CardTitle className="text-lg">Lead capture</CardTitle>
        </div>
        <CardDescription>
          Skippable by default (V1). Toggle a field on to require it before chat ends.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {!leadForm ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading lead form…
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {leadForm.fields.map((f) => (
              <li key={f.field_key} className="flex items-center justify-between gap-4 py-3">
                <div>
                  <p className="text-sm font-medium">{f.label}</p>
                  <p className="text-xs text-muted-foreground">
                    {f.field_type} · key <code className="font-mono text-[11px]">{f.field_key}</code>
                  </p>
                </div>
                <ToggleRow
                  compact
                  label={f.is_required ? "Required" : "Optional"}
                  checked={f.is_required}
                  disabled={busy === f.field_key}
                  onChange={(v) => void toggleField(f.field_key, v)}
                />
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function PublishHint({ botPublished }: { botPublished: boolean }) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 py-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-accent-foreground">
            <Rocket aria-hidden className="h-5 w-5" />
          </span>
          <div>
            <p className="font-display text-base font-semibold">
              {botPublished ? "Publish again to push your draft live" : "Publish your first snapshot"}
            </p>
            <p className="text-sm text-muted-foreground">
              Choose which ready sources to include. Visitors only see published snapshots.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button asChild variant="secondary">
            <a href="/knowledge">
              <Globe className="h-4 w-4" /> Pick sources
            </a>
          </Button>
          <Button asChild>
            <a href="/chatbot/publish">
              <Rocket className="h-4 w-4" /> Publish
            </a>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function Select({
  value,
  onChange,
  options,
  id,
  ...aria
}: {
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
  id?: string;
  "aria-describedby"?: string;
}) {
  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-describedby={aria["aria-describedby"]}
      className="flex h-10 w-full appearance-none rounded-lg border border-input bg-card px-3 py-2 text-sm text-foreground shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

function ToggleRow({
  label,
  description,
  checked,
  onChange,
  disabled,
  compact,
}: {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  compact?: boolean;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-center gap-3",
        !compact && "rounded-lg border border-border bg-subtle/40 p-3"
      )}
    >
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        disabled={disabled}
        className={cn(
          "relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border transition-colors",
          checked ? "border-primary bg-primary" : "border-border bg-muted",
          disabled && "opacity-60"
        )}
      >
        <span
          aria-hidden
          className={cn(
            "inline-block h-3.5 w-3.5 rounded-full bg-card shadow transition-transform",
            checked ? "translate-x-4" : "translate-x-1"
          )}
        />
      </button>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium">{label}</span>
        {description && <span className="block text-xs text-muted-foreground">{description}</span>}
      </span>
    </label>
  );
}
