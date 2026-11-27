"""Escalation dispatch worker (launch/06-ESCALATION-DESIGN.md §12):
reuses the jobs runner (kind='escalation_dispatch'). Dispatches
escalations to the appropriate channel based on contact priority.
"""
import json
import logging

from app.config import settings
from app.db import connection
from app.escalation.channels.email_smtp import send_escalation_email
from app.escalation.channels.slack_webhook import send_escalation_slack
from app.escalation.channels.telegram import send_escalation_telegram
from app.escalation.channels.whatsapp import send_escalation_whatsapp
from app.escalation.deep_link import generate_deep_link, set_jti_active

log = logging.getLogger(__name__)


def dispatch_escalation(escalation_id: str) -> str:
    """Send escalation alerts to contacts in priority order.
    Returns the resulting state."""
    with connection() as conn:
        esc = conn.execute(
            """
            SELECT id, company_id, severity, reason_summary, ai_summary,
                   deep_link_jti, state, conversation_id
            FROM escalations WHERE id = %s
            """,
            (escalation_id,),
        ).fetchone()
        if not esc:
            return "not_found"
        if esc["state"] not in ("created", "queued"):
            return esc["state"]

        company_id = str(esc["company_id"])
        deep_link_url = generate_deep_link(str(esc["deep_link_jti"]))
        set_jti_active(str(esc["deep_link_jti"]))

        contacts = conn.execute(
            """
            SELECT id, channel, address, priority
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

        bot = conn.execute(
            "SELECT b.draft_config->>'name' AS name FROM bots b WHERE b.company_id = %s LIMIT 1",
            (company_id,),
        ).fetchone()
        brand_name = (bot["name"] if bot and bot["name"] else "Knowmivo")

        any_sent = False
        for contact in contacts:
            channel = contact["channel"]
            address = contact["address"]
            attempt_num = contact["priority"]

            provider_msg_id = _deliver(
                channel, address,
                severity=esc["severity"],
                reason_summary=esc["reason_summary"],
                ai_summary=esc["ai_summary"],
                deep_link_url=deep_link_url,
                brand_name=brand_name,
            )

            state = "sent" if provider_msg_id else "failed"
            conn.execute(
                """
                INSERT INTO escalation_attempts (escalation_id, company_id, attempt, channel, address, provider_message_id, state)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (escalation_id, company_id, attempt_num, channel, address, provider_msg_id, state),
            )

            if provider_msg_id:
                any_sent = True
                break

        new_state = "sent" if any_sent else "failed"
        conn.execute(
            "UPDATE escalations SET state = %s, updated_at = now() WHERE id = %s",
            (new_state, escalation_id),
        )
        return new_state


def test_alert(company_id: str, contact_id: str, severity: str = "low") -> dict:
    """POST /escalations/test (launch/06-ESCALATION-DESIGN.md §10): runs
    the real delivery path against one specific contact and marks the
    resulting escalation row test=true. Returns live delivery status for
    the UI, rather than just an escalation id, since the whole point of
    the test button is immediate feedback."""
    import uuid

    with connection() as conn:
        contact = conn.execute(
            "SELECT id, channel, address, verified_at, active FROM escalation_contacts WHERE id = %s AND company_id = %s",
            (contact_id, company_id),
        ).fetchone()
        if not contact:
            return {"error": "Contact not found"}
        if not contact["active"] or not contact["verified_at"]:
            return {"state": "failed", "error": "Contact is not verified or not active"}

        bot = conn.execute(
            "SELECT b.draft_config->>'name' AS name FROM bots b WHERE b.company_id = %s LIMIT 1",
            (company_id,),
        ).fetchone()
        brand_name = (bot["name"] if bot and bot["name"] else "Knowmivo")

        deep_link_jti = str(uuid.uuid4())
        deep_link_url = generate_deep_link(deep_link_jti)
        set_jti_active(deep_link_jti)

        esc_row = conn.execute(
            """
            INSERT INTO escalations (company_id, conversation_id, severity, reason_summary, ai_summary, key_details, state, deep_link_jti, test)
            VALUES (%s, NULL, %s, %s, %s, '{}', 'queued', %s, true)
            RETURNING id
            """,
            (company_id, severity, "Test alert", "This is a test escalation triggered from the dashboard.", deep_link_jti),
        ).fetchone()
        escalation_id = str(esc_row["id"])

        provider_msg_id = _deliver(
            contact["channel"], contact["address"],
            severity=severity, reason_summary="Test alert",
            ai_summary="This is a test escalation triggered from the dashboard.",
            deep_link_url=deep_link_url, brand_name=brand_name,
        )
        state = "sent" if provider_msg_id else "failed"

        conn.execute(
            """
            INSERT INTO escalation_attempts (escalation_id, company_id, attempt, channel, address, provider_message_id, state)
            VALUES (%s, %s, 1, %s, %s, %s, %s)
            """,
            (escalation_id, company_id, contact["channel"], contact["address"], provider_msg_id, state),
        )
        conn.execute(
            "UPDATE escalations SET state = %s, updated_at = now() WHERE id = %s",
            (state, escalation_id),
        )

        return {"escalation_id": escalation_id, "state": state, "channel": contact["channel"]}


def _deliver(
    channel: str, address: str, *, severity: str, reason_summary: str,
    ai_summary: str, deep_link_url: str, brand_name: str,
) -> str | None:
    if channel == "email":
        return send_escalation_email(address, severity, reason_summary, ai_summary, deep_link_url, brand_name)
    elif channel == "slack":
        return send_escalation_slack(address, severity, reason_summary, ai_summary, deep_link_url, brand_name)
    elif channel == "telegram":
        parts = address.split(":", 1)
        if len(parts) != 2:
            log.warning("telegram address must be bot_token:chat_id, got %s", address[:20])
            return None
        return send_escalation_telegram(parts[0], parts[1], severity, reason_summary, ai_summary, deep_link_url, brand_name)
    elif channel == "whatsapp":
        return send_escalation_whatsapp(address, severity, reason_summary, ai_summary, deep_link_url, brand_name)
    else:
        log.warning("unsupported channel %s", channel)
        return None
