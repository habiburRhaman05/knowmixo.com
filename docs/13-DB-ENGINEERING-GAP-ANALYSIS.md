# Database engineering gap analysis

Reviewed as a senior DB engineer against [05-DATABASE.md](05-DATABASE.md) (target spec) and the live schema at `backend/infra/schema.sql` (actual state). Verdict: the live schema implements roughly **15%** of the target. It is a single-tenant demo schema (`tenant_id text`, no FK graph) with no identity, company, bot, publication, job, or version model. This is not an incremental migration target — it needs a parallel schema built and cut over, not ALTERs on the existing five tables.

## 1. What exists today

```
documents(id, tenant_id text, title, owner_sub, allowed_groups text[], s3_key, status, current_version, created_at)
feedback(id bigserial, tenant_id text, actor text, rating, note, created_at)
audit_events(id bigserial, actor text, tenant_id text, action, detail jsonb, created_at)
approvals(id uuid, tenant_id text, requester, question, status, reviewer, created_at, reviewed_at)
chat_messages(id bigserial, tenant_id text, conversation_id uuid, role, content, created_at)
```

No `users`, no `companies`, no `sessions`, no `bots`, no `publications`, no `jobs`, no `chunks` table (chunks live only in Pinecone), no `visitor_sessions`, no `leads` as a distinct table, no `usage_*` tables. `tenant_id` is a free-text string with no referential integrity — any caller can assert any tenant.

## 2. Structural gaps vs. the target spec

| Gap | Severity | Detail |
| --- | --- | --- |
| No identity tables | Blocker | `users`, `oauth_accounts`, `sessions`, `auth_tokens` do not exist. `owner_sub` on `documents` is a bare text column, not a foreign key — there is nothing it can reference. |
| No tenancy root | Blocker | `tenant_id text` has no backing `companies` row, no `memberships`, no uniqueness, no cascade behavior on company deletion. Tenant isolation today is "trust the string the caller sends." |
| No bot/publication model | Blocker | There is one global `documents` table with no `bots`, no `publications`, no `publication_sources`. The spec's core safety property — "a publication references immutable source versions, draft never leaks into active snapshot" — has no table to enforce it. |
| No document versioning | Blocker | `documents.current_version` is an integer counter with no `document_versions` row behind it — no checksum, no per-version status/stage, no `ready_at`, no way to know which version is actually searchable. Re-upload/replace semantics described in the PRD are unimplementable on this table. |
| No chunk manifest | High | `vector.py` presumably upserts directly to Pinecone with no PostgreSQL `chunks` table reconciling expected vs. actual vector count. The spec requires a chunk manifest precisely so partial upserts can't silently become "ready." |
| No durable job system | Blocker | No `jobs` or `job_attempts` tables. `documents.status` is a bare enum with no attempt count, no lease, no `available_at`, no idempotency key. A worker crash mid-processing has no recoverable state. |
| No visitor session model | Blocker | Public chat has no `visitor_sessions` table — nothing to scope a visitor token to a bot, record expiry, or revoke. |
| `conversations` table missing entirely | Blocker | Only `chat_messages` exists, keyed by a bare `conversation_id uuid` with no owning `conversations` row. There is no `owner_user_id`/`visitor_session_id`/`publication_id`/`context_scope` to authorize against. Message `status` (`pending/streaming/completed/failed/interrupted`) and `generation_id` do not exist — the SSE interruption/retry semantics in 03-TRD.md cannot be persisted. |
| `leads` not modeled | Medium | No table at all; PRD section G/K requires skippable name/email capture tied to a conversation with consent timestamp. |
| `usage_reservations` / `usage_daily` missing | High | Quota enforcement described in 04-STACK and 03-TRD ("reserve a global generation budget atomically... fail closed when quota state is unknown") has no backing table. Without this, `FREE_ONLY` budget enforcement is just application-memory state that resets on restart and races under concurrent requests. |
| `feedback` keyed on `actor text`, not `message_id` | High | Spec requires feedback to reference `message_id` plus `visitor_session_id` **or** `owner_user_id`, unique per actor/message. Current table has no FK to any message and no uniqueness constraint — duplicate/spoofed feedback is possible today. |
| `audit_events` has no `request_id` or `target_id` | Medium | Spec wants `company_id nullable, actor_id, action, target_id, request_id, safe_metadata`. Current table only has `actor text` (not a real user FK) and `detail jsonb` with no `request_id` for tracing. |
| `approvals` table is dead weight for V1 | Low | PRD explicitly excludes "LLM-driven destructive actions" and HITL approval execution. This table belongs to the old Bedrock demo, not the Knowmivo scope — either drop it or explicitly mark it legacy/unused rather than migrate it. |
| No UUID defaults on most tables | Medium | Only `approvals.id` has `DEFAULT gen_random_uuid()`. `documents.id` is `uuid PRIMARY KEY` with no default — the app must be generating IDs client-side today, which is fine, but it must stay consistent once Alembic owns these tables. |
| `chunks.text` location undecided | Medium | Spec explicitly says "store document text separately so the vector store remains replaceable," allowing `text` inline or `text_ref` to private storage. Nothing in the current schema stores extracted chunk text in PostgreSQL at all — today chunk text only exists inside Pinecone metadata/the vector call, which means Pinecone is accidentally the system of record for content, contradicting the spec's replaceability goal. |

## 3. Index and constraint gaps

- **No composite tenant-scoped indexes anywhere except `documents_acl_idx` and `audit_tenant_time`.** The target spec requires jobs indexed by due-state/`available_at`/lease-expiry, messages by conversation/time, sessions by user/expiry — none of this exists because the tables themselves don't exist yet.
- **No unique constraints enforcing the invariants the PRD depends on**: `oauth_accounts(provider, provider_subject)`, `memberships(company_id, user_id)`, `document_versions(document_id, version)`, `chunks(version_id, ordinal)`, `chunks.vector_id` unique, `jobs.idempotency_key` unique, `sessions.token_hash` unique, `auth_tokens.token_hash` unique. Every one of these is a concrete security or correctness property (e.g., token hash uniqueness prevents collision-based session confusion) that currently has zero database-level enforcement.
- **No foreign keys at all in the live schema** except the implicit UUID column shapes. `documents.tenant_id`, `feedback.tenant_id`, `audit_events.tenant_id` are unconstrained text — a typo'd tenant ID silently creates a new "tenant" with no error.
- **`chat_messages.role` CHECK only allows `('user','assistant')`** — the target status model needs `role` plus a separate `status` enum (`pending/streaming/completed/failed/interrupted`); conflating role and lifecycle state in one table with no status column means the API cannot represent "this message is still streaming."

## 4. Data-integrity risks specific to this domain

1. **Cross-tenant leakage by construction, not by bug.** Because `tenant_id` is a free string with no FK and no RLS, any query that forgets a `WHERE tenant_id = :t` clause doesn't fail — it just returns another tenant's rows. The spec correctly notes RLS is defense-in-depth, not a substitute for API authorization, but right now there is neither.
2. **Partial-ingestion-becomes-visible risk.** With no `document_versions.status`/`chunks` manifest, there is no DB-enforced way to distinguish "upsert in progress" from "ready." The current `documents.status` enum is updated by whichever process touches it last — a race between a worker retry and a manual refresh can flip status backward or mark a document ready with zero reconciled chunks.
3. **No immutable publication snapshot.** Without `publications`/`publication_sources`, "unpublish blocks new visitor sessions immediately" and "draft replacement never leaks into the active snapshot" (acceptance criterion H) are *behavioral promises with no data model to keep them*. Today there is nothing to snapshot — `documents` is mutated in place.
4. **Session revocation has no table to revoke.** Acceptance criterion A requires "logout-all immediately blocks old backend tokens." There is no `sessions` table, so there is nothing to revoke — any session semantics today must be living in a JWT with no server-side kill switch, which directly contradicts the opaque-backend-token design in 03-TRD.md.

## 5. Recommended path (DB engineering judgment)

Do not attempt to ALTER the existing five tables into the target shape — the shapes are fundamentally incompatible (`tenant_id text` vs. `company_id uuid FK`, no versioning vs. versioned documents, no job table vs. durable queue). Instead:

1. **Phase 1 migration**: create the full target schema (users → … → audit_events, per 05-DATABASE.md) as new tables under Alembic, additive, alongside the legacy five.
2. **Phase 2 cutover**: point `app/` and `worker/` at the new tables exclusively once auth/company/bot code lands (Sprint 1–2 below). Do not attempt a live data migration of the legacy `documents`/`chat_messages` rows — there is no real tenant/user data behind them (`owner_sub`/`actor` are demo placeholders), so a backfill would be migrating fictional demo rows, not real customer data.
3. **Phase 3 cleanup**: drop `approvals` (out of V1 scope) and the legacy five tables once Phase 2 is verified in a non-prod environment, documented as a destructive migration requiring explicit sign-off per [11-AGENT-RULES.md](11-AGENT-RULES.md) rule 3.
4. **Enforce every uniqueness/FK constraint from 05-DATABASE.md at creation time**, not added later — retrofitting uniqueness onto a populated table risks constraint-violation failures that are harder to triage than defining them up front.
5. **Add `request_id` to `audit_events` and `messages` from day one** — distributed tracing across BFF → FastAPI → worker → provider is explicitly required by the TRD's streaming/error semantics, and it is far cheaper to add a column before any row exists than to backfill it.

This gap analysis is the input to the sprint plan below — Sprint 0/1 is entirely blocked on building this schema before any application code in `app/` can use real identity or tenancy.
