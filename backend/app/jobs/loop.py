"""The worker process loop: claim a due job, run its executor, resolve to
complete/retry/dead/quota_wait. This is the real-process entry point;
app/jobs/runner.py's individual functions are what the crash-recovery test
suite exercises directly (killing a "worker" is just: stop calling
heartbeat/complete and let the lease expire)."""
import logging
import time

from app.db import connection
from app.jobs.executors import DEFAULT_EXECUTORS
from app.jobs.runner import (
    PermanentJobError,
    QuotaWaitError,
    TransientJobError,
    claim_next_job,
    complete_job,
    fail_job_permanent,
    fail_job_quota,
    fail_job_transient,
    heartbeat,
)

logger = logging.getLogger("knowmivo.worker")


def _make_heartbeat(job_id: str, lease_token, lease_seconds: int):
    def _beat() -> bool:
        with connection() as conn:
            return heartbeat(conn, job_id, lease_token, lease_seconds)

    return _beat


def _sync_document_version_status(job: dict, status: str, error_code: str | None) -> None:
    """Couples the generic job runner to document_versions' state machine
    (docs/05-DATABASE.md: pending/processing/retrying/quota_wait/ready/
    failed/retired). This coupling is deliberately kept in the loop layer,
    not inside app/jobs/runner.py, so the runner itself stays reusable for
    future non-ingestion job kinds (e.g. webhook delivery, docs/18) that
    have no document_version to update."""
    if job.get("kind") != "ingest_document" or not job.get("document_version_id"):
        return
    with connection() as conn:
        conn.execute(
            "UPDATE document_versions SET status = %s, error_code = %s WHERE id = %s",
            (status, error_code, job["document_version_id"]),
        )


def process_one(lease_seconds: int, executors: dict | None = None) -> bool:
    """Claims and runs at most one job. Returns True if a job was claimed
    (regardless of its outcome), False if the queue was empty."""
    executors = executors or DEFAULT_EXECUTORS

    with connection() as conn:
        job = claim_next_job(conn, lease_seconds)
    if job is None:
        return False

    job_id = str(job["id"])
    lease_token = job["lease_token"]
    executor = executors.get(job["kind"])

    if executor is None:
        with connection() as conn:
            fail_job_permanent(conn, job_id, lease_token, error_code="unknown_job_kind")
        return True

    beat = _make_heartbeat(job_id, lease_token, lease_seconds)

    try:
        with connection() as conn:
            executor(conn, job, beat)
    except TransientJobError as exc:
        with connection() as conn:
            fail_job_transient(conn, job_id, lease_token, exc.error_code, exc.stage)
            final_state = conn.execute("SELECT state FROM jobs WHERE id = %s", (job_id,)).fetchone()
        if final_state and final_state["state"] == "dead":
            _sync_document_version_status(job, "failed", exc.error_code)
        else:
            _sync_document_version_status(job, "retrying", exc.error_code)
        return True
    except PermanentJobError as exc:
        with connection() as conn:
            fail_job_permanent(conn, job_id, lease_token, exc.error_code)
        _sync_document_version_status(job, "failed", exc.error_code)
        return True
    except QuotaWaitError as exc:
        with connection() as conn:
            fail_job_quota(conn, job_id, lease_token, exc.error_code, exc.retry_after_seconds)
        _sync_document_version_status(job, "quota_wait", exc.error_code)
        return True
    except Exception as exc:  # noqa: BLE001 -- any unexpected executor bug is a transient failure, not a crash
        logger.exception("Unhandled executor error for job %s", job_id)
        with connection() as conn:
            fail_job_transient(conn, job_id, lease_token, error_code="unhandled_executor_error", stage=None)
            final_state = conn.execute("SELECT state FROM jobs WHERE id = %s", (job_id,)).fetchone()
        status = "failed" if final_state and final_state["state"] == "dead" else "retrying"
        _sync_document_version_status(job, status, "unhandled_executor_error")
        return True

    with connection() as conn:
        complete_job(conn, job_id, lease_token)
    return True


def run_forever(lease_seconds: int = 300, poll_interval_seconds: float = 2.0, executors: dict | None = None) -> None:
    """Simple poll loop. Phase 6 adds adaptive Redis-driven wake-ups per
    docs/03-TRD.md; this unconditional poll is correct but not yet
    resource-optimized, which is an explicitly deferred, not hidden, gap."""
    logger.info("Worker loop starting (lease_seconds=%s, poll_interval=%s)", lease_seconds, poll_interval_seconds)
    while True:
        try:
            claimed = process_one(lease_seconds, executors)
        except Exception:  # noqa: BLE001 -- never let the loop die on an unexpected error
            logger.exception("Worker loop iteration failed")
            claimed = False
        if not claimed:
            time.sleep(poll_interval_seconds)
