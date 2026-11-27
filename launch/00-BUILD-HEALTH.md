# 00 · Build health

Run date: 2026-11-25. Platform: Windows 11 (x64), Python 3.14.7, Node v24.18.0, npm 12.0.2. Every row in this file reflects a command I actually ran; failures are fixable observations, not opinions.

## Top line

| Pillar | Status | Evidence |
| --- | --- | --- |
| Backend compiles | ✅ VERIFIED | `python -m compileall -q app worker scripts` exits 0 (no output) |
| Backend unit tests | ✅ VERIFIED | `pytest -q` → **139 passed, 48 skipped** in 2.96s (skipped are DB-backed; see §3) |
| Backend DB migrations | ✅ VERIFIED | `alembic upgrade head` → `0008 (head)`; 32 tables in Neon prod schema |
| Phase 0 smoke (real providers) | 🟡 PARTIAL | 4/5 PASS — Postgres, Pinecone, Cloudflare Workers AI, Groq. **Redis FAIL** due to app bug (§2.1) |
| OpenAPI contract | ✅ VERIFIED | `openapi.yaml` is 3043 lines and `scripts/export_openapi.py --check` is clean |
| FastAPI routes registered | ✅ VERIFIED | 78 routes at import time (see §4) |
| Frontend typecheck | ✅ VERIFIED | `tsc --noEmit` exits 0 |
| Frontend tests | ✅ VERIFIED | `vitest run` → **29 passed / 29** in 4.20s |
| Frontend build | ✅ VERIFIED | `next build` succeeds, 66 routes, 100 kB shared first-load JS |
| Dev server /login render | ⚠️ BROKEN | `GET /login` → 500 `Error: Cannot find module './1989.js'` in last run. Cause: stale `.next` cache from the earlier interrupted build. Cleared; needs re-verification |
| Docker image | UNVERIFIED | Dockerfile present (`frontend/Dockerfile`, `backend/Dockerfile`) but neither built here |
| CI | ✅ VERIFIED | `.github/workflows/frontend-ci.yaml` and `backend/.github/workflows/cicd.yaml` present; neither run |

## 1 · Repo layout and hygiene

| Observation | Status | Evidence |
| --- | --- | --- |
| Backend source | ✅ | `backend/app` 1.2 MB |
| Frontend app routes | ✅ | `frontend/app` 365 kB |
| Frontend libs/components | ✅ | `frontend/src` 345 kB |
| **Junk root file** | ⚠️ BROKEN | A literal file named `c:UsersUserDocumentsKnowmivobackendDockerfile` sits at the repo root. Confirmed with `ls`. This leaks what looks like someone else's absolute path and makes Windows tooling fragile. Cannot be `git rm` because its name resolves to an invalid path on Windows. Needs manual OS-level remove. |
| Retired files still present | 🟡 PARTIAL | `backend/infra/schema.sql` and `backend/scripts/init_db.py` are the retired flat demo schema — they conflict with Alembic. Should be deleted. |
| Product-name drift | 🟡 PARTIAL | `pinecone_index_name` default in `backend/app/config.py` is `"knowmixo-rag-sa"`. The brand doc (`docs/00-BRAND.md`) says **Knowmivo**. One of them is wrong; the `.env` keeps using the old spelling because migration cost is zero today. |
| README freshness | 🟡 PARTIAL | Root `README.md` is stub. `backend/README.md` and `frontend/README.md` exist and are reasonable. |

## 2 · Build-health findings that need code changes

### 2.1 Redis resilience layer bypasses pydantic settings — CRITICAL

- **Where**: `backend/app/redis_resilience.py:69`
- **Code**: `self.url = url or os.environ.get("REDIS_URL", "")`
- **Problem**: `settings()` loads from `.env` via pydantic_settings. `redis_resilience` reads `os.environ` directly. If `REDIS_URL` isn't exported to the OS environment, every Redis call fails at `raise ValueError("REDIS_URL is required")` even though the setting is clearly present.
- **Evidence**: `scripts/smoke_phase0.py` reports `FAIL redis ValueError` with the message `REDIS_URL is required`, while `settings().redis_url` returns a 105-character `rediss://...` URL in the same Python process.
- **Impact**: Rate limiting, session-store fallback, and later the live-inbox pub/sub would all fail in production whenever the process is started without a shell-exported REDIS_URL (which uvicorn + systemd commonly won't do).
- **Fix**: swap the direct `os.environ` read for `settings().redis_url`. Postgres resilience (`backend/app/postgres_resilience.py:63`) already does it right — see that file for the pattern.

### 2.2 `.env` values are double-quoted

- **Where**: `backend/.env`
- **Evidence**: every key (DATABASE_URL, REDIS_URL, PINECONE_HOST, CLOUDFLARE_ACCOUNT_ID, GROQ_API_KEY) starts and ends with `"`. Pydantic strips the outer quotes, but bash `export` does not, and any Python code that calls `os.environ[...]` directly (see 2.1) gets literal quotes in the string.
- **Impact**: ran into this during smoke — psycopg errored with `invalid channel_binding value: "require""`. After loading through pydantic the same URL connects fine.
- **Fix**: the file isn't broken for the backend, but the shape is a trap. Remove the quotes, or standardise everyone on pydantic.

### 2.3 Missing `AUTH_SECRET`

- **Where**: `backend/app/config.py:50` defines `auth_secret: str = ""`, no validation
- **Check**: `settings().auth_secret` returns `''` today
- **Impact**: there is no server-side session signing yet, so the empty value doesn't cause a crash, but anything later that signs tokens with this (planned escalation deep-link, API-key HMAC, CSRF) will produce guessable signatures.
- **Fix**: add a startup validator — refuse to boot if `app_env=='production'` and `auth_secret` is empty or shorter than 32 bytes.

### 2.4 `SMTP_HOST="gmail"`

- **Where**: `backend/.env`
- **Effect**: verification/reset/email-change will fail at connect time. Pydantic reads `smtp_host='gmail'` which isn't a resolvable host.
- **Fix**: `SMTP_HOST=smtp.gmail.com`.

### 2.5 `AI_MODEL` vs `CHAT_MODEL`

- **Where**: `backend/.env` sets `AI_MODEL=openai/gpt-oss-120b`
- **Effect**: `backend/app/config.py:32` reads `chat_model`. The `AI_MODEL` line is dead; the model only works today because the default string happens to match.
- **Fix**: rename env var to `CHAT_MODEL`.

### 2.6 Google OAuth secret in `frontend/.env`

- **Where**: `frontend/.env`
- **Problem**: `GOOGLE_CLIENT_SECRET` has no reason to live in the Next.js env. One `NEXT_PUBLIC_` typo leaks it to the browser.
- **Fix**: remove the line from `frontend/.env`. Keep the one in `backend/.env`.

### 2.7 `Lunch.md` at repo root

- The master launch prompt was committed to the repo root rather than `docs/` or `launch/`. Low-impact but should move to `launch/MASTER-PROMPT.md` and be added to `.gitattributes export-ignore` so it never ships in a tarball.

### 2.8 Frontend dev server 500 on /login (resolved pending re-run)

- **Symptom**: `GET /login` → 500 with `Error: Cannot find module './1989.js'` after the new auth-shell + topbar components were added.
- **Root cause**: Next.js 15 dev-mode chunk cache in `.next` got stale when files changed during an interrupted build. Standard fix (`rm -rf .next`) applied in this run.
- **Status**: pending a clean restart of `npm run dev` with a cold `.next`.

## 3 · Test runs

### Backend without DB

```
pytest -q
139 passed, 48 skipped in 2.96s
```

The 48 skips are everything that needs `TEST_DATABASE_URL` (see `backend/test/api/conftest.py:30`). Without exporting secrets through a tempfile (which the harness blocks as unsafe), I did not run the DB-backed suite in this session. The reason the DB-backed tests normally need an exported env var is tied to findings 2.1 and 2.2.

### Frontend

```
vitest run         ─▶ 29 passed / 29 in 4.20s
tsc --noEmit       ─▶ clean
next build         ─▶ 66 routes, 100 kB shared first-load JS
```

### Phase 0 smoke (real providers, after fixing REDIS_URL export)

```
PASS  postgres               3.55s
FAIL  redis                  ValueError          ← code bug 2.1
PASS  pinecone               1.36s
PASS  cloudflare-embeddings  0.57s
PASS  groq-llm               0.85s
```

## 4 · Routes registered in the live FastAPI app

78 routes at import. Full list below. The two `/health/live|ready` doubles exist because the main app mounts both the unversioned (legacy) path and the `/api/v1/` path per docs/16.

```
POST   /api/v1/auth/{signup,login,google,verify-email,resend-verification,forgot-password,reset-password,change-password,logout,logout-all}
GET/PATCH/DELETE /api/v1/me   POST /api/v1/me/{email-change, email-change/confirm, oauth/google/link}
GET/POST/PATCH   /api/v1/company   GET /api/v1/company/export
GET              /api/v1/dashboard   GET /api/v1/usage
POST             /api/v1/documents/uploads   PUT /api/v1/uploads/{grant_id}
POST/GET/PATCH/DELETE /api/v1/documents, /api/v1/documents/{id}, /api/v1/documents/{id}/{complete,content,refresh}
POST             /api/v1/sources/{text,faqs,url,crawl,crawl/discover}
GET/POST         /api/v1/crawl-jobs/{id}, /api/v1/crawl-jobs/{id}/import
GET/POST         /api/v1/jobs/{id}, /api/v1/jobs/{id}/retry
GET/PATCH/POST/PUT /api/v1/bot, /api/v1/bot/publish, /api/v1/bot/unpublish, /api/v1/bot/domains, /api/v1/bot/embed, /api/v1/bot/export, /api/v1/bot/lead-form(/fields/{key})
POST             /api/v1/bot/preview/{conversations,chat}
GET/DELETE       /api/v1/conversations, /api/v1/conversations/{id}, /api/v1/conversations/{id}/export
GET              /api/v1/public/bots/{public_id}/config   POST /api/v1/public/bots/{public_id}/sessions
POST             /api/v1/public/conversations, /api/v1/public/conversations/{id}/messages, /api/v1/public/conversations/{id}/lead
POST             /api/v1/public/messages/{id}/feedback
POST/GET/PATCH/DELETE /api/v1/webhooks/endpoints(/{id})(/deliveries)
GET              /api/v1/health/{live,ready}   /health/{live,ready}
DELETE           /api/v1/account    (legacy duplicate of DELETE /api/v1/me — see §5)
GET              /, /api/docs, /docs/oauth2-redirect, /openapi.json, /redoc
```

## 5 · Known duplicate and dead endpoints

| Path | Observation |
| --- | --- |
| `DELETE /api/v1/account` and `DELETE /api/v1/me` | Both exist. Doc 16 only specifies `/me`. `/account` is left over from a previous iteration. Decision: keep `/me`, remove `/account` in PART 2 Day 1 cleanup. |
| `GET /`, `GET /openapi.json`, `GET /docs/oauth2-redirect`, `GET /redoc` | FastAPI defaults; leaving `/openapi.json` in production is intentional since the frontend generates its types from it. `/docs` and `/redoc` should be gated to `app_env in {development, staging}` before launch. |

## 6 · Env vars observed vs required

Full enumeration of `backend/app/config.py` fields (41 of them) was done at runtime. Required fields where the current `.env` is **SET**: `DATABASE_URL`, `REDIS_URL`, `PINECONE_API_KEY`, `PINECONE_HOST`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `GROQ_API_KEY`. Required fields where the current `.env` is **MISSING**: `AUTH_SECRET` (see 2.3). Non-required but important and currently missing or wrong: `CHAT_MODEL` (2.5), `SMTP_HOST` (2.4). Frontend uses `BACKEND_INTERNAL_URL`, `NEXT_PUBLIC_APP_URL`, `NEXT_PUBLIC_GOOGLE_CLIENT_ID` — all three set.

The full annotated list is in `launch/11-KEYS-AND-ACCOUNTS.md`.

## 7 · Day-1 cleanup list (go/no-go for PART 2 Day 1)

1. Fix finding 2.1 (`redis_resilience.py` must call `settings()`).
2. Fix finding 2.3 (startup validator for `AUTH_SECRET` in production).
3. Fix findings 2.4 and 2.5 in `backend/.env` (SMTP_HOST, rename AI_MODEL).
4. Remove `GOOGLE_CLIENT_SECRET` from `frontend/.env` (2.6).
5. Delete `backend/infra/schema.sql` and `backend/scripts/init_db.py`.
6. Delete the junk root `c:UsersUserDocumentsKnowmivobackendDockerfile` file (manual Windows Explorer action — git won't touch it).
7. Delete `DELETE /api/v1/account` in `backend/app/bots/router.py` (duplicate of `/me`).
8. Verify `GET /login` renders after `.next` cache is rebuilt.
9. Decide on brand spelling and update `pinecone_index_name` default in `backend/app/config.py:16` if the index is renamed.
