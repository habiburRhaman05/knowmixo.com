"""Email delivery channel for escalations using SMTP (launch/06-ESCALATION-DESIGN.md §4)."""
import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

log = logging.getLogger(__name__)


def send_escalation_email(
    to_address: str,
    severity: str,
    reason_summary: str,
    ai_summary: str,
    deep_link_url: str,
    brand_name: str = "Knowmivo",
) -> str | None:
    s = settings()
    if not s.smtp_user or not s.smtp_app_password:
        log.warning("SMTP not configured, skipping email escalation")
        return None

    subject = f"{'URGENT' if severity == 'critical' else 'Important'} — {brand_name} escalation"
    # CAN-SPAM (K.15): same sender-identification + postal-address footer
    # as app/email.py -- this channel has its own SMTP send path and
    # doesn't go through send_email(), so the footer has to be applied
    # here too, not just centrally.
    from app.email import COMPANY_POSTAL_ADDRESS

    body = f"""{brand_name} — {'URGENT' if severity == 'critical' else 'Important'}

Reason: {reason_summary}
Summary: {ai_summary[:300]}

Acknowledge: {deep_link_url}

This is an automated escalation alert from {brand_name}.

---
Knowmivo · {COMPANY_POSTAL_ADDRESS}
You're receiving this because you're a configured escalation contact for this account.
"""

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = s.email_from or s.smtp_user
    msg["To"] = to_address
    msg.set_content(body)

    try:
        with smtplib.SMTP(s.smtp_host, 587, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(s.smtp_user, s.smtp_app_password)
            smtp.send_message(msg)
        log.info("escalation email sent to %s", to_address)
        return f"smtp:{to_address}"
    except Exception:
        log.exception("failed to send escalation email to %s", to_address)
        return None
