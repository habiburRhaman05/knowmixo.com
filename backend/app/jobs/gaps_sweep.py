"""Gaps recomputation sweep (D8.3): clusters answer_no_evidence events
per bot (launch/02-GAP-ANALYSIS.md: "nightly batch job that groups
low-confidence Qs"). Run nightly as a scheduled job (cron or Kubernetes
CronJob), same pattern as app/jobs/retention_sweep.py.
"""
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("gaps_sweep")


def main():
    from app.db import connection
    from app.quality.gaps import recompute_gaps

    logger.info("Starting gaps sweep")
    try:
        with connection() as conn:
            bots = conn.execute("SELECT id, company_id FROM bots").fetchall()
        total = 0
        for bot in bots:
            total += recompute_gaps(str(bot["company_id"]), str(bot["id"]))
        logger.info(f"Gaps sweep complete. Bots processed: {len(bots)}, gap clusters touched: {total}")
    except Exception:
        logger.exception("Gaps sweep failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
