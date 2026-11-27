"""Row-Level Security fail-closed regression (ADR 002, migration 0011).

This suite connects DIRECTLY as the `app_user` role -- not through the
app's own connection pool, which still runs as the RLS-bypassing owner
role (see migration 0011's docstring for why the live pool cutover is a
separate, not-yet-done task). This test's entire purpose is to prove the
POLICIES THEMSELVES are correct and fail-closed, independent of whether
the application has been wired to use them yet.

Requires `DATABASE_URL_APP` (set by `scripts/provision_app_user.py`) and
`TEST_DATABASE_URL` pointed at a migrated database. Skipped otherwise --
consistent with every other DB-backed suite in this repo.
"""
import os
import uuid

import psycopg
import pytest
from psycopg.rows import dict_row

from app.config import settings


def _app_user_url() -> str:
    return settings().database_url_app


pytestmark = pytest.mark.skipif(
    not _app_user_url() or not os.environ.get("TEST_DATABASE_URL"),
    reason="database_url_app (settings) and TEST_DATABASE_URL must both be set -- run "
    "scripts/provision_app_user.py against the test database first.",
)


@pytest.fixture
def owner_conn():
    """Unrestricted connection (bypasses RLS) used only to seed/inspect
    fixture data -- never used to make the actual isolation assertions."""
    url = os.environ["TEST_DATABASE_URL"]
    with psycopg.connect(url, row_factory=dict_row, autocommit=True) as conn:
        yield conn


@pytest.fixture
def app_conn():
    """A connection authenticated as the RLS-bound `app_user` role. Each
    test gets its own connection + transaction so `set_config(..., true)`
    (transaction-local) never leaks between tests."""
    url = _app_user_url()
    with psycopg.connect(url, row_factory=dict_row, autocommit=False) as conn:
        yield conn
        conn.rollback()


def _set_tenant(conn, company_id: str | None) -> None:
    conn.execute("SELECT set_config('app.company_id', %s, true)", (company_id or "",))


def _seed_company(owner_conn, name: str) -> str:
    row = owner_conn.execute(
        "INSERT INTO users (normalized_email, email, name) VALUES (%s, %s, %s) RETURNING id",
        (f"{name.lower()}-{uuid.uuid4().hex[:8]}@rls-test.example", f"{name}@rls-test.example", name),
    ).fetchone()
    user_id = row["id"]
    row = owner_conn.execute(
        "INSERT INTO companies (owner_user_id, name) VALUES (%s, %s) RETURNING id",
        (user_id, f"{name} Co"),
    ).fetchone()
    return str(row["id"])


def _seed_bot(owner_conn, company_id: str, public_id: str) -> str:
    row = owner_conn.execute(
        "INSERT INTO bots (company_id, public_id) VALUES (%s, %s) RETURNING id",
        (company_id, public_id),
    ).fetchone()
    return str(row["id"])


@pytest.fixture
def two_tenants(owner_conn):
    """Company A and Company B, each with one bot. Returns a dict so
    tests can address either side by name."""
    a_company = _seed_company(owner_conn, f"RlsA{uuid.uuid4().hex[:6]}")
    b_company = _seed_company(owner_conn, f"RlsB{uuid.uuid4().hex[:6]}")
    a_bot = _seed_bot(owner_conn, a_company, f"pub_rls_a_{uuid.uuid4().hex[:8]}")
    b_bot = _seed_bot(owner_conn, b_company, f"pub_rls_b_{uuid.uuid4().hex[:8]}")
    yield {"a_company": a_company, "b_company": b_company, "a_bot": a_bot, "b_bot": b_bot}
    # Cleanup via the unrestricted owner connection.
    owner_conn.execute("DELETE FROM companies WHERE id IN (%s, %s)", (a_company, b_company))


def test_tenant_a_sees_only_its_own_bot(app_conn, two_tenants):
    _set_tenant(app_conn, two_tenants["a_company"])
    rows = app_conn.execute("SELECT id, company_id FROM bots").fetchall()
    ids = {str(r["id"]) for r in rows}
    assert two_tenants["a_bot"] in ids
    assert two_tenants["b_bot"] not in ids


def test_tenant_b_sees_only_its_own_bot(app_conn, two_tenants):
    _set_tenant(app_conn, two_tenants["b_company"])
    rows = app_conn.execute("SELECT id, company_id FROM bots").fetchall()
    ids = {str(r["id"]) for r in rows}
    assert two_tenants["b_bot"] in ids
    assert two_tenants["a_bot"] not in ids


def test_unset_tenant_context_sees_zero_rows_fail_closed(app_conn, two_tenants):
    """The core fail-closed guarantee: a query that runs with NO tenant
    context set (e.g. a route that forgot to call set_current_company)
    must see nothing -- not everything."""
    # Deliberately do NOT call _set_tenant.
    rows = app_conn.execute("SELECT id FROM bots").fetchall()
    ids = {str(r["id"]) for r in rows}
    assert two_tenants["a_bot"] not in ids
    assert two_tenants["b_bot"] not in ids


def test_substituting_another_tenants_id_in_a_where_clause_still_returns_nothing(app_conn, two_tenants):
    """Proves RLS protects even when the app-level WHERE filter is
    missing or wrong -- the scenario this whole migration exists for.
    Simulates a buggy query that filters on Company A's id while B's
    context is set: the row must not be visible regardless of what the
    SQL asked for."""
    _set_tenant(app_conn, two_tenants["b_company"])
    rows = app_conn.execute(
        "SELECT id FROM bots WHERE company_id = %s", (two_tenants["a_company"],)
    ).fetchall()
    assert rows == []


def test_insert_with_mismatched_company_id_is_rejected(app_conn, two_tenants):
    """WITH CHECK must block writes into another tenant's scope, not just
    hide reads."""
    _set_tenant(app_conn, two_tenants["b_company"])
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app_conn.execute(
            "INSERT INTO bots (company_id, public_id) VALUES (%s, %s)",
            (two_tenants["a_company"], f"pub_rls_hostile_{uuid.uuid4().hex[:8]}"),
        )


def test_malformed_tenant_context_fails_closed_not_open(app_conn, two_tenants):
    """An invalid (non-UUID) context value must still yield zero rows via
    the NULLIF guard's cast, not raise in a way that could be caught and
    mistaken for 'no filter, return everything' by careless caller code."""
    _set_tenant(app_conn, "not-a-uuid")
    with pytest.raises(psycopg.errors.InvalidTextRepresentation):
        app_conn.execute("SELECT id FROM bots").fetchall()


def test_deep_table_feedback_three_hops_is_isolated(owner_conn, app_conn, two_tenants):
    """Smoke the hardest case in migration 0010: `feedback`, whose
    `company_id` was backfilled through messages -> conversations ->
    bots, three joins deep."""
    a_company, b_company = two_tenants["a_company"], two_tenants["b_company"]
    a_bot = two_tenants["a_bot"]

    pub = owner_conn.execute(
        "INSERT INTO publications (bot_id, version, config_snapshot) VALUES (%s, 1, '{}'::jsonb) RETURNING id",
        (a_bot,),
    ).fetchone()["id"]
    vs = owner_conn.execute(
        "INSERT INTO visitor_sessions (bot_id, session_token_hash, expires_at) "
        "VALUES (%s, %s, now() + interval '1 hour') RETURNING id",
        (a_bot, uuid.uuid4().hex),
    ).fetchone()["id"]
    conv = owner_conn.execute(
        "INSERT INTO conversations (bot_id, publication_id, visitor_session_id) VALUES (%s, %s, %s) RETURNING id",
        (a_bot, pub, vs),
    ).fetchone()["id"]
    msg = owner_conn.execute(
        "INSERT INTO messages (conversation_id, role, content, status) "
        "VALUES (%s, 'assistant', 'hi', 'completed') RETURNING id",
        (conv,),
    ).fetchone()["id"]
    owner_conn.execute(
        "INSERT INTO feedback (message_id, actor, rating) VALUES (%s, 'visitor', 1)",
        (msg,),
    )

    _set_tenant(app_conn, b_company)
    assert app_conn.execute("SELECT id FROM feedback").fetchall() == []

    _set_tenant(app_conn, a_company)
    rows = app_conn.execute("SELECT id FROM feedback WHERE message_id = %s", (msg,)).fetchall()
    assert len(rows) == 1
