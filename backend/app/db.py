import json
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import settings

_pool: ConnectionPool | None = None


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


@contextmanager
def connection():
    """A pooled connection. Commits on clean exit, rolls back on exception."""
    with get_pool().connection() as conn:
        yield conn


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
