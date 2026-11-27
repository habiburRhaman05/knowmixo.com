# ADR 003 — Queueing + event outbox

**Status**: Decided 2026-11-25. Implementation Day 2.

## Context

We need one proven queue for ingestion, webhooks, and escalation. Current code already has a durable Postgres-backed queue (`backend/app/jobs/runner.py` with lease-tokens, fencing, dead-letter) and one running worker. We need to add event emission for webhooks (H.5) and escalation (F).

## Options

**A — Keep `jobs` runner; add outbox table for events.**
**B — Replace with Celery + Redis.** Adds ops surface for no gain at our scale.
**C — Add RabbitMQ / NATS.** Over-kill.

## Decision

**Option A.** Add `event_outbox` table:

```sql
event_outbox (
  id uuid PK,
  company_id uuid,
  topic text NOT NULL,         -- e.g. 'conversation.started'
  payload jsonb NOT NULL,
  dispatched_at timestamptz,
  attempts int DEFAULT 0,
  next_try_at timestamptz,
  dead_at timestamptz
)
```

Producers insert into `event_outbox` in the same transaction as the domain change. A new `event_dispatcher` worker (same `jobs` loop, different executor `kind='dispatch_event'`) reads, fans out to webhook_deliveries + escalation + analytics with backoff. Idempotent on `(company_id, topic, payload_hash)`.

## Trade-offs

- Preserves ACID guarantees for the domain mutation + event emission.
- Adds one more worker executor; trivial.
- Latency between commit and dispatch ≤ 1 s under normal load; acceptable for webhooks and escalation (SLA on escalation is seconds, not milliseconds).

## Rollback

Disable the dispatcher; events pile up in the outbox but no state is lost. Resume when ready.
