"""Facebook Messenger (Meta Graph API) adapter (D6.4, code only --
inbound wiring is verified Day 10 per launch/13-SPRINT-10-DAYS.md).
Shares the same webhook signature scheme and Graph API family as
WhatsApp, but sends through the page's own access token.
"""
import logging

import httpx

from app.config import settings

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com"


def _graph_url(path: str) -> str:
    return f"{GRAPH_BASE}/{settings().channels_api_version}/{path}"


def send_text_message(recipient_psid: str, text: str) -> str | None:
    s = settings()
    if not s.messenger_page_access_token:
        log.warning("Messenger not configured, skipping send to %s", recipient_psid)
        return None
    try:
        resp = httpx.post(
            _graph_url("me/messages"),
            params={"access_token": s.messenger_page_access_token},
            json={"recipient": {"id": recipient_psid}, "message": {"text": text[:2000]}},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            msg_id = data.get("message_id")
            log.info("Messenger message sent, id=%s", msg_id)
            return msg_id
        log.warning("Messenger send returned %s: %s", resp.status_code, resp.text[:500])
        return None
    except Exception:
        log.exception("failed to send Messenger message")
        return None


def parse_inbound_webhook(payload: dict) -> dict:
    """Normalizes a Messenger webhook payload ({"object": "page", ...})
    into {"messages": [{"page_id", "sender_id", "text", "message_id"}]}."""
    messages = []
    for entry in payload.get("entry", []):
        page_id = entry.get("id")
        for event in entry.get("messaging", []) or []:
            message = event.get("message") or {}
            if message.get("is_echo"):
                continue  # our own outbound message echoed back, not inbound
            text = message.get("text", "")
            if not text:
                continue
            messages.append({
                "page_id": page_id,
                "sender_id": (event.get("sender") or {}).get("id"),
                "text": text,
                "message_id": message.get("mid"),
            })
    return {"messages": messages}
