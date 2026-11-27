# ADR 009 — Data retention, soft delete, backups

**Status**: Decided 2026-11-25. Implementation Day 7 + Day 10.

## Context

`retention_days=30` is a config default today; `backend/app/jobs/retention_sweep.py` exists and purges old `conversations`, `leads`, `audit_events`, `webhook_deliveries` once instrumented. Backups rely on Neon PITR; never verified.

## Decision

- **Per-plan retention**: 30 d (Starter), 90 d (Growth), 1 y (Scale). Owner can reduce below plan maximum. Hard-delete after retention window; export is always available for 7 days post-retention.
- **Soft delete window**: `deleted_at` already exists on documents + companies. 7 days of grace, then hard-delete worker.
- **Backups**: Neon PITR at 24 h. Weekly cron copies the day's `pg_dump` of critical schemas to R2 (worst case: restore from `.sql`).
- **Restore drill**: Day 10 task — restore a company's data to a scratch DB; verify row counts match.
- **PII redaction toggle**: owner setting; nightly batch redacts transcripts older than N days (replaces email/phone/credit-card regex matches with `[REDACTED]`).
- **Export pre-delete**: on any destructive owner action (DELETE /me, DELETE /conversations/{id}), surface the "export first?" button before the confirm.

## Rollback

Toggle `retention.hard_delete = false`; data lingers indefinitely but UI still respects retention filter. Must still comply with CCPA deletion requests via a separate code path.
