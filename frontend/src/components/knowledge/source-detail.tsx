"use client";
import * as React from "react";
import { X, RefreshCw, Trash2, BookOpen, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { SourceStatusBadge } from "./status-badge";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { type DocumentDetail, type DocumentContent } from "@/lib/types";
import { useToast } from "@/components/ui/toast";
import { cn, fromNow } from "@/lib/utils";

type Props = {
  document: DocumentDetail;
  onClose: () => void;
  onRefresh: () => void;
  onDeleted: () => void;
  onChanged: () => void;
};

export function SourceDetail({ document, onClose, onRefresh, onDeleted, onChanged }: Props) {
  const { toast } = useToast();
  const [content, setContent] = React.useState<DocumentContent | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [contentError, setContentError] = React.useState<unknown>(null);

  React.useEffect(() => {
    if (document.status !== "ready") {
      setContent(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const data = await apiFetch<DocumentContent>(`/api/bff/documents/${document.id}/content`);
        if (!cancelled) setContent(data);
      } catch (e) {
        if (!cancelled) setContentError(e);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [document.id, document.status]);

  async function onDelete() {
    if (!window.confirm(`Delete "${document.title}"? This can't be undone.`)) return;
    try {
      await apiFetch(`/api/bff/documents/${document.id}`, { method: "DELETE" });
      toast({ tone: "success", title: "Source deleted" });
      onDeleted();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    }
  }

  return (
    <aside
      role="dialog"
      aria-label={`Source: ${document.title}`}
      className="fixed inset-y-0 right-0 z-40 flex w-full max-w-2xl flex-col border-l border-border bg-card shadow-elevated animate-fade-in sm:w-[560px]"
    >
      <header className="flex items-start justify-between gap-4 border-b border-border p-5">
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex items-center gap-2">
            <SourceStatusBadge status={document.status} stage={document.stage} />
            {document.chunk_count ? (
              <span className="text-xs text-muted-foreground">
                {document.chunk_count} chunks indexed
              </span>
            ) : null}
          </div>
          <h2 className="truncate font-display text-lg font-semibold">{document.title}</h2>
          <p className="text-xs text-muted-foreground">
            Version {document.current_version ?? "-"} · Added {fromNow(document.created_at)}
          </p>
        </div>
        <Button variant="ghost" size="icon" aria-label="Close source detail" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </header>

      <div className="flex-1 overflow-y-auto p-5">
        {document.source_url && (
          <section className="mb-5 rounded-lg border border-border bg-subtle/60 p-3">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Source URL</p>
            <a
              className="link-subtle break-all text-sm"
              href={document.source_url}
              target="_blank"
              rel="noreferrer noopener"
            >
              {document.source_url}
            </a>
          </section>
        )}

        {document.status !== "ready" && (
          <Alert tone="info" title={document.status === "failed" ? "Ingestion failed" : "Preparing source"}>
            {document.status === "failed"
              ? "The extracted-text preview is available only once a version completes successfully."
              : "We'll show the extracted text as soon as this version is ready."}
          </Alert>
        )}

        {document.status === "ready" && (
          <section>
            <div className="mb-3 flex items-center gap-2 text-sm font-medium">
              <BookOpen aria-hidden className="h-4 w-4 text-primary" />
              Extracted text preview
              {content?.truncated && (
                <span className="text-xs font-normal text-muted-foreground">(truncated)</span>
              )}
            </div>
            {loading && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> Loading preview…
              </div>
            )}
            {contentError ? (
              <Alert tone="danger" title="Couldn't load the preview">
                {describeError(contentError).message}
              </Alert>
            ) : null}
            {content && (
              <div className="space-y-4">
                {content.pages_or_headings.length > 0 && (
                  <nav
                    aria-label="Document outline"
                    className="rounded-lg border border-border bg-subtle/60 p-3 text-xs"
                  >
                    <p className="mb-2 font-medium text-foreground">Outline</p>
                    <ul className="space-y-1">
                      {content.pages_or_headings.slice(0, 20).map((o, i) => (
                        <li key={i} className="flex items-center gap-2 text-muted-foreground">
                          {o.page !== null && (
                            <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">
                              p.{o.page}
                            </span>
                          )}
                          <span className="truncate">{o.heading ?? "(section)"}</span>
                        </li>
                      ))}
                    </ul>
                  </nav>
                )}
                <pre
                  className={cn(
                    "whitespace-pre-wrap rounded-lg border border-border bg-subtle/60 p-4 font-sans text-sm leading-relaxed text-foreground"
                  )}
                >
                  {content.preview_text}
                </pre>
              </div>
            )}
          </section>
        )}
      </div>

      <footer className="flex items-center justify-between gap-3 border-t border-border bg-subtle/60 p-4">
        <Button variant="secondary" onClick={onRefresh} disabled={document.status === "processing"}>
          <RefreshCw className="h-4 w-4" />
          Refresh / re-index
        </Button>
        <Button variant="destructive" onClick={onDelete}>
          <Trash2 className="h-4 w-4" />
          Delete
        </Button>
      </footer>
    </aside>
  );
}
