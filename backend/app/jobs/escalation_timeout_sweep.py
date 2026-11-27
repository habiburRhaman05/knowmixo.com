"""Escalation timeout sweep job (F.7 launch punch-list item,
launch/06-ESCALATION-DESIGN.md §5/§7). Finds escalations still waiting on
an acknowledgement and enqueues `escalation_timeout_check` jobs for them
-- the executor (app/jobs/executors.py) does the actual
retry/escalate/dead decision via app.escalation.worker.check_timeout.

Run as a scheduled job (cron or Kubernetes CronJob), same as
retention_sweep.py / change_detection_sweep.py. Should run frequently
(every 1-2 minutes) since the shortest SLA (critical: retry at 60s) is
tight.
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
logger = logging.getLogger("escalation_timeout_sweep")


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


def find_due_escalations(conn) -> list[dict]:
    """Escalations not yet acknowledged or dead. check_timeout() itself
    decides, per-severity, whether enough time has actually passed to act
    -- this just finds the candidates worth checking."""
    rows = conn.execute(
        """
        SELECT id, company_id FROM escalations
        WHERE state IN ('sent', 'failed') AND acknowledged_at IS NULL
        """
    ).fetchall()
    return rows


def run_sweep(pool: ConnectionPool, dry_run: bool = False) -> int:
    with pool.connection() as conn:
        due = find_due_escalations(conn)
        logger.info(f"{len(due)} escalation(s) pending acknowledgement")
        if dry_run:
            return len(due)

        enqueued = 0
        for escalation in due:
            with conn.transaction():
                _job_id, is_new = enqueue_job(
                    conn,
                    str(escalation["company_id"]),
                    kind="escalation_timeout_check",
                    payload={"escalation_id": str(escalation["id"])},
                    idempotency_key=f"escalation_timeout_check:{escalation['id']}:{_current_minute()}",
                )
            if is_new:
                enqueued += 1
        logger.info(f"Enqueued {enqueued} escalation_timeout_check job(s)")
        return enqueued


def _current_minute() -> int:
    import time
    return int(time.time() // 60)


def main():
    parser = argparse.ArgumentParser(description="Escalation timeout sweep job")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be enqueued without enqueuing")
    args = parser.parse_args()

    pool = create_pool()
    pool.open()
    pool.wait()

    logger.info("Starting escalation timeout sweep")
    try:
        run_sweep(pool, args.dry_run)
    except Exception as e:  # noqa: BLE001
        logger.exception(f"Escalation timeout sweep failed: {e}")
        sys.exit(1)
    finally:
        pool.close()


if __name__ == "__main__":
    main()
