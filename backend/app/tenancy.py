"""Per-request tenant context for Row-Level Security (ADR 002).

`app/db.py:connection()` reads this contextvar and, if set, issues
`SELECT set_config('app.company_id', ..., true)` as the first statement
on every newly acquired connection -- before any tenant-table query runs.
The Postgres RLS policies from migration 0011 compare each row's
`company_id` against that same session setting; an unset value makes the
comparison NULL (never true), so a request that forgot to set a tenant
context sees zero rows instead of every tenant's data.

`set_config(..., true)` ("is_local") is transaction-scoped: it reverts
automatically at COMMIT or ROLLBACK, so it can never leak from one
request into the next on a connection the pool hands to a different
request afterward.

A ContextVar (not a thread-local or a module global) is required because
FastAPI route handlers run in a worker thread via anyio, which explicitly
copies the calling context into that thread -- a plain global would be
shared and racy across concurrent requests; a ContextVar is not.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar

_current_company_id: ContextVar[str | None] = ContextVar("current_company_id", default=None)


def set_current_company(company_id: str | None) -> None:
    """Call once per request, as early as possible (the auth dependency),
    with the resolved principal's company_id -- or None for routes that
    have no tenant context (unauthenticated routes, or operations that
    legitimately bootstrap a new tenant, e.g. signup)."""
    if company_id is not None:
        # Fail fast with a clear error here rather than a cryptic Postgres
        # cast error surfacing deep inside an unrelated query later.
        uuid.UUID(str(company_id))
    _current_company_id.set(str(company_id) if company_id is not None else None)


def get_current_company() -> str | None:
    return _current_company_id.get()


def clear_current_company() -> None:
    _current_company_id.set(None)
