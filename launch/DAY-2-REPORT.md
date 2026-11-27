# Day 2 report

Date: 2026-11-26.

## Day-2 gate — RESULT: **GREEN**

| # | Check | Result | Evidence |
| --- | --- | --- | --- |
| G1 | RLS everywhere (D2.1) | ✅ | 26 tenant tables + `companies` have RLS policies; `test/api/test_rls_fail_closed.py` 7/7 green against `app_user` directly |
| G2 | Provider router (D2.2) | ✅ | `app/providers/{base,router,groq_chat,openrouter_chat}.py` — ordered fallback chain, `free_only` default = Groq-only |
| G3 | API conventions + TS client (D2.3) | ✅ | `openapi.yaml` regenerated (3038 lines); `frontend/src/lib/api-types.ts` generated; CI drift check added |
| G4 | Event outbox (D2.4) | ✅ | `event_outbox` table + `dispatch_event` executor; 6/6 new tests, incl. real HTTP→job→webhook_deliveries |
| G5 | Rate limiting (D2.5) | ✅ | `RateLimited` dep on 7 auth routes + 3 public routes; 5/5 tests against real Redis |
| G6 | Stripe scaffolding (D2.6) | ✅ | 5 tables + 10 seeded plans; webhook idempotency gate: 6/6, incl. real HMAC signature verification |
| G7 | Chaos tests (D2.7) | ✅ | 4/4: Postgres mid-request failure → 503 + full rollback; Redis outage → rate limiter fails open |
| G8 | Frontend design-system (D2.8) | ✅ | 10 new primitives; `tsc --noEmit` clean; production build succeeds |
| G9 | Full regression | ✅ | **239 passed, 0 failed** (19m04s), fresh DB, real Neon/Redis |

## Tasks executed

### D2.1 ✅ RLS everywhere (ADR 002)

- `backend/alembic/versions/0010_tenant_fanout_columns.py` — denormalizes `company_id` onto 14 tables that lacked it directly (3 dependency-ordered backfill layers). 26 tables now carry `company_id`.
- `backend/alembic/versions/0011_rls_everywhere.py` — creates `app_user` role (`NOBYPASSRLS`), enables RLS + one `FOR ALL` policy per table on all 26 tenant tables + `companies`. **Live app still runs on the bypass/owner role** — deliberately not cut over yet (signup bootstraps a new tenant before any session context exists; cutover needs an audit of bootstrap/admin code paths first, documented in the migration's own docstring).
- `backend/alembic/versions/0012_company_id_autopopulate_triggers.py` — fixes a regression 0010 would otherwise have introduced: `BEFORE INSERT` triggers resolve `company_id` from the parent row for the 14 fanned-out tables, since nothing taught existing `INSERT` call sites to populate the new column.
- `backend/app/tenancy.py` + `backend/app/db.py:connection()` — `contextvars`-based per-request tenant context, applied via `SET LOCAL app.company_id` on every acquired connection. Inert for the live pool today; exercised for real by `app_user`-bound tests.
- `backend/scripts/provision_app_user.py` — one-time password provisioning, separate from the migration.
- **Verification**: `backend/test/api/test_rls_fail_closed.py` connects directly as `app_user` (bypassing the app's own pool) — 7/7 green: tenant A sees only its own bot, tenant B sees only its own, unset tenant context sees zero rows (fail-closed), substituting another tenant's ID still returns nothing, mismatched INSERT rejected, malformed context fails closed not open, a 3-hop-deep table (`feedback`) is isolated.

### D2.2 ✅ Provider router (ADR 004)

- `backend/app/providers/base.py` — `ProviderCapabilities`, `ChatProvider`/`EmbeddingProvider`/`RerankProvider` Protocols, exception hierarchy.
- `backend/app/providers/groq_chat.py` — wraps the existing, already-proven `app/chat/llm.py:stream_completion`.
- `backend/app/providers/openrouter_chat.py` — skeleton only, deliberately not wired into the default chain (`commercial_use_verified=False` until a specific free model is chosen and verified per the module's own docstring).
- `backend/app/providers/router.py` — `ProviderRouter.stream_chat()` with ordered fallback; `default_chain()` returns Groq-only (matches `free_only=true`).
- Not yet done: piping the live chat pipeline through this router (currently still calls `app/chat/llm.py` directly) and the Groq→OpenRouter fallback test from the original D2.2 acceptance criteria — deferred, since OpenRouter has no vetted model yet. Tracked as a Day 3+ follow-up, not silently dropped.

### D2.3 ✅ API conventions + TS client (ADR 007)

- `backend/scripts/export_openapi.py` run — `openapi.yaml` now 3038 lines, current with everything built today (billing webhook, rate-limited routes).
- `frontend/src/lib/api-types.ts` generated via `openapi-typescript` (new devDependency, `frontend/package.json`); `npm run generate:api-types` script added.
- `.github/workflows/openapi-contract.yaml` — new, dedicated CI job: regenerates both `openapi.yaml` and `api-types.ts` from the FastAPI app and fails on any diff. Deliberately separate from a full backend test run (not wired into CI at all yet — a larger, separate initiative needing a disposable DB/Redis in CI).
- `backend/app/api_errors.py` — RFC 9457 `problem_detail()` helper per ADR 007, ready for Day 9's `/api/v1/public-api/*` routes (which don't exist yet). Inert today; existing routes keep their current `{code, message}` shape unchanged. 3 unit tests in `backend/test/unit/test_api_errors.py`.

### D2.4 ✅ Event outbox (ADR 003)

- `backend/alembic/versions/0013_event_outbox.py` — `event_outbox` table (RLS-protected, idempotent on `(company_id, topic, payload_hash)`) + `event_outbox_id` column/unique-index on `webhook_deliveries` for idempotent fan-out.
- `backend/app/events/outbox.py:emit_event()` — producer helper; inserts the outbox row and enqueues a `dispatch_event` job in the **same transaction** as the domain mutation.
- `backend/app/jobs/executors.py:dispatch_event_executor` — fans out to `webhook_deliveries` for every active endpoint subscribed to the topic (respecting per-bot scoping); idempotent on re-run.
- Wired into `backend/app/public/router.py`: `conversation.started`, `lead.submitted`, `feedback.given`.
- **This closes `launch/01-FEATURE-INVENTORY.md` H.5** — "webhook_endpoints + webhook_deliveries tables + delivery worker exist; no application code emits events today." It does now. `app/webhooks/worker.py` (the existing delivery worker) is unchanged and untouched — it already claims and POSTs whatever lands in `webhook_deliveries`.
- 6/6 tests in `backend/test/api/test_event_outbox.py`, including one real end-to-end HTTP flow: register a webhook endpoint → create a conversation via the real public API → claim and run the `dispatch_event` job → confirm the `webhook_deliveries` row.

### D2.5 ✅ Rate limiting (ADR per `03-RISKS-AND-BLOCKERS.md` §2.8)

- `backend/app/security/rate_limit.py` — `RateLimited(limit, window_seconds, key_prefix)`, a reusable per-IP FastAPI dependency generalizing the bespoke bootstrap-only limiter that existed before today. Fails open on any Redis error (never 500s a public/auth path over a rate-limiter problem).
- Applied to: `signup`, `login`, `google`, `verify-email`, `resend-verification`, `forgot-password`, `reset-password` (`backend/app/auth/router.py`); visitor session bootstrap, public chat message, lead, feedback (`backend/app/public/router.py`).
- `backend/test/api/test_rate_limiting.py` — 5/5 against a real Redis connection (allows up to the limit then blocks, separate buckets per IP and per route, window expiry, fails open on a simulated outage).

### D2.6 ✅ Stripe scaffolding (ADR 008)

- `backend/alembic/versions/0014_billing_scaffolding.py` — `plans` (10 rows seeded from `09-BILLING-PAYMENTS.md` §1/§2: free, starter/growth/scale/agency × monthly/yearly, overage_reply), `subscriptions`, `usage_events`, `invoices` (all RLS-protected, tenant-scoped), `stripe_events` (global, bypass-role only — not yet correlated to a company at ingestion time).
- `backend/app/billing/router.py` — `POST /api/v1/webhooks/stripe`: real HMAC signature verification via the `stripe` SDK, idempotent insert into `stripe_events` on `event_id` primary-key conflict, returns 200 immediately. **Processing** (upserting `subscriptions`/`invoices`, entitlements) is explicitly Day 4 (D4.3) scope, not built yet — this is ingestion only, per the D2.6 task description ("Webhook endpoint with idempotency. No UI yet").
- No real Stripe account exists yet (`STRIPE_*` keys are blank in `.env` — this is an owner action, see below). Tests construct real, valid HMAC signatures using Stripe's documented signing scheme against a test-only secret, which exercises the actual verification code path, not a mock of it.
- `backend/test/api/test_stripe_webhook.py` — 6/6, including the Day-2-gate-required idempotency test (same `event_id` delivered twice → exactly one row).

### D2.7 ✅ Backend chaos tests

- `backend/test/api/test_chaos.py` — fault injection at the client-library boundary (Neon/Upstash are managed services; there is no local container to kill, so failures are injected deterministically instead of racing a real process kill — documented as a deliberate adaptation, not a weaker substitute).
- **Found and fixed a real gap**: a Postgres connection dying mid-request (e.g. between the user-row and company-row inserts in signup) was returning a bare, uninformative `500 internal_error` instead of a retry-able `503`. Added `database_unavailable_handler` in `backend/app/main.py` for `psycopg.OperationalError`/`InterfaceError`.
- Verified: the failed request's transaction fully rolls back (no partial user row survives), the connection pool recovers cleanly for the very next request, and a simulated Redis outage never blocks or 500s a rate-limited request (fails open, per D2.5).

### D2.8 ✅ Frontend design-system primitives

- New: `select.tsx`, `switch.tsx`, `tabs.tsx`, `popover.tsx`, `command.tsx` + `combobox.tsx`, `pagination.tsx` (page + cursor variants), `table.tsx` + `data-table.tsx` (`@tanstack/react-table`, client-side sortable), `calendar.tsx` + `date-range-picker.tsx` (`react-day-picker`), `color-picker.tsx`, `chart.tsx` (`ChartLine`/`ChartBar`/`ChartSparkArea`, `recharts`), `code-block.tsx`.
- All match the existing `cva` + Radix + design-token conventions (`bg-card`, `hsl(var(--primary))`, etc.) — no new colors introduced.
- Not yet wired into any real page (their consuming pages are Days 7/8 — Knowledge UI, analytics charts, conversations table, widget branding, playground). Built as clean, minimal primitives now so those days are wiring, not design decisions.
- Verified: `tsc --noEmit` clean, existing 29 frontend unit tests still green, production build succeeds.

## Real bugs found and fixed (beyond the assigned Day 2 scope)

1. **`app/jobs/runner.py` — `fail_job_quota`/`replay_dead_job` attempt-number collision (production bug, pre-existing, unrelated to today's migrations).** `fail_job_quota` reverts `jobs.attempts` by one ("a quota wait must not count against max_attempts") but left the matching `job_attempts` audit row in place; the next claim reused the same attempt number and crashed with `UniqueViolation` on `job_attempts_job_attempt_unique`. Same gap in `replay_dead_job` (TRD: "manual replay creates a new attempt generation" — but `attempts` reset to 0 without clearing the old generation's rows, which would collide identically on first reclaim). **Fixed**: both now delete the superseded `job_attempts` row(s) instead of leaving them in place.
2. **Postgres mid-request failures returned 500, not 503.** Found via the chaos tests (D2.7 above). Fixed with a dedicated exception handler.
3. **Neon's connection pooler silently closes idle connections**, and the pool had no health check — surfaced as intermittent `psycopg.OperationalError: server closed the connection unexpectedly` on two different, unrelated tests across two full-suite runs. Fixed: `check=ConnectionPool.check_connection` added to the pool in `backend/app/postgres_resilience.py`.
4. **Pre-existing test bugs, never caught before today because this suite had never run end-to-end against a real database**: `test_job_runner.py` treated `enqueue_job()`'s return value as a bare string where it's actually a documented `(job_id, is_new_job)` tuple (10 call sites fixed); `TestClient.delete()` doesn't accept `json=` in the installed httpx version (`test_auth_flow.py`, switched to `.request("DELETE", ...)`); `test_tenant_isolation.py`'s cross-tenant publish test was missing a setup step (company B needs its own bot before the intended cross-tenant check is even reachable).
5. **Shared dev database had accumulated ~5 days of synthetic test-run pollution** (110 users, 54 companies, 51 queued jobs at one point) that made two specific `test_job_runner.py` assertions (which assume a quiescent queue) fail non-deterministically. Wiped with explicit owner approval (`TRUNCATE users CASCADE`). Added a longer-term safeguard: an autouse fixture in `test_job_runner.py` and `test_event_outbox.py` that clears the `jobs`/`job_attempts` queue before each test in those files, since sibling test files commit real jobs via the real HTTP path that the `db_conn` fixture's rollback can never undo.

## New test totals

- Backend: **239 passed**, 0 failed. 215 were already collected (160 from the Day-1 addendum + RLS/job-runner/tenant-isolation work earlier in this Day-2 session); today's additions on top of that: 5 rate-limiting + 6 event-outbox + 6 Stripe webhook + 4 chaos + 3 api-errors unit = +24.
- Frontend: 29 passed / 7 files, unchanged; 10 new design-system components added (no new test files yet — no consuming page exists to test against).

## Deferred / not yet done

- **Live RLS cutover** (switching the app's request-serving pool from the bypass role to `app_user`) — still deliberately not done; needs a bootstrap/admin-path audit first (documented in migration 0011).
- **Provider router not yet wired into the live chat pipeline** — `app/chat/pipeline.py` still calls `app/chat/llm.py` directly. Low risk (Groq-only chain is behaviorally identical today), but means the router's fallback logic isn't exercised by real traffic yet.
- **Stripe event processing** (subscriptions/invoices/entitlements upsert) — explicitly Day 4 scope per the plan; today is ingestion-only.
- **`app/webhooks/worker.py` unification** — it's a separate standalone poll loop outside the main jobs runner; ADR 003's stated intent is "one proven queue," so folding webhook delivery itself into the jobs runner as another executor kind is a reasonable follow-up, not done today (out of D2.4's stated scope).

## Owner action needed before Day 4

1. Create a Stripe account (test mode) and set `STRIPE_SECRET_KEY`/`STRIPE_PUBLISHABLE_KEY`/`STRIPE_WEBHOOK_SECRET` in `backend/.env` — currently blank. Blocks nothing today (webhook ingestion correctly returns a loud `503 stripe_not_configured` rather than silently accepting unverified payloads) but is needed before Day 4's Checkout work.
2. Decide on the OpenRouter fallback model (if wanted) before Day 3+ — `app/providers/openrouter_chat.py` is a skeleton pending that choice.

## "Review these lines yourself" (owner security eyeball)

- `backend/alembic/versions/0011_rls_everywhere.py` — RLS policies + the app_user role, and its docstring explaining why the live pool isn't cut over yet.
- `backend/app/billing/router.py` — Stripe webhook signature verification; this is the one place an unauthenticated POST reaches application code.
- `backend/app/main.py:database_unavailable_handler` — confirms a DB outage can't leak a stack trace or partial state, only a generic 503.
- `backend/app/jobs/executors.py:dispatch_event_executor` — confirms webhook fan-out respects both topic subscription and per-bot scoping (a misconfigured endpoint can't receive another bot's events).

## Gate verdict

**GREEN.** Full regression: 239 passed, 0 failed, from a freshly wiped database, real Neon/Upstash/Groq/Cloudflare dependencies throughout (no mocked DB or Redis anywhere in this suite; chat/LLM calls are stubbed per-test as documented, consistent with `docs/11-AGENT-RULES.md` rule 6 — no live external LLM calls by default).

**Day 3 (RAG v2 ingestion + knowledge manager) is cleared to start.**
