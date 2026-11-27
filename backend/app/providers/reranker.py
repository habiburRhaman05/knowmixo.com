"""Cloudflare Workers AI reranker adapter (@cf/baai/bge-reranker-base),
D3.4 / launch/05-RAG-V2-SPEC.md §3.5. Request/response shape confirmed
against a real live call (docs/03-TRD.md "validate before trusting" --
not assumed from documentation alone):

  request:  {"query": str, "contexts": [{"text": str}, ...]}
  response: {"result": {"response": [{"id": int, "score": float}, ...]}}

`id` is the 0-indexed position of the passage in the `contexts` list sent
in the request; the response is already sorted best-first.
"""
import httpx

from app.config import settings
from app.jobs.runner import PermanentJobError, QuotaWaitError, TransientJobError

CLOUDFLARE_TIMEOUT_SECONDS = 30.0


def rerank(query: str, passages: list[str], top_k: int) -> list[tuple[int, float]]:
    """Returns (original_index, score) pairs, best-first, length <= top_k.
    Returns [] immediately for an empty passage list -- no provider call
    needed, and Cloudflare's endpoint has no defined behavior for it."""
    if not passages:
        return []

    s = settings()
    url = f"https://api.cloudflare.com/client/v4/accounts/{s.cloudflare_account_id}/ai/run/{s.reranker_model}"
    headers = {"Authorization": f"Bearer {s.cloudflare_api_token}"}
    payload = {"query": query, "contexts": [{"text": p} for p in passages]}

    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=CLOUDFLARE_TIMEOUT_SECONDS)
    except httpx.TimeoutException as exc:
        raise TransientJobError("rerank_provider_timeout", stage="rerank") from exc
    except httpx.HTTPError as exc:
        raise TransientJobError("rerank_provider_unreachable", stage="rerank") from exc

    if response.status_code == 429:
        retry_after = int(response.headers.get("retry-after", "60"))
        raise QuotaWaitError("rerank_quota_exhausted", retry_after_seconds=retry_after)
    if response.status_code >= 500:
        raise TransientJobError("rerank_provider_error", stage="rerank")
    if response.status_code >= 400:
        raise PermanentJobError("rerank_provider_rejected_request")

    try:
        body = response.json()
        results = body["result"]["response"]
    except (ValueError, KeyError, TypeError) as exc:
        raise TransientJobError("rerank_response_shape_unexpected", stage="rerank") from exc

    if not isinstance(results, list):
        raise TransientJobError("rerank_response_shape_unexpected", stage="rerank")

    pairs = []
    for item in results:
        try:
            idx, score = int(item["id"]), float(item["score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TransientJobError("rerank_response_shape_unexpected", stage="rerank") from exc
        if not (0 <= idx < len(passages)):
            raise TransientJobError("rerank_response_index_out_of_range", stage="rerank")
        pairs.append((idx, score))

    return pairs[:top_k]
