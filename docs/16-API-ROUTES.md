# Full API route specification

Base path `/api/v1`. Expands [06-API.md](06-API.md) into an implementation-ready route list. All IDs are opaque strings (UUID, not exposed as sequential). Owner routes require a backend bearer session forwarded by the Next.js BFF; `public/*` routes require a visitor token obtained from bootstrap. Company/bot scope is always derived from the authenticated session — never from a body/query parameter. Every response includes `request_id`. Errors: `{code, message, retry_after_seconds?, fields?}`.

Standard status codes used throughout: `400` malformed request, `401` unauthenticated, `403` unauthorized, `404` inaccessible/not found, `409` conflict (revision/idempotency), `413` payload too large, `422` validation failure, `429` rate/quota limit, `503` dependency unavailable.

## Auth

| Method | Path | Auth | Body | Response | Notes |
| --- | --- | --- | --- | --- | --- |
| POST | /auth/signup | none | `{email, password, name}` | `202 {status:"verify_email_sent"}` | Always same shape regardless of existing account |
| POST | /auth/login | none | `{email, password}` | `200 {}` + session cookie set via BFF | 401 on bad credentials; 403 if unverified and attempting owner-only action downstream |
| POST | /auth/google | none | `{id_token}` | `200 {}` + session | Validates audience/issuer/expiry/verified-email against Google independently |
| POST | /auth/verify-email | none | `{token}` | `200 {}` | Single-use, short-lived; 410 if consumed/expired |
| POST | /auth/resend-verification | rate-limited, none | `{email}` | `202 {}` | Generic response; cooldown enforced server-side |
| POST | /auth/forgot-password | rate-limited, none | `{email}` | `202 {}` | Generic response regardless of account existence |
| POST | /auth/reset-password | none | `{token, new_password}` | `200 {}` | Revokes all prior sessions on success |
| POST | /auth/change-password | session | `{current_password, new_password}` | `200 {}` | Requires recent reauthentication |
| POST | /auth/logout | session | — | `204` | Revokes current session only |
| POST | /auth/logout-all | session | — | `204` | Revokes every session for the user immediately |

## Profile and OAuth linking

| Method | Path | Auth | Body | Response | Notes |
| --- | --- | --- | --- | --- | --- |
| GET | /me | session | — | `200 {id, email, name, avatar_url, email_verified_at}` | |
| PATCH | /me | session | `{name?, avatar_key?}` | `200 {}` | |
| DELETE | /me | session + reauth | `{confirm:true}` | `202 {cleanup_status_url}` | Immediate session/publication revocation; async cleanup tracked |
| POST | /me/email-change | session + reauth | `{new_email}` | `202 {}` | Sends verification to new address |
| POST | /me/email-change/confirm | none | `{token}` | `200 {}` | Old email stays active until confirmed |
| POST | /me/oauth/google/link | session + reauth | `{id_token}` | `200 {}` | Explicit linking only; never implicit email-match linking |

## Company

| Method | Path | Auth | Body | Response | Notes |
| --- | --- | --- | --- | --- | --- |
| GET | /company | session | — | `200 {name, website, industry, contact, logo_key}` | |
| POST | /company | session | `{name, industry?, website?}` | `201 {}` | One company per owner in V1 |
| PATCH | /company | session (owner) | `{name?, website?, industry?, contact?, logo_key?}` | `200 {}` | |
| GET | /company/export | session (owner) | — | `200` file stream | Excludes provider secrets by construction |

## Dashboard / usage

| Method | Path | Auth | Body | Response | Notes |
| --- | --- | --- | --- | --- | --- |
| GET | /dashboard | session | — | `200 {setup_checklist, source_counts_by_state, conversation_count, usage_summary}` | |
| GET | /usage | session | — | `200 {company_daily, global_daily, quota_state, next_reset_at}` | No paid-upgrade fields |

## Document uploads and other sources

| Method | Path | Auth | Body | Response | Notes |
| --- | --- | --- | --- | --- | --- |
| POST | /documents/uploads | session | `{filename, content_type, size_bytes}` | `201 {grant_id, upload_url, expires_at}` | Scoped, short-lived, size-capped grant |
| PUT | /uploads/{grant_id} | grant token | raw bytes | `200 {}` | Streamed to private temp storage; size/MIME re-validated server-side |
| POST | /documents/{id}/complete | session, idempotency key | `{grant_id, checksum}` | `202 {job_id}` | Idempotent; creates source version + job in one transaction |
| POST | /sources/text | session | `{title, text}` | `202 {document_id, job_id}` | |
| POST | /sources/faqs | session | `{title, items:[{q,a}]}` | `202 {document_id, job_id}` | |
| POST | /sources/url | session | `{url}` | `202 {document_id, job_id}` | SSRF-validated server-side fetch |
| POST | /sources/crawl/discover | session | `{root_url, max_pages?}` | `202 {crawl_job_id}` | Async; capped same-domain, sitemap-aware |
| GET | /crawl-jobs/{id} | session | — | `200 {status, discovered_pages:[{url,title}]}` | |
| POST | /crawl-jobs/{id}/import | session, idempotency key | `{selected_urls:[...]}` | `202 {document_ids, job_ids}` | Bounded selection creates per-page sources |

## Source management

| Method | Path | Auth | Body | Response | Notes |
| --- | --- | --- | --- | --- | --- |
| GET | /documents | session | query: `state?, type?, q?, cursor?` | `200 {items, next_cursor}` | |
| GET | /documents/{id} | session | — | `200 {title, type, status, current_version, stage, error_code?}` | |
| PATCH | /documents/{id} | session | `{title?}` | `200 {}` | |
| DELETE | /documents/{id} | session | — | `202 {}` | Immediate access revocation; queued physical/vector cleanup |
| GET | /documents/{id}/content | session | — | `200 {preview_text, pages_or_headings}` | Extracted text preview, not raw file passthrough |
| POST | /documents/{id}/refresh | session, idempotency key | — | `202 {job_id}` | Creates a new version; old version stays active until new one is ready |

## Jobs

| Method | Path | Auth | Body | Response | Notes |
| --- | --- | --- | --- | --- | --- |
| GET | /jobs/{id} | session | — | `200 {state, stage, attempts, error_code?, available_at?}` | Owner-scoped only |
| POST | /jobs/{id}/retry | session, idempotency key | — | `202 {new_attempt_generation}` | Safe replay; validates current source version |

## Bot configuration, publishing, embed

| Method | Path | Auth | Body | Response | Notes |
| --- | --- | --- | --- | --- | --- |
| GET | /bot | session | — | `200 {draft_config, draft_revision, active_publication_id}` | |
| PATCH | /bot | session | `{draft_revision, config_patch}` | `200 {}` / `409` | Optimistic concurrency on `draft_revision` |
| POST | /bot/publish | session, idempotency key | `{selected_document_version_ids}` | `201 {publication_id, version}` | Rejects if any selected version is not `ready` |
| POST | /bot/unpublish | session | — | `200 {}` | Immediately denies new visitor sessions |
| PUT | /bot/domains | session | `{allowed_domains:[...]}` | `200 {}` | |
| GET | /bot/embed | session | — | `200 {script_snippet, react_snippet, nextjs_snippet, hosted_chat_url}` | Public IDs only, no secrets |
| GET | /bot/export | session | — | `200` file | Config snapshot, no credentials |
| POST | /bot/preview/conversations | session | — | `201 {conversation_id}` | Authenticated draft scope |
| POST | /bot/preview/chat | session | `{conversation_id, message}` | `200` SSE | Same pipeline as public chat, draft scope |

## Visitor bootstrap and chat (public)

| Method | Path | Auth | Body | Response | Notes |
| --- | --- | --- | --- | --- | --- |
| GET | /public/bots/{public_id}/config | origin-checked | — | `200 {name, branding, greeting, suggestions, lead_capture_enabled}` | Only from an active publication; 404 if unpublished |
| POST | /public/bots/{public_id}/sessions | origin-checked | — | `201 {visitor_token, expires_at}` | Bot-scoped, short-lived, never an owner token |
| POST | /public/conversations | visitor token | — | `201 {conversation_id}` | Visitor owns the conversation |
| POST | /public/conversations/{id}/messages | visitor token, idempotency key | `{text}` | `200` SSE (`meta/delta/sources/done/error`) | Server selects published scope; abort-safe |
| POST | /public/conversations/{id}/lead | visitor token | `{name?, email?, consent:true}` | `201 {}` | Skippable; consent timestamp recorded |
| POST | /public/messages/{id}/feedback | visitor token or session | `{rating, comment?}` | `201 {}` | Unique per actor/message; message must be in authorized scope |

## Conversation history (owner)

| Method | Path | Auth | Body | Response | Notes |
| --- | --- | --- | --- | --- | --- |
| GET | /conversations | session | query: `date_from?, date_to?, status?, has_feedback?, cursor?` | `200 {items, next_cursor}` | |
| GET | /conversations/{id} | session | — | `200 {messages, citations, lead, status}` | Owner-scoped; 403/404 on ID substitution |
| DELETE | /conversations/{id} | session | — | `202 {}` | Cascades to messages, leads, cached answers |
| GET | /conversations/{id}/export | session | — | `200` file | Excludes secrets |

## Health

| Method | Path | Auth | Response | Notes |
| --- | --- | --- | --- | --- |
| GET | /health/live | none | `200 {}` | Local-only check, no dependency calls |
| GET | /health/ready | none | `200 {}` / `503 {failing_dependencies}` | Checks Postgres/Redis/Pinecone reachability, never a paid generation call |

## Cross-cutting conventions

- **Idempotency**: required on `documents/{id}/complete`, `crawl-jobs/{id}/import`, `bot/publish`, `jobs/{id}/retry`, and every `public/conversations/{id}/messages` send — pass an `Idempotency-Key` header; replays with the same key return the original result, never a duplicate side effect.
- **Pagination**: cursor-based (`cursor`/`next_cursor`), never offset — avoids skipped/duplicated rows under concurrent writes on `documents` and `conversations`.
- **Avatar/logo uploads**: reuse the `/documents/uploads` grant abstraction but route through an image-decode + dimension-limit + private-to-public validation step before any asset is served publicly — never expose an arbitrary uploaded file as static content.
- **SSE transport**: POST with fetch-readable streams, not GET/EventSource. `Content-Type: text/event-stream`, no intermediary buffering, heartbeats, ordered `seq` numbers, terminal `done`/`error` always sent on a connected stream.
- **Error-code stability**: `error_code` values on jobs/documents/messages are a fixed enum (e.g., `unsupported_scanned_pdf`, `quota_exhausted`, `extraction_empty`, `ssrf_blocked`) — frontend branches on these codes, never on free-text `message`.
