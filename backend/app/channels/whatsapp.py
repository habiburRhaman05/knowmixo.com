"""WhatsApp Cloud API adapter (D6.1, launch/06-ESCALATION-DESIGN.md §4/§13).
Template fetch, send, inbound/status webhook parsing, signature
verification, webhook handshake. Live delivery is PENDING_EXTERNAL on
Meta business verification + template approval -- every call here
no-ops and logs a warning when the required settings are blank, so the
module is safe to import and exercise in dev/CI without real credentials.
"""
import hashlib
import hmac
import logging

import httpx

from app.config import settings

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com"


def _configured() -> bool:
    s = settings()
    return bool(s.whatsapp_access_token and s.whatsapp_phone_number_id)


def _graph_url(path: str) -> str:
    return f"{GRAPH_BASE}/{settings().channels_api_version}/{path}"


def get_templates() -> list[dict]:
    s = settings()
    if not s.whatsapp_access_token or not s.whatsapp_business_account_id:
        log.warning("WhatsApp not configured, returning empty template list")
        return []
    try:
        resp = httpx.get(
            _graph_url(f"{s.whatsapp_business_account_id}/message_templates"),
            headers={"Authorization": f"Bearer {s.whatsapp_access_token}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("data", [])
    except Exception:
        log.exception("failed to fetch WhatsApp templates")
        return []


def send_template_message(to: str, template_name: str, language: str = "en_US", components: list[dict] | None = None) -> str | None:
    s = settings()
    if not _configured():
        log.warning("WhatsApp not configured, skipping template send to %s", to)
        return None
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
            "components": components or [],
        },
    }
    return _send(payload)


def send_text_message(to: str, text: str) -> str | None:
    """Free-form message, only valid inside the 24h customer-service
    window (a user-initiated contact in the last 24h)."""
    if not _configured():
        log.warning("WhatsApp not configured, skipping text send to %s", to)
        return None
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text[:4096]},
    }
    return _send(payload)


def _send(payload: dict) -> str | None:
    s = settings()
    try:
        resp = httpx.post(
            _graph_url(f"{s.whatsapp_phone_number_id}/messages"),
            headers={"Authorization": f"Bearer {s.whatsapp_access_token}", "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            messages = data.get("messages", [])
            msg_id = messages[0]["id"] if messages else None
            log.info("WhatsApp message sent, id=%s", msg_id)
            return msg_id
        log.warning("WhatsApp send returned %s: %s", resp.status_code, resp.text[:500])
        return None
    except Exception:
        log.exception("failed to send WhatsApp message")
        return None


def verify_webhook_token(mode: str | None, token: str | None, challenge: str | None) -> str | None:
    """GET handshake: Meta calls this once when the webhook URL is
    registered. Returns the challenge string to echo back, or None to
    reject (caller should 403)."""
    expected = settings().whatsapp_webhook_verify_token
    if mode == "subscribe" and expected and token == expected:
        return challenge
    return None


def verify_webhook_signature(payload_bytes: bytes, signature_header: str | None) -> bool:
    """X-Hub-Signature-256: 'sha256=<hex hmac>' over the raw request body,
    keyed by the Meta app secret."""
    secret = settings().meta_app_secret
    if not secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


def parse_inbound_webhook(payload: dict) -> dict:
    """Normalizes a WhatsApp webhook payload into
    {"messages": [{"phone_number_id", "from", "text", "message_id"}],
     "statuses": [{"message_id", "status", "recipient_id"}]}."""
    messages = []
    statuses = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            phone_number_id = value.get("metadata", {}).get("phone_number_id")
            for msg in value.get("messages", []) or []:
                text = (msg.get("text") or {}).get("body", "")
                messages.append({
                    "phone_number_id": phone_number_id,
                    "from": msg.get("from"),
                    "text": text,
                    "message_id": msg.get("id"),
                    "type": msg.get("type", "text"),
                })
            for status in value.get("statuses", []) or []:
                statuses.append({
                    "message_id": status.get("id"),
                    "status": status.get("status"),
                    "recipient_id": status.get("recipient_id"),
                })
    return {"messages": messages, "statuses": statuses}
