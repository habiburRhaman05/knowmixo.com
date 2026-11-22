"""Pinecone adapter: deterministic chunk IDs, full authorization metadata,
and the chunk-manifest reconciliation that gates whether a version is
allowed to become 'ready' (docs/03-TRD.md steps 8-9).

Note: describe_index_stats()'s metadata-filtered count must be validated
against a real Pinecone response during the Phase 0 spike -- serverless
and pod-based indexes have historically differed in whether filtered
stats are supported, per the same "validate before trusting" discipline
as the embeddings adapter.
"""
from functools import lru_cache

from pinecone import Pinecone

from app.config import settings
from app.jobs.runner import TransientJobError


def deterministic_vector_id(company_id: str, document_id: str, version_id: str, ordinal: int) -> str:
    """Deterministic IDs mean a retried upsert of the same chunk overwrites
    rather than duplicates -- the core idempotency property for crash
    recovery mid-embed (docs/03-TRD.md step 8)."""
    return f"{company_id}:{document_id}:{version_id}:{ordinal}"


@lru_cache
def _index():
    s = settings()
    pc = Pinecone(api_key=s.pinecone_api_key)
    return pc.Index(host=s.pinecone_host) if s.pinecone_host else pc.Index(s.pinecone_index_name)


def upsert_chunks(
    bot_id: str,
    company_id: str,
    document_id: str,
    version_id: str,
    embedding_model: str,
    chunks: list[dict],
) -> int:
    """chunks: [{"ordinal", "vector_id", "vector", "page", "checksum", "heading"}, ...].
    Returns the number of vectors Pinecone itself confirms were upserted
    -- never just "how many we sent"."""
    vectors = [
        {
            "id": chunk["vector_id"],
            "values": chunk["vector"],
            "metadata": {
                "company_id": company_id,
                "bot_id": bot_id,
                "document_id": document_id,
                "version_id": version_id,
                "page": chunk.get("page") or 0,
                "checksum": chunk.get("checksum") or "",
                "embedding_model": embedding_model,
                "chunk_ordinal": chunk["ordinal"],
            },
        }
        for chunk in chunks
    ]

    try:
        result = _index().upsert(vectors=vectors, namespace=company_id)
    except Exception as exc:  # noqa: BLE001 -- Pinecone client raises several distinct exception types
        raise TransientJobError("vector_upsert_failed", stage="upsert") from exc

    upserted_count = getattr(result, "upserted_count", None)
    if upserted_count is None or upserted_count != len(vectors):
        raise TransientJobError("vector_upsert_count_mismatch", stage="upsert")

    return upserted_count


def reconcile_chunk_count(company_id: str, version_id: str, expected_count: int) -> bool:
    """Confirms Pinecone actually holds `expected_count` vectors for this
    version before PostgreSQL is allowed to mark it ready -- the single
    safety property the whole Phase 3 gate is built around."""
    try:
        stats = _index().describe_index_stats(filter={"version_id": {"$eq": version_id}})
    except Exception as exc:  # noqa: BLE001
        raise TransientJobError("vector_reconciliation_failed", stage="finalize") from exc

    namespaces = getattr(stats, "namespaces", {}) or {}
    namespace_stats = namespaces.get(company_id)
    actual_count = getattr(namespace_stats, "vector_count", 0) if namespace_stats else 0
    return actual_count == expected_count


def delete_version_vectors(company_id: str, version_id: str) -> None:
    try:
        _index().delete(filter={"version_id": {"$eq": version_id}}, namespace=company_id)
    except Exception as exc:  # noqa: BLE001
        raise TransientJobError("vector_delete_failed", stage="cleanup") from exc
