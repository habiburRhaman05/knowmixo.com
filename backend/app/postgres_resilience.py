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
from psycopg.rows import dict_row
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


_vector_type_info = None  # psycopg.types.TypeInfo for 'vector', fetched once per process


def _register_vector_type(conn: psycopg.Connection) -> None:
    """Binds Python lists directly to pgvector columns/parameters on every
    pool connection (D3.3). pgvector's own register_vector() does 4 catalog
    round-trips per call (vector/bit/halfvec/sparsevec) -- ~3.2s against
    Neon, measured directly, which starved the pool under concurrent test
    load (every new pool connection blocked on configure() for 3+ seconds,
    and psycopg_pool won't hand out a connection until configure()
    returns). This app only ever stores `vector` columns, and a type's OID
    is stable for the process lifetime, so the TypeInfo is fetched from
    the network once (first connection only) and reused -- reuse measured
    at ~0.3ms, no network round-trip at all.
    """
    from psycopg.types import TypeInfo
    from pgvector.psycopg.vector import register_vector_info

    global _vector_type_info
    if _vector_type_info is None:
        _vector_type_info = TypeInfo.fetch(conn, "vector")
    register_vector_info(conn, _vector_type_info)


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

        # psycopg3 consumes plain libpq URLs. The "postgresql+psycopg://"
        # form is a SQLAlchemy dialect and is rejected by libpq, so never
        # rewrite the scheme here (alembic/env.py handles that for itself).
        pool = ConnectionPool(
            conninfo=url,
            min_size=1,
            max_size=10,
            kwargs={
                "row_factory": dict_row,  # all call sites use row["col"]
                "autocommit": False,
                "connect_timeout": PG_CONNECT_TIMEOUT,
                "application_name": "knowmivo-backend",
            },
            open=True,
            timeout=PG_CONNECT_TIMEOUT,
            # Neon's pooler silently closes idle connections server-side;
            # without this, a connection the pool thinks is fine comes back
            # as "server closed the connection unexpectedly" on first use
            # (observed in test/api/test_chat_and_lifecycle.py). This runs a
            # cheap round-trip on getconn() and transparently reconnects.
            check=ConnectionPool.check_connection,
            # D3.3: lets every connection bind a Python list directly to a
            # `vector` column/parameter (chunks.embedding) instead of
            # hand-formatting pgvector's text literal syntax ourselves.
            configure=_register_vector_type,
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
        """Check if error is transient and worth retrying.

        IMPORTANT: the message-substring fallback below must only ever be
        applied to actual database-driver exceptions (psycopg.Error and
        subclasses). It must NEVER be applied to arbitrary exceptions —
        e.g. an SMTP failure ("Connection unexpectedly closed") or an
        application ValueError can easily contain a word like
        "connection" or "timeout" in its message, and misclassifying those
        as a transient *database* error causes callers of `connection()`
        to have their own business-logic exceptions silently reclassified
        and retried, corrupting the generator-context-manager protocol
        (see launch/DAY-1-REPORT.md "generator didn't stop after throw()").
        """
        if isinstance(error, (OperationalError, InterfaceError)):
            return True
        if hasattr(error, "pgcode") and error.pgcode in TRANSIENT_ERROR_CODES:
            return True
        if hasattr(error, "sqlstate") and error.sqlstate in TRANSIENT_ERROR_CODES:
            return True
        if not isinstance(error, psycopg.Error):
            # Anything that isn't a psycopg-raised error is, by definition,
            # not a transient *database* error -- it's either a caller bug,
            # an unrelated third-party failure (SMTP, HTTP, etc.), or an
            # intentional application exception. Never retry those here.
            return False
        # Check error message for common transient patterns -- only reached
        # for psycopg.Error subclasses that aren't already covered above.
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
        """Get a database connection, retrying only the ACQUISITION of that
        connection from the pool on transient errors.

        This is deliberately NOT "retry the whole `with` block". Once a
        connection has been handed to the caller via `yield`, this
        generator must follow the generator-context-manager protocol
        exactly: propagate whatever the caller's code raises, exactly
        once, immediately. Looping back to `yield` a second time after an
        exception was already thrown into this generator is illegal (it
        raises `RuntimeError: generator didn't stop after throw()`) and
        previously masked the real exception from every caller of
        `connection()` -- see launch/DAY-1-REPORT.md for the incident this
        fixes. Retrying business logic that may have partially run (e.g.
        half of a transaction, or a non-idempotent side effect like
        sending an email) is also simply wrong regardless of the protocol
        violation.
        """
        last_exception: Optional[Exception] = None

        for attempt in range(PG_MAX_RETRIES):
            pool_cm = self.pool.connection()
            try:
                conn = pool_cm.__enter__()
            except Exception as e:  # noqa: BLE001 - acquisition failure only
                last_exception = e
                if not self._is_transient_error(e) or attempt == PG_MAX_RETRIES - 1:
                    if attempt == PG_MAX_RETRIES - 1:
                        log.error(f"Connection failed after {PG_MAX_RETRIES} attempts: {e}")
                    raise
                delay = min(PG_RETRY_BASE_DELAY * (2**attempt), PG_RETRY_MAX_DELAY)
                log.warning(
                    f"Transient connection error (attempt {attempt + 1}/{PG_MAX_RETRIES}), "
                    f"retrying in {delay}s: {e}"
                )
                time.sleep(delay)
                self._pool = None  # force reconnection on next attempt
                continue

            # Connection acquired. From here on, ANY exception -- including
            # one raised by the caller's own code inside the `with` block --
            # propagates through pool_cm.__exit__ and out of this generator
            # exactly once. It is never retried and never reclassified.
            try:
                yield conn
            except BaseException:
                import sys

                if not pool_cm.__exit__(*sys.exc_info()):
                    raise
            else:
                pool_cm.__exit__(None, None, None)
            return

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
    """Reset the global PostgreSQL wrapper (for testing). Also clears the
    cached vector TypeInfo: a reset can repoint at a different database
    (e.g. TEST_DATABASE_URL), where pgvector's 'vector' type OID is not
    guaranteed to match the previous database's."""
    global _pg_resilience, _vector_type_info
    if _pg_resilience:
        _pg_resilience.close()
    _pg_resilience = None
    _vector_type_info = None


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