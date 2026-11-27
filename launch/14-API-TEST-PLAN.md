# 14 · API test plan

Expands §3.11 of the master prompt. Scripts live in `scripts/`; test code in `backend/test/` and `frontend/e2e/`.

## 1 · Route catalogue (78 backend routes)

Source of truth: `backend/openapi.yaml` + live FastAPI `.routes`. Drift is a CI failure (ADR 007). The scanner in `backend/test/api/test_openapi_drift.py` compares both.

### 1.1 Expected codes per route class

| Route class | Happy | Validation | Unauth | Wrong tenant | Wrong role | Rate limited |
| --- | --- | --- | --- | --- | --- | --- |
| `/auth/*` | 200/202 | 422 | n/a (public) | n/a | n/a | 429 |
| `/me*`, `/company*`, `/dashboard`, `/usage` | 200 | 422 | 401 | 404 | 403 | 429 |
| `/documents*`, `/sources/*`, `/jobs/*`, `/crawl-jobs/*` | 200/201/202 | 422 | 401 | 404 | 403 | 429 |
| `/bot*`, `/bot/publish|unpublish|domains|embed|export|preview/*`, `/bot/lead-form*` | 200/201 | 422 | 401 | 404 | 403 | 429 |
| `/conversations*` | 200 | 422 | 401 | 404 | 403 | 429 |
| `/public/*` | 200/201 | 422 | 401 (visitor missing) | 404 | n/a | 429 |
| `/webhooks/*` | 200/201 | 422 | 401 | 404 | 403 | 429 |
| `/health/{live,ready}` | 200/503 | n/a | public | n/a | n/a | n/a |

### 1.2 Idempotent routes

- `POST /documents/{id}/complete`
- `POST /bot/publish`
- `POST /bot/preview/chat`
- `POST /jobs/{id}/retry`
- `POST /documents/{id}/refresh`
- `POST /crawl-jobs/{id}/import`
- `POST /public/conversations/{id}/messages`
- (new) `POST /public-api/conversations`, `POST /webhooks/stripe`

Each has an integration test that sends the same `Idempotency-Key` twice and asserts identical response + no duplicate side effect.

## 2 · Test suites

### 2.1 Auth + MFA

Covers: happy signup→verify→login; wrong password; disabled account; google token rejected; verify-email token reuse → 410; forgot-password cooldown; reset-password revokes all sessions; change-password with/without current; logout + logout-all; MFA TOTP setup, step-up on destructive, recovery codes.

### 2.2 Ingestion

- Each format (PDF / DOCX / TXT / MD / CSV) parses a fixture and reaches `ready`.
- Oversize + corrupt + duplicate + malicious-magic-byte rejected with correct `error_code`.
- Retry an `ingest_document` job twice → one pipeline run.
- Delete source → `delete_version_vectors` called → chunks gone.

### 2.3 RAG v2

- Unit per stage (guard, intent, rewrite, retrieve, rerank, grade, generate, verify, postprocess).
- Integration end-to-end with fake provider router (replays canned responses).
- Golden set eval runs under pytest with a flag `--eval` (nightly only).

### 2.4 Chat SSE

- Event order `meta` → `sources` → `delta*` → `done` or `error`.
- Abort mid-stream → message status `interrupted`, reservation released.
- Quota exhausted → 429 with `Retry-After` and NO provider call.

### 2.5 Tenant isolation (every authenticated route)

A single parametrised test iterates `(method, path)` for every row in a route catalogue table. For each row:

1. Two companies A, B each with a valid session.
2. Create a target resource under A.
3. Call route with B's credentials, substituting ids from A.
4. Assert 404 (never 403 — enumeration leak) OR 401 if route is owner-only verified-email, or 403 if the test deliberately supplies an unverified user for a verified-only route.

Fallback: route catalogue is derived from `openapi.yaml` so new routes automatically enter the regression.

### 2.6 RLS fail-closed

- Spin a connection with `SET app.company_id = <B>`, run every SELECT that expects a A row and assert 0 rows.
- Drop the app-level `WHERE company_id` filter in `app/sources/service.list_documents` and assert list still returns only B's rows via RLS alone.

### 2.7 Widget origin + signed identity

- Bootstrap session from a non-allow-listed origin → 403.
- Bootstrap from allow-listed → 201.
- Identify with bad HMAC → treated as anonymous.
- Identify with good HMAC → `visitor_sessions.identified_user_id` set.
- Shared-BFF-secret path: `X-Parent-Origin: foo` without matching `X-BFF-Trust` → ignored.

### 2.8 Escalation suite

Fake WhatsApp + Twilio servers run in test harness.

- Each trigger (keyword, intent, rule, behavior) produces exactly one escalation per dedupe window.
- Severity classifier mapping.
- Safety reply text for emergency.
- Template variable rendering within length bounds.
- Retry/backoff + fallback ordering.
- ACK via link opens → state transitions.
- Re-escalation with freezegun.
- Quiet hours honored except critical.
- Dedupe appends context, does not resend.
- Storm protection flips to digest.
- Deep link JWT: expiry, replay prevention, bad signature.
- Opt-in enforcement: unverified contact → fail without calling provider.
- Tenant isolation: Company B rules cannot fire on Company A conversations.

### 2.9 Handoff inbox realtime

- Takeover flips status in DB and visitor receives `agent_joined` SSE within 1 s of button click.
- Two agents race → one wins; the other gets 409.

### 2.10 Billing

- Signature failure on webhook → 400.
- Duplicate event id → 200 (idempotent).
- Out-of-order event → skipped.
- Every event type (subscription created/updated/deleted, invoice paid, invoice.payment_failed, checkout.session.completed, trial_will_end) updates DB correctly.
- Upgrade, downgrade, cancel, reactivate round-trips.
- Over-quota enforcement.
- Dunning soft-disable on day 14, hard-disable day 21 (freezegun).

### 2.11 Public API keys + scopes

- Create key → shown once; subsequent fetch returns only prefix.
- Wrong scope → 403.
- Revoked key → 401.
- Rate limit per key.

### 2.12 Outbound webhook signing + retry

- HMAC signature matches docs schema.
- Timeout → retry per schedule.
- Final failure writes `webhook_deliveries.state='dead'`.

### 2.13 SSRF + XSS payload suites

- SSRF: loopback, rfc1918, link-local, metadata (`169.254.169.254`), zero-config, redirect to internal, DNS rebinding.
- XSS: markdown with `<script>`, `<img onerror>`, `javascript:` URLs, data URLs; feedback comment field; lead values; owner names.

### 2.14 Prompt-injection suite

- 20 fixtures of injected instructions inside sources + visitor messages.
- Assert: bot does not reveal system prompt, does not follow embedded instructions, cites only legitimate passages, abstains when injection replaces real content.

## 3 · Tooling

- **Backend**: pytest with `--timeout=30`; DB tests use `TEST_DATABASE_URL` + per-test rollback.
- **HTTP collection**: `scripts/api_checks.http` for Bruno/VS Code REST client; same cases as pytest for manual repro.
- **Playwright e2e**: `frontend/e2e/*` — golden path (signup → onboarding → upload → ready → customize widget → install on test page → visitor chat → emergency → fake-escalation received → takeover → resolve → analytics increments → upgrade via Stripe test).
- **axe**: `playwright + @axe-core/playwright`.
- **Lighthouse CI**: `.lighthouserc.json` with budgets.
- **k6 load**: `scripts/loadtest.js` — 50-100 concurrent SSE streams.

## 4 · `scripts/verify_launch.sh` — one-command proof

Outputs a PASS/FAIL table. Non-zero exit on any failure. First version ships Day 1; grows each day.

```bash
#!/usr/bin/env bash
# scripts/verify_launch.sh — one-command proof of Day-N readiness.
set -u -o pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
RED=$'\033[31m'; GRN=$'\033[32m'; DIM=$'\033[2m'; RST=$'\033[0m'
PASS=0; FAIL=0
STATUS_TABLE=()

run() {
  local label="$1"; shift
  local out
  if out="$(eval "$@" 2>&1)"; then
    STATUS_TABLE+=("${GRN}PASS${RST}	$label")
    PASS=$((PASS+1))
  else
    STATUS_TABLE+=("${RED}FAIL${RST}	$label	${DIM}$(echo "$out" | tail -2 | tr '\n' ' ')${RST}")
    FAIL=$((FAIL+1))
  fi
}

cd "$ROOT"

# ── Build health ──
run "backend compile"     "cd backend && ./.venv/Scripts/python -m compileall -q app worker scripts"
run "backend unit tests"  "cd backend && ./.venv/Scripts/python -m pytest -q -p no:cacheprovider -W ignore"
run "frontend typecheck"  "cd frontend && npx tsc --noEmit"
run "frontend tests"      "cd frontend && npx vitest run --silent"
run "openapi drift"       "cd backend && ./.venv/Scripts/python scripts/export_openapi.py --check"
run "frontend build"      "cd frontend && BACKEND_INTERNAL_URL=http://127.0.0.1:8000 NEXT_PUBLIC_APP_URL=http://localhost:3000 npx next build"

# ── Phase 0 providers (real) ──
run "phase 0 smoke"       "cd backend && ./.venv/Scripts/python scripts/smoke_phase0.py"

# ── DB-bound ──
if [ -n "${TEST_DATABASE_URL:-}" ]; then
  run "alembic head"      "cd backend && ./.venv/Scripts/alembic upgrade head"
  run "DB-backed pytest"  "cd backend && ./.venv/Scripts/python -m pytest -q -p no:cacheprovider -W ignore --timeout=30"
fi

# ── Security scans ──
command -v gitleaks >/dev/null && run "gitleaks secrets scan" "gitleaks detect --redact --no-banner -s $ROOT"
command -v pip-audit >/dev/null && run "pip-audit"            "cd backend && ./.venv/Scripts/pip-audit --strict"
command -v npm      >/dev/null && run "npm audit (high)"      "cd frontend && npm audit --omit=dev --audit-level=high"

# ── Eval (if golden set exists) ──
[ -d backend/eval/golden ] && run "RAG eval ship-gate" "cd backend && ./.venv/Scripts/python -m eval.harness --config v2 --ship-gate"

echo
echo "--- Verify-launch result ---"
printf '%s\n' "${STATUS_TABLE[@]}"
echo
echo "PASS: $PASS   FAIL: $FAIL"
[ $FAIL -eq 0 ]
```

## 5 · CI wiring

- `.github/workflows/frontend-ci.yaml` already runs typecheck + vitest + build.
- Add `.github/workflows/backend-ci.yaml` — pytest with service Postgres, alembic cycle, openapi drift, pip-audit.
- Add `.github/workflows/verify-launch.yaml` — triggered on PR to `main`, runs `scripts/verify_launch.sh` against a disposable DB.

## 6 · Day-N expansion

Each sprint day adds its new test files to `verify_launch.sh` via a numbered block (the script is idempotent and additive). By Day 10 the script runs ~45 checks.
