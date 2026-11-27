"""Alerts evaluation sweep (D8.3): checks the 3 built-in rules (quota
80/100, unanswered spike, ingestion failure) for every company. Run as a
scheduled job (cron or Kubernetes CronJob), same pattern as
app/jobs/retention_sweep.py -- hourly is a reasonable cadence given
UNANSWERED_SPIKE_WINDOW_MINUTES = 60 in app.quality.alerts.
"""
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("alerts_sweep")


def main():
    from app.quality.alerts import evaluate_all_companies

    logger.info("Starting alerts sweep")
    try:
        checked = evaluate_all_companies()
        logger.info(f"Alerts sweep complete. Companies checked: {checked}")
    except Exception:
        logger.exception("Alerts sweep failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
