"""Live inbox + visitor state SSE streams (ADR 005).

Owner inbox: GET /api/v1/inbox/stream?since=<iso timestamp> -- subscribes
to inbox:{company_id}, seeded from event_outbox so a reconnect never
misses events the Redis channel dropped while disconnected.

Visitor state: GET /api/v1/public/conversations/{id}/stream -- a sidecar
to the existing chat SSE (which only streams one message turn at a time);
this one stays open for the life of the tab and pushes handoff/agent-
joined state events.
"""
import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse

from app.auth.service import SessionPrincipal
from app.db import connection
from app.deps import get_verified_principal
from app.realtime.pubsub import conversation_channel, inbox_channel, subscribe

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["realtime"])

SSE_HEADERS = {"Cache-Control": "no-cache, no-transform", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
HEARTBEAT_SECONDS = 20.0

_INBOX_TOPICS = (
    "conversation.message",
    "conversation.agent_message",
    "conversation.handoff_requested",
    "conversation.assigned",
    "conversation.resolved",
    "conversation.returned_to_bot",
)
_CONVERSATION_TOPICS = (
    "conversation.agent_message",
    "conversation.handoff_requested",
    "conversation.assigned",
    "conversation.resolved",
    "conversation.returned_to_bot",
)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _seed_from_outbox(company_id: str, since: str | None, topics: tuple[str, ...], conversation_id: str | None = None) -> list[dict]:
    with connection() as conn:
        if conversation_id:
            rows = conn.execute(
                """
                SELECT topic, payload, created_at FROM event_outbox
                WHERE company_id = %s AND topic = ANY(%s)
                  AND payload->>'conversation_id' = %s
                  AND (%s::timestamptz IS NULL OR created_at > %s::timestamptz)
                ORDER BY created_at ASC LIMIT 200
                """,
                (company_id, list(topics), conversation_id, since, since),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT topic, payload, created_at FROM event_outbox
                WHERE company_id = %s AND topic = ANY(%s)
                  AND (%s::timestamptz IS NULL OR created_at > %s::timestamptz)
                ORDER BY created_at ASC LIMIT 200
                """,
                (company_id, list(topics), since, since),
            ).fetchall()
        return [{"type": r["topic"], "data": r["payload"], "created_at": r["created_at"].isoformat()} for r in rows]


async def _stream(channel: str, seed_events: list[dict]) -> "asyncio.Any":
    for event in seed_events:
        yield _sse(event["type"], event["data"])

    agen = subscribe(channel)
    try:
        iterator = agen.__aiter__()
        while True:
            task = asyncio.ensure_future(iterator.__anext__())
            done, _ = await asyncio.wait({task}, timeout=HEARTBEAT_SECONDS)
            if not done:
                yield ": heartbeat\n\n"
                continue
            try:
                message = task.result()
            except StopAsyncIteration:
                return
            yield _sse(message["type"], message["data"])
    finally:
        aclose = getattr(agen, "aclose", None)
        if aclose:
            try:
                await aclose()
            except Exception:
                pass


@router.get("/inbox/stream")
async def inbox_stream(
    since: str | None = Query(default=None),
    principal: SessionPrincipal = Depends(get_verified_principal),
):
    seed = await asyncio.to_thread(_seed_from_outbox, principal.company_id, since, _INBOX_TOPICS)
    return StreamingResponse(_stream(inbox_channel(principal.company_id), seed), media_type="text/event-stream", headers=SSE_HEADERS)
