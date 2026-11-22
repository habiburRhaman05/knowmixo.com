# Backend architecture: current state vs. target, module by module

This supersedes nothing in [08-BACKEND-GAP-MAP.md](08-BACKEND-GAP-MAP.md) — it adds direct code-level findings from reading the actual files, and maps each gap to the sprint that closes it.

## Current reality in one paragraph

`backend/` is a 603-line AWS Bedrock teaching demo ("Atlas Enterprise AI"), not a partially-built SaaS backend. Every request resolves to a hardcoded `Principal(subject="demo-operator", tenant="demo-workspace", admin=True)` — there is no code path, today, that can fail authorization, because authorization doesn't exist. `app/config.py` has no auth, email, Cloudflare, OpenRouter, or local-storage settings — only AWS/Pinecone/Postgres. The schema has no identity, company, bot, publication, or job tables (detailed in [13-DB-ENGINEERING-GAP-ANALYSIS.md](13-DB-ENGINEERING-GAP-ANALYSIS.md)). Treat this as a reference architecture to study, not a codebase to incrementally patch into production.

## Module-by-module findings

### `app/demo_context.py` (11 lines) — **replace entirely, Sprint 1**
```python
def principal() -> Principal:
    return Principal()  # always admin, always same tenant
```
Every endpoint that calls `principal()` today is, by construction, unauthenticated and over-privileged. This is the single highest-severity finding in the whole codebase: it's not a bug to fix, it's the absence of the feature the entire product depends on. Sprint 1 must delete this function from any production import path and replace it with a dependency that resolves an opaque session token → `sessions` row → `users` row → `memberships` row, failing closed (401/403) at every step.

### `app/config.py` (27 lines) — **extend substantially, Sprint 1–2**
Current fields: AWS region/keys, S3 bucket, Bedrock model IDs, Pinecone, upload byte cap, HITL flag, memory turns. Missing entirely: `FREE_ONLY` flag and startup validation that refuses to boot with paid providers enabled in production; Cloudflare account/token/model/dimension; OpenRouter key/model/allowlist; local storage path; SMTP/email settings; `GOOGLE_CLIENT_ID`/secret; `AUTH_SECRET`; session lifetime; job runner tuning (`JOB_MAX_ATTEMPTS`, lease seconds); retention days; quota limits (global/company daily). Per 11-AGENT-RULES.md rule 6, the startup check that "fails closed when quota state is unknown" and refuses unsafe production defaults needs to live here, and does not exist today in any form.

### `app/aws.py` (44 lines) — **replace with provider adapters, Sprint 2, 4**
This is a direct boto3 client wrapper (Bedrock Titan embeddings, Bedrock Nova Lite chat). The target architecture needs two swappable *protocols* — `EmbeddingProvider` and `ChatProvider` — with Cloudflare Workers AI and OpenRouter as the only enabled implementations in free-tier deployment. Keep the Bedrock implementation only as an optional, explicitly-disabled-by-default adapter behind `FREE_ONLY=false` for a future paid tier; it must not be reachable when `FREE_ONLY=true`.

### `app/vector.py` (69 lines) — **extend with validation and lifecycle, Sprint 2, 3**
Handles Pinecone client setup, namespacing, and upsert. What's missing, concretely: (1) no validation that the embedding response's dimension matches `EMBEDDING_DIM` before upsert — a silent provider schema change would upsert corrupt vectors; (2) no reconciliation against a PostgreSQL chunk manifest, so there's no way to detect a partial upsert; (3) no deletion-fencing — nothing stops a slow in-flight upsert from writing vectors for a document version that was deleted moments ago; (4) metadata shape needs to carry `company_id, bot_id, document_id, version_id, chunk_id, page, embedding_model` for every authorization check downstream in retrieval, and currently carries whatever the Bedrock-era demo needed, which is not documented to match.

### `app/graph.py` (74 lines) — **rework the state and streaming contract, Sprint 4**
LangGraph orchestration skeleton exists, which is genuinely reusable structurally. Two concrete problems found: the TRD explicitly flags "unconditional last-question concatenation" as the current history handling — i.e., multi-turn context is naively appended rather than bounded/authorized per message, which is both a correctness and a prompt-injection surface issue. Second, there's no typed state carrying authorized `company_id`/`bot_id`/publication snapshot through the graph — retrieval has nothing to scope itself against except whatever the caller (today, always the demo principal) passed in.

### `worker/ingest.py` (73 lines) — **rebuild as a durable job runner, Sprint 2 (the sprint's core deliverable)**
Has real, reusable logic for PDF/DOCX parsing and a "stable vector ID" naming idea — worth keeping as a starting point for the parser layer. Missing everything that makes ingestion safe: no claim/lease mechanism (there is no `jobs` table to claim from), no checkpointing (a crash mid-file restarts from zero, not from a validated checkpoint), no retry/backoff classification, no quota-wait state, and no fencing to stop a stale worker from finalizing a version a newer attempt already superseded. This file today assumes synchronous, single-attempt, never-crashes execution — the opposite of the target's explicit crash-recovery requirement.

### `app/db.py` (19 lines) — **replace with a real data-access layer, Sprint 1 onward**
19 lines of parameterized SQL helpers over a raw connection, no pool management, no transaction helpers, no repository pattern. Every sprint from 1 onward needs transactional multi-statement writes (e.g., Sprint 1's "create session + consume token" or Sprint 2's "create document_version + job in one transaction, notify Redis only after commit" from the TRD). This file cannot support that today — it needs a connection-pool-backed layer with explicit transaction boundaries before Sprint 1 can finish.

### `app/memory.py` (23 lines) — **replace with conversation/message state machine, Sprint 4**
Currently just persists message rows with role `user`/`assistant` into `chat_messages`. No ownership scoping, no `status` lifecycle (`pending/streaming/completed/failed/interrupted`), no `generation_id` to prevent duplicate-text retries. This needs a full rewrite against the new `conversations`/`messages` tables from Sprint 4's migration, not an extension.

### `app/main.py` (185 lines) — **split into routers, Sprint 1–5**
Single flat file mixing routing, UI serving, and (implicitly) business logic for the old demo's documents/chat/approvals/admin routes. Target architecture per 08-BACKEND-GAP-MAP.md: split into `auth`, `company`, `sources`, `bot`, `public`, `conversations` routers, each depending on the real principal dependency, each returning the typed error contract from [16-API-ROUTES.md](16-API-ROUTES.md). This file's current routes (`/api/documents/*`, `/api/chat`, `/api/approvals/*`, `/api/admin/*`) do not match the target route table at all — they are being replaced, not renamed.

### `app/guardrails.py` (47 lines) — **keep as a starting point, extend Sprint 4**
Deterministic input/output checks exist. Needs extension for the prompt-injection fixture suite (Sprint 4) and an explicit statement that regex guardrails are not a confidentiality guarantee — buffered whole-response review is required only where moderation is mandated (per TRD streaming section), and this file doesn't yet distinguish streamed vs. buffered paths.

### `app/observability.py` (30 lines) — **make fully optional, Sprint 6**
Glassflow Rius integration, currently a `requirements.txt` dependency. Target: structured redacted logging by default, Rius fully optional and never required or paid by default. Confirm no document text or provider key can reach a trace span (the redaction gap analysis belongs in Sprint 6's logging audit).

### `app/rag.py` (1 line) — **effectively unimplemented**
Essentially a stub. Whatever RAG orchestration exists lives in `graph.py` instead; this file needs either real content (if it's meant to hold the retrieval-authorization validation step from the TRD) or removal once the Sprint 4 retrieval pipeline lands, to avoid a second, unused "source of truth" file confusing future contributors.

### `requirements.txt` — **prune and add, Sprint 1–2**
Remove `boto3` (once Cloudflare/OpenRouter adapters replace Bedrock calls) and `glassflow-rius` from the default/required set (make it optional-extra). Add: `alembic`, `argon2-cffi`, a maintained Google token verification library, `pytest`/`pytest-asyncio`/`httpx` test extras, and multipart/streaming upload support. Pin every version — the current file already pins most entries, which is good practice to continue.

### `test.py` / `test/bedrock_test.py` — **remove from default CI, Sprint 1**
These make live external Bedrock calls. Per 11-AGENT-RULES.md rule 6 ("no default live external API calls in tests"), these must not run in default CI. Replace with the isolated-Postgres-fixture + provider-fake test suites specified per sprint above.

## Priority-ordered fix list (first five things to build, in order)

1. **Alembic + target schema** (Sprint 1) — nothing else is buildable without real tables.
2. **Real principal/session dependency, deleting the demo context from any reachable route** (Sprint 1) — the authorization foundation every other sprint assumes exists.
3. **Transactional data-access layer in `db.py`** (Sprint 1) — required by both auth (session+token consumption) and ingestion (version+job creation).
4. **Durable job runner replacing `worker/ingest.py`'s synchronous assumptions** (Sprint 2) — the TRD's crash-recovery requirement is unimplementable without this, and it is the component most likely to hide a silent data-integrity bug if built last instead of early.
5. **Cloudflare/OpenRouter provider adapters replacing `app/aws.py`** (Sprint 2/4) — needed before any ingestion or chat test can run against anything other than a mocked response, and per agent rule 13, a feature must not be marked complete while backed by mocks.

## What to explicitly keep (don't rewrite for its own sake)

- PDF/DOCX parsing logic in `worker/ingest.py` — extend with token-aware chunking and checkpoints, don't discard.
- LangGraph orchestration skeleton in `app/graph.py` — rework the state shape and history handling, keep the graph structure.
- Guardrail check scaffolding in `app/guardrails.py` — extend, don't replace.
- Pinecone client setup in `app/vector.py` — add validation/reconciliation around the existing upsert call, don't re-architect the Pinecone integration itself.

This keeps the rebuild scoped to what's actually broken (identity, tenancy, durability, provider lock-in) rather than a wholesale rewrite of working parsing/orchestration logic.
