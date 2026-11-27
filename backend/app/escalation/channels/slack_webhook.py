"""Slack webhook delivery channel for escalations."""
import json
import logging

import httpx

log = logging.getLogger(__name__)


def send_escalation_slack(
    webhook_url: str,
    severity: str,
    reason_summary: str,
    ai_summary: str,
    deep_link_url: str,
    brand_name: str = "Knowmivo",
) -> str | None:
    urgency = "URGENT" if severity == "critical" else "Important"
    payload = {
        "text": f"*{brand_name} — {urgency}*\n\nReason: {reason_summary}\nSummary: {ai_summary[:300]}\n\n<{deep_link_url}|Acknowledge>",
    }
    try:
        resp = httpx.post(webhook_url, json=payload, timeout=10)
        if resp.status_code == 200:
            log.info("escalation slack message sent")
            return f"slack:{webhook_url[:30]}"
        log.warning("slack webhook returned %s", resp.status_code)
        return None
    except Exception:
        log.exception("failed to send slack escalation")
        return None
