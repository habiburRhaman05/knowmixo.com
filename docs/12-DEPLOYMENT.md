# Environment and deployment runbook

## Development

Use the existing i5/8 GB PC as a Linux or Docker development host. Run FastAPI, one worker and the future Next.js app there. Keep PostgreSQL, Redis and Pinecone in selected free cloud plans. Hosted embeddings and LLM avoid loading a large model into 8 GB RAM. Measure memory and worker concurrency, starting at one ingestion worker and one upload per company.

Current preserved backend commands run from backend. Existing code still expects AWS until the migration is implemented. Do not mistake the new environment contract below for a working replacement today.

```text
cd backend
python -m venv .venv
python -m pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

After implementation add documented commands for `alembic upgrade head`, the Python worker entry point and `pytest`. Frontend setup starts day 4 with pinned package manager and lockfile. Do not run legacy Bedrock smoke tests as part of the free setup.

## Proposed environment contract

| Variable | Scope and purpose |
| --- | --- |
| APP_ENV, PUBLIC_APP_URL, BACKEND_INTERNAL_URL | Environment and trusted URLs |
| DATABASE_URL | Backend/worker only, TLS cloud PostgreSQL connection |
| REDIS_URL | Backend/worker secret, Free database |
| STORAGE_BACKEND=local, PRIVATE_STORAGE_DIR | Private mounted persistent directory |
| FREE_ONLY=true | Startup policy forbidding paid/default AWS model routes |
| CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN | Embedding account and scoped token |
| EMBEDDING_MODEL=@cf/baai/bge-m3, EMBEDDING_DIM=1024 | Expected model identity and validated dimension |
| PINECONE_API_KEY, PINECONE_INDEX | Backend/worker vector credentials |
| OPENROUTER_API_KEY, CHAT_MODEL, ALLOWED_FREE_CHAT_MODELS | Explicit verified free model allowlist |
| GLOBAL_CHAT_DAILY_LIMIT, COMPANY_CHAT_DAILY_LIMIT | Conservative app budgets below actual account allowance |
| RESEND_API_KEY, EMAIL_FROM | Backend verification/reset mail |
| GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET | Next OAuth credentials, backend knows audience ID |
| AUTH_SECRET | Next Auth.js cookie protection, generated secret |
| SESSION_MAX_AGE_SECONDS | Backend and Next aligned lifetime |
| MAX_FILE_BYTES, MAX_CRAWL_PAGES, MAX_COMPANY_STORAGE_BYTES | Enforced resource limits |
| JOB_MAX_ATTEMPTS=4, JOB_LEASE_SECONDS | Worker policy, tune against heartbeat behavior |
| RETENTION_DAYS=30 | Conversations/leads policy |

Frontend public environment contains URLs and public bot IDs only. Provider keys, database URLs, backend sessions and Auth.js secrets never use a browser-public prefix.

## VPS production topology

Existing Hostinger VPS hosts Nginx, Next.js, FastAPI and one worker with restart policies. Terminate HTTPS at Nginx. Bind internal services to loopback or a private container network. Mount persistent private file storage outside web root. Separate health probes from paid provider calls. Configure streaming locations with buffering disabled and tested read timeouts. Forward request IDs and propagate disconnect cancellation.

Keep services unprivileged. Restrict SSH with keys and firewall. Use least-privilege database credentials and TLS for cloud connections. Limit connection pools across API and worker processes to the free database allowance. Track RAM, disk, provider errors, dead jobs, source age and quota remaining without logging document text.

## Deploy and rollback

Before deploy create an encrypted database and file-manifest backup and retain the previous application image/config. Apply reviewed backward-compatible migrations once. Start worker/API, run isolated health checks, deploy frontend, verify real owner and visitor smoke journeys. Roll back app images only when schema remains compatible. Use a forward fix for destructive/incompatible migrations rather than an untested automatic downgrade.

Keep a seven-day rolling encrypted backup on the existing PC or another already available device in addition to the VPS. Do not count a backup on the same disk as disaster recovery. Verify capacity and restoration. Provider-managed free backups may be limited and are not assumed.

Pause new registrations and generation before free allowances are exhausted. Quota-wait jobs resume only after confirmed reset. Disable a failing public bot immediately while preserving owner access and diagnostic state. No deployment step enables billing or publishes an unrestricted unlimited service.
