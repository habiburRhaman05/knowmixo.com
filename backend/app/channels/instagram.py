"""Instagram messaging (Meta Graph API) adapter (D6.4, code only --
inbound wiring is verified Day 10). Instagram DMs route through the
same Graph API messages endpoint as Messenger, keyed by the IG-linked
page's access token, so this mirrors messenger.py almost exactly.
"""
import logging

import httpx

from app.config import settings

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com"


def _graph_url(path: str) -> str:
    return f"{GRAPH_BASE}/{settings().channels_api_version}/{path}"


def send_text_message(recipient_igsid: str, text: str) -> str | None:
    s = settings()
    if not s.instagram_access_token:
        log.warning("Instagram not configured, skipping send to %s", recipient_igsid)
        return None
    try:
        resp = httpx.post(
            _graph_url("me/messages"),
            params={"access_token": s.instagram_access_token},
            json={"recipient": {"id": recipient_igsid}, "message": {"text": text[:1000]}},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            msg_id = data.get("message_id")
            log.info("Instagram message sent, id=%s", msg_id)
            return msg_id
        log.warning("Instagram send returned %s: %s", resp.status_code, resp.text[:500])
        return None
    except Exception:
        log.exception("failed to send Instagram message")
        return None


def parse_inbound_webhook(payload: dict) -> dict:
    """Normalizes an Instagram webhook payload ({"object": "instagram", ...})
    into {"messages": [{"account_id", "sender_id", "text", "message_id"}]}."""
    messages = []
    for entry in payload.get("entry", []):
        account_id = entry.get("id")
        for event in entry.get("messaging", []) or []:
            message = event.get("message") or {}
            if message.get("is_echo"):
                continue
            text = message.get("text", "")
            if not text:
                continue
            messages.append({
                "account_id": account_id,
                "sender_id": (event.get("sender") or {}).get("id"),
                "text": text,
                "message_id": message.get("mid"),
            })
    return {"messages": messages}
