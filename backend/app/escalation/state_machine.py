"""Escalation state machine (launch/06-ESCALATION-DESIGN.md §5):
created → queued → sent → delivered → acknowledged
                    ↓          ↓
                  failed    failed_delivery
                    ↓
             fallback_channel → dead
"""
import logging

from app.db import connection

log = logging.getLogger(__name__)

_SEVERITY_TIMEOUTS = {
    "critical": {"retry_s": 60, "escalate_s": 180, "dead_s": 900},
    "high": {"retry_s": 120, "escalate_s": 600, "dead_s": 1800},
    "medium": {"retry_s": 300, "escalate_s": 1800, "dead_s": 3600},
    "low": {"retry_s": 600, "escalate_s": 3600, "dead_s": 7200},
}


def advance_escalation(escalation_id: str) -> str:
    """Advance the escalation state machine. Returns the new state."""
    with connection() as conn:
        esc = conn.execute(
            "SELECT id, company_id, severity, state, conversation_id, deep_link_jti FROM escalations WHERE id = %s",
            (escalation_id,),
        ).fetchone()
        if not esc:
            return "not_found"

        current = esc["state"]
        company_id = str(esc["company_id"])

        if current == "created":
            contacts = conn.execute(
                """
                SELECT id, channel, address, priority, verified_at
                FROM escalation_contacts
                WHERE company_id = %s AND active = true AND verified_at IS NOT NULL
                ORDER BY priority ASC
                """,
                (company_id,),
            ).fetchall()
            if not contacts:
                conn.execute(
                    "UPDATE escalations SET state = 'failed', updated_at = now() WHERE id = %s",
                    (escalation_id,),
                )
                return "failed"
            conn.execute(
                "UPDATE escalations SET state = 'queued', updated_at = now() WHERE id = %s",
                (escalation_id,),
            )
            return "queued"

        if current == "queued":
            conn.execute(
                "UPDATE escalations SET state = 'sent', updated_at = now() WHERE id = %s",
                (escalation_id,),
            )
            return "sent"

        if current == "sent":
            conn.execute(
                "UPDATE escalations SET state = 'delivered', updated_at = now() WHERE id = %s",
                (escalation_id,),
            )
            return "delivered"

        return current


def acknowledge_escalation(escalation_id: str, user_id: str | None = None, channel: str = "link") -> bool:
    with connection() as conn:
        result = conn.execute(
            """
            UPDATE escalations
            SET state = 'acknowledged', acknowledged_at = now(), acknowledged_by = %s, acknowledged_channel = %s, updated_at = now()
            WHERE id = %s AND state NOT IN ('acknowledged', 'dead')
            """,
            (user_id, channel, escalation_id),
        )
        return result.rowcount > 0


def mark_dead(escalation_id: str) -> None:
    with connection() as conn:
        conn.execute(
            "UPDATE escalations SET state = 'dead', updated_at = now() WHERE id = %s",
            (escalation_id,),
        )
