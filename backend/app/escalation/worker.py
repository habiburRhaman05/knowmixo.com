"""Escalation dispatch worker (launch/06-ESCALATION-DESIGN.md §12):
reuses the jobs runner (kind='escalation_dispatch'). Dispatches
escalations to the appropriate channel based on contact priority.
"""
import json
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import settings
from app.db import connection
from app.escalation.channels.email_smtp import send_escalation_email
from app.escalation.channels.slack_webhook import send_escalation_slack
from app.escalation.channels.telegram import send_escalation_telegram
from app.escalation.channels.whatsapp import send_escalation_whatsapp
from app.escalation.deep_link import generate_deep_link, set_jti_active
from app.redis_resilience import get_redis

log = logging.getLogger(__name__)

# Storm protection (launch/06-ESCALATION-DESIGN.md §8): per-company
# sends/minute. Beyond the hard limit, individual per-contact alerts stop
# going out and a single digest takes their place, so a bad minute
# (misconfigured rule, bot loop, mass incident) can't spam every contact
# or burn through the WhatsApp/SMS send budget.
STORM_SOFT_LIMIT_PER_MINUTE = 5
STORM_HARD_LIMIT_PER_MINUTE = 10


def _in_quiet_hours(contact: dict, now_utc: datetime | None = None) -> bool:
    """§7: per-contact quiet hours, bypassed entirely for `critical`
    severity by the caller (never checked here) -- "critical severity
    always overrides quiet hours" is a contractual requirement."""
    tz_name = contact.get("quiet_hours_tz")
    start = contact.get("quiet_hours_start")
    end = contact.get("quiet_hours_end")
    if not tz_name or start is None or end is None:
        return False
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    local_now = (now_utc or datetime.now(timezone.utc)).astimezone(tz).time()
    if start <= end:
        return start <= local_now < end
    return local_now >= start or local_now < end  # window wraps midnight


def _storm_count(company_id: str) -> int:
    """Count of escalation sends attempted for this company in the
    current UTC minute. Fails open (returns 0) on a degraded Redis, same
    policy as app.security.rate_limit.RateLimited -- never let a cache
    outage block a real alert."""
    try:
        redis = get_redis()
        minute_bucket = int(datetime.now(timezone.utc).timestamp() // 60)
        key = f"escalation_storm:{company_id}:{minute_bucket}"
        count = redis.incr(key)
        if count == 1:
            redis.expire(key, 70)
        return int(count)
    except Exception:
        log.warning("escalation storm counter unavailable, failing open", exc_info=True)
        return 0


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
        severity = esc["severity"]

        if _storm_count(company_id) > STORM_HARD_LIMIT_PER_MINUTE:
            log.warning("escalation storm hard limit hit for company %s, switching to digest", company_id)
            return _send_digest(conn, company_id)

        deep_link_url = generate_deep_link(str(esc["deep_link_jti"]))
        set_jti_active(str(esc["deep_link_jti"]))

        contacts = conn.execute(
            """
            SELECT id, channel, address, priority, quiet_hours_tz, quiet_hours_start, quiet_hours_end
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
        any_attempted = False
        for contact in contacts:
            if severity != "critical" and _in_quiet_hours(contact):
                continue  # §7: non-critical alerts wait out quiet hours; retried by the timeout sweep

            any_attempted = True
            channel = contact["channel"]
            address = contact["address"]
            attempt_num = contact["priority"]

            provider_msg_id = _deliver(
                channel, address,
                severity=severity,
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

        if any_sent:
            new_state = "sent"
        elif not any_attempted:
            # Every contact is in quiet hours and nothing was sent yet --
            # leave it queued (not failed) so the timeout sweep retries
            # once a window opens, instead of giving up on a healthy setup.
            return esc["state"] if esc["state"] in ("created", "queued") else "queued"
        else:
            new_state = "failed"
        conn.execute(
            "UPDATE escalations SET state = %s, updated_at = now() WHERE id = %s",
            (new_state, escalation_id),
        )
        return new_state


def _send_digest(conn, company_id: str) -> str:
    """§8 storm protection overflow: fold every not-yet-delivered
    escalation for this company into one message to the top-priority
    contact, instead of one message per escalation. Marks all of them
    'sent' -- the shared link points at the inbox, where each is still
    individually visible and actionable, rather than at a single
    escalation's deep link."""
    pending = conn.execute(
        "SELECT id FROM escalations WHERE company_id = %s AND state IN ('created', 'queued') ORDER BY created_at ASC",
        (company_id,),
    ).fetchall()
    if not pending:
        return "sent"

    contact = conn.execute(
        """
        SELECT id, channel, address FROM escalation_contacts
        WHERE company_id = %s AND active = true AND verified_at IS NOT NULL
        ORDER BY priority ASC LIMIT 1
        """,
        (company_id,),
    ).fetchone()

    pending_ids = [str(r["id"]) for r in pending]
    if not contact:
        conn.execute(
            "UPDATE escalations SET state = 'failed', updated_at = now() WHERE id = ANY(%s)",
            (pending_ids,),
        )
        return "failed"

    bot = conn.execute(
        "SELECT b.draft_config->>'name' AS name FROM bots b WHERE b.company_id = %s LIMIT 1",
        (company_id,),
    ).fetchone()
    brand_name = (bot["name"] if bot and bot["name"] else "Knowmivo")
    inbox_url = f"{settings().public_app_url}/inbox"
    provider_msg_id = _deliver(
        contact["channel"], contact["address"],
        severity="high",
        reason_summary=f"{len(pending_ids)} alerts in the last minute",
        ai_summary="Too many alerts arrived at once -- showing a single digest instead of one message each. Open the inbox to see and act on all of them.",
        deep_link_url=inbox_url,
        brand_name=brand_name,
    )
    for escalation_id in pending_ids:
        conn.execute(
            """
            INSERT INTO escalation_attempts (escalation_id, company_id, attempt, channel, address, provider_message_id, state)
            VALUES (%s, %s, 1, %s, %s, %s, %s)
            """,
            (escalation_id, company_id, contact["channel"], contact["address"], provider_msg_id,
             "sent" if provider_msg_id else "failed"),
        )

    conn.execute(
        "UPDATE escalations SET state = 'sent', updated_at = now() WHERE id = ANY(%s)",
        (pending_ids,),
    )
    return "sent"


def check_timeout(escalation_id: str) -> str:
    """§5/§7 re-escalation timing (F.7 launch punch-list item): enqueued by
    app/jobs/escalation_timeout_sweep.py for every unacknowledged
    escalation. Per the SLA table (app.escalation.state_machine):
    - past `dead_s` with no ack: mark dead, notify the owner.
    - `failed` past `retry_s`: retried from the top contact.
    - `sent` but unacknowledged past `escalate_s`: escalated to the next
      untried contact by priority (the fallback channel in §5), and the
      clock restarts for that contact.
    Returns the resulting state, or 'noop'/'not_found' when nothing
    needed to happen."""
    from app.escalation.state_machine import _SEVERITY_TIMEOUTS

    with connection() as conn:
        esc = conn.execute(
            """
            SELECT id, company_id, severity, state, reason_summary, ai_summary,
                   deep_link_jti, conversation_id, acknowledged_at, updated_at
            FROM escalations WHERE id = %s
            """,
            (escalation_id,),
        ).fetchone()
        if not esc:
            return "not_found"
        if esc["acknowledged_at"] is not None or esc["state"] in ("acknowledged", "dead"):
            return esc["state"]
        if esc["state"] not in ("sent", "failed"):
            return esc["state"]  # created/queued: the initial dispatch hasn't run yet

        thresholds = _SEVERITY_TIMEOUTS.get(esc["severity"], _SEVERITY_TIMEOUTS["low"])
        elapsed = (datetime.now(timezone.utc) - esc["updated_at"]).total_seconds()
        company_id = str(esc["company_id"])

        if elapsed >= thresholds["dead_s"]:
            conn.execute(
                "UPDATE escalations SET state = 'dead', updated_at = now() WHERE id = %s",
                (escalation_id,),
            )
            _notify_owner_escalation_dead(conn, company_id, esc)
            return "dead"

        if esc["state"] == "failed":
            if elapsed < thresholds["retry_s"]:
                return "noop"
            conn.execute(
                "UPDATE escalations SET state = 'queued', updated_at = now() WHERE id = %s",
                (escalation_id,),
            )
            return dispatch_escalation(escalation_id)

        # state == 'sent': unacknowledged past escalate_s -> next contact in priority order
        if elapsed < thresholds["escalate_s"]:
            return "noop"

        highest_tried = conn.execute(
            "SELECT COALESCE(MAX(attempt), 0) AS n FROM escalation_attempts WHERE escalation_id = %s",
            (escalation_id,),
        ).fetchone()["n"]
        next_contact = conn.execute(
            """
            SELECT id, channel, address, priority, quiet_hours_tz, quiet_hours_start, quiet_hours_end
            FROM escalation_contacts
            WHERE company_id = %s AND active = true AND verified_at IS NOT NULL AND priority > %s
            ORDER BY priority ASC LIMIT 1
            """,
            (company_id, highest_tried),
        ).fetchone()
        if not next_contact or (esc["severity"] != "critical" and _in_quiet_hours(next_contact)):
            return "noop"  # no backup left (or it's asleep); dead_s will close this out

        deep_link_url = generate_deep_link(str(esc["deep_link_jti"]))
        bot = conn.execute(
            "SELECT b.draft_config->>'name' AS name FROM bots b WHERE b.company_id = %s LIMIT 1",
            (company_id,),
        ).fetchone()
        brand_name = (bot["name"] if bot and bot["name"] else "Knowmivo")
        provider_msg_id = _deliver(
            next_contact["channel"], next_contact["address"],
            severity=esc["severity"], reason_summary=esc["reason_summary"],
            ai_summary=esc["ai_summary"], deep_link_url=deep_link_url, brand_name=brand_name,
        )
        conn.execute(
            """
            INSERT INTO escalation_attempts (escalation_id, company_id, attempt, channel, address, provider_message_id, state)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (escalation_id, company_id, next_contact["priority"], next_contact["channel"], next_contact["address"],
             provider_msg_id, "sent" if provider_msg_id else "failed"),
        )
        # Restart the ack-wait clock against the newly-notified contact,
        # regardless of whether this particular attempt succeeded -- the
        # original 'sent' state stands (someone was notified earlier).
        conn.execute("UPDATE escalations SET updated_at = now() WHERE id = %s", (escalation_id,))
        return "sent"


def _notify_owner_escalation_dead(conn, company_id: str, esc: dict) -> None:
    from app.email import send_email
    from app.events.outbox import emit_event

    emit_event(conn, company_id, "escalation.dead", {
        "escalation_id": str(esc["id"]), "conversation_id": str(esc["conversation_id"]),
        "severity": esc["severity"], "reason_summary": esc["reason_summary"],
    })
    owner = conn.execute(
        "SELECT u.email FROM users u JOIN companies c ON c.owner_user_id = u.id WHERE c.id = %s",
        (company_id,),
    ).fetchone()
    if not owner:
        return
    try:
        send_email(
            to=owner["email"],
            subject=f"Unacknowledged {esc['severity']} escalation went unanswered",
            body=(
                f"An escalation (\"{esc['reason_summary']}\") was sent to every configured contact "
                f"but never acknowledged within the time limit for its severity.\n\n"
                f"Check the conversation: {settings().public_app_url}/conversations/{esc['conversation_id']}\n\n"
                "Consider adding a backup contact or adjusting your escalation contacts."
            ),
        )
    except Exception:
        log.exception("failed to send escalation-dead notice to owner for company %s", company_id)


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
