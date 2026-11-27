"""WhatsApp escalation delivery (launch/06-ESCALATION-DESIGN.md §4.1/§4.2),
built on the generic Cloud API adapter in app.channels.whatsapp. Template
names are submitted to Meta for approval (~24-72h, PENDING_EXTERNAL);
this reuses whatsapp.send_template_message so it no-ops/logs cleanly
until that approval and the real access token land.
"""
import logging
from datetime import datetime

from app.channels.whatsapp import send_template_message

log = logging.getLogger(__name__)

_TEMPLATE_BY_SEVERITY = {
    "critical": "escalation_critical_v1",
    "high": "escalation_high_v1",
}


def send_escalation_whatsapp(
    to_address: str,
    severity: str,
    reason_summary: str,
    ai_summary: str,
    deep_link_url: str,
    brand_name: str = "Knowmivo",
) -> str | None:
    template_name = _TEMPLATE_BY_SEVERITY.get(severity, "escalation_high_v1")
    components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": brand_name},
                {"type": "text", "text": reason_summary[:80]},
                {"type": "text", "text": ai_summary[:200]},
                {"type": "text", "text": "-"},  # contact_or_dash_40 -- no visitor contact captured yet
                {"type": "text", "text": "-"},  # page_url_60 -- not tracked on this escalation yet
                {"type": "text", "text": datetime.now().strftime("%Y-%m-%d %H:%M")[:20]},
                {"type": "text", "text": deep_link_url},
            ],
        }
    ]
    msg_id = send_template_message(to_address, template_name, components=components)
    if msg_id:
        log.info("escalation WhatsApp template sent to %s", to_address)
        return f"whatsapp:{msg_id}"
    return None
