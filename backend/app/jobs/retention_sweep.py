"""Retention sweep job for Phase 7 hardening.

Handles:
- 30-day conversation/lead purge (tenant-scoped)
- 30-day audit log purge (tenant-scoped)
- 24-hour artifact cleanup (orphaned files, temp data)

Run as a scheduled job (cron or Kubernetes CronJob).
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from psycopg_pool import ConnectionPool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("retention_sweep")


def create_pool() -> ConnectionPool:
    """Create database connection pool."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")

    return ConnectionPool(
        database_url,
        min_size=1,
        max_size=3,
        open=False,
        kwargs={"connect_timeout": 10},
    )


def purge_old_conversations(pool: ConnectionPool, days: int = 30, dry_run: bool = False) -> int:
    """Purge conversations older than N days (and their messages/citations)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    with pool.connection() as conn:
        # First count what would be deleted
        count = conn.execute(
            """
            SELECT COUNT(*) FROM conversations
            WHERE created_at < %s
            """,
            (cutoff,),
        ).fetchone()[0]

        if dry_run:
            logger.info(f"[DRY RUN] Would delete {count} conversations older than {days} days")
            return count

        if count == 0:
            logger.info(f"No conversations older than {days} days to purge")
            return 0

        # Delete messages first (FK), then conversations
        conn.execute(
            """
            DELETE FROM messages
            WHERE conversation_id IN (
                SELECT id FROM conversations WHERE created_at < %s
            )
            """,
            (cutoff,),
        )

        deleted = conn.execute(
            """
            DELETE FROM conversations
            WHERE created_at < %s
            RETURNING id
            """,
            (cutoff,),
        ).rowcount

        logger.info(f"Purged {deleted} conversations (and their messages) older than {days} days")
        return deleted


def purge_old_leads(pool: ConnectionPool, days: int = 30, dry_run: bool = False) -> int:
    """Purge leads older than N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    with pool.connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE submitted_at < %s",
            (cutoff,),
        ).fetchone()[0]

        if dry_run:
            logger.info(f"[DRY RUN] Would delete {count} leads older than {days} days")
            return count

        if count == 0:
            logger.info(f"No leads older than {days} days to purge")
            return 0

        deleted = conn.execute(
            "DELETE FROM leads WHERE submitted_at < %s RETURNING id",
            (cutoff,),
        ).rowcount

        logger.info(f"Purged {deleted} leads older than {days} days")
        return deleted


def purge_old_audit_events(pool: ConnectionPool, days: int = 30, dry_run: bool = False) -> int:
    """Purge audit events older than N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    with pool.connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM audit_events WHERE created_at < %s",
            (cutoff,),
        ).fetchone()[0]

        if dry_run:
            logger.info(f"[DRY RUN] Would delete {count} audit events older than {days} days")
            return count

        if count == 0:
            logger.info(f"No audit events older than {days} days to purge")
            return 0

        deleted = conn.execute(
            "DELETE FROM audit_events WHERE created_at < %s RETURNING id",
            (cutoff,),
        ).rowcount

        logger.info(f"Purged {deleted} audit events older than {days} days")
        return deleted


def purge_orphaned_artifacts(pool: ConnectionPool, hours: int = 24, dry_run: bool = False) -> int:
    """Purge orphaned artifacts (documents without sources, etc.) older than N hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    with pool.connection() as conn:
        # Find documents that have no source referencing them and are older than cutoff
        count = conn.execute(
            """
            SELECT COUNT(*) FROM documents d
            WHERE d.created_at < %s
              AND NOT EXISTS (
                  SELECT 1 FROM document_versions dv WHERE dv.document_id = d.id
              )
            """,
            (cutoff,),
        ).fetchone()[0]

        if dry_run:
            logger.info(f"[DRY RUN] Would delete {count} orphaned documents older than {hours} hours")
            return count

        if count == 0:
            logger.info(f"No orphaned documents older than {hours} hours to purge")
            return 0

        deleted = conn.execute(
            """
            DELETE FROM documents
            WHERE created_at < %s
              AND NOT EXISTS (
                  SELECT 1 FROM document_versions dv WHERE dv.document_id = documents.id
              )
            RETURNING id
            """,
            (cutoff,),
        ).rowcount

        logger.info(f"Purged {deleted} orphaned documents older than {hours} hours")
        return deleted


def purge_dead_webhook_deliveries(pool: ConnectionPool, days: int = 7, dry_run: bool = False) -> int:
    """Purge dead webhook deliveries older than N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    with pool.connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM webhook_deliveries WHERE status = 'dead' AND created_at < %s",
            (cutoff,),
        ).fetchone()[0]

        if dry_run:
            logger.info(f"[DRY RUN] Would delete {count} dead webhook deliveries older than {days} days")
            return count

        if count == 0:
            logger.info(f"No dead webhook deliveries older than {days} days to purge")
            return 0

        deleted = conn.execute(
            "DELETE FROM webhook_deliveries WHERE status = 'dead' AND created_at < %s RETURNING id",
            (cutoff,),
        ).rowcount

        logger.info(f"Purged {deleted} dead webhook deliveries older than {days} days")
        return deleted


def main():
    parser = argparse.ArgumentParser(description="Retention sweep job")
    parser.add_argument("--conversation-days", type=int, default=30, help="Days to retain conversations")
    parser.add_argument("--lead-days", type=int, default=30, help="Days to retain leads")
    parser.add_argument("--audit-days", type=int, default=30, help="Days to retain audit events")
    parser.add_argument("--artifact-hours", type=int, default=24, help="Hours to retain orphaned artifacts")
    parser.add_argument("--webhook-days", type=int, default=7, help="Days to retain dead webhook deliveries")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")
    args = parser.parse_args()

    pool = create_pool()
    pool.open()
    pool.wait()

    logger.info("Starting retention sweep")
    if args.dry_run:
        logger.info("DRY RUN MODE - no data will be deleted")

    try:
        total = 0
        total += purge_old_conversations(pool, args.conversation_days, args.dry_run)
        total += purge_old_leads(pool, args.lead_days, args.dry_run)
        total += purge_old_audit_events(pool, args.audit_days, args.dry_run)
        total += purge_orphaned_artifacts(pool, args.artifact_hours, args.dry_run)
        total += purge_dead_webhook_deliveries(pool, args.webhook_days, args.dry_run)

        logger.info(f"Retention sweep complete. Total records purged: {total}")
    except Exception as e:
        logger.exception(f"Retention sweep failed: {e}")
        sys.exit(1)
    finally:
        pool.close()


if __name__ == "__main__":
    main()