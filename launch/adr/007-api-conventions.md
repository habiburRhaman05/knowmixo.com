# ADR 007 — API conventions (v1 lock, OpenAPI as source of truth, errors)

**Status**: Decided 2026-11-25. Implementation Day 2.

## Context

We have `openapi.yaml` (3043 lines) auto-generated from the FastAPI app. Section 2 adds a public REST API with keys + scopes. Launch must not require clients to rewrite in month two.

## Decision

- **Lock `/api/v1` for life.** Breaking changes go into `/api/v2` running side-by-side; `/v1` deprecation requires 12-month notice.
- **OpenAPI is the source of truth.** CI runs `scripts/export_openapi.py --check` — if the FastAPI app and the committed yaml drift, the build fails.
- **Generated TS client**: `openapi-typescript` emits `frontend/src/lib/api-types.ts`. Frontend imports typed responses; CI fails if drift.
- **Error shape**: RFC 9457 problem-details JSON — `{type, title, status, code, message, request_id, retry_after_seconds?, fields?}`. Preserve the current shape for internal routes; add `type` URL for the public API only.
- **Cursor pagination** on every list.
- **Idempotency**: every mutating public API endpoint accepts `Idempotency-Key` header; stored for 24 h.

## Public API scope + API keys

- Routes: `/api/v1/public-api/*` (distinct from the browser public routes which live under `/api/v1/public/*`).
- Auth: `Authorization: Bearer km_live_...` where `km_live_` is the public prefix and `...` is the secret.
- Scopes (jsonb column): `conversations:read`, `conversations:write`, `leads:read`, `sources:write`, `events:webhook`.
- Storage: `api_keys(id, company_id, prefix, hashed, scopes jsonb, last_used_at, created_by, revoked_at)`. Secret shown once at creation; hashed with Argon2id.

## Rollback

Leave `/api/v1` unlocked for one more week while generated-client wiring completes; worst case we roll back to just FastAPI inspection. No data impact.
