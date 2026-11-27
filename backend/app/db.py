import json
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import settings
from app.postgres_resilience import get_pg, PostgresResilience
from app.tenancy import get_current_company

_pool: ConnectionPool | None = None
_pg_resilience: PostgresResilience | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        url = settings().database_url
        if not url:
            raise RuntimeError("DATABASE_URL is missing from .env")
        _pool = ConnectionPool(
            conninfo=url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row, "autocommit": False},
            open=True,
        )
    return _pool


def get_pg_resilience() -> PostgresResilience:
    """Get the PostgresResilience wrapper for resilient database operations."""
    # get_pg() owns the process-wide singleton; do not cache a second copy
    # here or reset_pg() (used by tests) would leave a stale pool behind.
    return get_pg()


@contextmanager
def connection():
    """A pooled connection with resilience (retry on transient errors).

    Applies the current request's tenant context (ADR 002 / app/tenancy.py)
    as the first statement on every acquired connection, via
    `set_config(..., true)` so it is transaction-scoped and can never leak
    to a different request on a reused pooled connection. This is inert
    today for the live app's pool (still running as the RLS-bypassing
    owner role -- see migration 0011's docstring for the audit that must
    happen before switching); it is exercised for real by any connection
    opened against the `app_user` role, e.g. the RLS regression suite.
    """
    pg = get_pg_resilience()
    with pg.connection() as conn:
        company_id = get_current_company()
        if company_id is not None:
            conn.execute("SELECT set_config('app.company_id', %s, true)", (company_id,))
        yield conn


def execute_with_retry(query: str, params: tuple = ()):
    """Execute a query with automatic retry on transient errors."""
    pg = get_pg_resilience()
    return pg.execute(query, params)


def execute_one_with_retry(query: str, params: tuple = ()):
    """Execute a query returning one row with automatic retry on transient errors."""
    pg = get_pg_resilience()
    return pg.execute_one(query, params)


def audit(conn, actor, tenant, action, detail):
    """Legacy audit_events writer (actor/tenant as free text). Superseded by
    the rebuilt audit_events schema in migration 0005 (Phase 7) which adds a
    real actor_id FK, request_id and target_id -- see
    docs/18-DATABASE-V2-V3-SCALABLE-SCHEMA.md. Kept only for the legacy demo
    routes until they are removed in Phase 2/3.
    """
    conn.execute(
        "INSERT INTO audit_events (actor,tenant_id,action,detail) VALUES (%s,%s,%s,%s)",
        (actor, tenant, action, json.dumps(detail)),
    )
