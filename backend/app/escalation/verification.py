"""Opt-in verification for escalation contacts (launch/06-ESCALATION-DESIGN.md §9):
owner adds a contact -> backend sends a 6-digit code over that same
channel -> owner enters the code -> verified_at is set. Without
verified_at the dispatch worker refuses to send to that address.
"""
import logging
import secrets

from app.db import connection
from app.redis_resilience import get_redis

log = logging.getLogger(__name__)

CODE_TTL_SECONDS = 600  # 10 minutes


def _code_key(contact_id: str) -> str:
    return f"esc_verify:{contact_id}"


def send_verification_code(company_id: str, contact_id: str) -> bool:
    with connection() as conn:
        contact = conn.execute(
            "SELECT channel, address FROM escalation_contacts WHERE id = %s AND company_id = %s",
            (contact_id, company_id),
        ).fetchone()
    if not contact:
        return False

    code = f"{secrets.randbelow(1_000_000):06d}"
    try:
        get_redis().setex(_code_key(contact_id), CODE_TTL_SECONDS, code)
    except Exception:
        log.exception("failed to store verification code")
        return False

    message = f"Your Knowmivo verification code is {code}. It expires in 10 minutes."
    channel = contact["channel"]
    address = contact["address"]

    if channel == "whatsapp":
        from app.channels.whatsapp import send_text_message
        send_text_message(address, message)
    elif channel == "telegram":
        parts = address.split(":", 1)
        if len(parts) == 2:
            from app.escalation.channels.telegram import send_escalation_telegram
            send_escalation_telegram(parts[0], parts[1], "low", "Verification code", message, "", "Knowmivo")
    elif channel == "email":
        from app.escalation.channels.email_smtp import send_escalation_email
        send_escalation_email(address, "low", "Verification code", message, "", "Knowmivo")
    elif channel == "slack":
        from app.escalation.channels.slack_webhook import send_escalation_slack
        send_escalation_slack(address, "low", "Verification code", message, "", "Knowmivo")
    else:
        log.warning("cannot send verification code over channel %s", channel)
        return False

    return True


def confirm_verification_code(company_id: str, contact_id: str, code: str) -> bool:
    try:
        stored = get_redis().get(_code_key(contact_id))
    except Exception:
        log.exception("failed to read verification code")
        return False

    if not stored or stored != code:
        return False

    with connection() as conn:
        result = conn.execute(
            "UPDATE escalation_contacts SET verified_at = now() WHERE id = %s AND company_id = %s",
            (contact_id, company_id),
        )
        if result.rowcount == 0:
            return False

    try:
        get_redis().delete(_code_key(contact_id))
    except Exception:
        pass
    return True
