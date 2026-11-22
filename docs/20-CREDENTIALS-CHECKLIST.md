# Phase 0 checklist — credentials, accounts, and environment

Fill this in before any Phase 1 code is written. Mark each row's **Status** as you go. Never commit real values here or anywhere in the repo — this file tracks *which variables exist and are verified*, not their contents. Real values go only in a local `.env` (gitignored) and, for production, the VPS's restricted-permission env file per [12-DEPLOYMENT.md](12-DEPLOYMENT.md).

## Core infrastructure

| # | Item | Env var(s) | Where to get it | Status |
| --- | --- | --- | --- | --- |
| 1 | PostgreSQL (Neon Free) | `DATABASE_URL` | Neon console → create project → connection string (require TLS) | ☐ |
| 2 | Redis (Upstash Free) | `REDIS_URL` | Upstash console → create Redis database → confirm **Free** plan selected explicitly | ☐ |
| 3 | Pinecone (Starter) | `PINECONE_API_KEY`, `PINECONE_INDEX` | Pinecone console → API key → create/confirm index matches embedding dimension | ☐ |
| 4 | Private file storage path | `STORAGE_BACKEND=local`, `PRIVATE_STORAGE_DIR` | A writable, persistent directory outside web root on the dev/VPS host | ☐ |

## AI providers

| # | Item | Env var(s) | Where to get it | Status |
| --- | --- | --- | --- | --- |
| 5 | Cloudflare account ID | `CLOUDFLARE_ACCOUNT_ID` | Cloudflare dashboard → account home | ☐ |
| 6 | Cloudflare Workers AI API token | `CLOUDFLARE_API_TOKEN` | Cloudflare dashboard → Workers AI API-token setup (scoped, not global API key) | ☐ |
| 7 | Embedding model + dimension confirmed live | `EMBEDDING_MODEL=@cf/baai/bge-m3`, `EMBEDDING_DIM` | Run the Phase 0 spike call, read the actual response shape — do not assume 1024 until verified | ☐ |
| 8 | OpenRouter account + key | `OPENROUTER_API_KEY` | OpenRouter dashboard | ☐ |
| 9 | OpenRouter free model selected and tested | `CHAT_MODEL`, `ALLOWED_FREE_CHAT_MODELS` | Run the Phase 0 spike: confirm streaming, English + Bangla output, and current `:free` pricing/availability | ☐ |
| 10 | Budget enforcement flag | `FREE_ONLY=true` | Set in every environment; startup must refuse to boot if a paid route is reachable | ☐ |
| 11 | Chat budget caps | `GLOBAL_CHAT_DAILY_LIMIT`, `COMPANY_CHAT_DAILY_LIMIT` | Set conservatively below the observed OpenRouter account-wide cap, leaving headroom for testing/retries | ☐ |

## Authentication

| # | Item | Env var(s) | Where to get it | Status |
| --- | --- | --- | --- | --- |
| 12 | Google OAuth client | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google Cloud Console → OAuth consent screen + credentials, redirect URI set to the real (not placeholder) callback URL | ☐ |
| 13 | Auth.js cookie secret | `AUTH_SECRET` | Generate a strong random secret (e.g. `openssl rand -base64 32`) | ☐ |
| 14 | Session lifetime alignment | `SESSION_MAX_AGE_SECONDS` | Decide value (spec suggests 7-day max); must match on both FastAPI and Next.js sides | ☐ |

## Email

| # | Item | Env var(s) | Where to get it | Status |
| --- | --- | --- | --- | --- |
| 15 | Gmail SMTP app password | `SMTP_HOST`, `SMTP_USER`, `SMTP_APP_PASSWORD`, `EMAIL_FROM` | Google account → security → app passwords (requires 2FA enabled on the sending account) | ☐ |
| 16 | Verified sending domain/DNS (if not using raw Gmail address) | SPF/DKIM records | Only needed if sending as a custom domain address, not `@gmail.com` directly | ☐ |

## Limits (defaults — confirm before Phase 3)

| # | Item | Env var(s) | Default from PRD | Status |
| --- | --- | --- | --- | --- |
| 17 | Max file size | `MAX_FILE_BYTES` | 10 MiB | ☐ |
| 18 | Max crawl pages | `MAX_CRAWL_PAGES` | 20 | ☐ |
| 19 | Max company storage | `MAX_COMPANY_STORAGE_BYTES` | 100 MiB | ☐ |
| 20 | Job runner tuning | `JOB_MAX_ATTEMPTS=4`, `JOB_LEASE_SECONDS` | Tune against real heartbeat behavior in Phase 2 | ☐ |
| 21 | Retention policy | `RETENTION_DAYS=30` | Conversations/leads/audit | ☐ |

## Networking and domains (needed before Phase 7/launch, confirm ownership now)

| # | Item | Notes | Status |
| --- | --- | --- | --- |
| 22 | Production domain | `knowmivo.com` registrability was unconfirmed as of the last check in [00-BRAND.md](00-BRAND.md) — resolve registrar checkout before relying on it for Google OAuth redirect URIs or email DNS | ☐ |
| 23 | VPS access | SSH key access to the existing Hostinger VPS confirmed working | ☐ |
| 24 | TLS | Let's Encrypt plan for the chosen domain | ☐ |

## V2-relevant items to note now, act on later (no credentials needed yet)

- **Webhook delivery**: no external account needed in V1 — `webhook_endpoints`/`webhook_deliveries` tables are built per [18-DATABASE-V2-V3-SCALABLE-SCHEMA.md](18-DATABASE-V2-V3-SCALABLE-SCHEMA.md), but there is no outbound provider to configure until a real owner adds their own endpoint URL in V2.
- **Analytics**: `analytics_events` starts being written in Phase 6 with no new infrastructure — it's just rows in the existing Postgres instance from item #1.

## Exit check for Phase 0

Run the smoke script described in [19-BACKEND-SPRINT-PLAN-V2.md](19-BACKEND-SPRINT-PLAN-V2.md) Phase 0: it must reach Postgres, Redis, Pinecone, call Cloudflare embeddings once, and call the OpenRouter model once, all successfully, before Phase 1 coding begins.
