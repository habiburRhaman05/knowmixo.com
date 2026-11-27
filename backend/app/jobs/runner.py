"""Durable job runner over PostgreSQL `jobs` (docs/03-TRD.md "Durable
queues, retries and crashes"). This is the Phase 2 core deliverable: prove
crash-safety against synthetic jobs before any real ingestion logic uses
it (Phase 3).

Fencing invariant: every state-changing call takes the lease_token the
caller was given at claim time and includes it in the WHERE clause. If a
lease expired and another worker reclaimed the job, the original worker's
calls affect zero rows and return False -- it must not write any further
state (not even "I finished"), because it no longer owns the job. This is
what makes "a worker finishing with a stale lease token cannot publish
status" (docs/03-TRD.md) true at the SQL level, not just by convention.
"""
import random
import uuid

BACKOFF_SCHEDULE_SECONDS = [5, 30, 120]
JITTER_RANGE = (0.8, 1.2)


class TransientJobError(Exception):
    """Retry-eligible failure (e.g. a provider timeout)."""

    def __init__(self, error_code: str, stage: str | None = None):
        super().__init__(error_code)
        self.error_code = error_code
        self.stage = stage


class PermanentJobError(Exception):
    """Invalid input or unrecoverable failure -- goes dead immediately,
    regardless of remaining attempts (docs/03-TRD.md: "Invalid input is
    permanently failed")."""

    def __init__(self, error_code: str):
        super().__init__(error_code)
        self.error_code = error_code


class QuotaWaitError(Exception):
    """Provider quota exhaustion -- defers without burning a retry
    attempt (docs/03-TRD.md: "does not burn all retries")."""

    def __init__(self, error_code: str, retry_after_seconds: int):
        super().__init__(error_code)
        self.error_code = error_code
        self.retry_after_seconds = retry_after_seconds


def compute_backoff_seconds(attempt: int) -> float:
    """attempt is 1-indexed: the attempt number that just failed. Jittered
    +/-20% around the schedule; holds at the schedule's last value for any
    attempt beyond its length."""
    index = min(max(attempt - 1, 0), len(BACKOFF_SCHEDULE_SECONDS) - 1)
    base = BACKOFF_SCHEDULE_SECONDS[index]
    return base * random.uniform(*JITTER_RANGE)


def claim_next_job(conn, lease_seconds: int) -> dict | None:
    """Atomically claims one due job: a fresh 'queued' job, a 'quota_wait'
    job whose available_at has arrived, or a 'processing' job whose lease
    expired (the previous worker crashed or was killed). FOR UPDATE SKIP
    LOCKED means concurrent workers never claim the same row."""
    lease_token = uuid.uuid4()
    row = conn.execute(
        """
        WITH candidate AS (
            SELECT id FROM jobs
            WHERE queue_kind IN ('main', 'retry')
              AND (
                    state IN ('queued', 'quota_wait')
                    OR (state = 'processing' AND lease_expires_at < now())
                  )
              AND available_at <= now()
            ORDER BY available_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        UPDATE jobs
        SET state = 'processing',
            attempts = attempts + 1,
            lease_token = %s,
            lease_expires_at = now() + make_interval(secs => %s),
            updated_at = now()
        WHERE id = (SELECT id FROM candidate)
        RETURNING *
        """,
        (str(lease_token), lease_seconds),
    ).fetchone()

    if not row:
        return None

    conn.execute(
        "INSERT INTO job_attempts (job_id, attempt, lease_token, stage) VALUES (%s, %s, %s, %s)",
        (row["id"], row["attempts"], str(lease_token), row["stage"]),
    )
    return row


def heartbeat(conn, job_id: str, lease_token: uuid.UUID, lease_seconds: int) -> bool:
    """Extends the lease while work is legitimately still in progress.
    Returns False if the lease was already stolen -- the caller must abort
    immediately and must not call complete/fail after this."""
    row = conn.execute(
        """
        UPDATE jobs
        SET lease_expires_at = now() + make_interval(secs => %s), updated_at = now()
        WHERE id = %s AND lease_token = %s AND state = 'processing'
        RETURNING id
        """,
        (lease_seconds, job_id, str(lease_token)),
    ).fetchone()
    return row is not None


def complete_job(conn, job_id: str, lease_token: uuid.UUID) -> bool:
    row = conn.execute(
        """
        UPDATE jobs
        SET state = 'succeeded', lease_token = NULL, lease_expires_at = NULL, updated_at = now()
        WHERE id = %s AND lease_token = %s AND state = 'processing'
        RETURNING attempts
        """,
        (job_id, str(lease_token)),
    ).fetchone()
    if not row:
        return False
    conn.execute(
        "UPDATE job_attempts SET ended_at = now() WHERE job_id = %s AND attempt = %s",
        (job_id, row["attempts"]),
    )
    return True


def fail_job_transient(conn, job_id: str, lease_token: uuid.UUID, error_code: str, stage: str | None = None) -> bool:
    job = conn.execute(
        "SELECT attempts, max_attempts FROM jobs WHERE id = %s AND lease_token = %s AND state = 'processing'",
        (job_id, str(lease_token)),
    ).fetchone()
    if not job:
        return False  # fenced: another worker already owns or finished this job

    conn.execute(
        "UPDATE job_attempts SET ended_at = now(), safe_error = %s, stage = %s WHERE job_id = %s AND attempt = %s",
        (error_code, stage, job_id, job["attempts"]),
    )

    if job["attempts"] >= job["max_attempts"]:
        conn.execute(
            """
            UPDATE jobs
            SET state = 'dead', queue_kind = 'dead', lease_token = NULL, lease_expires_at = NULL,
                error_code = %s, stage = %s, updated_at = now()
            WHERE id = %s AND lease_token = %s
            """,
            (error_code, stage, job_id, str(lease_token)),
        )
        return True

    delay = compute_backoff_seconds(job["attempts"])
    conn.execute(
        """
        UPDATE jobs
        SET state = 'queued', queue_kind = 'retry', lease_token = NULL, lease_expires_at = NULL,
            available_at = now() + make_interval(secs => %s), error_code = %s, stage = %s, updated_at = now()
        WHERE id = %s AND lease_token = %s
        """,
        (delay, error_code, stage, job_id, str(lease_token)),
    )
    return True


def fail_job_permanent(conn, job_id: str, lease_token: uuid.UUID, error_code: str) -> bool:
    job = conn.execute(
        "SELECT attempts FROM jobs WHERE id = %s AND lease_token = %s AND state = 'processing'",
        (job_id, str(lease_token)),
    ).fetchone()
    if not job:
        return False

    conn.execute(
        "UPDATE job_attempts SET ended_at = now(), safe_error = %s WHERE job_id = %s AND attempt = %s",
        (error_code, job_id, job["attempts"]),
    )
    conn.execute(
        """
        UPDATE jobs
        SET state = 'dead', queue_kind = 'dead', lease_token = NULL, lease_expires_at = NULL,
            error_code = %s, updated_at = now()
        WHERE id = %s AND lease_token = %s
        """,
        (error_code, job_id, str(lease_token)),
    )
    return True


def fail_job_quota(conn, job_id: str, lease_token: uuid.UUID, error_code: str, retry_after_seconds: int) -> bool:
    """Decrements attempts back down -- a quota wait must not count against
    max_attempts (docs/03-TRD.md). The job returns to the queue in
    'quota_wait' state and becomes claimable again once available_at
    arrives, without having spent one of its limited real retry attempts.

    Since this attempt number is reverted (and will be reused by the next
    real claim), its job_attempts row is deleted rather than marked ended --
    leaving it would collide with job_attempts_job_attempt_unique as soon
    as the job is reclaimed."""
    job = conn.execute(
        "SELECT attempts FROM jobs WHERE id = %s AND lease_token = %s AND state = 'processing'",
        (job_id, str(lease_token)),
    ).fetchone()
    if not job:
        return False

    conn.execute(
        "DELETE FROM job_attempts WHERE job_id = %s AND attempt = %s",
        (job_id, job["attempts"]),
    )
    conn.execute(
        """
        UPDATE jobs
        SET state = 'quota_wait', attempts = attempts - 1, lease_token = NULL, lease_expires_at = NULL,
            available_at = now() + make_interval(secs => %s), error_code = %s, updated_at = now()
        WHERE id = %s AND lease_token = %s
        """,
        (retry_after_seconds, error_code, job_id, str(lease_token)),
    )
    return True


def replay_dead_job(conn, job_id: str) -> bool:
    """Idempotent manual replay: only affects a job actually in 'dead'
    state, so a second call on an already-requeued job is a safe no-op
    (docs/03-TRD.md: "Manual replay creates a new attempt generation ...
    and remains idempotent"). Resetting attempts to 0 means the next claim
    reuses attempt numbers 1, 2, ... from the dead generation, so that
    generation's job_attempts rows are cleared here -- otherwise the first
    reclaim after replay collides with job_attempts_job_attempt_unique."""
    row = conn.execute(
        """
        UPDATE jobs
        SET state = 'queued', queue_kind = 'main', attempts = 0,
            lease_token = NULL, lease_expires_at = NULL, available_at = now(),
            error_code = NULL, stage = NULL, updated_at = now()
        WHERE id = %s AND state = 'dead'
        RETURNING id
        """,
        (job_id,),
    ).fetchone()
    if row is None:
        return False
    conn.execute("DELETE FROM job_attempts WHERE job_id = %s", (job_id,))
    return True
