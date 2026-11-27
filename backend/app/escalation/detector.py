"""Escalation detector (launch/06-ESCALATION-DESIGN.md §2):
evaluates rules + behavioral triggers, creates escalation rows.
Runs as an event_outbox consumer for 'escalation.requested' events
(fired by intent.py's emergency fast-path).
"""
import json
import logging
import uuid

from app.db import connection
from app.escalation.rules import evaluate_rules
from app.jobs.queue import enqueue_job

log = logging.getLogger(__name__)


def detect_and_create(
    company_id: str,
    conversation_id: str,
    text: str,
    intent: str,
    severity: str,
    ai_summary: str = "",
    key_details: dict | None = None,
) -> str | None:
    """Evaluate rules, create an escalation row if warranted. Returns escalation id or None."""
    matched_rule = evaluate_rules(company_id, text, intent, severity)

    should_escalate = matched_rule is not None or severity in ("critical", "high")

    if not should_escalate:
        return None

    rule_severity = matched_rule["severity"] if matched_rule else severity
    reason = matched_rule["name"] if matched_rule else f"{intent}_{severity}"
    rule_id = str(matched_rule["id"]) if matched_rule else None

    deep_link_jti = str(uuid.uuid4())

    try:
        with connection() as conn:
            row = conn.execute(
                """
                INSERT INTO escalations (
                    company_id, conversation_id, rule_id, severity,
                    reason_summary, ai_summary, key_details, state, deep_link_jti
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, 'created', %s)
                ON CONFLICT (conversation_id, severity, date_trunc('minute', created_at AT TIME ZONE 'UTC'))
                DO NOTHING
                RETURNING id
                """,
                (
                    company_id, conversation_id,
                    rule_id,
                    rule_severity, reason,
                    ai_summary or f"Escalation triggered: {reason}",
                    json.dumps(key_details or {}),
                    deep_link_jti,
                ),
            ).fetchone()
            if row:
                escalation_id = str(row["id"])
                # Launch-blocker fix (K.1/F.7): this INSERT used to be the
                # entire effect of an escalation -- nothing anywhere ever
                # enqueued the `escalation_dispatch` job, so a triggered
                # escalation sat in state='created' forever and no contact
                # was ever actually notified, despite the tool's reply
                # telling the visitor "a human has been notified". Enqueued
                # in the SAME transaction as the INSERT so a crash between
                # the two can't silently drop the notification.
                enqueue_job(
                    conn, company_id, kind="escalation_dispatch",
                    payload={"escalation_id": escalation_id},
                    idempotency_key=f"escalation_dispatch:{escalation_id}",
                )
                return escalation_id
            return None
    except Exception:
        log.exception("failed to create escalation")
        return None


def process_escalation_event(conn, event: dict) -> None:
    """Process an event_outbox 'escalation.requested' event."""
    payload = event.get("payload") or {}
    company_id = str(event["company_id"])
    conversation_id = payload.get("conversation_id")
    if not conversation_id:
        return

    escalation_id = detect_and_create(
        company_id=company_id,
        conversation_id=conversation_id,
        text="",
        intent=payload.get("intent", "emergency"),
        severity=payload.get("severity", "critical"),
        ai_summary=payload.get("reason", "Emergency language detected"),
    )
    if escalation_id:
        from app.escalation.state_machine import advance_escalation
        advance_escalation(escalation_id)
