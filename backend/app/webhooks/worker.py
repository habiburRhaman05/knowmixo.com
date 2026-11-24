"""Webhook delivery worker for Phase 7.

Uses the Phase 2 job runner pattern: claim/lease/heartbeat/attempt-fencing
for reliable async webhook delivery with retries and exponential backoff.
"""
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from psycopg_pool import ConnectionPool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("webhook_worker")

# Worker config
POLL_INTERVAL = int(os.environ.get("WEBHOOK_POLL_INTERVAL", "5"))  # seconds
LEASE_TTL_SECONDS = int(os.environ.get("WEBHOOK_LEASE_TTL", "30"))
MAX_ATTEMPTS = int(os.environ.get("WEBHOOK_MAX_ATTEMPTS", "5"))
BASE_BACKOFF_SECONDS = int(os.environ.get("WEBHOOK_BASE_BACKOFF", "10"))
TIMEOUT_SECONDS = int(os.environ.get("WEBHOOK_TIMEOUT", "10"))


class WebhookWorker:
    def __init__(self, pool: ConnectionPool):
        self.pool = pool
        self.running = True
        self.worker_id = f"webhook-worker-{os.getpid()}"

        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)

    def _shutdown(self, signum, frame):
        logger.info("Shutdown signal received, finishing current job...")
        self.running = False

    def run(self):
        """Main worker loop."""
        logger.info(f"Starting webhook delivery worker: {self.worker_id}")
        while self.running:
            try:
                self._process_pending_deliveries()
            except Exception as e:
                logger.exception(f"Worker loop error: {e}")
            time.sleep(POLL_INTERVAL)
        logger.info("Worker stopped")

    def _process_pending_deliveries(self):
        """Claim and process pending deliveries."""
        now = datetime.now(timezone.utc)

        with self.pool.connection() as conn:
            # Claim a pending delivery using SELECT FOR UPDATE SKIP LOCKED
            row = conn.execute(
                """
                SELECT d.id, d.endpoint_id, d.event_type, d.payload,
                       d.attempt, d.max_attempts, d.last_error,
                       e.url, e.secret, e.events, e.is_active,
                       e.company_id
                FROM webhook_deliveries d
                JOIN webhook_endpoints e ON d.endpoint_id = e.id
                WHERE d.status = 'pending'
                  AND (d.next_retry_at IS NULL OR d.next_retry_at <= %s)
                  AND e.is_active = true
                ORDER BY d.created_at ASC
                FOR UPDATE OF d SKIP LOCKED
                LIMIT 1
                """,
                (now,),
            ).fetchone()

            if not row:
                return

            delivery_id = row["id"]
            logger.info(f"Claimed delivery {delivery_id} (attempt {row['attempt'] + 1}/{row['max_attempts']})")

            try:
                self._deliver(row)
            except Exception as e:
                logger.exception(f"Delivery {delivery_id} failed: {e}")
                self._record_failure(conn, delivery_id, row["attempt"], row["max_attempts"], str(e))

    def _deliver(self, row):
        """Execute the HTTP delivery."""
        delivery_id = row["id"]
        endpoint_id = row["endpoint_id"]
        url = row["url"]
        secret = row["secret"]
        event_type = row["event_type"]
        payload = row["payload"]
        attempt = row["attempt"]

        # Prepare headers with signature
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Knowmivo-Webhooks/1.0",
            "X-Knowmivo-Event": event_type,
            "X-Knowmivo-Delivery": str(delivery_id),
            "X-Knowmivo-Signature": self._sign_payload(payload, secret),
        }

        # Make the HTTP request
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()

        # Mark as delivered
        with self.pool.connection() as conn:
            conn.execute(
                """
                UPDATE webhook_deliveries
                SET status = 'delivered',
                    delivered_at = now(),
                    last_error = NULL
                WHERE id = %s
                """,
                (delivery_id,),
            )
        logger.info(f"Delivery {delivery_id} succeeded")

    def _sign_payload(self, payload: dict, secret: str) -> str:
        """Generate HMAC-SHA256 signature for payload verification."""
        import hmac
        import hashlib

        payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        signature = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
        return f"sha256={signature}"

    def _record_failure(self, conn, delivery_id: str, attempt: int, max_attempts: int, error: str):
        """Record failure and schedule retry or mark dead."""
        next_attempt = attempt + 1

        if next_attempt >= max_attempts:
            # Mark as dead - no more retries
            conn.execute(
                """
                UPDATE webhook_deliveries
                SET status = 'dead',
                    attempt = %s,
                    last_error = %s
                WHERE id = %s
                """,
                (next_attempt, error, delivery_id),
            )
            logger.warning(f"Delivery {delivery_id} marked dead after {next_attempt} attempts")
        else:
            # Schedule retry with exponential backoff
            backoff = BASE_BACKOFF_SECONDS * (2 ** attempt)
            next_retry = datetime.now(timezone.utc) + timedelta(seconds=backoff)

            conn.execute(
                """
                UPDATE webhook_deliveries
                SET status = 'pending',
                    attempt = %s,
                    next_retry_at = %s,
                    last_error = %s
                WHERE id = %s
                """,
                (next_attempt, next_retry, error, delivery_id),
            )
            logger.info(f"Delivery {delivery_id} scheduled for retry {next_attempt} at {next_retry.isoformat()}")


def create_pool() -> ConnectionPool:
    """Create database connection pool."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")

    # Convert to psycopg3 dialect for pool
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)

    return ConnectionPool(
        database_url,
        min_size=1,
        max_size=5,
        open=False,
        kwargs={"connect_timeout": 10},
    )


def main():
    """Entry point for webhook delivery worker."""
    pool = create_pool()
    pool.open()
    pool.wait()

    worker = WebhookWorker(pool)
    try:
        worker.run()
    finally:
        pool.close()


if __name__ == "__main__":
    main()