# API contracts

Use `/api/v1`. Owner endpoints require a backend bearer session forwarded by the BFF. Public bot routes require a visitor token after bootstrap. All IDs are opaque. Derive company access from the session rather than trusting a body company ID. Return typed JSON with `request_id`. Error responses contain `code`, safe `message`, optional `retry_after_seconds` and field errors.

| Area | Routes | Contract |
| --- | --- | --- |
| Identity | POST /auth/signup, /auth/login, /auth/google | Signup sends verification mail. Login returns server-consumed opaque session. Google verifies ID token. |
| Email/password | POST /auth/verify-email, /auth/resend-verification, /auth/forgot-password, /auth/reset-password, /auth/change-password | Rate-limited, single-use tokens, generic account-existence responses where relevant |
| Sessions | POST /auth/logout, /auth/logout-all | Revoke canonical backend sessions |
| Profile | GET/PATCH/DELETE /me, POST /me/email-change, POST /me/email-change/confirm | Verified email changes, reauthentication and tracked deletion |
| OAuth linking | POST /me/oauth/google/link | Explicit authenticated linking with fresh verified Google identity |
| Company | GET/POST/PATCH /company, GET /company/export | One owned company in V1 |
| Dashboard | GET /dashboard, GET /usage | Authorized counts and quota state |
| Uploads | POST /documents/uploads, PUT /uploads/{grant_id}, POST /documents/{id}/complete | Upload grant is scoped, short-lived and size capped. Complete is idempotent and returns 202 job_id. |
| Other sources | POST /sources/text, /sources/faqs, /sources/url, /sources/crawl/discover | URL/crawl fetch happens asynchronously with SSRF checks |
| Crawl selection | GET /crawl-jobs/{id}, POST /crawl-jobs/{id}/import | Select bounded discovered pages, create per-page sources/jobs |
| Source management | GET /documents, GET/PATCH/DELETE /documents/{id}, GET /documents/{id}/content, POST /documents/{id}/refresh | Deletion revokes immediately, replacement creates a new version |
| Jobs | GET /jobs/{id}, POST /jobs/{id}/retry | Owner-scoped safe progress and idempotent replay |
| Bot | GET/PATCH /bot, POST /bot/publish, POST /bot/unpublish | PATCH uses draft revision conflict control. Publish receives selected ready version IDs. |
| Domain/embed | PUT /bot/domains, GET /bot/embed, GET /bot/export | Script snippet and hosted link contain public IDs only |
| Owner preview | POST /bot/preview/conversations, POST /bot/preview/chat | Authenticated draft scope, SSE chat |
| Visitor bootstrap | GET /public/bots/{public_id}/config, POST /public/bots/{public_id}/sessions | Published sanitized config and expiring bot-scoped visitor token |
| Visitor chat | POST /public/conversations, POST /public/conversations/{id}/messages | SSE, visitor owns conversation, server selects published scope |
| Leads/feedback | POST /public/conversations/{id}/lead, POST /public/messages/{id}/feedback | Optional consented lead and authorized message reference |
| History | GET /conversations, GET/DELETE /conversations/{id}, GET /conversations/{id}/export | Owner scope, bounded cursor pagination and filters |
| Health | GET /health/live, GET /health/ready | Liveness local. Readiness checks critical dependencies without paid generation calls. |

For avatar/logo use the same restricted upload abstraction with image decoding, dimension limits and private-to-public asset validation. Do not expose arbitrary uploaded files as public static content.

## SSE example

```text
event: meta
data: {"message_id":"m1","request_id":"r1","seq":0}

event: delta
data: {"text":"Our company is Knowmivo.","seq":1}

event: sources
data: {"items":[{"source_id":"s1","title":"Company profile","page":1}],"seq":2}

event: done
data: {"status":"completed","seq":3}

```

Send `Content-Type: text/event-stream`, prevent intermediary buffering and use heartbeats. Source download/view links require signed scoped access or a safe preview, not raw filesystem paths. Public citations must never contain owner-only storage URLs. A stream error has a safe code and retryability flag. Provider credentials, prompts and internal stack traces never go to the client.

Mutations support idempotency keys for source completion, import, publication, retry and chat start. Standard failures include 401 unauthenticated, 403 unauthorized, 404 inaccessible resource, 409 revision conflict, 413 too large, 422 validation failure, 429 rate/quota limit and 503 unavailable. Bootstrap origin validation supplements bot/token validation and is not proof of a human visitor's identity.
