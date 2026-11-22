"""Cloudflare Workers AI embeddings adapter (@cf/baai/bge-m3). Validates
response shape, dimension, and finiteness before any value is trusted
(docs/03-TRD.md step 7: "Validate response count, finite values and
expected dimensions").

The exact response envelope below ({"result": {"data": [...]}}) matches
Cloudflare's documented Workers AI response shape as of the stack
decision in docs/04-STACK-AND-SERVICES.md, but that doc explicitly warns
"model page schema and examples can differ" -- this must be confirmed
against a real live call in the Phase 0 spike before this is trusted in
production, not assumed correct from documentation alone.
"""
import httpx

from app.config import settings
from app.jobs.runner import PermanentJobError, QuotaWaitError, TransientJobError

CLOUDFLARE_TIMEOUT_SECONDS = 30.0


def _is_finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))  # NaN != NaN is how we catch it


def embed_batch(texts: list[str]) -> list[list[float]]:
    s = settings()
    url = f"https://api.cloudflare.com/client/v4/accounts/{s.cloudflare_account_id}/ai/run/{s.embedding_model}"
    headers = {"Authorization": f"Bearer {s.cloudflare_api_token}"}

    try:
        response = httpx.post(url, headers=headers, json={"text": texts}, timeout=CLOUDFLARE_TIMEOUT_SECONDS)
    except httpx.TimeoutException as exc:
        raise TransientJobError("embedding_provider_timeout", stage="embed") from exc
    except httpx.HTTPError as exc:
        raise TransientJobError("embedding_provider_unreachable", stage="embed") from exc

    if response.status_code == 429:
        retry_after = int(response.headers.get("retry-after", "60"))
        raise QuotaWaitError("embedding_quota_exhausted", retry_after_seconds=retry_after)
    if response.status_code >= 500:
        raise TransientJobError("embedding_provider_error", stage="embed")
    if response.status_code >= 400:
        raise PermanentJobError("embedding_provider_rejected_request")

    try:
        body = response.json()
        data = body["result"]["data"]
    except (ValueError, KeyError, TypeError) as exc:
        raise TransientJobError("embedding_response_shape_unexpected", stage="embed") from exc

    if not isinstance(data, list) or len(data) != len(texts):
        raise TransientJobError("embedding_response_count_mismatch", stage="embed")

    for vector in data:
        if not isinstance(vector, list) or len(vector) != s.embedding_dim:
            raise PermanentJobError("embedding_dimension_mismatch")
        if not all(_is_finite(v) for v in vector):
            raise TransientJobError("embedding_contains_non_finite_values", stage="embed")

    return data
