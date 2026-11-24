"use client";
import * as React from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Upload,
  FileText,
  Link2,
  Globe,
  Plus,
  Trash2,
  AlertCircle,
  ArrowRight,
  CheckCircle2,
} from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Alert } from "@/components/ui/alert";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { FormErrorAlert } from "@/components/auth/form-errors";
import { apiFetch } from "@/lib/api-client";
import { describeError, ERROR_COPY } from "@/lib/errors";
import { ERROR_CODE_COPY, type UploadGrantResponse, type CrawlJobResponse } from "@/lib/types";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

const ALLOWED_EXT = [".pdf", ".docx", ".txt", ".md"] as const;
const MAX_FILE_BYTES = 10 * 1024 * 1024;

type Props = { open: boolean; onOpenChange: (open: boolean) => void; onDone: () => void };

type Tab = "file" | "text" | "faq" | "url" | "crawl";

const TABS: Array<{ key: Tab; label: string; icon: React.ElementType; description: string }> = [
  { key: "file", label: "Upload file", icon: Upload, description: "PDF, DOCX, TXT or Markdown, up to 10 MB." },
  { key: "text", label: "Paste text", icon: FileText, description: "Paste or write content directly." },
  { key: "faq", label: "FAQ", icon: FileText, description: "Question and answer pairs." },
  { key: "url", label: "Single URL", icon: Link2, description: "One page from your site or help center." },
  { key: "crawl", label: "Crawl website", icon: Globe, description: "Discover pages, then pick which to import." },
];

export function AddSourceDialog({ open, onOpenChange, onDone }: Props) {
  const [tab, setTab] = React.useState<Tab>("file");

  React.useEffect(() => {
    if (open) setTab("file");
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Add a knowledge source</DialogTitle>
          <DialogDescription>
            Every answer the assistant gives will cite the exact passage from here.
          </DialogDescription>
        </DialogHeader>
        <div
          role="tablist"
          aria-label="Source type"
          className="flex flex-wrap gap-1 rounded-lg border border-border bg-subtle p-1"
        >
          {TABS.map((t) => {
            const active = t.key === tab;
            return (
              <button
                key={t.key}
                role="tab"
                aria-selected={active}
                type="button"
                onClick={() => setTab(t.key)}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                  active
                    ? "bg-card text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <t.icon aria-hidden className="h-4 w-4" />
                {t.label}
              </button>
            );
          })}
        </div>
        <p className="text-xs text-muted-foreground">{TABS.find((t) => t.key === tab)!.description}</p>

        <div className="pt-1">
          {tab === "file" && <FilePanel onDone={onDone} onClose={() => onOpenChange(false)} />}
          {tab === "text" && <TextPanel onDone={onDone} onClose={() => onOpenChange(false)} />}
          {tab === "faq" && <FaqPanel onDone={onDone} onClose={() => onOpenChange(false)} />}
          {tab === "url" && <UrlPanel onDone={onDone} onClose={() => onOpenChange(false)} />}
          {tab === "crawl" && <CrawlPanel onDone={onDone} onClose={() => onOpenChange(false)} />}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// --- File upload ----------------------------------------------------------

function FilePanel({ onDone, onClose }: { onDone: () => void; onClose: () => void }) {
  const { toast } = useToast();
  const [file, setFile] = React.useState<File | null>(null);
  const [progress, setProgress] = React.useState(0);
  const [stage, setStage] =
    React.useState<"idle" | "grant" | "upload" | "complete" | "done">("idle");
  const [error, setError] = React.useState<unknown>(null);
  const [dragging, setDragging] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  function onPick(next: File | null) {
    setError(null);
    if (!next) return setFile(null);
    const ext = "." + (next.name.split(".").pop() ?? "").toLowerCase();
    if (!ALLOWED_EXT.includes(ext as (typeof ALLOWED_EXT)[number])) {
      setError({ code: "unsupported_file_type", message: ERROR_CODE_COPY.unsupported_file_type });
      return;
    }
    if (next.size <= 0 || next.size > MAX_FILE_BYTES) {
      setError({ code: "file_too_large", message: ERROR_CODE_COPY.file_too_large });
      return;
    }
    setFile(next);
  }

  async function upload() {
    if (!file) return;
    setError(null);
    setProgress(2);
    setStage("grant");
    try {
      const grant = await apiFetch<UploadGrantResponse>("/api/bff/documents/uploads", {
        method: "POST",
        json: {
          filename: file.name,
          content_type: file.type || "application/octet-stream",
          size_bytes: file.size,
        },
      });
      setStage("upload");
      setProgress(10);

      // Stream PUT via XHR so we get upload progress events.
      await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("PUT", `/api/bff/uploads/${encodeURIComponent(grant.grant_id)}`);
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            const pct = 10 + Math.round((e.loaded / e.total) * 80);
            setProgress(pct);
          }
        };
        xhr.onload = () => (xhr.status < 400 ? resolve() : reject(new Error(xhr.responseText || "Upload failed")));
        xhr.onerror = () => reject(new Error("Network error"));
        xhr.send(file);
      });

      setStage("complete");
      setProgress(95);
      await apiFetch(`/api/bff/documents/${grant.document_id}/complete`, {
        method: "POST",
        headers: { "Idempotency-Key": `complete:${grant.grant_id}` },
        json: { grant_id: grant.grant_id },
      });
      setStage("done");
      setProgress(100);
      toast({ tone: "success", title: "Upload started", description: file.name });
      onDone();
      onClose();
    } catch (e) {
      setError(e);
      setStage("idle");
      setProgress(0);
    }
  }

  return (
    <div className="space-y-4">
      <FormErrorAlert error={error} />
      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          onPick(e.dataTransfer.files?.[0] ?? null);
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-8 text-center transition-colors",
          dragging ? "border-primary bg-accent/50" : "border-border bg-subtle/60 hover:bg-subtle"
        )}
      >
        <input
          ref={inputRef}
          type="file"
          className="sr-only"
          accept={ALLOWED_EXT.join(",")}
          onChange={(e) => onPick(e.target.files?.[0] ?? null)}
        />
        <Upload aria-hidden className="h-6 w-6 text-muted-foreground" />
        <div>
          <p className="text-sm font-medium">
            {file ? file.name : "Drop a file here or click to browse"}
          </p>
          <p className="text-xs text-muted-foreground">
            {file
              ? `${(file.size / 1024 / 1024).toFixed(2)} MB`
              : "PDF, DOCX, TXT, Markdown · up to 10 MB"}
          </p>
        </div>
      </label>

      {stage !== "idle" && (
        <div className="space-y-2">
          <Progress value={progress} />
          <p className="text-xs text-muted-foreground">
            {stage === "grant" && "Requesting upload…"}
            {stage === "upload" && `Uploading… ${progress}%`}
            {stage === "complete" && "Finalising upload…"}
            {stage === "done" && "Done, source is queued for ingestion."}
          </p>
        </div>
      )}

      <DialogFooter>
        <Button variant="ghost" onClick={onClose} type="button">
          Cancel
        </Button>
        <Button onClick={upload} disabled={!file || stage !== "idle"} loading={stage !== "idle" && stage !== "done"}>
          Upload and process
          <ArrowRight className="h-4 w-4" />
        </Button>
      </DialogFooter>
    </div>
  );
}

// --- Text -----------------------------------------------------------------

const textSchema = z.object({
  title: z.string().trim().min(1, "Give this source a title.").max(200),
  text: z.string().trim().min(1, "Paste or write some content.").max(1_000_000),
});
type TextInput = z.infer<typeof textSchema>;

function TextPanel({ onDone, onClose }: { onDone: () => void; onClose: () => void }) {
  const { toast } = useToast();
  const [serverError, setServerError] = React.useState<unknown>(null);
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<TextInput>({ resolver: zodResolver(textSchema), defaultValues: { title: "", text: "" } });
  const text = watch("text") ?? "";

  async function onSubmit(values: TextInput) {
    setServerError(null);
    try {
      await apiFetch("/api/bff/sources/text", { method: "POST", json: values });
      toast({ tone: "success", title: "Text source queued" });
      onDone();
      onClose();
    } catch (e) {
      setServerError(e);
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      <FormErrorAlert error={serverError} />
      <Field label="Title" error={errors.title?.message} required>
        {(a11y) => <Input {...a11y} {...register("title")} placeholder="Returns policy" />}
      </Field>
      <Field
        label="Content"
        error={errors.text?.message}
        required
        hint={`${text.length.toLocaleString()} / 1,000,000 characters`}
      >
        {(a11y) => (
          <Textarea
            {...a11y}
            {...register("text")}
            rows={10}
            placeholder="Paste the text your assistant should answer from…"
          />
        )}
      </Field>
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" loading={isSubmitting}>
          Add text source
        </Button>
      </DialogFooter>
    </form>
  );
}

// --- FAQ ------------------------------------------------------------------

const faqSchema = z.object({
  title: z.string().trim().min(1, "Give this FAQ a title.").max(200),
  items: z
    .array(
      z.object({
        q: z.string().trim().min(1, "Question is required.").max(500),
        a: z.string().trim().min(1, "Answer is required.").max(5000),
      })
    )
    .min(1, "Add at least one Q&A."),
});
type FaqInput = z.infer<typeof faqSchema>;

function FaqPanel({ onDone, onClose }: { onDone: () => void; onClose: () => void }) {
  const { toast } = useToast();
  const [serverError, setServerError] = React.useState<unknown>(null);
  const {
    register,
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FaqInput>({
    resolver: zodResolver(faqSchema),
    defaultValues: { title: "FAQ", items: [{ q: "", a: "" }] },
  });
  const { fields, append, remove } = useFieldArray({ control, name: "items" });

  async function onSubmit(values: FaqInput) {
    setServerError(null);
    try {
      await apiFetch("/api/bff/sources/faqs", { method: "POST", json: values });
      toast({ tone: "success", title: "FAQ source queued" });
      onDone();
      onClose();
    } catch (e) {
      setServerError(e);
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      <FormErrorAlert error={serverError} />
      <Field label="Title" error={errors.title?.message} required>
        {(a11y) => <Input {...a11y} {...register("title")} />}
      </Field>
      <div className="space-y-3 max-h-[320px] overflow-y-auto pr-1">
        {fields.map((f, i) => (
          <div key={f.id} className="space-y-2 rounded-lg border border-border bg-subtle/60 p-3">
            <div className="flex items-center justify-between">
              <Badge tone="primary">Q&amp;A {i + 1}</Badge>
              {fields.length > 1 && (
                <button
                  type="button"
                  onClick={() => remove(i)}
                  aria-label={`Remove Q&A ${i + 1}`}
                  className="inline-flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-destructive"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
            <Field label="Question" error={errors.items?.[i]?.q?.message} required>
              {(a) => (
                <Input {...a} {...register(`items.${i}.q` as const)} placeholder="What is your return policy?" />
              )}
            </Field>
            <Field label="Answer" error={errors.items?.[i]?.a?.message} required>
              {(a) => (
                <Textarea
                  {...a}
                  {...register(`items.${i}.a` as const)}
                  rows={3}
                  placeholder="We offer a 30-day return window…"
                />
              )}
            </Field>
          </div>
        ))}
      </div>
      {errors.items?.message && (
        <p className="flex items-center gap-1 text-xs text-destructive">
          <AlertCircle className="h-3 w-3" /> {errors.items.message}
        </p>
      )}
      <Button
        type="button"
        variant="secondary"
        size="sm"
        onClick={() => append({ q: "", a: "" })}
        disabled={fields.length >= 200}
      >
        <Plus className="h-4 w-4" /> Add another Q&amp;A
      </Button>
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" loading={isSubmitting}>
          Add FAQ source
        </Button>
      </DialogFooter>
    </form>
  );
}

// --- URL ------------------------------------------------------------------

const urlSchema = z.object({
  url: z.string().trim().url("Enter a full URL, like https://example.com/pricing").max(2000),
});
type UrlInput = z.infer<typeof urlSchema>;

function UrlPanel({ onDone, onClose }: { onDone: () => void; onClose: () => void }) {
  const { toast } = useToast();
  const [serverError, setServerError] = React.useState<unknown>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<UrlInput>({ resolver: zodResolver(urlSchema), defaultValues: { url: "" } });

  async function onSubmit(values: UrlInput) {
    setServerError(null);
    try {
      await apiFetch("/api/bff/sources/url", { method: "POST", json: values });
      toast({ tone: "success", title: "URL queued", description: values.url });
      onDone();
      onClose();
    } catch (e) {
      setServerError(e);
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      <FormErrorAlert error={serverError} />
      <Field
        label="Page URL"
        error={errors.url?.message}
        required
        hint="We fetch this one page. For a whole site, use the Crawl option."
      >
        {(a11y) => <Input {...a11y} {...register("url")} placeholder="https://example.com/help/returns" />}
      </Field>
      <Alert tone="info">
        We check every URL for safety (no internal networks) before fetching. If the host blocks
        automated requests, we&apos;ll surface that honestly.
      </Alert>
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" loading={isSubmitting}>
          Add URL source
        </Button>
      </DialogFooter>
    </form>
  );
}

// --- Crawl ----------------------------------------------------------------

const crawlSchema = z.object({
  root_url: z.string().trim().url("Enter the home page or a section URL.").max(2000),
  max_pages: z.coerce.number().int().min(1).max(200).default(20),
});
type CrawlInput = z.infer<typeof crawlSchema>;

function CrawlPanel({ onDone, onClose }: { onDone: () => void; onClose: () => void }) {
  const { toast } = useToast();
  const [serverError, setServerError] = React.useState<unknown>(null);
  const [crawlId, setCrawlId] = React.useState<string | null>(null);
  const [status, setStatus] = React.useState<CrawlJobResponse | null>(null);
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [importing, setImporting] = React.useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<CrawlInput>({
    resolver: zodResolver(crawlSchema),
    defaultValues: { root_url: "", max_pages: 20 },
  });

  // Poll the crawl job until it's done/failed.
  React.useEffect(() => {
    if (!crawlId || status?.status === "completed" || status?.status === "failed") return;
    const id = window.setInterval(async () => {
      try {
        const next = await apiFetch<CrawlJobResponse>(`/api/bff/crawl-jobs/${crawlId}`);
        setStatus(next);
        if (next.status === "completed") {
          setSelected(new Set(next.discovered_pages.map((p) => p.url)));
        }
      } catch (e) {
        setServerError(e);
      }
    }, 2000);
    return () => window.clearInterval(id);
  }, [crawlId, status?.status]);

  async function onDiscover(values: CrawlInput) {
    setServerError(null);
    setStatus(null);
    try {
      const resp = await apiFetch<{ crawl_job_id: string }>("/api/bff/sources/crawl/discover", {
        method: "POST",
        json: values,
      });
      setCrawlId(resp.crawl_job_id);
      setStatus({ status: "queued", discovered_pages: [], error_code: null });
    } catch (e) {
      setServerError(e);
    }
  }

  async function importSelected() {
    if (!crawlId) return;
    setImporting(true);
    try {
      await apiFetch(`/api/bff/crawl-jobs/${crawlId}/import`, {
        method: "POST",
        json: { selected_urls: Array.from(selected) },
        headers: { "Idempotency-Key": `crawl-import:${crawlId}` },
      });
      toast({ tone: "success", title: "Pages queued", description: `${selected.size} pages are being processed.` });
      onDone();
      onClose();
    } catch (e) {
      setServerError(e);
    } finally {
      setImporting(false);
    }
  }

  function toggle(url: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(url)) next.delete(url);
      else next.add(url);
      return next;
    });
  }

  if (!crawlId) {
    return (
      <form onSubmit={handleSubmit(onDiscover)} className="space-y-4" noValidate>
        <FormErrorAlert error={serverError} />
        <Field label="Root URL" error={errors.root_url?.message} required>
          {(a) => <Input {...a} {...register("root_url")} placeholder="https://example.com" />}
        </Field>
        <Field label="Max pages" error={errors.max_pages?.message}>
          {(a) => <Input {...a} type="number" {...register("max_pages")} min={1} max={200} />}
        </Field>
        <Alert tone="info">
          We&apos;ll check the sitemap first, then fall back to safe same-domain discovery. You&apos;ll
          pick which pages to import after discovery completes.
        </Alert>
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={isSubmitting}>
            Start discovery
            <ArrowRight className="h-4 w-4" />
          </Button>
        </DialogFooter>
      </form>
    );
  }

  const running = status?.status !== "completed" && status?.status !== "failed";

  return (
    <div className="space-y-4">
      <FormErrorAlert error={serverError} />
      {status?.status === "failed" && (
        <Alert tone="danger" title="Discovery failed">
          {ERROR_CODE_COPY[status.error_code ?? ""] ||
            ERROR_COPY[status.error_code ?? ""]?.message ||
            "Try a different starting URL."}
        </Alert>
      )}
      {running && (
        <div className="space-y-2">
          <Progress indeterminate />
          <p className="text-sm text-muted-foreground">Discovering same-domain pages…</p>
        </div>
      )}
      {status?.status === "completed" && (
        <>
          <div className="flex items-center justify-between">
            <p className="text-sm">
              <strong className="text-foreground">{status.discovered_pages.length}</strong> page
              {status.discovered_pages.length === 1 ? "" : "s"} found.
            </p>
            <div className="flex gap-2 text-xs">
              <button
                className="link-subtle"
                onClick={() => setSelected(new Set(status.discovered_pages.map((p) => p.url)))}
                type="button"
              >
                Select all
              </button>
              <span className="text-muted-foreground">·</span>
              <button className="link-subtle" onClick={() => setSelected(new Set())} type="button">
                Clear
              </button>
            </div>
          </div>
          <ul className="max-h-[260px] space-y-1 overflow-y-auto rounded-lg border border-border bg-subtle/60 p-2">
            {status.discovered_pages.map((p) => {
              const checked = selected.has(p.url);
              return (
                <li key={p.url}>
                  <label
                    className={cn(
                      "flex cursor-pointer items-start gap-3 rounded-md px-2 py-2 text-sm transition-colors hover:bg-card",
                      checked && "bg-card"
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggle(p.url)}
                      className="mt-1 h-4 w-4 rounded border-border text-primary focus-visible:ring-2 focus-visible:ring-ring"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{p.title || p.url}</span>
                      <span className="block truncate text-xs text-muted-foreground">{p.url}</span>
                    </span>
                    {checked && <CheckCircle2 className="mt-1 h-4 w-4 text-primary" />}
                  </label>
                </li>
              );
            })}
          </ul>
        </>
      )}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button
          type="button"
          onClick={importSelected}
          disabled={status?.status !== "completed" || selected.size === 0}
          loading={importing}
        >
          Import {selected.size} page{selected.size === 1 ? "" : "s"}
        </Button>
      </DialogFooter>
    </div>
  );
}
