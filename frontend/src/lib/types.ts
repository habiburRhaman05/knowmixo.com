/**
 * Response types for the backend data this frontend reads. Kept in one
 * file so a schema drift is one edit, not a hunt. These mirror
 * backend/openapi.yaml but we only type the fields we actually consume --
 * extra unknown fields pass through harmlessly.
 */

export type DocumentStatus =
  | "pending"
  | "processing"
  | "retrying"
  | "quota_wait"
  | "ready"
  | "failed"
  | "retired";

export type DocumentKind = "file" | "text" | "faq" | "url" | "crawl_page";

export type DocumentStage =
  | "validate"
  | "extract"
  | "chunk"
  | "embed"
  | "upsert"
  | "finalize"
  | null;

export type DocumentRow = {
  id: string;
  type: DocumentKind;
  title: string;
  source_url: string | null;
  status: DocumentStatus | null;
  stage: DocumentStage;
  error_code: string | null;
  current_version: number | null;
  version_id: string | null;
  chunk_count: number | null;
  ready_at: string | null;
  created_at: string;
};

export type DocumentListResponse = {
  items: DocumentRow[];
  next_cursor: string | null;
};

export type DocumentDetail = DocumentRow;

export type DocumentContent = {
  title: string;
  preview_text: string;
  truncated: boolean;
  pages_or_headings: Array<{ page: number | null; heading: string | null }>;
};

export type JobRow = {
  id: string;
  kind: string;
  state: "queued" | "processing" | "quota_wait" | "succeeded" | "dead";
  stage: string | null;
  attempts: number;
  max_attempts: number;
  error_code: string | null;
  available_at: string | null;
};

export type UploadGrantResponse = {
  document_id: string;
  version_id: string;
  grant_id: string;
  upload_url: string;
  expires_at: number;
  max_bytes: number;
};

export type CrawlJobResponse = {
  status: "queued" | "running" | "completed" | "failed";
  discovered_pages: Array<{ url: string; title: string }>;
  error_code: string | null;
};

export type BotResponse = {
  id: string;
  public_id: string;
  draft_config: Record<string, unknown>;
  draft_revision: number;
  active_publication_id: string | null;
};

export type LeadFormResponse = {
  id: string;
  name: string;
  trigger: string;
  is_required: boolean;
  fields: Array<{
    field_key: string;
    label: string;
    field_type: string;
    is_required: boolean;
    sort_order: number;
  }>;
};

export type EmbedResponse = {
  public_id: string;
  script_snippet: string;
  react_snippet: string;
  nextjs_snippet: string;
  hosted_chat_url: string;
};

export type ConversationListItem = {
  id: string;
  status: "active" | "closed";
  created_at: string;
  updated_at: string;
  message_count: number;
  has_feedback: boolean;
  has_lead: boolean;
};

export type ConversationListResponse = {
  items: ConversationListItem[];
  next_cursor: string | null;
};

export type ConversationMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: string;
  citations: Array<{
    index: number;
    document_id: string;
    title: string;
    page: number | null;
    excerpt?: string;
  }>;
  feedback_rating: number | null;
  created_at: string;
};

export type ConversationDetail = {
  id: string;
  status: string;
  created_at: string;
  messages: ConversationMessage[];
  citations: ConversationMessage["citations"];
  lead: {
    values: Record<string, string>;
    consent_at: string | null;
    submitted_at: string;
  } | null;
};

/** Visual status descriptor + user-facing label for each status code. */
export const STATUS_META: Record<
  DocumentStatus,
  { label: string; tone: "ready" | "processing" | "waiting" | "failed" | "idle" }
> = {
  pending: { label: "Queued", tone: "idle" },
  processing: { label: "Processing", tone: "processing" },
  retrying: { label: "Retrying", tone: "waiting" },
  quota_wait: { label: "Quota paused", tone: "waiting" },
  ready: { label: "Ready", tone: "ready" },
  failed: { label: "Failed", tone: "failed" },
  retired: { label: "Retired", tone: "idle" },
};

/** Stage name for the progress strip inside a processing source. */
export const STAGE_LABEL: Record<NonNullable<DocumentStage>, string> = {
  validate: "Validating",
  extract: "Extracting text",
  chunk: "Chunking",
  embed: "Embedding",
  upsert: "Indexing",
  finalize: "Finalizing",
};

/** User-safe messages for error_code values the backend surfaces. */
export const ERROR_CODE_COPY: Record<string, string> = {
  unsupported_scanned_pdf:
    "This PDF looks scanned (image-only). Convert it to text first, or upload a text version.",
  unsupported_file_type: "This file type isn't supported. Try PDF, DOCX, TXT or Markdown.",
  file_too_large: "The file exceeds the size limit for your plan.",
  extraction_empty: "We couldn't extract any text from this source.",
  ssrf_blocked: "That URL isn't reachable from our servers for safety reasons.",
  quota_exhausted: "Free-tier limit reached. The job will resume after the daily reset.",
  embedding_quota_exhausted: "Embedding quota reached. The job will retry automatically.",
  checksum_mismatch: "The upload didn't match the expected checksum. Try again.",
  grant_expired: "The upload grant expired before the file was received. Try the upload again.",
  file_signature_mismatch: "The file's content doesn't match its declared type.",
  no_pages_discovered: "No pages were found at that URL.",
  crawl_not_ready: "Crawl discovery hasn't completed yet.",
  page_not_discovered: "Selected pages must come from this crawl's discovered list.",
};
