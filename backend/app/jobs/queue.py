"""Enqueue API for the durable job table. Callers (auth-protected routes in
Phase 3+) create a job in the same transaction as the domain row it belongs
to (e.g. a document_version), per docs/03-TRD.md: "In one PostgreSQL
transaction create the source version and durable ingestion job."
"""
import json

from app.job_idempotency import enqueue_job_idempotent, generate_idempotency_key


def enqueue_job(
    conn,
    company_id: str,
    kind: str,
    document_version_id: str | None = None,
    idempotency_key: str | None = None,
    checkpoint_ref: dict | None = None,
    max_attempts: int = 4,
    payload: dict | None = None,
) -> tuple[str, bool]:
    """Returns (job_id, is_new_job).

    If idempotency_key is given and a job with that key already exists (and
    is not dead), returns the existing job's id with is_new_job=False.
    If idempotency_key is not provided, one is generated from company/kind/
    document_version_id/payload.
    """
    if idempotency_key is None:
        idempotency_key = generate_idempotency_key(
            company_id, kind, payload or {}, document_version_id
        )

    job_id, is_new = enqueue_job_idempotent(
        conn,
        company_id=company_id,
        kind=kind,
        payload=payload or {},
        document_version_id=document_version_id,
        idempotency_key=idempotency_key,
        max_attempts=max_attempts,
        checkpoint_ref=checkpoint_ref,
    )
    return job_id, is_new
