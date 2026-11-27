"""Drives an inbound channel message (WhatsApp/Messenger/Instagram)
through the existing chat pipeline and sends the reply back out over
the same channel (D6.4). Runs inside a job executor, not inline in the
webhook handler -- Meta webhooks expect a fast 200 ack and retry
aggressively if the handler is slow, so the handler only enqueues.
"""
import asyncio
import logging

from app.chat import pipeline
from app.chat.pipeline import ChatError
from app.channels.bindings import get_or_create_channel_conversation
from app.config import settings
from app.db import connection

log = logging.getLogger(__name__)


def _send_reply(channel: str, external_id: str, text: str) -> None:
    if channel == "whatsapp":
        from app.channels.whatsapp import send_text_message
        send_text_message(external_id, text)
    elif channel == "messenger":
        from app.channels.messenger import send_text_message
        send_text_message(external_id, text)
    elif channel == "instagram":
        from app.channels.instagram import send_text_message
        send_text_message(external_id, text)
    else:
        log.warning("unknown channel %s, cannot send reply", channel)


async def _drain_answer(turn) -> str:
    """Runs the configured pipeline (v1 or v2) to completion and returns
    just the final assistant text -- channel adapters are request/response,
    not SSE, so only the finished answer matters here."""
    if settings().rag_engine == "v2":
        from app.chat.rag_v2.pipeline import stream_turn_v2 as stream_fn
    else:
        stream_fn = pipeline.stream_turn

    answer = ""
    async for event in stream_fn(turn):
        if event.startswith("event: delta"):
            for line in event.splitlines():
                if line.startswith("data: "):
                    import json
                    data = json.loads(line.removeprefix("data: "))
                    answer += data.get("text", "")
    return answer


def process_inbound_message(company_id: str, bot_id: str, channel: str, external_id: str, text: str) -> None:
    conv = get_or_create_channel_conversation(company_id, bot_id, channel, external_id)

    with connection() as conn:
        scope = pipeline.visitor_scope(conn, conv["visitor_session_id"], conv["conversation_id"])

    try:
        turn = pipeline.prepare_turn(scope, text, client_key=None)
    except ChatError as exc:
        log.warning("channel inbound prepare_turn failed: %s", exc.code)
        if exc.code != "request_in_progress":
            _send_reply(channel, external_id, "Sorry, something went wrong. Please try again in a moment.")
        return

    if turn.replay:
        _send_reply(channel, external_id, turn.replay["content"])
        return

    answer = asyncio.run(_drain_answer(turn))
    if answer:
        _send_reply(channel, external_id, answer)
