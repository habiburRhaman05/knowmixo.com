"""Event outbox producer helper (ADR 003, alembic/versions/0013_event_outbox.py).

Call emit_event() inside the SAME transaction as the domain mutation it
reports (e.g. a conversation starting), so the event can never be
silently dropped by a crash between the domain write and the event write.
"""
import hashlib
import json

from app.jobs.queue import enqueue_job


def _payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def emit_event(conn, company_id: str, topic: str, payload: dict, bot_id: str | None = None) -> str | None:
    """Idempotent on (company_id, topic, payload_hash): re-emitting the
    same logical event (e.g. a retried request) is a no-op, not a
    duplicate dispatch job or duplicate webhook delivery.

    Returns the event_outbox row id, or None if this exact event was
    already recorded (a dispatch job for it already exists or ran)."""
    payload_hash = _payload_hash(payload)
    row = conn.execute(
        """
        INSERT INTO event_outbox (company_id, bot_id, topic, payload, payload_hash)
        VALUES (%s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (company_id, topic, payload_hash) DO NOTHING
        RETURNING id
        """,
        (company_id, bot_id, topic, json.dumps(payload, default=str), payload_hash),
    ).fetchone()
    if not row:
        return None

    event_id = str(row["id"])
    enqueue_job(
        conn,
        company_id,
        kind="dispatch_event",
        checkpoint_ref={"event_outbox_id": event_id},
        idempotency_key=f"dispatch_event:{event_id}",
    )
    return event_id
