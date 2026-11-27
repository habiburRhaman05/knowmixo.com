# 13 · Ten-day sprint

Each day uses 4 parallel lanes (A Backend/AI · B Frontend/UX · C Infra/Billing/Realtime · D Quality/Security). Task IDs are `D<day>.<n>`. Hours are an honest estimate for one engineer in that lane.

Per-day structure: tasks → Day gate → buffer → scope-cut order → docs/CHANGELOG.

The task template appears once; every row after uses the same shape.

---

## Day 1 — Make it run

**Theme**: fix the build-health findings from `00-BUILD-HEALTH.md`, run migrations + smoke + eval baseline, start long-lead approvals.

### D1.1 Fix `redis_resilience` to read from `settings()`
- Lane: A · Feature refs: R01 · Depends on: none · Estimate: 1 h · Files: `backend/app/redis_resilience.py`, `backend/test/unit/test_redis_resilience.py`
- Instruction: """Replace `os.environ.get('REDIS_URL', '')` with `settings().redis_url`. Add a unit test that monkeypatches `settings()` to return a fake URL and asserts `get_redis().url` matches. Do not change public API."""
- Acceptance: `smoke_phase0.py` reports PASS for redis · unit test passes
- Verify: `python scripts/smoke_phase0.py && pytest backend/test/unit/test_redis_resilience.py -q`
- Rollback: revert file
- Needs from owner: none

### D1.2 Startup validator for `AUTH_SECRET`
- Lane: A · Refs: R02 · Est: 1 h · Files: `backend/app/config.py`
- Instruction: """In the Settings constructor, after existing validation, raise ValueError if `app_env == 'production'` and `len(auth_secret) < 32`. In development, just log a warning once."""
- Acceptance: setting `APP_ENV=production` with missing secret fails to boot; dev boots with a warning · existing tests still pass
- Verify: `APP_ENV=production python -c "from app.config import settings; settings()"` → exits 1

### D1.3 Env hygiene
- Lane: C · Refs: R21, R22, R17 · Est: 1 h · Files: `backend/.env`, `frontend/.env`, `backend/.env.example`, `frontend/.env.example`
- Instruction: """Fix SMTP_HOST → smtp.gmail.com. Rename AI_MODEL → CHAT_MODEL. Remove GOOGLE_CLIENT_SECRET from frontend/.env. Remove unquoted-value trap (standardize on unquoted). Add the new env block from `11-KEYS-AND-ACCOUNTS.md` §5 to .env.example (placeholders only)."""
- Acceptance: `scripts/export_openapi.py --check` clean · `python scripts/smoke_phase0.py` all PASS · gitleaks clean

### D1.4 Delete junk + legacy files
- Lane: C · Refs: `00-BUILD-HEALTH` §1 · Est: 1 h
- Files to delete: `c:UsersUserDocumentsKnowmivobackendDockerfile` (manual OS) · `backend/infra/schema.sql` · `backend/scripts/init_db.py` · `backend/test.py` · `backend/test_db.py` · `backend/test/bedrock_test.py`
- Instruction: """Delete the files; add `Lunch.md` → `launch/00-MASTER-PROMPT.md` and update references; add `.gitattributes` with `Lunch.md export-ignore` just in case the rename lags."""
- Acceptance: git status clean after move · `backend/test` has no live-API files · CI still green

### D1.5 Remove `DELETE /api/v1/account` duplicate
- Lane: A · Refs: `00-BUILD-HEALTH` §5 · Est: 0.5 h · Files: `backend/app/bots/router.py`, `backend/openapi.yaml`
- Instruction: """Remove the legacy `@router.delete("/account")` and regenerate OpenAPI. Keep `/me` as the only account-deletion endpoint."""
- Verify: `grep -rn "api/v1/account" backend frontend | wc -l` → 0

### D1.6 Alembic 0009: pgvector + FTS columns + hnsw index
- Lane: A · Refs: ADR 001 · Est: 4 h · Files: `backend/alembic/versions/0009_pgvector_fts.py`
- Instruction: """Add pgvector extension (`CREATE EXTENSION IF NOT EXISTS vector`), add `embedding vector(1024)`, `tsvector tsvector`, `language text` columns to chunks; HNSW index on embedding; GIN index on tsvector; `(company_id, version_id)` index. Write a migration test that creates + rolls back."""
- Acceptance: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` succeeds on a disposable DB
- Rollback: `alembic downgrade 0008`

### D1.7 Baseline eval harness (`backend/eval/`)
- Lane: D · Refs: `05-RAG-V2-SPEC` §8 · Est: 8 h · Files: `backend/eval/*`
- Instruction: """Create harness skeleton: `golden/en/general.jsonl` (40 cases hand-written), `golden/en/injection.jsonl`, `golden/en/emergency.jsonl`, `golden/es/general.jsonl`, `harness.py` runs any pipeline, `judge.py` LLM-as-judge rubric, `metrics.py` outputs hit@5, MRR, faithfulness, abstain correctness, TTFT, cost. Run against the current v1 pipeline and write results to `launch/eval/baseline_v1.md`."""
- Acceptance: baseline numbers recorded · the file lists exact per-case pass/fail

### D1.8 Sentry + OTel wired
- Lane: C · Refs: R17 · Est: 4 h · Files: `backend/app/observability.py`, `frontend/src/lib/sentry.ts`
- Instruction: """Add `sentry-sdk[fastapi]`; init in `app/main.py`. Frontend uses `@sentry/nextjs` with lazy init. `SENTRY_DSN_*` env vars via `11-KEYS-AND-ACCOUNTS.md`."""
- Acceptance: a deliberate `/debug/sentry` endpoint raises → shows up in Sentry within 30 s

### D1.9 Staging deploy
- Lane: C · Est: 6 h · Files: `docker-compose.staging.yml`, Nginx conf, `.env.staging`
- Instruction: """VPS target: provision one 4 vCPU/8 GB instance, docker-compose with `api`, `worker`, `nginx`. SSE-aware Nginx (`proxy_buffering off`). TLS via certbot. Point `app.staging.knowmivo.com` + `api.staging.knowmivo.com` at it."""
- Acceptance: `/health/ready` returns 200 from the public URL · signup flow works end-to-end · verification email arrives

### D1.10 Long-lead submissions
- Lane: C · Refs: `11-KEYS-AND-ACCOUNTS.md` §1 · Est: 2 h (owner time)
- Needs from owner: start LL1-LL6 TODAY
- Record each submission ticket number in `launch/long-lead-status.md`

### D1.11 Decide ADRs
- Lane: all · Est: 2 h (reviews)
- Confirm the 9 ADRs in `launch/adr/*.md`; attach short meeting notes.

### D1.12 Fixture seed script
- Lane: D · Est: 2 h · Files: `backend/scripts/seed_fixtures.py`
- Instruction: """Seed one company, one bot, three docs (PDF/MD/FAQ) to help eval + e2e runs."""

**Day 1 gate (pass/fail)**:
1. `scripts/smoke_phase0.py` → all 5 PASS
2. `alembic upgrade head` → 0009
3. `scripts/verify_launch.sh` → PASS table reports 11 PASS 0 FAIL
4. Eval baseline recorded
5. Staging URL answers `/health/ready` 200
6. Long-lead tickets filed

Buffer: 15 % (12 h total across lanes).

Scope-cut order if slipping: D1.9 (defer to Day 2), D1.7 (ship with 20 cases instead of 40).

CHANGELOG: `0.1.0 → 0.1.1 Build-health fixes`.

---

## Day 2 — Foundations

### D2.1 RLS everywhere (ADR 002)
- Lane: A · Est: 10 h · Files: `backend/alembic/versions/0010_rls.py`, `backend/app/db.py`
- Instruction: """Migration enables RLS on 27 tenant tables; FastAPI middleware sets `SET LOCAL app.company_id` per request; two roles (`app_user`, `app_admin`); regression test revokes app-side filter and asserts 0 rows for Company B."""
- Acceptance: tenant-isolation suite passes without the explicit `WHERE company_id` in any listed route

### D2.2 Provider router (ADR 004)
- Lane: A · Est: 12 h · Files: `backend/app/providers/router.py`, `base.py`, `openrouter.py`, `cache.py`, `rl.py`, migrate `chat/llm.py` into `providers/groq.py`
- Instruction: """Implement provider router with ordered fallback, token-bucket RL per company in Redis, exact + semantic cache, capability flags per model."""
- Acceptance: pipe chat through router; Groq→OpenRouter fallback test passes by simulating 429 on primary

### D2.3 API conventions + TS client (ADR 007)
- Lane: B+C · Est: 6 h
- Instruction: """Generate `frontend/src/lib/api-types.ts` via `openapi-typescript`; CI fails on drift; add `type` field to error responses behind a flag for `/public-api/*` only."""

### D2.4 Event outbox worker (ADR 003)
- Lane: A · Est: 6 h · Files: `backend/alembic/versions/0011_event_outbox.py`, `backend/app/events/*`, `backend/app/jobs/executors.py`
- Instruction: """Create `event_outbox` table, `event_dispatcher` executor, fan-out to webhook_deliveries and (later) escalation + analytics. Idempotent on `(company_id, topic, payload_hash)`."""

### D2.5 Rate limiting on auth + public routes
- Lane: A · Est: 4 h · Files: `backend/app/security/rate_limit.py` + route deps
- Instruction: """Add `RateLimited(limit, window)` dep; apply to signup, login, forgot/reset, google, verify-email, resend-verification, public bootstrap, public chat, lead, feedback. Uses fixed `RateLimiter`."""

### D2.6 Stripe scaffolding
- Lane: C · Est: 10 h
- Instruction: """Alembic 0012: `plans`, `subscriptions`, `usage_events`, `invoices`, `stripe_events`. Seed plans from `09-BILLING-PAYMENTS.md` §1. Webhook endpoint with idempotency. No UI yet."""

### D2.7 Backend chaos tests (Postgres failover, Redis outage)
- Lane: D · Est: 8 h
- Instruction: """Add chaos test harness: kill Redis container mid-request; assert degraded graceful; kill Postgres connection mid-txn; assert request errors with 503, not partial commit."""

### D2.8 Frontend design-system polish
- Lane: B · Est: 6 h
- Instruction: """Ship Select, Combobox, Switch, Tabs, Pagination, DataTable, DateRangePicker, ColorPicker, ChartLine/ChartBar/ChartSparkArea, CodeBlock. Use existing tokens."""

**Day 2 gate**: RLS regression green · provider router falls back under simulated 429 · Stripe webhook idempotency test passes.

---

## Day 3 — RAG v2 ingestion + knowledge manager

### D3.1 Structure-aware parsers v2
- Lane: A · Est: 10 h
- Instruction: """pdf: swap to `pdfplumber` for tables + headings; docx: iterate tables as Markdown; html: BeautifulSoup table detection; csv: new parser."""

### D3.2 Contextual chunker + real tokenizer
- Lane: A · Est: 8 h
- Instruction: """Replace char/4 estimate with `tiktoken` (`cl100k_base`); split on heading/section boundaries; target 200-400 tokens; attach `doc title > heading path` context; FAQ pairs whole."""

### D3.3 Dual-write to pgvector + Pinecone (72 h window)
- Lane: A · Est: 6 h · Files: `backend/app/ingestion/pipeline.py`, `providers/vector_store.py`
- Instruction: """Write both; read from pgvector when `settings.vector_store='pgvector'`."""

### D3.4 Hybrid retrieval SQL + rerank adapter
- Lane: A · Est: 10 h · Files: `backend/app/chat/rag_v2/stages/retrieve.py`, `rerank.py`
- Instruction: """Implement the RRF CTE from ADR 001 + Cloudflare bge-reranker call."""

### D3.5 Scheduled jobs + change-detection scaffolding
- Lane: A · Est: 4 h (scaffolding only; schedule UI Day 7)

### D3.6 Knowledge manager backend extras
- Lane: A · Est: 4 h — `size_bytes`, `disabled_at`, tags column (not UI yet)

### D3.7 Eval golden set to 150
- Lane: D · Est: 14 h
- Owner note: review the English Spanish split with a native speaker if available.

**Day 3 gate**: retrieval hit@5 against baseline ≥ 50 % improvement on multi-hop set · all parser fixtures ingest without error · golden set 150 cases loaded.

---

## Day 4 — RAG v2 runtime + Billing MVP

### D4.1 Rewrite + sufficiency loop + verifier + grounded prompt
- Lane: A · Est: 16 h
- Instruction: """Implement `rag_v2/pipeline.py` state machine; wire via `settings.rag.engine='v2'` behind a feature flag."""

### D4.2 rag_traces write path
- Lane: A · Est: 4 h

### D4.3 Stripe Checkout + Portal + entitlements
- Lane: C · Est: 12 h · Files: `backend/app/billing/*`, `frontend/app/(app)/billing/*`, `/api/bff/billing/*`
- Instruction: """Checkout session endpoint, Portal link endpoint, webhook processor, entitlements layer with Redis cache, three UI views: Plan picker / Current plan / Usage card."""

### D4.4 First v2-vs-baseline eval
- Lane: D · Est: 4 h

**Day 4 gate**: v2 beats v1 on hit@5 / faithfulness / abstain-correctness; first-token time within budget; billing checkout → success → webhook → entitlement cache update works in test mode.

---

## Day 5 — Agent + actions + escalation core

### D5.1 Tool framework + built-in tools
- Lane: A · Est: 10 h
- Tools: `search_knowledge`, `capture_lead`, `escalate_to_human`.

### D5.2 Owner HTTP action (CRUD + SSRF + test button)
- Lane: A+B · Est: 10 h

### D5.3 Severity classifier + rule engine
- Lane: A · Est: 8 h · Files: `backend/app/escalation/*` per `06-ESCALATION-DESIGN.md`

### D5.4 State machine + delivery workers (email, Slack, Telegram)
- Lane: C · Est: 10 h

### D5.5 Handoff backend (status column, assignment, canned replies)
- Lane: A · Est: 8 h

**Day 5 gate**: escalation.email delivered in e2e test; state machine transitions to acknowledged on link click; tool framework handles happy + error paths.

---

## Day 6 — WhatsApp + live inbox + realtime + channel adapters start

### D6.1 WhatsApp Cloud API adapter
- Lane: C · Est: 12 h
- Includes: template fetch, send, delivery/read webhooks, opt-in verification flow, test harness with fake server.
- Status: live delivery PENDING_EXTERNAL on template approval.

### D6.2 SSE live inbox + Redis pub/sub (ADR 005)
- Lane: A+B+C · Est: 16 h

### D6.3 Inbox UI + takeover button
- Lane: B · Est: 10 h

### D6.4 Visitor adapter adapters start (WhatsApp/Messenger/Instagram inbound)
- Lane: C · Est: 8 h (code only; verification Day 10)

**Day 6 gate**: owner inbox updates within 2 s of a new visitor message; takeover flips `handoff_status` and visitor sees agent joined within 1 s.

---

## Day 7 — Widget v2 + Knowledge UI + Playground

### D7.1 Widget config v2 + full JS API
- Lane: B · Est: 14 h per `07-WIDGET-SPEC.md`

### D7.2 Loader + install snippets (script, React, Next.js, GTM, WordPress)
- Lane: B · Est: 10 h

### D7.3 Live preview editor
- Lane: B · Est: 8 h — device toggle + presets

### D7.4 Knowledge UI finish (bulk actions, tags, disabled toggle)
- Lane: B · Est: 10 h — BUT bulk + tags are NEEDS_MORE_TIME per `12-FEASIBILITY-MATRIX.md`; ship just disabled + size + last synced

### D7.5 Playground (retrieval inspector reading `rag_traces`)
- Lane: B · Est: 10 h

**Day 7 gate**: widget passes axe clean · Lighthouse a11y ≥ 95 · install snippet verifies in staging · playground renders full trace.

---

## Day 8 — Owner monitoring + billing UI complete + accounts/MFA/teams/roles

### D8.1 Conversations: filters + CSV export + tags (schema only; UI label Day 11)
- Lane: A+B · Est: 10 h

### D8.2 Analytics: 3 core charts
- Lane: A+B · Est: 12 h — conversations, deflection, TTFT

### D8.3 Gaps + Bad-answers queue + Alerts (3 built-in rules)
- Lane: A+B · Est: 14 h

### D8.4 Billing UI (invoices list, plan change, usage card)
- Lane: B · Est: 6 h

### D8.5 MFA (TOTP + recovery codes)
- Lane: A+B · Est: 10 h

### D8.6 Roles + team invites
- Lane: A+B · Est: 10 h

**Day 8 gate**: full owner UI reachable + working · MFA setup + step-up on destructive actions · invited member can read conversations.

---

## Day 9 — Polish + hardening + marketing site + public API + integrations

### D9.1 Onboarding wizard (3-min target)
- Lane: B · Est: 10 h

### D9.2 Industry templates (SaaS + E-commerce ship)
- Lane: A+B · Est: 6 h

### D9.3 Marketing site: landing fix, pricing, docs, help center skeleton, legal pages
- Lane: B+D · Est: 12 h

### D9.4 Public API + API keys + Zapier docs
- Lane: A · Est: 10 h

### D9.5 Slack app + alerts channel
- Lane: C · Est: 6 h

### D9.6 Full security suite (SSRF redirect fix, DNS rebinding fix, markdown sanitiser, XSS corpus)
- Lane: D · Est: 10 h

### D9.7 Load test (k6, 50-100 concurrent streams)
- Lane: D · Est: 6 h

### D9.8 a11y + Lighthouse fixes
- Lane: D · Est: 6 h

**Day 9 gate**: load test reports TTFT within budget · zero critical axe violations · Lighthouse targets met · public API keys work with scopes · Slack alert for test escalation arrives.

---

## Day 10 — Launch

### D10.1 Full regression (`scripts/verify_launch.sh`)
- Lane: D · Est: 4 h

### D10.2 Eval report final
- Lane: D · Est: 2 h

### D10.3 Backup restore drill (Neon PITR → scratch DB)
- Lane: C · Est: 4 h

### D10.4 Stripe LIVE switch + real-charge-and-refund
- Lane: C+owner · Est: 2 h

### D10.5 Demo bots setup (2 industries)
- Lane: owner + A · Est: 4 h

### D10.6 Launch gate review (`15-LAUNCH-GATE.md`)
- Lane: all · Est: 2 h

### D10.7 Go-live
- DNS cutover, support rota on, monitoring on, incident runbook open.

**Day 10 gate = Launch gate.** See `15-LAUNCH-GATE.md`.

---

## Notes

- Every task writes to `launch/DAY-<n>-REPORT.md`.
- Every task adds to CHANGELOG.
- Every task that touches a security-critical line is tagged `[REVIEW]` so the owner sees it in the PR.
- Buffer 15 % of each day's capacity reserved by default.
- Scope-cut order (never cut): tenant isolation · billing correctness · escalation reliability · eval ship-gate · backups · privacy/terms/AI disclosure · accessibility basics.
