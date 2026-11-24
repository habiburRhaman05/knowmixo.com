"""Job replay idempotency for Phase 8 hardening.

Provides utilities to ensure jobs can be safely replayed without
duplicate side effects. Uses idempotency keys, attempt fencing,
and deterministic job identities.
"""
import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import settings
from app.jobs.runner import (
    TransientJobError,
    PermanentJobError,
    QuotaWaitError,
)

log = logging.getLogger(__name__)

# Configuration
IDEMPOTENCY_KEY_PREFIX = "idempotency"
MAX_IDEMPOTENCY_AGE_DAYS = int(os.environ.get("MAX_IDEMPOTENCY_AGE_DAYS", "90"))


@dataclass
class JobIdempotencyResult:
    """Result of an idempotency check."""
    is_duplicate: bool
    job_id: Optional[str] = None
    existing_status: Optional[str] = None
    message: str = ""


def generate_idempotency_key(
    company_id: str,
    kind: str,
    payload: dict,
    document_version_id: Optional[str] = None,
) -> str:
    """Generate a deterministic idempotency key for a job.

    The key is based on the company, job kind, document version (if any),
    and a hash of the payload. This ensures identical requests produce
    the same key.
    """
    # Create a deterministic payload representation
    payload_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    components = [
        company_id,
        kind,
        document_version_id or "",
        hashlib.sha256(payload_str.encode()).hexdigest()[:16],
    ]

    return f"{IDEMPOTENCY_KEY_PREFIX}:{':'.join(components)}"


def check_idempotency(
    conn,
    idempotency_key: str,
) -> JobIdempotencyResult:
    """Check if a job with this idempotency key already exists.

    Returns a JobIdempotencyResult indicating if this is a duplicate
    and the status of the existing job.
    """
    row = conn.execute(
        """
        SELECT id, state, error_code, created_at
        FROM jobs
        WHERE idempotency_key = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (idempotency_key,),
    ).fetchone()

    if not row:
        return JobIdempotencyResult(is_duplicate=False)

    job_id = str(row["id"])
    status = row["state"]
    created_at = row["created_at"]

    # Check if the existing job is too old to be relevant
    age_days = (datetime.now(timezone.utc) - created_at.replace(tzinfo=timezone.utc)).days
    if age_days > MAX_IDEMPOTENCY_AGE_DAYS:
        log.info(f"Idempotency key {idempotency_key} references job {job_id} older than {MAX_IDEMPOTENCY_AGE_DAYS} days, allowing new job")
        return JobIdempotencyResult(is_duplicate=False)

    # Job exists - determine response based on state
    if status in ("succeeded", "processing", "queued", "quota_wait"):
        return JobIdempotencyResult(
            is_duplicate=True,
            job_id=job_id,
            existing_status=status,
            message=f"Job {job_id} already exists with status '{status}'",
        )
    elif status == "dead":
        # Dead jobs can be replayed
        return JobIdempotencyResult(
            is_duplicate=False,
            job_id=job_id,
            existing_status=status,
            message=f"Job {job_id} is dead, can be replayed",
        )
    else:
        # Unknown state - treat as duplicate for safety
        return JobIdempotencyResult(
            is_duplicate=True,
            job_id=job_id,
            existing_status=status,
            message=f"Job {job_id} exists with unknown status '{status}'",
        )


def enqueue_job_idempotent(
    conn,
    company_id: str,
    kind: str,
    payload: dict,
    document_version_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    max_attempts: int = 4,
    checkpoint_ref: Optional[dict] = None,
) -> tuple[str, bool]:
    """Enqueue a job with idempotency protection.

    Returns (job_id, is_new_job) where is_new_job is False if an existing
    job was found and returned instead of creating a new one.

    If idempotency_key is not provided, one is generated from the payload.
    """
    if idempotency_key is None:
        idempotency_key = generate_idempotency_key(company_id, kind, payload, document_version_id)

    # Check for existing job
    existing = conn.execute(
        "SELECT id, state FROM jobs WHERE idempotency_key = %s ORDER BY created_at DESC LIMIT 1",
        (idempotency_key,),
    ).fetchone()

    if existing:
        job_id = str(existing["id"])
        status = existing["state"]

        # If dead, replay it
        if status == "dead":
            log.info(f"Replaying dead job {job_id} for idempotency key {idempotency_key}")
            conn.execute(
                """
                UPDATE jobs
                SET state = 'queued', queue_kind = 'main', attempts = 0,
                    lease_token = NULL, lease_expires_at = NULL, available_at = now(),
                    error_code = NULL, stage = NULL, updated_at = now(),
                    checkpoint_ref = %s, max_attempts = %s
                WHERE id = %s
                """,
                (json.dumps(checkpoint_ref) if checkpoint_ref else None, max_attempts, job_id),
            )
            return job_id, False  # Not new, but replayed

        # For any other state, return existing job
        log.info(f"Idempotency hit: returning existing job {job_id} (status: {status})")
        return job_id, False

    # Create new job
    import json as json_module
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
            json_module.dumps(checkpoint_ref) if checkpoint_ref is not None else None,
        ),
    ).fetchone()

    job_id = str(row["id"])
    log.info(f"Created new job {job_id} with idempotency key {idempotency_key}")
    return job_id, True


def replay_job_idempotent(conn, job_id: str) -> tuple[bool, str]:
    """Safely replay a dead job with idempotency protection.

    Only affects jobs in 'dead' state. Returns (success, message).
    """
    # First check the job exists and is dead
    row = conn.execute(
        "SELECT id, state, idempotency_key FROM jobs WHERE id = %s",
        (job_id,),
    ).fetchone()

    if not row:
        return False, f"Job {job_id} not found"

    if row["state"] != "dead":
        return False, f"Job {job_id} is not in 'dead' state (current: {row['state']})"

    idempotency_key = row["idempotency_key"]

    # Check if there's already a newer job with the same idempotency key
    if idempotency_key:
        newer = conn.execute(
            """
            SELECT id, state FROM jobs
            WHERE idempotency_key = %s AND id != %s AND created_at > (
                SELECT created_at FROM jobs WHERE id = %s
            )
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (idempotency_key, job_id, job_id),
        ).fetchone()

        if newer:
            return False, f"Newer job {newer['id']} (status: {newer['state']}) already exists for this idempotency key"

    # Reset the dead job
    conn.execute(
        """
        UPDATE jobs
        SET state = 'queued', queue_kind = 'main', attempts = 0,
            lease_token = NULL, lease_expires_at = NULL, available_at = now(),
            error_code = NULL, stage = NULL, updated_at = now()
        WHERE id = %s AND state = 'dead'
        """,
        (job_id,),
    )

    log.info(f"Replayed dead job {job_id}")
    return True, f"Job {job_id} requeued for replay"


def get_job_attempt_history(conn, job_id: str) -> list[dict]:
    """Get the full attempt history for a job."""
    rows = conn.execute(
        """
        SELECT attempt, stage, started_at, ended_at, safe_error, lease_token
        FROM job_attempts
        WHERE job_id = %s
        ORDER BY attempt ASC
        """,
        (job_id,),
    ).fetchall()

    return [dict(r) for r in rows]


def is_safe_to_retry(conn, job_id: str, lease_token: uuid.UUID) -> tuple[bool, str]:
    """Check if a job can be safely retried (not already completed by another worker).

    This is the core fencing check - ensures the current worker still owns the job.
    """
    row = conn.execute(
        "SELECT state, lease_token FROM jobs WHERE id = %s",
        (job_id,),
    ).fetchone()

    if not row:
        return False, "Job not found"

    if row["state"] != "processing":
        return False, f"Job not in processing state (current: {row['state']})"

    if row["lease_token"] != str(lease_token):
        return False, "Lease token mismatch - job claimed by another worker"

    return True, "Safe to retry"


# Decorator for idempotent job handlers
def idempotent_job_handler(job_kind: str):
    """Decorator that wraps a job handler with idempotency protection.

    Usage:
        @idempotent_job_handler("ingest_document")
        def handle_ingest(conn, job_id, payload):
            # Your handler logic
            pass
    """
    def decorator(handler: Callable):
        def wrapper(conn, job_id: str, payload: dict, lease_token: uuid.UUID, *args, **kwargs):
            # Verify we still own this job
            safe, msg = is_safe_to_retry(conn, job_id, lease_token)
            if not safe:
                log.warning(f"Job {job_id} not safe to execute: {msg}")
                raise PermanentJobError("job_fenced")

            # Check if this attempt was already completed (idempotency within attempt)
            attempt_row = conn.execute(
                "SELECT ended_at FROM job_attempts WHERE job_id = %s AND lease_token = %s",
                (job_id, str(lease_token)),
            ).fetchone()

            if attempt_row and attempt_row["ended_at"]:
                log.info(f"Job {job_id} attempt already completed, skipping")
                return {"status": "already_completed"}

            try:
                result = handler(conn, job_id, payload, lease_token, *args, **kwargs)
                return result
            except TransientJobError:
                raise
            except PermanentJobError:
                raise
            except QuotaWaitError:
                raise
            except Exception as e:
                log.exception(f"Job {job_id} handler failed: {e}")
                raise TransientJobError("handler_error", stage=job_kind)

        return wrapper
    return decorator


# Idempotency cleanup utilities
def cleanup_old_idempotency_keys(conn, days: int = MAX_IDEMPOTENCY_AGE_DAYS) -> int:
    """Clean up old idempotency keys by deleting associated dead jobs.

    Returns number of jobs deleted.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Only delete dead jobs with old idempotency keys
    result = conn.execute(
        """
        DELETE FROM jobs
        WHERE state = 'dead'
          AND idempotency_key IS NOT NULL
          AND created_at < %s
        RETURNING id
        """,
        (cutoff,),
    )

    count = result.rowcount
    if count > 0:
        log.info(f"Cleaned up {count} old dead jobs with idempotency keys")

    return count


# Import timedelta for cleanup function
from datetime import timedelta