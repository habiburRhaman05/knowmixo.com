"""Change-detection sweep job (D3.5 scaffolding,
launch/13-SPRINT-10-DAYS.md). Finds URL/crawl-page documents due for a
re-check and enqueues `check_source_for_changes` jobs for them -- the
executor (app/jobs/executors.py) does the actual fetch-and-compare and
triggers re-ingestion only if the content changed.

Run as a scheduled job (cron or Kubernetes CronJob), same as
retention_sweep.py. `check_interval_hours` is NULL by default for every
document today (no endpoint sets it yet -- that's Day 7's schedule UI),
so this sweep is a safe no-op in production until that ships; it is
fully exercised in test/unit/test_change_detection_sweep.py.
"""
import argparse
import logging
import os
import sys

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.jobs.queue import enqueue_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("change_detection_sweep")


def create_pool() -> ConnectionPool:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")

    return ConnectionPool(
        database_url,
        min_size=1,
        max_size=3,
        open=False,
        kwargs={"connect_timeout": 10, "row_factory": dict_row},
    )


def find_due_documents(conn) -> list[dict]:
    """Documents with a check interval set, whose source hasn't been
    checked yet or whose interval has elapsed since the last check."""
    rows = conn.execute(
        """
        SELECT id, company_id FROM documents
        WHERE check_interval_hours IS NOT NULL
          AND source_url IS NOT NULL
          AND deleted_at IS NULL
          AND disabled_at IS NULL
          AND (last_checked_at IS NULL OR last_checked_at < now() - make_interval(hours => check_interval_hours))
        """
    ).fetchall()
    return rows


def run_sweep(pool: ConnectionPool, dry_run: bool = False) -> int:
    with pool.connection() as conn:
        due = find_due_documents(conn)
        logger.info(f"{len(due)} document(s) due for a change check")
        if dry_run:
            return len(due)

        enqueued = 0
        for document in due:
            with conn.transaction():
                _job_id, is_new = enqueue_job(
                    conn,
                    str(document["company_id"]),
                    kind="check_source_for_changes",
                    checkpoint_ref={"document_id": str(document["id"])},
                )
            if is_new:
                enqueued += 1
        logger.info(f"Enqueued {enqueued} check_source_for_changes job(s)")
        return enqueued


def main():
    parser = argparse.ArgumentParser(description="Change-detection sweep job")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be enqueued without enqueuing")
    args = parser.parse_args()

    pool = create_pool()
    pool.open()
    pool.wait()

    logger.info("Starting change-detection sweep")
    try:
        run_sweep(pool, args.dry_run)
    except Exception as e:  # noqa: BLE001
        logger.exception(f"Change-detection sweep failed: {e}")
        sys.exit(1)
    finally:
        pool.close()


if __name__ == "__main__":
    main()
