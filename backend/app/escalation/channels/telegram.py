"""Telegram delivery channel for escalations."""
import logging

import httpx

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


def send_escalation_telegram(
    bot_token: str,
    chat_id: str,
    severity: str,
    reason_summary: str,
    ai_summary: str,
    deep_link_url: str,
    brand_name: str = "Knowmivo",
) -> str | None:
    urgency = "URGENT" if severity == "critical" else "Important"
    text = (
        f"*{brand_name} — {urgency}*\n\n"
        f"Reason: {reason_summary}\n"
        f"Summary: {ai_summary[:300]}\n\n"
        f"[Acknowledge]({deep_link_url})"
    )
    try:
        resp = httpx.post(
            f"{TELEGRAM_API}/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            msg_id = data.get("result", {}).get("message_id")
            log.info("escalation telegram message sent, msg_id=%s", msg_id)
            return f"telegram:{msg_id}"
        log.warning("telegram API returned %s", resp.status_code)
        return None
    except Exception:
        log.exception("failed to send telegram escalation")
        return None
