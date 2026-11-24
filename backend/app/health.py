"""Dependency reachability checks for GET /health/ready (docs/16 "Health").

Never makes a paid generation call -- only a Postgres `SELECT 1`, a Redis
PING and a Pinecone index-stats read (all free/cheap)."""
import logging

log = logging.getLogger(__name__)


def _check_postgres() -> None:
    from app.db import connection

    with connection() as conn:
        conn.execute("SELECT 1").fetchone()


def _check_redis() -> None:
    from app.redis_resilience import get_redis

    if not get_redis().ping():
        raise RuntimeError("redis ping failed")


def _check_pinecone() -> None:
    from app.providers.vector_store import ping

    ping()


CHECKS = {"postgres": _check_postgres, "redis": _check_redis, "pinecone": _check_pinecone}


def failing_dependencies() -> list[str]:
    failing = []
    for name, check in CHECKS.items():
        try:
            check()
        except Exception as exc:  # noqa: BLE001 - report the name only, never the error text (may contain URLs/keys)
            log.warning("readiness check failed: %s (%s)", name, type(exc).__name__)
            failing.append(name)
    return failing
