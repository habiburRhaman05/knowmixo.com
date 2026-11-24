"use client";
import * as React from "react";
import {
  BookOpen,
  Plus,
  Search,
  Filter,
  Upload,
  AlertTriangle,
  RefreshCw,
} from "lucide-react";

import { TopBar } from "@/components/layout/topbar";
import { PageShell } from "@/components/layout/page-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Alert } from "@/components/ui/alert";
import { EmptyState } from "@/components/ui/empty-state";
import { AddSourceDialog } from "@/components/knowledge/add-source-dialog";
import { SourceRow } from "@/components/knowledge/source-row";
import { SourceDetail } from "@/components/knowledge/source-detail";
import {
  type DocumentListResponse,
  type DocumentRow,
  type DocumentStatus,
  type DocumentKind,
} from "@/lib/types";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 25;

type Filter = {
  state: DocumentStatus | "processing" | "";
  type: DocumentKind | "";
  q: string;
};

const STATE_FILTERS: Array<{ value: Filter["state"]; label: string }> = [
  { value: "", label: "All" },
  { value: "ready", label: "Ready" },
  { value: "processing", label: "Processing" },
  { value: "failed", label: "Failed" },
];

const TYPE_FILTERS: Array<{ value: Filter["type"]; label: string }> = [
  { value: "", label: "Any type" },
  { value: "file", label: "File" },
  { value: "text", label: "Text" },
  { value: "faq", label: "FAQ" },
  { value: "url", label: "URL" },
  { value: "crawl_page", label: "Crawl page" },
];

export default function KnowledgePage() {
  const { toast } = useToast();
  const [filter, setFilter] = React.useState<Filter>({ state: "", type: "", q: "" });
  const [query, setQuery] = React.useState("");
  const [items, setItems] = React.useState<DocumentRow[] | null>(null);
  const [cursor, setCursor] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<unknown>(null);
  const [addOpen, setAddOpen] = React.useState(false);
  const [detail, setDetail] = React.useState<DocumentRow | null>(null);

  // Debounce the search input.
  React.useEffect(() => {
    const id = window.setTimeout(() => setFilter((f) => ({ ...f, q: query.trim() })), 250);
    return () => window.clearTimeout(id);
  }, [query]);

  const fetchKey = React.useMemo(
    () => JSON.stringify([filter.state, filter.type, filter.q]),
    [filter.state, filter.type, filter.q]
  );

  const load = React.useCallback(
    async (opts: { reset?: boolean } = {}) => {
      const params = new URLSearchParams();
      if (filter.state) params.set("state", filter.state);
      if (filter.type) params.set("type", filter.type);
      if (filter.q) params.set("q", filter.q);
      params.set("limit", String(PAGE_SIZE));
      if (!opts.reset && cursor) params.set("cursor", cursor);
      setLoading(true);
      setError(null);
      try {
        const data = await apiFetch<DocumentListResponse>(`/api/bff/documents?${params.toString()}`);
        setItems((prev) => (opts.reset || !prev ? data.items : [...prev, ...data.items]));
        setCursor(data.next_cursor);
      } catch (e) {
        setError(e);
      } finally {
        setLoading(false);
      }
    },
    // We intentionally don't depend on `cursor` here -- "load more" passes
    // the current cursor explicitly and the reset path clears it. Depending
    // on it would reload on every pagination click.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [fetchKey]
  );

  React.useEffect(() => {
    setCursor(null);
    void load({ reset: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchKey]);

  // Poll while any source is still in a non-terminal state (visible rows).
  const hasInFlight =
    items?.some((i) => i.status !== "ready" && i.status !== "failed" && i.status !== "retired") ?? false;
  React.useEffect(() => {
    if (!hasInFlight) return;
    const id = window.setInterval(() => void load({ reset: true }), 3000);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasInFlight]);

  async function onRetryOrRefresh(row: DocumentRow) {
    try {
      if (row.status === "failed" && row.version_id) {
        // Prefer the exact job retry if we have the latest job id; refresh
        // works as a user-visible "try again" for any source regardless.
        await apiFetch(`/api/bff/documents/${row.id}/refresh`, {
          method: "POST",
          headers: { "Idempotency-Key": `refresh:${row.id}:${row.current_version ?? 0}` },
        });
      } else {
        await apiFetch(`/api/bff/documents/${row.id}/refresh`, {
          method: "POST",
          headers: { "Idempotency-Key": `refresh:${row.id}:${row.current_version ?? 0}` },
        });
      }
      toast({ tone: "success", title: "Reprocessing queued" });
      await load({ reset: true });
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    }
  }

  async function onDelete(row: DocumentRow) {
    if (!window.confirm(`Delete "${row.title}"? This can't be undone.`)) return;
    try {
      await apiFetch(`/api/bff/documents/${row.id}`, { method: "DELETE" });
      toast({ tone: "success", title: "Source deleted" });
      setItems((prev) => (prev ? prev.filter((d) => d.id !== row.id) : prev));
      if (detail?.id === row.id) setDetail(null);
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    }
  }

  const totalShown = items?.length ?? 0;

  return (
    <>
      <TopBar
        title="Knowledge"
        description="Everything your assistant is allowed to answer from."
      />
      <main>
        <PageShell>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div className="space-y-1">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Sources</p>
              <p className="font-display text-xl font-semibold">
                {items === null ? "Loading…" : `${totalShown} ${totalShown === 1 ? "source" : "sources"}`}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="secondary" size="md" onClick={() => void load({ reset: true })}>
                <RefreshCw className="h-4 w-4" /> Refresh
              </Button>
              <Button onClick={() => setAddOpen(true)}>
                <Plus className="h-4 w-4" /> Add source
              </Button>
            </div>
          </div>

          <Card className="mt-6">
            <div className="flex flex-col gap-3 border-b border-border p-4 sm:flex-row sm:items-center sm:gap-6">
              <div className="relative flex-1">
                <Search
                  aria-hidden
                  className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
                />
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search by title…"
                  className="pl-9"
                  aria-label="Search sources"
                />
              </div>
              <div className="flex flex-wrap items-center gap-1">
                <Filter aria-hidden className="h-4 w-4 text-muted-foreground" />
                <FilterGroup
                  label="Status"
                  options={STATE_FILTERS}
                  value={filter.state}
                  onChange={(v) => setFilter((f) => ({ ...f, state: v as Filter["state"] }))}
                />
              </div>
              <div className="flex flex-wrap items-center gap-1">
                <FilterGroup
                  label="Type"
                  options={TYPE_FILTERS}
                  value={filter.type}
                  onChange={(v) => setFilter((f) => ({ ...f, type: v as Filter["type"] }))}
                />
              </div>
            </div>

            {error ? (
              <div className="p-5">
                <Alert tone="danger" title={describeError(error).title} icon={AlertTriangle}>
                  {describeError(error).message}
                </Alert>
              </div>
            ) : items === null || loading ? (
              <SkeletonList />
            ) : items.length === 0 ? (
              <EmptyState
                icon={BookOpen}
                title="No sources yet"
                description={
                  filter.q || filter.state || filter.type
                    ? "No sources match these filters."
                    : "Add a document, FAQ or URL to teach your assistant."
                }
                action={
                  <Button onClick={() => setAddOpen(true)}>
                    <Upload className="h-4 w-4" /> Add your first source
                  </Button>
                }
              />
            ) : (
              <ul>
                {items.map((row) => (
                  <SourceRow
                    key={row.id}
                    row={row}
                    onOpen={(d) => setDetail(d)}
                    onRefresh={onRetryOrRefresh}
                    onDelete={onDelete}
                  />
                ))}
              </ul>
            )}
            {cursor && items && items.length > 0 && !loading && (
              <div className="flex items-center justify-center p-4">
                <Button variant="secondary" onClick={() => void load()} loading={loading}>
                  Load more
                </Button>
              </div>
            )}
          </Card>
        </PageShell>
      </main>

      <AddSourceDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        onDone={() => void load({ reset: true })}
      />
      {detail && (
        <SourceDetail
          document={items?.find((i) => i.id === detail.id) ?? detail}
          onClose={() => setDetail(null)}
          onRefresh={() => {
            void onRetryOrRefresh(detail);
          }}
          onDeleted={() => {
            setDetail(null);
            void load({ reset: true });
          }}
          onChanged={() => {
            void load({ reset: true });
          }}
        />
      )}
    </>
  );
}

function FilterGroup<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: Array<{ value: T; label: string }>;
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div role="group" aria-label={label} className="flex rounded-md border border-border bg-subtle p-0.5">
      {options.map((o) => (
        <button
          key={o.value || "all"}
          type="button"
          onClick={() => onChange(o.value)}
          aria-pressed={value === o.value}
          className={cn(
            "rounded-sm px-2.5 py-1 text-xs font-medium transition-colors",
            value === o.value
              ? "bg-card text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function SkeletonList() {
  return (
    <ul>
      {Array.from({ length: 5 }).map((_, i) => (
        <li key={i} className="grid grid-cols-[auto_1fr_auto] items-center gap-4 border-b border-border px-5 py-4 last:border-b-0">
          <div className="h-10 w-10 skeleton rounded-lg" />
          <div className="space-y-2">
            <div className="h-4 w-1/3 skeleton" />
            <div className="h-3 w-1/4 skeleton" />
          </div>
          <div className="h-8 w-24 skeleton rounded-md" />
        </li>
      ))}
    </ul>
  );
}
