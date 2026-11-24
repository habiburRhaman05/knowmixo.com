"""Executor registry: maps a job's `kind` to the function that actually
does the work. Phase 2 ships only synthetic executors to prove the runner
is crash-safe before any real parsing/embedding code depends on it
(docs/19-BACKEND-SPRINT-PLAN-V2.md Phase 2). Phase 3 adds 'ingest_document'
here -- the runner itself does not change.

Executor signature: executor(conn, job: dict, heartbeat: Callable[[], bool]) -> None
  - raise TransientJobError for a retry-eligible failure
  - raise PermanentJobError for invalid/unrecoverable input
  - raise QuotaWaitError for provider quota exhaustion
  - return normally on success
"""
from typing import Callable

from app.jobs.runner import PermanentJobError, QuotaWaitError, TransientJobError


def noop_test_executor(conn, job: dict, heartbeat: Callable[[], bool]) -> None:
    """Always succeeds immediately. Used to prove the claim/complete path
    works before any real ingestion logic exists."""
    return


def always_transient_fail_executor(conn, job: dict, heartbeat: Callable[[], bool]) -> None:
    """Always raises a transient error. Used to exercise the
    retry -> backoff -> dead pipeline deterministically in tests."""
    raise TransientJobError(error_code="synthetic_transient_failure", stage="test")


def always_permanent_fail_executor(conn, job: dict, heartbeat: Callable[[], bool]) -> None:
    raise PermanentJobError(error_code="synthetic_permanent_failure")


def always_quota_wait_executor(conn, job: dict, heartbeat: Callable[[], bool]) -> None:
    raise QuotaWaitError(error_code="synthetic_quota_exhausted", retry_after_seconds=60)


def ingest_document_executor(conn, job: dict, heartbeat: Callable[[], bool]) -> None:
    """Real ingestion (Phase 3). Everything here runs inside the single
    transaction the caller (app/jobs/loop.py) opened for this attempt --
    see app/ingestion/pipeline.py's module docstring for why the whole
    attempt is kept atomic rather than incrementally committed."""
    from app.ingestion.pipeline import run_ingestion
    from app.providers.embeddings import embed_batch
    from app.providers.vector_store import reconcile_chunk_count, upsert_chunks

    document_version = conn.execute(
        "SELECT * FROM document_versions WHERE id = %s", (job["document_version_id"],)
    ).fetchone()
    if not document_version:
        raise PermanentJobError("document_version_not_found")

    document = conn.execute(
        "SELECT * FROM documents WHERE id = %s", (document_version["document_id"],)
    ).fetchone()
    if not document or document["deleted_at"] is not None:
        raise PermanentJobError("document_not_found_or_deleted")

    conn.execute("UPDATE document_versions SET status = 'processing' WHERE id = %s", (document_version["id"],))

    chunk_count = run_ingestion(
        conn=conn,
        document=document,
        document_version=document_version,
        embed_fn=embed_batch,
        upsert_fn=upsert_chunks,
        reconcile_fn=reconcile_chunk_count,
        heartbeat=heartbeat,
    )

    from app.config import settings

    s = settings()
    conn.execute(
        """
        UPDATE document_versions
        SET status = 'ready', stage = 'finalize', chunk_count = %s,
            embedding_model = %s, dimensions = %s, ready_at = now()
        WHERE id = %s
        """,
        (chunk_count, s.embedding_model, s.embedding_dim, document_version["id"]),
    )
    conn.execute(
        "UPDATE documents SET active_version_id = %s, updated_at = now() WHERE id = %s",
        (document_version["id"], document["id"]),
    )


def company_cleanup_executor(conn, job: dict, heartbeat: Callable[[], bool]) -> None:
    """Async half of account deletion (docs/16 DELETE /me): vectors first
    (a transient provider failure retries the whole job, data is purged only
    once vectors are gone), then all tenant rows. Idempotent."""
    from app.bots.history import purge_company_data
    from app.providers.vector_store import delete_company_vectors

    company_id = str(job["company_id"])
    delete_company_vectors(company_id)
    heartbeat()
    purge_company_data(conn, company_id)


def crawl_discover_executor(conn, job: dict, heartbeat: Callable[[], bool]) -> None:
    """Runs sitemap/link discovery for a crawl_jobs row (docs/16
    POST /sources/crawl/discover) and stores the page list for the owner to
    select from. The crawl job id travels in jobs.checkpoint_ref."""
    from app.ingestion.crawler import CrawlError, discover_pages

    ref = job.get("checkpoint_ref") or {}
    crawl_job_id = ref.get("crawl_job_id")
    row = conn.execute(
        "SELECT id, root_url, max_pages FROM crawl_jobs WHERE id = %s AND company_id = %s",
        (crawl_job_id, job["company_id"]),
    ).fetchone()
    if not row:
        raise PermanentJobError("crawl_job_not_found")

    conn.execute("UPDATE crawl_jobs SET status = 'running', updated_at = now() WHERE id = %s", (row["id"],))
    try:
        pages = discover_pages(row["root_url"], max_pages=row["max_pages"])
    except CrawlError as exc:
        conn.execute(
            "UPDATE crawl_jobs SET status = 'failed', error_code = %s, updated_at = now() WHERE id = %s",
            (exc.code, row["id"]),
        )
        return  # a terminal, user-visible failure on the crawl job, not a runner retry
    heartbeat()
    import json
    from urllib.parse import urlparse

    discovered = [{"url": u, "title": urlparse(u).path.strip("/") or urlparse(u).netloc} for u in pages]
    conn.execute(
        "UPDATE crawl_jobs SET status = 'completed', discovered_pages = %s::jsonb, updated_at = now() WHERE id = %s",
        (json.dumps(discovered), row["id"]),
    )


DEFAULT_EXECUTORS: dict[str, Callable] = {
    "company_cleanup": company_cleanup_executor,
    "crawl_discover": crawl_discover_executor,
    "noop_test": noop_test_executor,
    "always_transient_fail_test": always_transient_fail_executor,
    "always_permanent_fail_test": always_permanent_fail_executor,
    "always_quota_wait_test": always_quota_wait_executor,
    "ingest_document": ingest_document_executor,
}
