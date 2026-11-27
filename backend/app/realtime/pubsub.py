"""Async Redis pub/sub for the live inbox and visitor state stream
(ADR 005). Separate from app.redis_resilience's sync ResilientRedis --
SSE endpoints are async and must not block the event loop on a blocking
Redis read, so this uses redis.asyncio directly. Pub/sub is
fire-and-forget: callers that need delivery guarantees also write to
event_outbox (ADR 003) via app.events.outbox.emit_event, and a stream
endpoint seeds from that table on connect before switching to live
pub/sub (see realtime/router.py).
"""
import asyncio
import json
import logging
from typing import AsyncIterator

import redis.asyncio as aioredis

from app.config import settings

log = logging.getLogger(__name__)

_client: aioredis.Redis | None = None


def _get_client() -> aioredis.Redis:
    """Cached client, bound to whatever event loop first calls this --
    only safe to use from the app's own long-lived event loop (the SSE
    router). Sync call sites must use publish_sync() instead, which opens
    an isolated connection per call rather than risk sharing a
    loop-bound connection pool across loops."""
    global _client
    if _client is None:
        _client = aioredis.from_url(settings().redis_url, decode_responses=True)
    return _client


def inbox_channel(company_id: str) -> str:
    return f"inbox:{company_id}"


def conversation_channel(conversation_id: str) -> str:
    return f"conv:{conversation_id}"


async def publish(channel: str, event_type: str, data: dict) -> None:
    """Best-effort publish. Never raises -- a dropped realtime push degrades
    UX (client falls back to the next event_outbox-seeded reconnect) but
    must never fail the request that triggered it."""
    try:
        client = _get_client()
        await client.publish(channel, json.dumps({"type": event_type, "data": data}, default=str))
    except Exception:
        log.warning("realtime publish failed for channel %s", channel, exc_info=True)


def publish_sync(channel: str, event_type: str, data: dict) -> None:
    """For synchronous call sites (pipeline.py, handoff/service.py) that
    run inside asyncio.to_thread worker threads with no event loop of
    their own. Opens and closes an isolated connection per call instead
    of touching the cached asyncio client above, which is loop-bound and
    would break if shared across ad-hoc asyncio.run() loops."""
    try:
        asyncio.run(_publish_oneshot(channel, event_type, data))
    except Exception:
        log.warning("realtime publish_sync failed for channel %s", channel, exc_info=True)


async def _publish_oneshot(channel: str, event_type: str, data: dict) -> None:
    client = aioredis.from_url(settings().redis_url, decode_responses=True)
    try:
        await client.publish(channel, json.dumps({"type": event_type, "data": data}, default=str))
    finally:
        await client.aclose()


async def subscribe(channel: str) -> AsyncIterator[dict]:
    """Yields decoded {"type":..., "data":...} messages for `channel`
    until the caller stops iterating (e.g. client disconnect)."""
    client = _get_client()
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(channel)
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                yield json.loads(message["data"])
            except (TypeError, ValueError):
                log.warning("dropped malformed realtime message on %s", channel)
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
        except Exception:
            pass
