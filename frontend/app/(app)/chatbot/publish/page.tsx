"use client";
import * as React from "react";
import Link from "next/link";
import {
  Rocket,
  Copy,
  Globe,
  ExternalLink,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  PowerOff,
  ArrowLeft,
} from "lucide-react";

import { TopBar } from "@/components/layout/topbar";
import { PageShell } from "@/components/layout/page-shell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert } from "@/components/ui/alert";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { useToast } from "@/components/ui/toast";
import {
  type BotResponse,
  type DocumentListResponse,
  type DocumentRow,
  type EmbedResponse,
} from "@/lib/types";
import { cn } from "@/lib/utils";

type DomainsResponse = { allowed_domains: string[] };

export default function PublishPage() {
  const { toast } = useToast();
  const [bot, setBot] = React.useState<BotResponse | null>(null);
  const [ready, setReady] = React.useState<DocumentRow[] | null>(null);
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [publishing, setPublishing] = React.useState(false);
  const [unpublishing, setUnpublishing] = React.useState(false);
  const [embed, setEmbed] = React.useState<EmbedResponse | null>(null);
  const [domains, setDomains] = React.useState<string[]>([]);
  const [domainsDraft, setDomainsDraft] = React.useState("");

  React.useEffect(() => {
    void (async () => {
      try {
        const [botResp, listResp, embedResp, domainResp] = await Promise.all([
          apiFetch<BotResponse>("/api/bff/bot"),
          apiFetch<DocumentListResponse>("/api/bff/documents?state=ready&limit=100"),
          apiFetch<EmbedResponse>("/api/bff/bot/embed").catch(() => null),
          apiFetch<DomainsResponse>("/api/bff/bot/domains").catch(() => ({ allowed_domains: [] })),
        ]);
        setBot(botResp);
        setReady(listResp.items);
        setSelected(new Set(listResp.items.map((i) => i.version_id!).filter(Boolean) as string[]));
        if (embedResp) setEmbed(embedResp);
        setDomains(domainResp.allowed_domains ?? []);
        setDomainsDraft((domainResp.allowed_domains ?? []).join("\n"));
      } catch (e) {
        const info = describeError(e);
        toast({ tone: "danger", title: info.title, description: info.message });
      }
    })();
  }, [toast]);

  function toggle(versionId: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(versionId)) next.delete(versionId);
      else next.add(versionId);
      return next;
    });
  }

  async function publish() {
    if (selected.size === 0) {
      toast({ tone: "warning", title: "Select at least one source" });
      return;
    }
    setPublishing(true);
    try {
      const ids = Array.from(selected).sort();
      const key = `publish:${ids.join(",")}`;
      const resp = await apiFetch<{ publication_id: string; version: number }>(
        "/api/bff/bot/publish",
        { method: "POST", headers: { "Idempotency-Key": key }, json: { selected_document_version_ids: ids } }
      );
      toast({ tone: "success", title: `Published version ${resp.version}` });
      const refreshed = await apiFetch<BotResponse>("/api/bff/bot");
      setBot(refreshed);
      const embedResp = await apiFetch<EmbedResponse>("/api/bff/bot/embed");
      setEmbed(embedResp);
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    } finally {
      setPublishing(false);
    }
  }

  async function unpublish() {
    if (!window.confirm("Unpublish? Your assistant will immediately stop replying to visitors.")) return;
    setUnpublishing(true);
    try {
      await apiFetch("/api/bff/bot/unpublish", { method: "POST" });
      const refreshed = await apiFetch<BotResponse>("/api/bff/bot");
      setBot(refreshed);
      toast({ tone: "success", title: "Assistant unpublished" });
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    } finally {
      setUnpublishing(false);
    }
  }

  async function saveDomains() {
    const list = domainsDraft
      .split("\n")
      .map((d) => d.trim())
      .filter(Boolean);
    try {
      const resp = await apiFetch<DomainsResponse>("/api/bff/bot/domains", {
        method: "PUT",
        json: { allowed_domains: list },
      });
      setDomains(resp.allowed_domains);
      toast({ tone: "success", title: "Allowed domains updated" });
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    }
  }

  return (
    <>
      <TopBar
        title="Publish"
        description="Pick which ready sources to include, then push a snapshot live."
      />
      <main>
        <PageShell>
          <div className="mb-6 flex items-center justify-between">
            <Button asChild variant="ghost" size="sm">
              <Link href="/chatbot">
                <ArrowLeft className="h-4 w-4" />
                Back to studio
              </Link>
            </Button>
            {bot?.active_publication_id ? (
              <Button variant="destructive" onClick={unpublish} loading={unpublishing}>
                <PowerOff className="h-4 w-4" />
                Unpublish
              </Button>
            ) : null}
          </div>

          <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Ready sources</CardTitle>
                  <CardDescription>
                    Only sources in the <strong className="text-foreground">Ready</strong> state can be
                    published. Add or wait for sources to finish on the Knowledge page.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {ready === null ? (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" /> Loading sources…
                    </div>
                  ) : ready.length === 0 ? (
                    <Alert tone="warning" title="Nothing ready yet" icon={AlertTriangle}>
                      <div className="space-y-2">
                        <p>You need at least one source in Ready before you can publish.</p>
                        <Button asChild size="sm" variant="secondary">
                          <Link href="/knowledge">
                            <Globe className="h-4 w-4" /> Open Knowledge
                          </Link>
                        </Button>
                      </div>
                    </Alert>
                  ) : (
                    <ul className="divide-y divide-border rounded-lg border border-border">
                      {ready.map((row) => {
                        const vid = row.version_id!;
                        const checked = selected.has(vid);
                        return (
                          <li key={row.id}>
                            <label
                              className={cn(
                                "flex cursor-pointer items-center gap-3 px-4 py-3 text-sm transition-colors hover:bg-subtle/60",
                                checked && "bg-accent/40"
                              )}
                            >
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggle(vid)}
                                className="h-4 w-4 rounded border-border text-primary"
                              />
                              <span className="min-w-0 flex-1">
                                <span className="block truncate font-medium">{row.title}</span>
                                <span className="block text-xs text-muted-foreground">
                                  {row.chunk_count ?? 0} chunks · version {row.current_version}
                                </span>
                              </span>
                              {checked && <CheckCircle2 className="h-4 w-4 text-primary" />}
                            </label>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Allowed domains</CardTitle>
                  <CardDescription>
                    Domains where the embed widget can start a session. Leave empty to allow any
                    origin (useful during setup).
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <Field label="One domain per line" hint="Use *.example.com for subdomain wildcards.">
                    {(a) => (
                      <Textarea
                        {...a}
                        rows={4}
                        value={domainsDraft}
                        onChange={(e) => setDomainsDraft(e.target.value)}
                        placeholder="example.com&#10;*.shop.example.com"
                      />
                    )}
                  </Field>
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs text-muted-foreground">
                      {domains.length === 0
                        ? "No restriction — any site may embed."
                        : `${domains.length} domain${domains.length === 1 ? "" : "s"} saved.`}
                    </p>
                    <Button variant="secondary" onClick={saveDomains}>
                      Save domains
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </div>

            <aside className="space-y-6 lg:sticky lg:top-24 lg:self-start">
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Publish snapshot</CardTitle>
                  <CardDescription>
                    Publishing creates an immutable copy of your draft and selected sources.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Currently live</span>
                    <Badge tone={bot?.active_publication_id ? "success" : "neutral"}>
                      {bot?.active_publication_id ? "Published" : "Draft only"}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Selected sources</span>
                    <span className="text-sm font-medium">{selected.size}</span>
                  </div>
                  <Button block loading={publishing} onClick={publish} disabled={!ready || ready.length === 0 || selected.size === 0}>
                    <Rocket className="h-4 w-4" />
                    {bot?.active_publication_id ? "Publish new snapshot" : "Publish"}
                  </Button>
                  <p className="text-xs text-muted-foreground">
                    Visitors see the published snapshot. Drafts never reach them.
                  </p>
                </CardContent>
              </Card>

              {embed && <InstallCard embed={embed} />}
            </aside>
          </div>
        </PageShell>
      </main>
    </>
  );
}

function InstallCard({ embed }: { embed: EmbedResponse }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Install on your site</CardTitle>
        <CardDescription>Public IDs only — no secrets in the snippet.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <SnippetBox label="Script tag" code={embed.script_snippet} />
        <SnippetBox label="React component" code={embed.react_snippet} />
        <SnippetBox label="Next.js (app router)" code={embed.nextjs_snippet} />
        <div className="rounded-lg border border-border bg-subtle/60 p-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Hosted chat URL</span>
            <a
              href={embed.hosted_chat_url}
              target="_blank"
              rel="noreferrer noopener"
              className="link-subtle inline-flex items-center gap-1"
            >
              Open <ExternalLink className="h-3 w-3" />
            </a>
          </div>
          <p className="truncate font-mono text-xs text-foreground">{embed.hosted_chat_url}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function SnippetBox({ label, code }: { label: string; code: string }) {
  const { toast } = useToast();
  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      toast({ tone: "success", title: "Copied to clipboard" });
    } catch {
      toast({ tone: "danger", title: "Couldn't copy", description: "Select the code manually." });
    }
  }
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        <button
          onClick={copy}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-primary hover:bg-accent"
        >
          <Copy className="h-3 w-3" /> Copy
        </button>
      </div>
      <pre className="overflow-x-auto rounded-lg border border-border bg-subtle/60 p-3 text-[11px] leading-relaxed">
        <code className="font-mono">{code}</code>
      </pre>
    </div>
  );
}
