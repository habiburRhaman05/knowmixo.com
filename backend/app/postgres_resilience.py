"""PostgreSQL failover handling for Phase 8 hardening.

Provides connection pool resilience, automatic failover support, and
retry logic for transient database errors.
"""
import logging
import os
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

import psycopg
from psycopg import OperationalError, InterfaceError
from psycopg_pool import ConnectionPool

from app.config import settings

log = logging.getLogger(__name__)

# Configuration
PG_MAX_RETRIES = int(os.environ.get("PG_MAX_RETRIES", "3"))
PG_RETRY_BASE_DELAY = float(os.environ.get("PG_RETRY_BASE_DELAY", "0.5"))
PG_RETRY_MAX_DELAY = float(os.environ.get("PG_RETRY_MAX_DELAY", "10.0"))
PG_HEALTH_CHECK_INTERVAL = int(os.environ.get("PG_HEALTH_CHECK_INTERVAL", "30"))
PG_CONNECT_TIMEOUT = float(os.environ.get("PG_CONNECT_TIMEOUT", "10.0"))

T = TypeVar("T")

# Transient error codes that warrant retry
TRANSIENT_ERROR_CODES = {
    "08000",  # connection_exception
    "08001",  # sqlclient_unable_to_establish_sqlconnection
    "08003",  # connection_does_not_exist
    "08004",  # sqlserver_rejected_establishment_of_sqlconnection
    "08006",  # connection_failure
    "08007",  # transaction_resolution_unknown
    "53300",  # too_many_connections
    "57P01",  # admin_shutdown
    "57P02",  # crash_shutdown
    "57P03",  # cannot_connect_now
    "40001",  # serialization_failure
    "40P01",  # deadlock_detected
}


class PostgresResilience:
    """PostgreSQL connection pool with resilience features."""

    def __init__(self, pool: Optional[ConnectionPool] = None):
        self._pool = pool
        self._last_health_check = 0.0
        self._healthy = True

    @property
    def pool(self) -> ConnectionPool:
        if self._pool is None:
            self._pool = self._create_pool()
        return self._pool

    def _create_pool(self) -> ConnectionPool:
        url = settings().database_url
        if not url:
            raise RuntimeError("DATABASE_URL is missing")

        # Convert to psycopg3 dialect if needed
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)

        pool = ConnectionPool(
            conninfo=url,
            min_size=1,
            max_size=10,
            kwargs={
                "autocommit": False,
                "connect_timeout": PG_CONNECT_TIMEOUT,
                "application_name": "knowmivo-backend",
            },
            open=True,
            timeout=PG_CONNECT_TIMEOUT,
        )
        pool.wait()
        log.info("PostgreSQL connection pool created")
        return pool

    def health_check(self) -> bool:
        """Check database connectivity."""
        try:
            with self.pool.connection() as conn:
                conn.execute("SELECT 1").fetchone()
            self._healthy = True
            self._last_health_check = time.time()
            return True
        except Exception as e:
            self._healthy = False
            log.error(f"PostgreSQL health check failed: {e}")
            return False

    def is_healthy(self) -> bool:
        """Quick health check with caching."""
        if time.time() - self._last_health_check > PG_HEALTH_CHECK_INTERVAL:
            return self.health_check()
        return self._healthy

    def _is_transient_error(self, error: Exception) -> bool:
        """Check if error is transient and worth retrying."""
        if isinstance(error, (OperationalError, InterfaceError)):
            return True
        if hasattr(error, "pgcode") and error.pgcode in TRANSIENT_ERROR_CODES:
            return True
        if hasattr(error, "sqlstate") and error.sqlstate in TRANSIENT_ERROR_CODES:
            return True
        # Check error message for common transient patterns
        error_str = str(error).lower()
        transient_patterns = [
            "connection",
            "timeout",
            "deadlock",
            "serialization",
            "too many connections",
            "server closed",
            "connection reset",
            "broken pipe",
        ]
        return any(pattern in error_str for pattern in transient_patterns)

    def _execute_with_retry(self, operation: Callable[..., T], *args, **kwargs) -> T:
        """Execute a database operation with retry logic for transient errors."""
        last_exception = None

        for attempt in range(PG_MAX_RETRIES):
            try:
                result = operation(*args, **kwargs)
                return result
            except Exception as e:
                last_exception = e
                if not self._is_transient_error(e):
                    log.error(f"Non-transient database error, not retrying: {e}")
                    raise

                if attempt < PG_MAX_RETRIES - 1:
                    delay = min(
                        PG_RETRY_BASE_DELAY * (2 ** attempt),
                        PG_RETRY_MAX_DELAY,
                    )
                    log.warning(
                        f"Transient database error (attempt {attempt + 1}/{PG_MAX_RETRIES}), "
                        f"retrying in {delay}s: {e}"
                    )
                    time.sleep(delay)
                    # Force pool to reconnect on next attempt
                    try:
                        self._pool = None  # Will be recreated on next access
                    except Exception:
                        pass
                else:
                    log.error(f"Database operation failed after {PG_MAX_RETRIES} attempts: {e}")

        raise last_exception

    @contextmanager
    def connection(self):
        """Get a database connection with automatic retry on transient errors."""
        last_exception = None

        for attempt in range(PG_MAX_RETRIES):
            try:
                with self.pool.connection() as conn:
                    yield conn
                return
            except Exception as e:
                last_exception = e
                if not self._is_transient_error(e):
                    raise

                if attempt < PG_MAX_RETRIES - 1:
                    delay = min(
                        PG_RETRY_BASE_DELAY * (2 ** attempt),
                        PG_RETRY_MAX_DELAY,
                    )
                    log.warning(
                        f"Transient connection error (attempt {attempt + 1}/{PG_MAX_RETRIES}), "
                        f"retrying in {delay}s: {e}"
                    )
                    time.sleep(delay)
                    # Invalidate pool to force reconnection
                    try:
                        self._pool = None
                    except Exception:
                        pass
                else:
                    log.error(f"Connection failed after {PG_MAX_RETRIES} attempts: {e}")

        raise last_exception

    def execute(self, query: str, params: tuple = ()) -> Any:
        """Execute a query with retry logic."""
        return self._execute_with_retry(self._execute_query, query, params)

    def _execute_query(self, query: str, params: tuple) -> Any:
        with self.pool.connection() as conn:
            return conn.execute(query, params).fetchall()

    def execute_one(self, query: str, params: tuple = ()) -> Any:
        """Execute a query returning one row with retry logic."""
        return self._execute_with_retry(self._execute_query_one, query, params)

    def _execute_query_one(self, query: str, params: tuple) -> Any:
        with self.pool.connection() as conn:
            return conn.execute(query, params).fetchone()

    def close(self):
        """Close the connection pool."""
        if self._pool:
            self._pool.close()
            self._pool = None
            log.info("PostgreSQL connection pool closed")


# Global instance
_pg_resilience: Optional[PostgresResilience] = None


def get_pg() -> PostgresResilience:
    """Get or create the global PostgreSQL resilience wrapper."""
    global _pg_resilience
    if _pg_resilience is None:
        _pg_resilience = PostgresResilience()
    return _pg_resilience


def reset_pg():
    """Reset the global PostgreSQL wrapper (for testing)."""
    global _pg_resilience
    if _pg_resilience:
        _pg_resilience.close()
    _pg_resilience = None


def with_pg_retry(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator to add retry logic to database operations."""

    @wraps(func)
    def wrapper(*args, **kwargs) -> T:
        pg = get_pg()
        return pg._execute_with_retry(func, *args, **kwargs)

    return wrapper


# Context manager for database transactions with retry
@contextmanager
def transaction():
    """Context manager for database transactions with automatic retry on transient errors."""
    pg = get_pg()
    last_exception = None

    for attempt in range(PG_MAX_RETRIES):
        try:
            with pg.pool.connection() as conn:
                with conn.transaction():
                    yield conn
            return
        except Exception as e:
            last_exception = e
            if not pg._is_transient_error(e):
                raise

            if attempt < PG_MAX_RETRIES - 1:
                delay = min(
                    PG_RETRY_BASE_DELAY * (2 ** attempt),
                    PG_RETRY_MAX_DELAY,
                )
                log.warning(
                    f"Transient transaction error (attempt {attempt + 1}/{PG_MAX_RETRIES}), "
                    f"retrying in {delay}s: {e}"
                )
                time.sleep(delay)
                pg._pool = None
            else:
                log.error(f"Transaction failed after {PG_MAX_RETRIES} attempts: {e}")

    raise last_exception