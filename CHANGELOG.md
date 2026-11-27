# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/). Dates are UTC.

## [0.1.2] - 2026-11-26 — Day 2: Foundations

### Added
- Row-Level Security on 26 tenant tables + `companies`, `app_user` role (ADR 002). Live app pool not yet cut over — see `launch/DAY-2-REPORT.md`.
- Provider router skeleton: `ChatProvider`/`EmbeddingProvider`/`RerankProvider` protocols, Groq primary, OpenRouter skeleton (ADR 004).
- Event outbox (`event_outbox` table, `dispatch_event` job executor) — first application code to actually emit webhook events (ADR 003).
- Per-IP rate limiting on all auth and public-facing routes (`app/security/rate_limit.py`).
- Stripe billing scaffolding: `plans`/`subscriptions`/`usage_events`/`invoices`/`stripe_events` tables, 10 seeded plans, webhook ingestion with idempotency (ADR 008). Checkout/entitlements are Day 4.
- Generated TS API client (`frontend/src/lib/api-types.ts`) + CI drift check; RFC 9457 error-shape helper for the future public API (ADR 007).
- Backend chaos tests (Postgres mid-request failure, Redis outage).
- 10 new frontend design-system primitives: Select, Switch, Tabs, Combobox, Pagination (page + cursor), DataTable, DateRangePicker, ColorPicker, 3 chart components, CodeBlock.

### Fixed
- `app/jobs/runner.py`: `fail_job_quota`/`replay_dead_job` could crash on reclaim after reverting/resetting the attempt counter without clearing the superseded `job_attempts` row (`UniqueViolation`).
- A Postgres connection dying mid-request returned a bare 500 instead of a retry-able 503.
- Neon's pooler silently closing idle connections was undetected; added a pool health check.
- Several pre-existing, never-before-exercised test bugs (job-runner API misuse, httpx `TestClient.delete()` signature, a missing tenant-isolation test fixture step).

## [0.1.1] - 2026-11-25/26 — Day 1: Make it run

### Added
- pgvector + FTS columns and HNSW/GIN indexes on `chunks` (ADR 001).
- Eval harness skeleton + 34-case golden set + recorded baseline (`launch/eval/baseline_v1.md`).
- Sentry wiring (backend + frontend), PII-scrubbed.
- Fixture seed script (`backend/scripts/seed_fixtures.py`).

### Fixed
- `app/redis_resilience.py` read `os.environ` instead of `settings()`, breaking the Redis smoke check.
- Missing `AUTH_SECRET` startup validation (fails closed in production).
- `PostgresResilience.connection()` violated the generator-context-manager protocol, masking real exceptions as an opaque `RuntimeError` under specific error-message collisions.

### Removed
- Legacy/junk files (`infra/schema.sql`, `init_db.py`, `test.py`, `test_db.py`, `bedrock_test.py`, a misnamed root file) and the duplicate `DELETE /api/v1/account` route.
