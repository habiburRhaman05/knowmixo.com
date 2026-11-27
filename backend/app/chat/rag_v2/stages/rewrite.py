"""Rewrite stage (launch/05-RAG-V2-SPEC.md 3.3): turns the raw visitor
message plus conversation history into one standalone query (resolving
pronouns/ellipsis from history), decomposing a compound ask into up to
3 sub-queries. Falls through to the raw text on timeout or provider
failure -- a degraded-but-working retrieval beats a failed turn.
"""
import asyncio
import logging

from app.providers.router import ProviderError, get_router

log = logging.getLogger(__name__)

REWRITE_TIMEOUT_SECONDS = 1.5
MAX_SUBQUERIES = 3

_SYSTEM_PROMPT = (
    "Given the conversation history and the user's latest message, produce one or more "
    "standalone search queries that capture what the user is asking, resolving any pronouns "
    "or references to earlier turns. If the message asks about more than one distinct thing, "
    f"split it into up to {MAX_SUBQUERIES} separate queries. Respond with JSON only: "
    '{"queries": ["standalone query 1", ...]}.'
)


def _format_history(history: list[dict]) -> str:
    return "\n".join(f"{turn['role']}: {turn['content'][:500]}" for turn in history[-6:])


async def rewrite_query(text: str, history: list[dict]) -> list[str]:
    """Returns 1-3 standalone queries, best-effort. Always returns at
    least [text] even on total failure."""
    if not history:
        return [text]

    try:
        router = get_router()
        result = await asyncio.wait_for(
            router.complete_json(
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": f"HISTORY:\n{_format_history(history)}\n\nLATEST MESSAGE:\n{text}"},
                ],
                max_tokens=250,
            ),
            timeout=REWRITE_TIMEOUT_SECONDS,
        )
        queries = result.get("queries")
        if not isinstance(queries, list) or not queries:
            raise ValueError("rewrite_response_shape_unexpected")
        cleaned = [str(q).strip() for q in queries if str(q).strip()]
        if not cleaned:
            raise ValueError("rewrite_response_empty")
        return cleaned[:MAX_SUBQUERIES]
    except (asyncio.TimeoutError, ProviderError, ValueError, TypeError) as exc:
        log.warning("rewrite fell through to raw text (%s)", exc)
        return [text]
