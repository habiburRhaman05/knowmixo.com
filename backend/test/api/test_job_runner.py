"""Phase 2 gate (docs/19-BACKEND-SPRINT-PLAN-V2.md): the job runner must
survive a kill-and-restart cycle with zero duplicate completions on a
synthetic job, before any real parser/embedding code depends on it.

Requires TEST_DATABASE_URL pointed at a disposable, migrated database
(migrations 0001 + 0002 applied). Skipped entirely otherwise.
"""
import uuid

import psycopg
from psycopg.rows import dict_row

from app.jobs.queue import enqueue_job
from app.jobs.runner import (
    claim_next_job,
    compute_backoff_seconds,
    complete_job,
    fail_job_permanent,
    fail_job_quota,
    fail_job_transient,
    heartbeat,
    replay_dead_job,
)


def _make_company(conn) -> str:
    user = conn.execute(
        "INSERT INTO users (normalized_email, email, name) VALUES (%s, %s, %s) RETURNING id",
        (f"{uuid.uuid4()}@example.com", "jobtest@example.com", "Job Tester"),
    ).fetchone()
    company = conn.execute(
        "INSERT INTO companies (owner_user_id, name) VALUES (%s, %s) RETURNING id",
        (user["id"], "Job Test Co"),
    ).fetchone()
    return str(company["id"])


def test_enqueue_is_idempotent_by_key(db_conn):
    company_id = _make_company(db_conn)
    job_id_1 = enqueue_job(db_conn, company_id, kind="noop_test", idempotency_key="fixed-key-1")
    job_id_2 = enqueue_job(db_conn, company_id, kind="noop_test", idempotency_key="fixed-key-1")
    assert job_id_1 == job_id_2

    count = db_conn.execute(
        "SELECT count(*) AS n FROM jobs WHERE idempotency_key = %s", ("fixed-key-1",)
    ).fetchone()["n"]
    assert count == 1


def test_claim_runs_job_through_to_completion(db_conn):
    company_id = _make_company(db_conn)
    job_id = enqueue_job(db_conn, company_id, kind="noop_test")

    job = claim_next_job(db_conn, lease_seconds=300)
    assert job is not None
    assert str(job["id"]) == job_id
    assert job["state"] == "processing"
    assert job["attempts"] == 1

    attempt_row = db_conn.execute(
        "SELECT * FROM job_attempts WHERE job_id = %s AND attempt = 1", (job_id,)
    ).fetchone()
    assert attempt_row is not None
    assert attempt_row["ended_at"] is None  # not yet completed

    assert complete_job(db_conn, job_id, job["lease_token"]) is True

    final = db_conn.execute("SELECT state FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert final["state"] == "succeeded"

    attempt_row_after = db_conn.execute(
        "SELECT ended_at FROM job_attempts WHERE job_id = %s AND attempt = 1", (job_id,)
    ).fetchone()
    assert attempt_row_after["ended_at"] is not None


def test_no_job_available_returns_none(db_conn):
    assert claim_next_job(db_conn, lease_seconds=300) is None


def test_stale_lease_is_reclaimed_after_crash(db_conn):
    """Simulates: worker A claims the job, then crashes (never calls
    heartbeat/complete/fail). After the lease expires, a new claim must
    pick the job back up -- and the original (now-fenced) worker must be
    unable to complete it after the fact."""
    company_id = _make_company(db_conn)
    job_id = enqueue_job(db_conn, company_id, kind="noop_test")

    worker_a_job = claim_next_job(db_conn, lease_seconds=300)
    assert worker_a_job is not None

    # Simulate worker A's crash: force its lease into the past.
    db_conn.execute("UPDATE jobs SET lease_expires_at = now() - interval '1 second' WHERE id = %s", (job_id,))

    worker_b_job = claim_next_job(db_conn, lease_seconds=300)
    assert worker_b_job is not None
    assert str(worker_b_job["id"]) == job_id
    assert worker_b_job["lease_token"] != worker_a_job["lease_token"]
    assert worker_b_job["attempts"] == 2  # second claim incremented attempts again

    # Worker A, unaware it was fenced, tries to complete -- must fail.
    assert complete_job(db_conn, job_id, worker_a_job["lease_token"]) is False

    # Only worker B's completion is accepted.
    assert complete_job(db_conn, job_id, worker_b_job["lease_token"]) is True

    final = db_conn.execute("SELECT state FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert final["state"] == "succeeded"  # exactly one successful completion, not two


def test_heartbeat_extends_lease_and_fails_once_fenced(db_conn):
    company_id = _make_company(db_conn)
    job_id = enqueue_job(db_conn, company_id, kind="noop_test")
    job = claim_next_job(db_conn, lease_seconds=5)

    assert heartbeat(db_conn, job_id, job["lease_token"], lease_seconds=300) is True

    # Force expiry and let another worker reclaim -- the original heartbeat must now fail.
    db_conn.execute("UPDATE jobs SET lease_expires_at = now() - interval '1 second' WHERE id = %s", (job_id,))
    claim_next_job(db_conn, lease_seconds=300)  # worker B reclaims

    assert heartbeat(db_conn, job_id, job["lease_token"], lease_seconds=300) is False


def test_transient_failure_retries_then_goes_dead_after_max_attempts(db_conn):
    company_id = _make_company(db_conn)
    job_id = enqueue_job(db_conn, company_id, kind="always_transient_fail_test", max_attempts=2)

    # Attempt 1: transient failure -> requeued as a retry.
    job = claim_next_job(db_conn, lease_seconds=300)
    assert job["attempts"] == 1
    assert fail_job_transient(db_conn, job_id, job["lease_token"], "synthetic_transient_failure") is True

    row = db_conn.execute("SELECT state, queue_kind, available_at FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row["state"] == "queued"
    assert row["queue_kind"] == "retry"
    assert row["available_at"] > db_conn.execute("SELECT now() AS n").fetchone()["n"]

    # Force availability so the test doesn't sleep through the backoff window.
    db_conn.execute("UPDATE jobs SET available_at = now() WHERE id = %s", (job_id,))

    # Attempt 2 (== max_attempts): transient failure -> dead, not another retry.
    job2 = claim_next_job(db_conn, lease_seconds=300)
    assert job2["attempts"] == 2
    assert fail_job_transient(db_conn, job_id, job2["lease_token"], "synthetic_transient_failure") is True

    final = db_conn.execute("SELECT state, queue_kind FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert final["state"] == "dead"
    assert final["queue_kind"] == "dead"


def test_permanent_failure_goes_dead_immediately(db_conn):
    company_id = _make_company(db_conn)
    job_id = enqueue_job(db_conn, company_id, kind="always_permanent_fail_test", max_attempts=4)

    job = claim_next_job(db_conn, lease_seconds=300)
    assert job["attempts"] == 1  # far from exhausting max_attempts=4

    assert fail_job_permanent(db_conn, job_id, job["lease_token"], "synthetic_permanent_failure") is True

    final = db_conn.execute("SELECT state, queue_kind FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert final["state"] == "dead"  # dead despite having retries left


def test_quota_wait_does_not_burn_an_attempt(db_conn):
    company_id = _make_company(db_conn)
    job_id = enqueue_job(db_conn, company_id, kind="always_quota_wait_test", max_attempts=4)

    job = claim_next_job(db_conn, lease_seconds=300)
    assert job["attempts"] == 1

    assert fail_job_quota(db_conn, job_id, job["lease_token"], "synthetic_quota_exhausted", retry_after_seconds=60) is True

    row = db_conn.execute("SELECT state, attempts FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row["state"] == "quota_wait"
    assert row["attempts"] == 0  # reverted -- quota waits don't count toward max_attempts

    db_conn.execute("UPDATE jobs SET available_at = now() WHERE id = %s", (job_id,))
    job2 = claim_next_job(db_conn, lease_seconds=300)
    assert job2 is not None
    assert job2["attempts"] == 1  # starts fresh, not attempt 2 of a burned budget


def test_replay_dead_job_is_idempotent(db_conn):
    company_id = _make_company(db_conn)
    job_id = enqueue_job(db_conn, company_id, kind="always_permanent_fail_test")

    job = claim_next_job(db_conn, lease_seconds=300)
    fail_job_permanent(db_conn, job_id, job["lease_token"], "synthetic_permanent_failure")

    assert replay_dead_job(db_conn, job_id) is True
    row = db_conn.execute("SELECT state, queue_kind, attempts FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row["state"] == "queued"
    assert row["queue_kind"] == "main"
    assert row["attempts"] == 0

    # Second replay call on an already-requeued job must be a safe no-op.
    assert replay_dead_job(db_conn, job_id) is False


def test_backoff_schedule_is_bounded_and_jittered():
    for attempt in range(1, 6):
        delay = compute_backoff_seconds(attempt)
        assert 4.0 <= delay <= 144.0  # schedule [5,30,120] with +/-20% jitter, held at last value


def test_concurrent_workers_never_claim_the_same_job(test_database_url, db_conn):
    """Real two-connection concurrency check that FOR UPDATE SKIP LOCKED
    actually prevents a double-claim, not just the single-connection logic
    above. Needs the job to actually be committed so two independent
    connections can see it -- the shared db_conn fixture normally rolls
    back, so this test explicitly commits and then cleans up after
    itself rather than relying on the fixture's rollback."""
    company_id = _make_company(db_conn)
    job_id = enqueue_job(db_conn, company_id, kind="noop_test")
    db_conn.commit()  # must be visible to conn_a/conn_b, which are separate connections

    try:
        with psycopg.connect(test_database_url, row_factory=dict_row, autocommit=False) as conn_a, \
             psycopg.connect(test_database_url, row_factory=dict_row, autocommit=False) as conn_b:
            # conn_a starts the claim transaction and holds the row lock without committing yet.
            job_a = claim_next_job(conn_a, lease_seconds=300)
            assert job_a is not None

            # conn_b must not see the same row as available (SKIP LOCKED).
            job_b = claim_next_job(conn_b, lease_seconds=300)
            assert job_b is None

            conn_a.commit()
            conn_b.commit()
    finally:
        # Explicit cleanup since this test bypassed the fixture's rollback.
        owner = db_conn.execute("SELECT owner_user_id FROM companies WHERE id = %s", (company_id,)).fetchone()
        db_conn.execute("DELETE FROM companies WHERE id = %s", (company_id,))
        if owner:
            db_conn.execute("DELETE FROM users WHERE id = %s", (owner["owner_user_id"],))
        db_conn.commit()
