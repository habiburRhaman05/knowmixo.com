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
import json
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


def dispatch_event_executor(conn, job: dict, heartbeat: Callable[[], bool]) -> None:
    """Fans out one event_outbox row to webhook_deliveries for every
    active endpoint subscribed to its topic (ADR 003,
    app/events/outbox.py). Idempotent: a retried job after a crash
    partway through re-inserting deliveries skips endpoints already
    notified (idx_webhook_deliveries_event_endpoint), and is a complete
    no-op if the event was already fully dispatched."""
    ref = job.get("checkpoint_ref") or {}
    event_id = ref.get("event_outbox_id")
    event = conn.execute(
        "SELECT * FROM event_outbox WHERE id = %s AND company_id = %s",
        (event_id, job["company_id"]),
    ).fetchone()
    if not event:
        raise PermanentJobError("event_outbox_row_not_found")
    if event["dispatched_at"] is not None:
        return

    endpoints = conn.execute(
        """
        SELECT id FROM webhook_endpoints
        WHERE company_id = %s AND is_active
          AND %s = ANY(events)
          AND (bot_id IS NULL OR bot_id = %s)
        """,
        (event["company_id"], event["topic"], event["bot_id"]),
    ).fetchall()

    for endpoint in endpoints:
        conn.execute(
            """
            INSERT INTO webhook_deliveries (endpoint_id, event_type, payload, event_outbox_id)
            VALUES (%s, %s, %s::jsonb, %s)
            ON CONFLICT (event_outbox_id, endpoint_id) WHERE event_outbox_id IS NOT NULL DO NOTHING
            """,
            (endpoint["id"], event["topic"], json.dumps(event["payload"], default=str), event_id),
        )
    conn.execute("UPDATE event_outbox SET dispatched_at = now() WHERE id = %s", (event_id,))


def check_source_for_changes_executor(conn, job: dict, heartbeat: Callable[[], bool]) -> None:
    """D3.5 change-detection scaffolding: re-fetches a URL/crawl-page
    source, and only triggers re-ingestion (via the same path the owner's
    manual 'refresh' button uses) when the content actually changed.
    Enqueued by app/jobs/change_detection_sweep.py, not by any endpoint yet
    -- the per-source schedule UI is Day 7."""
    from app.ingestion.change_detection import has_changed
    from app.security.ssrf_http import SSRFBlocked
    from app.sources.service import refresh_document

    ref = job.get("checkpoint_ref") or {}
    document_id = ref.get("document_id")
    document = conn.execute(
        "SELECT id, source_url, source_checksum FROM documents WHERE id = %s AND company_id = %s AND deleted_at IS NULL",
        (document_id, job["company_id"]),
    ).fetchone()
    if not document or not document["source_url"]:
        raise PermanentJobError("document_not_found_or_not_url_sourced")

    try:
        changed, new_checksum = has_changed(document)
    except SSRFBlocked as exc:
        raise PermanentJobError(f"change_check_blocked:{exc.args[0] if exc.args else 'ssrf'}") from exc

    conn.execute(
        "UPDATE documents SET last_checked_at = now(), source_checksum = %s WHERE id = %s",
        (new_checksum, document["id"]),
    )
    if changed:
        refresh_document(conn, job["company_id"], str(document["id"]))


def process_stripe_events_executor(conn, job: dict, heartbeat: Callable[[], bool]) -> None:
    from app.billing.processor import process_pending_events
    processed = process_pending_events()
    if processed == 0:
        return
    heartbeat()


def channel_inbound_message_executor(conn, job: dict, heartbeat: Callable[[], bool]) -> None:
    from app.channels.inbound import process_inbound_message
    payload = job.get("payload") or {}
    required = ("company_id", "bot_id", "channel", "external_id", "text")
    if not all(payload.get(k) for k in required):
        raise PermanentJobError("missing_channel_inbound_fields")
    process_inbound_message(
        payload["company_id"], payload["bot_id"], payload["channel"],
        payload["external_id"], payload["text"],
    )


def compute_gaps_executor(conn, job: dict, heartbeat: Callable[[], bool]) -> None:
    from app.quality.gaps import recompute_gaps
    payload = job.get("payload") or {}
    bot_id = payload.get("bot_id")
    if not bot_id:
        raise PermanentJobError("missing_bot_id")
    recompute_gaps(job["company_id"], bot_id)


def evaluate_alerts_executor(conn, job: dict, heartbeat: Callable[[], bool]) -> None:
    from app.quality.alerts import evaluate_all_companies
    evaluate_all_companies()


def escalation_dispatch_executor(conn, job: dict, heartbeat: Callable[[], bool]) -> None:
    from app.escalation.worker import dispatch_escalation
    payload = job.get("payload") or {}
    escalation_id = payload.get("escalation_id")
    if not escalation_id:
        raise PermanentJobError("missing_escalation_id")
    dispatch_escalation(escalation_id)


def escalation_timeout_check_executor(conn, job: dict, heartbeat: Callable[[], bool]) -> None:
    """F.7: enqueued by app/jobs/escalation_timeout_sweep.py for every
    unacknowledged escalation due a check (retry/escalate/dead per the
    SLA table in app.escalation.state_machine)."""
    from app.escalation.worker import check_timeout
    payload = job.get("payload") or {}
    escalation_id = payload.get("escalation_id")
    if not escalation_id:
        raise PermanentJobError("missing_escalation_id")
    check_timeout(escalation_id)


def send_dunning_email_executor(conn, job: dict, heartbeat: Callable[[], bool]) -> None:
    payload = job.get("payload") or {}
    stripe_invoice_id = payload.get("stripe_invoice_id")
    attempt = payload.get("attempt", 1)
    company_id = job["company_id"]
    row = conn.execute(
        "SELECT u.email, u.name FROM users u JOIN companies c ON c.owner_user_id = u.id WHERE c.id = %s",
        (company_id,),
    ).fetchone()
    if not row:
        raise PermanentJobError("no_owner_for_dunning")
    # TODO: actual email sending via app.email once templates exist
    import logging
    logging.getLogger(__name__).info(
        "dunning email (attempt %s) for invoice %s to %s", attempt, stripe_invoice_id, row["email"]
    )


DEFAULT_EXECUTORS: dict[str, Callable] = {
    "company_cleanup": company_cleanup_executor,
    "crawl_discover": crawl_discover_executor,
    "dispatch_event": dispatch_event_executor,
    "noop_test": noop_test_executor,
    "always_transient_fail_test": always_transient_fail_executor,
    "always_permanent_fail_test": always_permanent_fail_executor,
    "always_quota_wait_test": always_quota_wait_executor,
    "ingest_document": ingest_document_executor,
    "check_source_for_changes": check_source_for_changes_executor,
    "process_stripe_events": process_stripe_events_executor,
    "send_dunning_email": send_dunning_email_executor,
    "escalation_dispatch": escalation_dispatch_executor,
    "escalation_timeout_check": escalation_timeout_check_executor,
    "channel_inbound_message": channel_inbound_message_executor,
    "compute_gaps": compute_gaps_executor,
    "evaluate_alerts": evaluate_alerts_executor,
}
