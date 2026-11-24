# Backend completion status (against 19-BACKEND-SPRINT-PLAN-V2 and 16-API-ROUTES)

Last updated 2026-11-24. Honest status: **code-complete against the written plan; not yet "100% verified"** because the database-backed suites and the real-provider smoke script have not been run in an environment with Postgres and credentials.

## What changed in this pass

| Area | Change |
| --- | --- |
| Routes | All 60 routes in doc 16 are registered (enforced by `test/unit/test_route_contract.py`, which parses doc 16). Added: `PATCH /me`, `POST /company`, `GET /company/export`, `GET /dashboard`, `GET /usage`, `PATCH /documents/{id}`, `GET /documents/{id}/content`, `GET /jobs/{id}`, `POST /sources/crawl/discover`, `GET /crawl-jobs/{id}`, `POST /crawl-jobs/{id}/import`, `POST /bot/preview/conversations`, `POST /bot/preview/chat`, `POST /public/conversations`, `POST /public/conversations/{id}/lead`, `POST /public/messages/{id}/feedback`. |
| Public chat | Rewritten under `/api/v1/public/...`. Old `/public/v1/*` was non-functional (a context manager used as a FastAPI dependency; wrong params). Visitor token is `Authorization: Bearer`, stored hashed, bot-scoped, 30 min. |
| Chat pipeline | New `app/chat/`: quota reserve-before-call, retrieval filtered to authorised source versions then re-validated in Postgres, Groq streaming adapter (no paid fallback), SSE with `meta/sources/delta/done/error`, ordered `seq`, heartbeats, abort -> `interrupted` + reservation released, output guardrail, idempotent replay. |
| Owner preview | Was a stub ("not fully implemented"). Now the same pipeline against draft config and the owner's ready sources. |
| Idempotency | `Idempotency-Key` on publish, refresh, retry, crawl import, complete, and chat sends. Same key + different body = 409. |
| Analytics | `analytics_events` written for conversation_started, message_sent, feedback_given, lead_submitted, answer_no_evidence, quota_blocked. |
| Account deletion | `DELETE /me` revokes sessions, unpublishes, disables the bot, marks sources deleted in one transaction, then queues a tracked `company_cleanup` job (vectors, then all tenant rows). |
| Health | `/health/ready` now checks Postgres + Redis + Pinecone and returns `503 {failing_dependencies}` (names only, never error text). |
| Errors | Every error carries `code`, `message`, `request_id`; `X-Request-ID` echoed on every response. `detail` kept for backward compatibility. |
| Contract | `openapi.yaml` is now generated (`scripts/export_openapi.py`, `--check` in CI). It previously described routes that did not exist. |
| CI / Docker | CI now runs migrations + pytest against a Postgres service. Dockerfile ships alembic and a healthcheck. |
| Smoke | `scripts/smoke_phase0.py` is the Phase 0 exit gate (Postgres, Redis, Pinecone, Cloudflare embedding, Groq). |
| Migration | `0008`: `analytics_events`, `idempotency_keys`, `crawl_jobs`, nullable preview conversations, `messages.client_key`, `leads.consent_at` + one lead per conversation. |

## Defects found and fixed in pre-existing code

- `postgres_resilience` built a `postgresql+psycopg://` URL (a SQLAlchemy dialect; libpq rejects it) and had no `dict_row` factory, so every `row["col"]` access would fail at runtime.
- `enqueue_job` returns `(job_id, is_new)` but callers treated it as a bare id.
- `delete_account` referenced `leads.bot_id`, `usage_*.bot_id` (columns do not exist); retention sweep used `leads.created_at` and a nonexistent `sources` table.
- Audit events passed non-UUID `target_id` values (a field key) into a `uuid` column.
- `fetchone()[0]` on dict rows; `secrets` used without import; `ANY(%s)` over text arrays against `uuid` columns.
- Legacy AWS/LangGraph modules (`graph.py`, `aws.py`, `vector.py`, `rag.py`, `memory.py`, `worker/ingest.py`) removed; `boto3`, `langgraph`, `groq` dropped from requirements.
- The audit context was a process-global singleton (actor/request_id could cross between concurrent requests); now a `ContextVar`, with a regression test.
- Messages in one transaction shared a `now()` timestamp, making user/assistant order nondeterministic; now `clock_timestamp()`.

## Verified here (no database, no network)

- `pytest`: 138 passed, 48 skipped (the skipped ones are the database-gated suites).
- Covered without a DB: route contract vs doc 16, auth fails closed on every owner route, SSE order/seq/heartbeat/abort/error, quota exhaustion makes zero provider calls, prompt-injection fixtures rejected before quota or DB, origin allowlist, cursor tamper rejection, idempotent replay logic, readiness never leaks error text.

## NOT verified (needs a migrated Postgres and, for smoke, real credentials)

1. `alembic upgrade head` through `0008` has not been run end to end.
2. `test/api/*` (including the new `test_chat_and_lifecycle.py`, 13 tests) is written but has not executed. Expect some first-run SQL fixes.
3. `scripts/smoke_phase0.py` has not been run against real services (Cloudflare and Pinecone response shapes in the adapters are still unconfirmed, as the adapters themselves warn).
4. No chaos run (Redis outage, Postgres failover) was executed for Phase 8.

## Known limitations (deliberate, documented, not hidden)

- Upload grants live in process memory (`storage/local.py`): fine for one API instance, must move to Redis/Postgres before running multiple instances.
- The output guardrail runs after streaming: a sensitive completion is blocked in storage and ends the stream with an `error`, but tokens already sent cannot be recalled.
- `DELETE /me` cleanup status URL requires an owner session, which has just been revoked, so the owner cannot poll it; the job id is returned for support use.
- `scripts/init_db.py` and `infra/schema.sql` are the retired flat demo schema and conflict with Alembic. They should be deleted; they were left because removal was not requested.
- A misnamed file `c:UsersUserDocumentsKnowmivobackendDockerfile` at the repo root is junk; git cannot address it on Windows, remove it manually.

## To reach "100% ready"

```
cd backend
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
set DATABASE_URL=<disposable postgres>   &  set TEST_DATABASE_URL=<same>
alembic upgrade head
python -m pytest -q                      # all suites, none skipped
python scripts/smoke_phase0.py           # real .env credentials
python scripts/export_openapi.py --check
```
