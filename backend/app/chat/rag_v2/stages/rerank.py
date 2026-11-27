"""Cross-encoder rerank stage (D3.4, launch/05-RAG-V2-SPEC.md §3.5):
rerank the ~30 retrieve() candidates down to `top_k` (default 8) using
Cloudflare's bge-reranker-base.

Failure mode per the spec's §7 table ("Rerank | provider 5xx |
fallthrough -- skip rerank, log"): a reranker outage must never fail the
whole turn. On any ProviderError from the adapter, this falls back to
the passages' own incoming order (already RRF-ranked) truncated to
top_k, and logs -- a visibly worse answer is acceptable; a 503 on every
chat message when the reranker alone is down is not.
"""
import logging

from app.chat.rag_v2.base import Passage
from app.jobs.runner import PermanentJobError, QuotaWaitError, TransientJobError
from app.providers.reranker import rerank as rerank_provider

log = logging.getLogger(__name__)

DEFAULT_TOP_K = 8


def rerank(query: str, passages: list[Passage], top_k: int = DEFAULT_TOP_K) -> list[Passage]:
    if not passages:
        return []

    try:
        pairs = rerank_provider(query, [p.text for p in passages], top_k=top_k)
    except (TransientJobError, PermanentJobError, QuotaWaitError) as exc:
        log.warning("rerank provider failed, falling back to RRF order: %s", exc)
        return passages[:top_k]

    reranked = []
    for idx, score in pairs:
        passage = passages[idx]
        passage.score_rerank = score
        reranked.append(passage)
    return reranked
