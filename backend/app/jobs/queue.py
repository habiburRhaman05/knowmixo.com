"""Enqueue API for the durable job table. Callers (auth-protected routes in
Phase 3+) create a job in the same transaction as the domain row it belongs
to (e.g. a document_version), per docs/03-TRD.md: "In one PostgreSQL
transaction create the source version and durable ingestion job."
"""
import json


def enqueue_job(
    conn,
    company_id: str,
    kind: str,
    document_version_id: str | None = None,
    idempotency_key: str | None = None,
    checkpoint_ref: dict | None = None,
    max_attempts: int = 4,
) -> str:
    """Returns the job id. If idempotency_key is given and a job with that
    key already exists, returns the existing job's id instead of creating a
    duplicate -- callers get 202 with the same job_id on a retried request."""
    if idempotency_key:
        existing = conn.execute(
            "SELECT id FROM jobs WHERE idempotency_key = %s", (idempotency_key,)
        ).fetchone()
        if existing:
            return str(existing["id"])

    row = conn.execute(
        """
        INSERT INTO jobs (company_id, document_version_id, kind, max_attempts, idempotency_key, checkpoint_ref)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            company_id,
            document_version_id,
            kind,
            max_attempts,
            idempotency_key,
            json.dumps(checkpoint_ref) if checkpoint_ref is not None else None,
        ),
    ).fetchone()
    return str(row["id"])
