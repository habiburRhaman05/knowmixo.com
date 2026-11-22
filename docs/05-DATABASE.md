# Database specification

PostgreSQL owns durable state. Use UUID keys, timezone-aware timestamps, explicit company scope and foreign keys. Existing tables need additive migrations and backfills before constraints are tightened. Do not drop and recreate live data.

| Table | Core fields and constraints |
| --- | --- |
| users | id, normalized_email unique, password_hash nullable, name, avatar_key, email_verified_at, disabled_at |
| oauth_accounts | user_id, provider, provider_subject, unique(provider, provider_subject) |
| sessions | id, user_id, token_hash unique, expires_at, revoked_at, created_at |
| auth_tokens | user_id, purpose, token_hash unique, expires_at, consumed_at, pending_email |
| companies | id, owner_user_id unique in V1, name, website, industry, contact, logo_key, deleted_at |
| memberships | company_id, user_id, role, unique(company_id, user_id), initially owner only |
| bots | id, company_id, public_id unique, draft_config JSONB, draft_revision, active_publication_id, disabled_at |
| publications | id, bot_id, version unique per bot, immutable config snapshot, prompt_version, created_at |
| publication_sources | publication_id, document_version_id, composite primary key |
| documents | id, company_id, bot_id, kind, title, source_url nullable, storage_key nullable, active_version_id, deleted_at |
| document_versions | id, document_id, version unique per document, checksum, status, stage, chunk_count, embedding_model, dimensions, error_code, ready_at |
| chunks | id, version_id, ordinal unique per version, page, heading, text or private text_ref, vector_id unique, checksum |
| jobs | id, company_id, document_version_id, kind, queue_kind, state, stage, attempts, max_attempts, available_at, lease_token, lease_expires_at, checkpoint_ref, error_code, idempotency_key unique |
| job_attempts | job_id, attempt, lease_token, started_at, ended_at, stage, safe_error, unique(job_id, attempt) |
| visitor_sessions | id, bot_id, token_hash unique, origin, expires_at, revoked_at |
| conversations | id, company_id, bot_id, owner_user_id nullable, visitor_session_id nullable, publication_id, context_scope, created_at |
| messages | id, conversation_id, role, content, status, generation_id, citations JSONB, usage JSONB, created_at |
| leads | conversation_id, name nullable, email nullable, consent_at, created_at |
| feedback | id, message_id, visitor_session_id or owner_user_id, rating, comment, unique per actor/message |
| usage_reservations | id, scope, budget_day, request_id unique, units, state, expires_at |
| usage_daily | scope, budget_day, request_count, tokens, embedding_units, unique(scope,budget_day) |
| audit_events | id, company_id nullable, actor_id, action, target_id, request_id, safe_metadata, created_at |

Index documents by company/bot/deleted state, jobs by due state/available_at and lease expiry, messages by conversation/time, and sessions by user/expiry. Add ownership predicates to every query. Cross-company references require transactional validation or composite foreign keys. Database row-level security may add defense in depth but does not replace API authorization.

## State machines

Source version states are `pending`, `processing`, `retrying`, `quota_wait`, `ready`, `failed`, `retired`. `stage` records validate/extract/chunk/embed/upsert/finalize. A temporary failure enters retrying. Failed means permanent or exhausted, not every transient attempt. Job state and source state are updated atomically where possible.

Message states are `pending`, `streaming`, `completed`, `failed`, `interrupted`. Persist a completed response only once per generation ID. Mark abandoned streams interrupted with a periodic reconciliation task.

## Retention and deletion

Start with 30-day conversations/leads retention, 30-day audit retention, and 24-hour processing-artifact retention after terminal jobs. Owner-visible policy must match actual cleanup. Security session records expire and are pruned. User deletion immediately revokes sessions/publication, schedules source/vector/file cleanup and reports cleanup status. Backups expire on a defined seven-day rolling policy for the beta. Explain that deleted content ages out of backups rather than claiming instant erasure from historical backups.

Redis keys use company, bot and publication scope. Do not use Redis as the only record of job failures or completed conversations. Pinecone metadata includes company_id, bot_id, document_id, version_id, chunk_id, page and embedding model. Store document text separately so the vector store remains replaceable.
