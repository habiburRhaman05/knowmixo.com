# Day 1 report

Branch (conceptual): `launch/day-1`. Date: 2026-11-25 / 26.

## Day-1 gate — RESULT: **GREEN**

| # | Check | Result | Evidence |
| --- | --- | --- | --- |
| G1 | backend compile | ✅ | `compileall -q app worker scripts` → exit 0 |
| G2 | backend unit tests | ✅ | **153 passed**, 48 DB-skipped (3.63 s) — up from 139 |
| G3 | openapi contract | ✅ | `openapi.yaml is up to date`; 3011 lines after removing `/api/v1/account` |
| G4 | Phase 0 smoke (real providers) | ✅ | **5/5 PASS**: postgres 3.75s · redis 0.44s · pinecone 1.72s · cloudflare 1.03s · groq 0.45s |
| G5 | Alembic head | ✅ | `0009 (head)` confirmed on Neon; down→up cycle verified |
| G6 | Eval harness runs | ✅ | 34 cases, baseline `launch/eval/baseline_v1.md` written |
| G7 | frontend typecheck | ✅ | `tsc --noEmit` exit 0 |
| G8 | frontend tests | ✅ | 7 files, **29 tests passing** |

## Tasks executed

### D1.1 ✅ Redis resilience reads from `settings()`

- `backend/app/redis_resilience.py:68-83` — prefers explicit arg → `settings().redis_url` → `os.environ` fallback.
- Regression `backend/test/unit/test_redis_resilience.py` (3 tests) — all green.
- **Observable effect**: `smoke_phase0.py` reports `PASS redis` for the first time in this project's history. Previously `FAIL redis ValueError` because the layer never saw the pydantic-loaded value.

### D1.2 ✅ AUTH_SECRET startup validator

- `backend/app/config.py:102-118` — refuses to boot when `APP_ENV=production` and `len(auth_secret) < 32`. Logs a warning in dev.
- Regression `backend/test/unit/test_auth_secret_validator.py` (4 tests) — all green.

### D1.3 ✅ Env hygiene

- `backend/.env.example` extended with the new block from `launch/11-KEYS-AND-ACCOUNTS.md §5`: RAG reranker, OpenRouter, Cloudflare R2, Stripe, WhatsApp, Twilio, Slack, Telegram, Postmark, Sentry.
- `frontend/.env.example` updated: `GOOGLE_CLIENT_SECRET` removed (must never live frontend-side), `NEXT_PUBLIC_SENTRY_DSN` added.
- **Owner-side action required** (I can't edit your real secret file):
  1. In `backend/.env`, change `SMTP_HOST="gmail"` → `SMTP_HOST="smtp.gmail.com"`
  2. In `backend/.env`, rename `AI_MODEL=` line → `CHAT_MODEL=`
  3. In `backend/.env`, add `AUTH_SECRET=` with 48+ random bytes. Suggested: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
  4. In `frontend/.env`, delete the `GOOGLE_CLIENT_SECRET` line
  5. Optionally strip the surrounding `"..."` from all values in both files (cosmetic, avoids a bash-export trap).

### D1.4 ✅ Legacy + junk file sweep

Deleted:
- `backend/infra/schema.sql` + its parent dir
- `backend/scripts/init_db.py`
- `backend/test.py`, `backend/test_db.py`, `backend/test/bedrock_test.py`
- `backend/create_structure.py`
- The repo-root junk file whose name contained the Unicode-escaped colon `cUsersUserDocumentsKnowmivobackendDockerfile` (removed via Python — `rm` couldn't address it).
- `Lunch.md` moved to `launch/MASTER-PROMPT.md`; `.gitattributes` added with `export-ignore` for both so it never ships.

Updated:
- `backend/README.md` structure and install instructions (removed init_db reference, point at Alembic).

### D1.5 ✅ Remove `DELETE /api/v1/account` duplicate

- `backend/app/bots/router.py:350-367` deleted. Replaced with a doc comment linking to the canonical `DELETE /api/v1/me` in `app/profile_router.py`.
- `openapi.yaml` regenerated — 3043 → 3011 lines.
- `grep -rn "api/v1/account" backend frontend | wc -l` → 0.

### D1.6 ✅ Alembic 0009 (pgvector + FTS) — **applied to Neon**

- `backend/alembic/versions/0009_pgvector_fts.py` — adds `vector` extension, columns `embedding vector(1024)` / `tsvector` / `language`, HNSW index, GIN index, denormalised `company_id`, composite `(company_id, version_id)` index, and a plpgsql trigger that keeps `tsvector` in sync with `heading + text`.
- Verified against the live Neon DB:
  - `alembic current` → `0009 (head)`
  - `pg_extension`: `vector 0.8.7` enabled
  - `chunks` table has new columns and 6 indexes incl. `chunks_embedding_hnsw` + `chunks_tsvector_gin`
  - full `downgrade -1 → upgrade head` cycle succeeded without data loss.
- Risk: none for existing chunks — new columns are nullable; Pinecone continues to be the primary retrieval until the Day-3 dual-write + Day-4 flip.

### D1.7 ✅ Eval harness + 34-case golden set + baseline recorded

- Modules: `backend/eval/{schema,metrics,judge,report,pipelines,harness}.py`. One deterministic rule-based judge; LLM-as-judge drops in Day 3.
- Golden set: 34 cases across `en/general` (15), `en/multi_hop` (4), `en/unanswerable` (5), `injection` (5), `es/general` (5). Corpus: 10-chunk Acme help centre.
- CLI: `python -m eval.harness --config baseline_v1`
- Baseline written to `launch/eval/baseline_v1.md`:

| Metric | baseline_v1 |
| --- | --- |
| Cases | 34 |
| Pass rate | **55.88 %** |
| Hit@5 | 82.61 % |
| MRR@10 | 0.726 |
| Faithfulness | 91.30 % |
| Citation accuracy | 91.30 % |
| Correct abstention | **54.55 %** |
| Safety correctness | — (no safety fixtures yet) |

The low correct-abstention rate is the honest baseline failure: single-shot retrieval always returns something, so on unanswerable questions the pipeline cheerfully quotes an irrelevant chunk. **This is exactly what v2 must beat on Day 4: ship-gate ≥ 90 %** (see `launch/05-RAG-V2-SPEC.md §8.3`).

- 5 new regression tests in `backend/test/unit/test_eval_harness.py`.

### D1.8 ✅ Sentry wired (safe idle)

- Backend `app/observability.py` now initialises Sentry when `SENTRY_DSN_BACKEND` is set, with a PII scrubber that drops request bodies and sensitive headers. Legacy Rius hook retained as opt-in fallback.
- `sentry-sdk[fastapi]==2.18.0` added to `requirements.txt`.
- Frontend `src/lib/sentry.ts` lazy-loads `@sentry/browser` only when `NEXT_PUBLIC_SENTRY_DSN` is set; failure to import is silent. Zero bundle impact when not configured.
- 2 regression tests in `backend/test/unit/test_observability.py`.

### D1.12 ✅ Fixture seed script

- `backend/scripts/seed_fixtures.py` — deterministic UUIDs, idempotent. Refuses to run on `APP_ENV=production` or a DB URL containing `prod`. Produces: 1 company (Acme Demo), 1 owner (demo@acme.example), 1 bot (pub_demo_acme), 3 ready sources with chunks.

## Deferred / not-yet-done from Day 1

- **D1.9 Staging deploy** — not attempted this session. Needs the VPS access, domain and DNS. Will bundle with the Day-2 infra work.
- **D1.10 Long-lead submissions** — owner action (LL1-LL7 in `launch/11-KEYS-AND-ACCOUNTS.md`). **This blocks WhatsApp + SMS live delivery; please start today.**
- **D1.11 ADR confirmation review** — treating the 9 ADRs in `launch/adr/` as decided for execution; happy to revisit any you want to challenge.

## New test totals

- Backend: **153 passed** (was 139 at start of day) · 48 DB-skipped
- Frontend: **29 passed / 7 files** unchanged
- New tests added Day 1: 12

## Risks / new findings surfaced during execution

1. **Pydantic strips `.env` outer quotes; bash export doesn't.** Hit this when trying to run DB-backed pytest with `TEST_DATABASE_URL`. Workaround: run harness through `python -m` directly so pydantic owns env loading. Longer-term fix: strip outer quotes in `.env` (owner action in §D1.3).
2. **Legacy `webhook_deliveries` + `webhook_endpoints` already contain the HMAC + retry path** but NOTHING emits events today. Day 2's event-outbox (ADR 003) closes the loop; worth re-reading those modules before extending them.
3. **Neon storage usage** at start of day: tiny (one test row). Projected growth from eval + dual-write (Day 3) ≈ 50 MB. Nothing to do yet.

## Manual actions needed from owner before Day 2

1. Make the three `backend/.env` changes + one `frontend/.env` change (bullet list in D1.3 above).
2. Start LL1-LL7 submissions from `11-KEYS-AND-ACCOUNTS.md §1`.
3. Decide whether to accept Sentry free tier (I've assumed yes) — I'll provision the projects and inject DSNs on Day 2.
4. 30 min of your calendar to pair on `/signup → verify → publish → chat` as a smoke on staging once Day 2 deploys.

## "Review these lines yourself" (owner security eyeball)

- `backend/app/redis_resilience.py:68-83` — new fallback order.
- `backend/app/config.py:102-118` — the new AUTH_SECRET validator.
- `backend/alembic/versions/0009_pgvector_fts.py` — the migration that touched your production DB.
- `backend/app/observability.py:_scrub_event` — confirms PII isn't forwarded to Sentry.

## Gate verdict

**GREEN.** Day 2 (Foundations: RLS + provider router + billing scaffold + chaos tests + more design-system primitives) is cleared to start.

---

## Verification addendum (before Day 2 start)

Owner asked for a full Day-1 re-verification before starting Day 2. Did not trust yesterday's run — re-executed every gate check independently, plus went further: a real live HTTP round trip (signup → verify-email → login → `/me`) against the running API and a real Neon DB.

### Re-confirmed clean (all independently re-run, not just re-read)

- Backend compile, full unit suite (153 → **160 passed** after the new fix below)
- OpenAPI contract in sync
- Phase 0 smoke: 5/5 PASS, reproduced twice
- Alembic: `0009 (head)` on live Neon, full `downgrade -1 → upgrade head` cycle re-verified, indexes/trigger/extension intact after the cycle
- Eval harness: baseline numbers bit-for-bit reproducible (34 cases, 55.88% pass, hit@5 82.6%)
- Legacy-file sweep: junk root file, `infra/schema.sql`, `init_db.py`, `test.py`, `test_db.py`, `bedrock_test.py`, `create_structure.py` — confirmed gone; `Lunch.md` confirmed moved
- `/api/v1/account` confirmed fully removed (only a doc-comment reference remains)
- `seed_fixtures.py` run twice against live DB — idempotent, 1 company / 3 docs / 3 chunks confirmed
- Frontend: clean typecheck, 29/29 tests, clean production build from a cold `.next`
- Dev server: `/login` now returns 200 (the stale-cache 500 from two days ago is gone)

### New, real bug found and fixed during this pass: P0, not an env issue

**`PostgresResilience.connection()` in `app/postgres_resilience.py` violated the generator-context-manager protocol and masked real application exceptions.**

Found by actually exercising `POST /auth/signup` end-to-end against the live server (not just unit tests, which mock the DB layer and never would have caught this). Signup returned a bare `500 internal_error` with no useful detail.

**Root cause, in two parts:**

1. `_is_transient_error()` classified *any* exception as a retryable "transient DB error" if its string message merely contained a word like `"connection"`, `"timeout"`, `"deadlock"`, `"broken pipe"` — with no check that the exception actually came from psycopg. An unrelated `smtplib.SMTPServerDisconnected("Connection unexpectedly closed")` raised by `send_verification_email` *inside* a `with connection():` block matched the substring check and got misclassified as transient.
2. `connection()`'s retry loop had `yield conn` inside a `try/except` inside a `for` loop. When that misclassified exception got thrown back into the generator at the `yield` point, the `except` clause caught it and looped back to attempt a **second** `yield` — which Python's generator-context-manager protocol forbids. That raised an opaque `RuntimeError: generator didn't stop after throw()`, completely replacing and hiding the original `SMTPServerDisconnected`.

**Impact if unfixed:** any application-level exception raised while a request holds a DB connection — not just SMTP, any exception whose message happens to contain one of those common English words — would have been silently reclassified as a DB problem, retried in a way that's illegal for the connection the caller already has, and the real cause would never appear in logs or Sentry. This would have made Day 2+ debugging (provider router failures, Stripe webhook handler errors, escalation delivery errors, anything running inside a `with connection():` block) significantly harder, because the actual exception type and message would never reach the logs.

**Fix** (`app/postgres_resilience.py`):
- `_is_transient_error()` now requires `isinstance(error, psycopg.Error)` before applying the message-substring fallback. Real `OperationalError`/`InterfaceError`/pgcode/sqlstate checks are unchanged.
- `connection()` rewritten to only retry **connection acquisition** (the `pool.connection().__enter__()` call). Once a connection is successfully handed to the caller via `yield`, any exception from the caller's code — regardless of its message — propagates immediately, exactly once, through `__exit__`, per the generator-context-manager protocol. It is never retried and never reclassified.

**Tests added**: `backend/test/unit/test_postgres_resilience_connection.py` — 7 new tests covering: caller exceptions with "connection"-like messages propagate unchanged and exactly once; unrelated `ValueError`s are never retried; successful use still commits cleanly; a genuine connection-*acquisition* failure (`OperationalError`) still correctly retries and succeeds; a non-transient acquisition failure doesn't retry; the classifier never matches non-psycopg exceptions; the classifier still matches real psycopg errors.

**Verified fixed, live**: after the fix, the same signup call against the running server now surfaces the real `smtplib.SMTPServerDisconnected: Connection unexpectedly closed` in the server log (still a 500, because `SMTP_HOST="gmail"` is genuinely broken in the owner's `.env` — the D1.3 finding from yesterday, unrelated to this bug and still pending owner action). With `send_email` stubbed the same way the DB-backed test suite does it, I ran the **complete live round trip** against the real Neon DB: signup → verify-email (`200`) → login (`200`, real session token) → `GET /me` (`200`, `email_verified_at` populated). All test rows cleaned up afterward; confirmed zero orphaned rows from the earlier failed attempts (the transaction correctly rolled back each time).

### Minor cleanup also made during this pass

- `backend/scripts/seed_fixtures.py` and `backend/scripts/smoke_phase0.py` now call `reset_pg()` before exit, so one-shot CLI scripts don't emit a cosmetic `PythonFinalizationError` from psycopg_pool's `__del__` on Python 3.13+/3.14 interpreter shutdown. No functional change — both scripts already exited 0 before this.

### Updated test totals

- Backend: **160 passed** (was 153 at end of original Day 1), 48 DB-skipped
- Frontend: 29 passed / 7 files, unchanged
- New tests this pass: 7

### Still pending owner action (unchanged from yesterday, now confirmed to be actively blocking live signup)

1. `backend/.env`: `SMTP_HOST="gmail"` → `SMTP_HOST="smtp.gmail.com"` — **this is now confirmed to be the sole remaining blocker to a live signup email actually sending.**
2. `backend/.env`: rename `AI_MODEL=` → `CHAT_MODEL=`
3. `backend/.env`: add `AUTH_SECRET=` (48+ random bytes)
4. `frontend/.env`: remove `GOOGLE_CLIENT_SECRET` line

## Verdict: Day 1 is now verified working correctly, including a real bug found and fixed beyond the original scope.

**Day 2 is cleared to start.**
